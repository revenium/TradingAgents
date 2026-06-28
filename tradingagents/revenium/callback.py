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

Run-scoped trace state (GAP-02-01 fix, 02-03):
- LangGraph executes every node inside its own ``copy_context().run()``, so any
  contextvar write in node A's ``on_llm_end`` is invisible to node B's
  ``on_chat_model_start``.  The Phase 2 research premise that the synchronous
  main thread keeps the parent-id contextvar visible across nodes is FALSE.
- ``begin_run(trace_id, ticker, trade_date)`` / ``end_run()`` store run-scoped
  state on the handler instance (``_run_trace_id``, ``_run_meta``,
  ``_last_transaction_id``) rather than per-node contextvars.  The handler
  instance is shared across all nodes, so instance-state writes survive the
  copy_context() boundary.
- Parent chain: ``on_chat_model_start`` reads ``self._last_transaction_id`` (under
  lock) instead of ``current_parent_transaction_id.get()``.  ``on_llm_end``
  advances ``self._last_transaction_id`` to this call's ``transaction_id`` (under
  lock) and no longer calls ``current_parent_transaction_id.set()``.
- Linearisation tradeoff: ``_last_transaction_id`` serialises the parent chain
  across parallel analyst fan-out into a single sequential dependency view.  This
  is acceptable per 02-VERIFICATION.md and still yields the bull→bear→bull
  repetition pattern needed for TRC-03 circular detection.
- Contextvar fallback: ``current_trace_id`` / ``current_run_meta`` are still read
  in ``on_llm_end`` when the handler-instance values are ``None``, so direct
  non-graph callers (``validate_metering.py`` path) continue to work unchanged.

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
from revenium_middleware._core import BudgetExceededError, check_enforcement

