"""Revenium LangChain callback handler for metering every LLM call exactly once.

This module provides ``ReveniumCallbackHandler``, which extends LangChain's
``BaseCallbackHandler`` (following the ``cli/stats_handler.py`` blueprint) to
meter each LLM completion as exactly ONE Revenium event, attributed with the
agent identity, trace context, task type, and billing fields required by
FND-04, MTR-01, and MTR-02.

Design rationale:
- Exactly one handler instance is shared per ``TradingAgentsGraph`` run — it is
  registered in ``__init__`` of the graph and passed to every LLM client via
  ``llm_kwargs["callbacks"]``.  This is the sole metering path; no OTLP or
  secondary handler must be added alongside it (double-counting guard, T-02-04,
  Pitfall 1 in PITFALLS.md).
- ``on_chat_model_start`` captures the provider/model and agent name from the
  current ``current_agent_name`` contextvar, keyed by LangChain's ``run_id`` so
  concurrent or sequential calls cannot cross-contaminate each other.
- ``on_llm_end`` fires exactly ONCE per completion.  It builds the full payload,
  then dispatches ``client.meter_ai_completion`` on a daemon ``threading.Thread``
  so the LangGraph node is never blocked waiting for the HTTP round-trip
  (ARCHITECTURE Anti-Pattern 3).
- The entire ``on_llm_end`` body is wrapped in ``except Exception`` (fail-open,
  T-02-03).  A Revenium outage, transient network error, or bad payload can
  never halt or corrupt a trading run.
- A background thread list (``_threads``) allows tests to ``join`` pending
  I/O before asserting call counts, without adding any real synchronisation
  overhead to production runs (daemon threads are collected after exit).

Key invariants:
- ``enabled`` is ``False`` when ``api_key`` is absent (D-05): every public
  method is a no-op and never raises.
- Subscriber PII (email address) is sent only as ``subscriber.id`` / ``email``
  in the metering payload over TLS to the trusted Revenium account (T-02-02).
- Only symbolic names (agent, operation label) appear in log messages;
  the API key, prompt bodies, and token payloads are never logged (D-06,
  T-02-01).
"""

from __future__ import annotations

import logging
import threading
import uuid
from datetime import datetime, timezone
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import AIMessage
from langchain_core.outputs import LLMResult

from tradingagents.revenium.client import ReveniumClient
from tradingagents.revenium.config import attribution_from_config, task_type_for_node
from tradingagents.revenium.context import current_agent_name, current_trace_id

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Provider detection helper (best-effort from LangChain serialized dict)
# ---------------------------------------------------------------------------

def _detect_provider(serialized: dict[str, Any]) -> str:
    """Infer the provider label from the LangChain serialized class path.

    ``serialized["id"]`` is a list like
    ``["langchain_anthropic", "chat_models", "ChatAnthropic"]``.
    We join it into a lower-case string and probe for known provider tokens.
    Falls back to ``"unknown"`` for any unrecognised path.

    Note: OpenAI-compatible providers (xAI, DeepSeek, etc.) all route through
    ``ChatOpenAI`` and will be labelled ``"openai"`` here — this is a
    known Revenium limitation on the LangChain path (STACK.md §Provider Coverage).
    """
    id_parts = " ".join(str(p).lower() for p in serialized.get("id", []))
    for candidate in ("anthropic", "openai", "google", "bedrock", "azure", "ollama"):
        if candidate in id_parts:
            return candidate
    return "unknown"


def _now_iso() -> str:
    """Return current UTC time as an ISO 8601 millisecond string."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


# ---------------------------------------------------------------------------
# Callback handler
# ---------------------------------------------------------------------------

class ReveniumCallbackHandler(BaseCallbackHandler):
    """LangChain callback handler that meters every LLM completion via Revenium.

    Drop-in alongside ``StatsCallbackHandler`` in ``TradingAgentsGraph``.
    One instance is shared for the whole ``propagate()`` call; all per-call
    state is keyed by LangChain's ``run_id`` under a threading lock.

    Public attributes (consumed by Phase 4 CLI cost panel):
        agent_costs:      Per-agent dict of ``{input_tokens, output_tokens}`` totals.
        run_total_tokens: Cumulative token count for the current run.
    """

    def __init__(
        self,
        client: ReveniumClient,
        attribution: dict,
        task_type_map: dict[str, str],
    ) -> None:
        """Construct the handler with a pre-built client and attribution fields.

        Prefer ``from_config`` for normal construction; this signature exists
        for explicit unit-test construction with a mock client.

        Args:
            client:        Fail-open ``ReveniumClient`` wrapping the SDK.
            attribution:   Dict from ``attribution_from_config()`` carrying
                           ``organizationName``, ``productName``, ``subscriber_id``.
            task_type_map: ``{node_name -> task_type}`` mapping from config.
        """
        super().__init__()
        self._client = client
        self._attribution = attribution
        self._task_type_map = task_type_map

        # Per-call state keyed by run_id (captured at on_chat_model_start).
        self._call_state: dict[str, dict] = {}
        self._lock = threading.Lock()

        # Background thread tracking — join in tests before asserting counts.
        self._threads: list[threading.Thread] = []

        # Phase 4 cost panel accumulators (public).
        self.agent_costs: dict[str, dict] = {}
        self.run_total_tokens: int = 0

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def from_config(cls, config: dict) -> ReveniumCallbackHandler:
        """Build a handler from a TradingAgents config dict (the primary API).

        Reads ``revenium_api_key``, ``revenium_api_url``, and the attribution
        constants from ``config``.  When ``api_key`` is empty the returned
        handler has ``enabled == False`` and is a silent no-op.

        Args:
            config: Process-global config dict (from ``get_config()`` or
                    ``DEFAULT_CONFIG``).

        Returns:
            A fully configured ``ReveniumCallbackHandler``.
        """
        attr = attribution_from_config(config)
        client = ReveniumClient(api_key=attr["api_key"], api_url=attr["api_url"])
        task_type_map: dict[str, str] = config.get("revenium_task_type_map", {})
        return cls(client=client, attribution=attr, task_type_map=task_type_map)

    # ------------------------------------------------------------------
    # Public properties
    # ------------------------------------------------------------------

    @property
    def enabled(self) -> bool:
        """``True`` when metering is active (non-empty API key, SDK initialised)."""
        return self._client.enabled

    # ------------------------------------------------------------------
    # LangChain callbacks
    # ------------------------------------------------------------------

    def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list[list[Any]],
        **kwargs: Any,
    ) -> None:
        """Capture provider, model, agent name, and start time for this call.

        Keyed by ``run_id`` so interleaved calls (future concurrency) don't
        cross-contaminate.  This method must never raise — it is in the hot
        path of every LLM call.
        """
        if not self.enabled:
            return
        try:
            run_id = str(kwargs.get("run_id", uuid.uuid4()))
            model = (
                serialized.get("kwargs", {}).get("model_name")
                or serialized.get("kwargs", {}).get("model")
                or "unknown"
            )
            provider = _detect_provider(serialized)
            agent = current_agent_name.get()  # "unknown" if no agent set this

            with self._lock:
                self._call_state[run_id] = {
                    "start_time": datetime.now(timezone.utc),
                    "model": model,
                    "provider": provider,
                    "agent": agent,
                }
        except Exception:  # noqa: BLE001 — fail open, never block the run
            logger.warning(
                "Revenium on_chat_model_start failed — continuing without capture",
                exc_info=True,
            )

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        """Fire exactly ONE Revenium metering event for this completion (fail-open).

        Extracts usage_metadata using the same pattern as ``StatsCallbackHandler``
        (stats_handler.py lines 40-56), builds the attributed payload, updates
        the cost accumulators under the lock, then dispatches to
        ``client.meter_ai_completion`` on a background daemon thread
        (fire-and-forget — never blocks the next graph node).

        All exceptions are swallowed (T-02-03); the graph run continues even if
        Revenium is unreachable.
        """
        if not self.enabled:
            return
        try:
            run_id = str(kwargs.get("run_id", ""))
            end_time = datetime.now(timezone.utc)

            # --- Token extraction (stats_handler pattern) ---
            try:
                generation = response.generations[0][0]
            except (IndexError, TypeError):
                return

            usage_metadata = None
            if hasattr(generation, "message"):
                message = generation.message
                if isinstance(message, AIMessage) and hasattr(message, "usage_metadata"):
                    usage_metadata = message.usage_metadata

            # --- Retrieve per-call state ---
            with self._lock:
                call_state = self._call_state.pop(run_id, {})

            start_time: datetime = call_state.get("start_time", end_time)
            model: str = call_state.get("model", "unknown")
            provider: str = call_state.get("provider", "unknown")
            agent: str = call_state.get("agent", current_agent_name.get())

            # --- Token counts ---
            input_tokens: int = (
                usage_metadata.get("input_tokens", 0) if usage_metadata else 0
            )
            output_tokens: int = (
                usage_metadata.get("output_tokens", 0) if usage_metadata else 0
            )
            total_tokens: int = input_tokens + output_tokens

            # --- Context fields ---
            trace_id: str = current_trace_id.get()
            task_type: str = self._task_type_map.get(agent, "analysis")

            # --- Timing ---
            delta_ms: int = max(
                int((end_time - start_time).total_seconds() * 1000), 0
            )
            request_time: str = start_time.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
            response_time: str = end_time.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

            # --- Build Revenium payload ---
            subscriber_id: str = self._attribution.get("subscriber_id", "")
            payload: dict[str, Any] = {
                # Required fields
                "completion_start_time": request_time,
                "cost_type": "AI",
                "input_token_count": input_tokens,
                "is_streamed": False,
                "model": model,
                "output_token_count": output_tokens,
                "provider": provider,
                "request_duration": delta_ms,
                "request_time": request_time,
                "response_time": response_time,
                "stop_reason": "END",
                "total_token_count": total_tokens,
                "transaction_id": str(uuid.uuid4()),
                # Attribution (MTR-02) — never empty (D-04 anti-UNCLASSIFIED)
                "organization_name": self._attribution.get("organizationName", ""),
                "product_name": self._attribution.get("productName", ""),
                "subscriber": {
                    "id": subscriber_id,
                    "email": subscriber_id,
                },
                # Identity (MTR-01)
                "agent": agent,
                "task_type": task_type,
                # Tracing
                "operation_type": "CHAT",
                "middleware_source": "tradingagents",
            }
            # Only include trace_id when it is non-empty (avoid sending blank UUIDs)
            if trace_id:
                payload["trace_id"] = trace_id

            # --- Update cost accumulators (Phase 4 CLI panel) ---
            with self._lock:
                entry = self.agent_costs.setdefault(
                    agent, {"input_tokens": 0, "output_tokens": 0}
                )
                entry["input_tokens"] += input_tokens
                entry["output_tokens"] += output_tokens
                self.run_total_tokens += total_tokens

            # --- Fire-and-forget (Anti-Pattern 3: never block the graph) ---
            # (T-02-03 mitigation: request_duration is counted but HTTP is async)
            t = threading.Thread(
                target=self._client.meter_ai_completion,
                args=(payload,),
                daemon=True,
                name=f"rev-meter-{agent[:16]}",
            )
            t.start()
            with self._lock:
                self._threads.append(t)

        except Exception:  # noqa: BLE001 — fail open, never block the run
            logger.warning(
                "Revenium on_llm_end failed for agent %r — event dropped",
                current_agent_name.get(),
                exc_info=True,
            )