from tradingagents.revenium.client import ReveniumClient
from tradingagents.revenium.config import attribution_from_config
from tradingagents.revenium.context import (
    current_agent_name,
    current_run_meta,
    current_trace_id,
)
from tradingagents.revenium.pricing import compute_cost  # Phase 4 local cost estimate

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
        trace_type: str = "trading-run",
    ) -> None:
        """Construct the handler with a pre-built client and attribution fields.

        Prefer ``from_config`` for normal construction; this signature exists
        for explicit unit-test construction with a mock client.

        Args:
            client:        Fail-open ``ReveniumClient`` wrapping the SDK.
            attribution:   Dict from ``attribution_from_config()`` carrying
                           ``organizationName``, ``productName``, ``subscriber_id``.
            task_type_map: ``{node_name -> task_type}`` mapping from config.
            trace_type:    Outbound label for the Revenium trace_type field
                           (e.g. "trading-run").  Defaults to "trading-run".
        """
        super().__init__()
        self._client = client
        self._attribution = attribution
        self._task_type_map = task_type_map
        self._trace_type: str = trace_type

        # Per-call state keyed by run_id (captured at on_chat_model_start).
        self._call_state: dict[str, dict] = {}
        self._lock = threading.Lock()

        # Run-scoped handler-instance trace state (GAP-02-01, 02-03).
        # These fields are set by begin_run() / cleared by end_run() and survive
        # LangGraph's per-node copy_context().run() isolation because they live
        # on the shared handler instance rather than per-node contextvars.
        #
        # _last_transaction_id: transaction_id of the most recently completed
        #   LLM call in this run.  Read by on_chat_model_start as parent_tid
        #   and advanced by on_llm_end.  Replaces current_parent_transaction_id
        #   as the primary parent-chain carrier for graph callers.
        # _run_trace_id: trace_id UUID for the current propagate() call.
        #   Set by begin_run(), read by on_llm_end, cleared by end_run().
        # _run_meta: {ticker, trade_date} for the current run.
        #   Set by begin_run(), read by on_llm_end, cleared by end_run().
        self._last_transaction_id: str = ""
        self._run_trace_id: str | None = None
        self._run_meta: dict | None = None

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
        trace_type: str = config.get("revenium_trace_type", "trading-run")
        return cls(client=client, attribution=attr, task_type_map=task_type_map, trace_type=trace_type)

    # ------------------------------------------------------------------
    # Public properties
    # ------------------------------------------------------------------

    @property
    def enabled(self) -> bool:
        """``True`` when metering is active (non-empty API key, SDK initialised)."""
        return self._client.enabled

    # ------------------------------------------------------------------
    # Run lifecycle (GAP-02-01 fix)
    # ------------------------------------------------------------------

    def begin_run(self, trace_id: str, ticker: str, trade_date: str) -> None:
        """Open a new propagate() run on this handler instance.

        Stores the run-scoped trace_id, ticker/date metadata, and resets the
        parent-chain cursor (_last_transaction_id) to "" so the first span of
        the new run has no parent.

        Called from ``trading_graph._run_graph`` immediately after entering the
        ``revenium_run_context`` block, before ``graph.invoke()``.

        Fail-open: any exception is caught and logged; the trading run is never
        blocked.  No-op when the handler is disabled.

        Args:
            trace_id:   The UUID trace identifier for this run (from revenium_run_context).
            ticker:     Ticker symbol being analysed (e.g. "NVDA").
            trade_date: ISO date string for the analysis date (e.g. "2026-06-27").
        """
        if not self.enabled:
            return
        try:
            with self._lock:
                self._run_trace_id = trace_id
                self._run_meta = {"ticker": ticker, "trade_date": str(trade_date)}
                self._last_transaction_id = ""
            logger.debug(
                "ReveniumCallbackHandler.begin_run: trace_id=%r ticker=%r",
                trace_id,
                ticker,
            )
        except Exception:  # noqa: BLE001 — fail open, never block the run
            logger.warning(
                "ReveniumCallbackHandler.begin_run failed — continuing without trace context",
                exc_info=True,
            )

    def end_run(self) -> None:
        """Close the current propagate() run on this handler instance.

        Clears run-scoped trace state so it does not bleed into the next run.
        Called from ``trading_graph._run_graph`` in a ``finally`` block so it
        runs even when ``graph.invoke()`` raises.

        Fail-open: any exception is caught and logged; the trading run is never
        blocked.  No-op when the handler is disabled.
        """
        if not self.enabled:
            return
        try:
            with self._lock:
                self._run_trace_id = None
                self._run_meta = None
                self._last_transaction_id = ""
                # Drop any per-call state left over from a malformed/aborted run
                # so it does not bleed into the next propagate() call (WR-01).
                self._call_state.clear()
                # Reset per-run cost panel accumulators so ×N counts and totals
                # do not bleed across runs (Phase 4 Pitfall 4).
                self.agent_costs.clear()
                self.run_total_tokens = 0
                # Prune finished daemon threads so the list does not grow
                # unbounded across reused-handler runs (CLI backtest / multi-ticker
                # scans); keeps the test-side join loop bounded to live threads (WR-02).
                self._threads = [t for t in self._threads if t.is_alive()]
            logger.debug("ReveniumCallbackHandler.end_run: run-scoped state cleared")
        except Exception:  # noqa: BLE001 — fail open, never block the run
            logger.warning(
                "ReveniumCallbackHandler.end_run failed — run-scoped state may not be cleared",
                exc_info=True,
            )

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
        cross-contaminate.

        Enforcement gate (CTL-01): ``check_enforcement()`` is called BEFORE the
        fail-open ``try/except`` so ``BudgetExceededError`` is deliberately
        allowed to propagate (D-03 exception to the fail-open convention).  This
        is the ONE method that can raise when a cost rule is breached.
        """
        if not self.enabled:
            return

        # Enforcement gate — D-03: deliberate exception to the fail-open
        # convention.  ONLY BudgetExceededError is allowed to propagate to
        # _run_graph / CLI so the run halts cleanly (CTL-01/02).  Every OTHER
        # exception (network blip, malformed compiled-rules payload, SDK error)
        # must fail open — a Revenium hiccup must never abort the trading run
        # (CR-01: a single provider hiccup mid-demo would otherwise crash it).
        # No-op when REVENIUM_CIRCUIT_BREAKER_ENABLED is unset or
        # REVENIUM_BYPASS=true (keeps keyless test suite green — DMO-04).
        # subscriber_credential is a PII email — never logged here (T-03-02).
        try:
            check_enforcement({
                "subscriber_credential": self._attribution.get("subscriber_id", ""),
            })
        except BudgetExceededError:
            raise  # D-03: deliberate propagation — the run must halt
        except Exception:  # noqa: BLE001 — fail open, never block the run
            logger.warning(
                "Revenium enforcement check failed — continuing without enforcement",
                exc_info=True,
            )

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
                # Read the parent-chain cursor from handler-instance state
                # (GAP-02-01: current_parent_transaction_id contextvar is NOT
                # used here — LangGraph's per-node copy_context().run() means
                # any .set() from the previous node's on_llm_end is invisible
                # in this node's context copy.  self._last_transaction_id lives
                # on the shared handler instance and is always visible.)
                self._call_state[run_id] = {
                    "start_time": datetime.now(timezone.utc),
                    "model": model,
                    "provider": provider,
                    "agent": agent,
                    "parent_tid": self._last_transaction_id,
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

            # --- Retrieve per-call state ---
            # Pop before the generation extraction so a malformed LLMResult that
            # early-returns below does not orphan this entry in _call_state (WR-01).
            with self._lock:
                call_state = self._call_state.pop(run_id, {})

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

            start_time: datetime = call_state.get("start_time", end_time)
            model: str = call_state.get("model", "unknown")
            provider: str = call_state.get("provider", "unknown")
            agent: str = call_state.get("agent", current_agent_name.get())
            parent_tid: str = call_state.get("parent_tid", "")

            # --- Token counts ---
            input_tokens: int = (
                usage_metadata.get("input_tokens", 0) if usage_metadata else 0
            )
            output_tokens: int = (
                usage_metadata.get("output_tokens", 0) if usage_metadata else 0
            )
            total_tokens: int = input_tokens + output_tokens

            # --- Context fields (GAP-02-01: prefer handler-instance state; ---
            # --- fall back to contextvars for direct non-graph callers)    ---
            with self._lock:
                run_trace_id = self._run_trace_id
                run_meta_inst = self._run_meta
            trace_id: str = run_trace_id if run_trace_id is not None else current_trace_id.get()
            task_type: str = self._task_type_map.get(agent, "analysis")
            run_meta: dict = run_meta_inst if run_meta_inst is not None else current_run_meta.get()
            ticker: str = run_meta.get("ticker", "")
            trade_date_str: str = run_meta.get("trade_date", "")
            trace_name: str = f"{ticker}-{trade_date_str}"[:200] if ticker else ""

            # --- Timing ---
            delta_ms: int = max(
                int((end_time - start_time).total_seconds() * 1000), 0
            )
            request_time: str = start_time.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
            response_time: str = end_time.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

            # --- Build Revenium payload ---
            subscriber_id: str = self._attribution.get("subscriber_id", "")
            transaction_id: str = str(uuid.uuid4())
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
                "transaction_id": transaction_id,
                "transaction_name": agent,
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
            if parent_tid:
                payload["parent_transaction_id"] = parent_tid
            if trace_name:
                payload["trace_name"] = trace_name
            if self._trace_type:
                payload["trace_type"] = self._trace_type

            # --- Update cost accumulators (Phase 4 CLI panel) ---
            # Compute local cost estimate BEFORE taking the lock (no I/O; pure math).
            local_cost = compute_cost(provider, model, input_tokens, output_tokens)
            with self._lock:
                entry = self.agent_costs.setdefault(
                    agent,
                    {"input_tokens": 0, "output_tokens": 0, "cost": 0.0, "call_count": 0},
                )
                entry["input_tokens"] += input_tokens
                entry["output_tokens"] += output_tokens
                entry["cost"] += local_cost
                entry["call_count"] += 1
                self.run_total_tokens += total_tokens

            # --- Fire-and-forget (Anti-Pattern 3: never block the graph) ---
            # (T-02-03 mitigation: request_duration is counted but HTTP is async)
            # The thread target is itself fail-open so a mock or real client
            # exception in the background thread does not surface as an
            # unhandled thread exception in tests or production.
            def _meter_safe(_payload: dict, _agent: str = agent) -> None:
                try:
                    self._client.meter_ai_completion(_payload)
                except Exception:  # noqa: BLE001 — fail open, never block the run
                    logger.warning(
                        "Revenium background metering failed for agent %r — dropped",
                        _agent,
                        exc_info=True,
                    )

            # Advance the parent-chain cursor on the shared handler instance
            # (GAP-02-01 fix).  Must happen synchronously before the background
            # thread starts so the next on_chat_model_start — in this same node
            # or the next node — reads the updated value under the lock.
            # Note: current_parent_transaction_id.set() is intentionally removed
            # here; it had no effect across nodes (copy_context() boundary) and
            # is replaced by self._last_transaction_id as the primary chain carrier.
            # The contextvar remains defined in context.py as the fallback path
            # for direct non-graph callers (see context.py module docstring).
            with self._lock:
                self._last_transaction_id = transaction_id

            t = threading.Thread(
                target=_meter_safe,
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
