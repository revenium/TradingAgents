# Phase 1: Foundation & Metering - Pattern Map

**Mapped:** 2026-06-27
**Files analyzed:** 13 new/modified files
**Analogs found:** 12 / 13

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `tradingagents/revenium/__init__.py` | config | N/A | `tradingagents/llm_clients/__init__.py` | role-match |
| `tradingagents/revenium/callback.py` | middleware | request-response | `cli/stats_handler.py` | exact |
| `tradingagents/revenium/context.py` | utility | event-driven | `tradingagents/dataflows/config.py` | role-match |
| `tradingagents/revenium/cost_gate.py` | middleware | request-response | `tradingagents/dataflows/errors.py` | partial |
| `tradingagents/revenium/billing.py` | service | request-response | `cli/stats_handler.py` | partial |
| `tradingagents/revenium/client.py` | service | request-response | `tradingagents/llm_clients/factory.py` | role-match |
| `tradingagents/revenium/config.py` | config | N/A | `tradingagents/default_config.py` | exact |
| `tradingagents/graph/trading_graph.py` (edit) | controller | event-driven | self | exact |
| `cli/main.py` (edit) | controller | request-response | self | exact |
| `tradingagents/default_config.py` (edit) | config | N/A | self | exact |
| `tradingagents/agents/**/*.py` (13 one-liners) | middleware | event-driven | `tradingagents/agents/analysts/market_analyst.py` | exact |
| `scripts/setup_revenium.py` | utility | request-response | `scripts/smoke_structured_output.py` | role-match |
| `scripts/validate_metering.py` | utility | request-response | `scripts/smoke_structured_output.py` | exact |
| `.env.example` (edit) | config | N/A | `.env.example` (self) | exact |

---

## Pattern Assignments

### `tradingagents/revenium/callback.py` (middleware, request-response)

**Analog:** `cli/stats_handler.py` (76 lines, read in full)

This is the primary blueprint. The new handler extends the same `BaseCallbackHandler` with the same import block and method signatures, adding Revenium metering logic inside `on_llm_end` and `on_tool_start`.

**Imports pattern** (stats_handler.py lines 1-7):
```python
import threading
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import AIMessage
from langchain_core.outputs import LLMResult
```

**Class skeleton pattern** (stats_handler.py lines 9-16):
```python
class StatsCallbackHandler(BaseCallbackHandler):
    """Callback handler that tracks LLM calls, tool calls, and token usage."""

    def __init__(self) -> None:
        super().__init__()
        self._lock = threading.Lock()
        self.llm_calls = 0
        ...
```

**`on_chat_model_start` signature** (stats_handler.py lines 30-38):
```python
def on_chat_model_start(
    self,
    serialized: dict[str, Any],
    messages: list[list[Any]],
    **kwargs: Any,
) -> None:
    """Increment LLM call counter when a chat model starts."""
    with self._lock:
        self.llm_calls += 1
```

**`on_llm_end` token-extraction pattern** (stats_handler.py lines 40-56):
```python
def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
    """Extract token usage from LLM response."""
    try:
        generation = response.generations[0][0]
    except (IndexError, TypeError):
        return

    usage_metadata = None
    if hasattr(generation, "message"):
        message = generation.message
        if isinstance(message, AIMessage) and hasattr(message, "usage_metadata"):
            usage_metadata = message.usage_metadata

    if usage_metadata:
        with self._lock:
            self.tokens_in += usage_metadata.get("input_tokens", 0)
            self.tokens_out += usage_metadata.get("output_tokens", 0)
```

**`on_tool_start` signature** (stats_handler.py lines 58-65):
```python
def on_tool_start(
    self,
    serialized: dict[str, Any],
    input_str: str,
    **kwargs: Any,
) -> None:
    """Increment tool call counter when a tool starts."""
    with self._lock:
        self.tool_calls += 1
```

**Fail-open pattern** (from CLAUDE.md conventions, applied inside `on_llm_end` around Revenium HTTP post):
```python
try:
    self._client.meter(...)
except Exception:  # noqa: BLE001 — fail open, never block the run
    logger.warning("Revenium metering failed, dropping event", exc_info=True)
```

**What changes vs the analog:**
- `__init__` adds `api_key`, `api_url`, `organization_name`, `product_name`, `subscriber_id` parameters — check `REVENIUM_METERING_API_KEY` at init; if absent, set `self._enabled = False` for silent no-op (D-05).
- `on_chat_model_start` additionally reads `current_agent_name` contextvar to record which agent is starting.
- `on_llm_end` adds: read `trace_id` and `current_agent_name` contextvars, compute cost, update `self.agent_costs` dict, fire `client.meter_ai_completion(...)` async/fire-and-forget (wrapped in `threading.Thread`).
- Add `agent_costs: dict[str, dict]` as a public attribute (for CLI cost panel in Phase 4).

---

### `tradingagents/revenium/context.py` (utility, event-driven)

**Analog:** `tradingagents/dataflows/config.py` — closest match for a process-global singleton with get/set accessors; the pattern of a module-level private object accessed only through functions.

**Module-level singleton pattern** (config.py lines 1-41):
```python
from copy import deepcopy
import tradingagents.default_config as default_config

_config: dict | None = None

def initialize_config():
    global _config
    if _config is None:
        _config = deepcopy(default_config.DEFAULT_CONFIG)

def set_config(config: dict):
    global _config
    initialize_config()
    ...

def get_config() -> dict:
    if _config is None:
        initialize_config()
    return deepcopy(_config)
```

**What `context.py` does instead:** replaces the module-level dict singleton with `contextvars.ContextVar` objects. The module exposes three vars and a context-manager helper for use in `propagate()`:

```python
import contextvars
import uuid
from contextlib import contextmanager

current_trace_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "revenium_trace_id", default=""
)
current_agent_name: contextvars.ContextVar[str] = contextvars.ContextVar(
    "revenium_agent_name", default="unknown"
)
current_run_meta: contextvars.ContextVar[dict] = contextvars.ContextVar(
    "revenium_run_meta", default={}
)

@contextmanager
def revenium_run_context(ticker: str, trade_date: str, **meta):
    """Set run-scoped contextvars for the duration of a propagate() call."""
    trace_id = str(uuid.uuid4())
    token_trace = current_trace_id.set(trace_id)
    token_meta = current_run_meta.set({"ticker": ticker, "trade_date": str(trade_date), **meta})
    try:
        yield trace_id
    finally:
        current_trace_id.reset(token_trace)
        current_run_meta.reset(token_meta)
```

**One-liner agent node set** (to be placed at the first line of each `*_node(state)` function body):
```python
from tradingagents.revenium.context import current_agent_name
current_agent_name.set("market_analyst")   # replace with the actual node name
```

---

### `tradingagents/revenium/config.py` (config, N/A)

**Analog:** `tradingagents/default_config.py` — exact pattern for `_ENV_OVERRIDES` dict and `_apply_env_overrides`.

**`_ENV_OVERRIDES` pattern** (default_config.py lines 10-21):
```python
_ENV_OVERRIDES = {
    "TRADINGAGENTS_LLM_PROVIDER":         "llm_provider",
    "TRADINGAGENTS_DEEP_THINK_LLM":       "deep_think_llm",
    ...
}
```

**New entries to add to `default_config.py` `_ENV_OVERRIDES`** (follow same format):
```python
"REVENIUM_METERING_API_KEY":    "revenium_api_key",
"REVENIUM_METERING_BASE_URL":   "revenium_api_url",
"REVENIUM_ORGANIZATION_NAME":   "revenium_organization_name",
"REVENIUM_PRODUCT_NAME":        "revenium_product_name",
"REVENIUM_SUBSCRIBER_ID":       "revenium_subscriber_id",
```

**New `DEFAULT_CONFIG` keys to add** (follow same format as default_config.py lines 45-135 dict literal):
```python
# Revenium metering — auto-enabled when api_key is non-empty (D-05)
"revenium_api_key":            os.getenv("REVENIUM_METERING_API_KEY", ""),
"revenium_api_url":            os.getenv("REVENIUM_METERING_BASE_URL", "https://api.revenium.ai"),
"revenium_organization_name":  "Revenium-Research-Desk",   # D-01
"revenium_product_name":       "trading-signal",            # D-03
"revenium_subscriber_id":      "john.demic+trading@revenium.io",  # D-02
"revenium_task_type_map": {    # D-11
    "market_analyst":          "analysis",
    "sentiment_analyst":       "analysis",
    "news_analyst":            "analysis",
    "fundamentals_analyst":    "analysis",
    "bull_researcher":         "research_debate",
    "bear_researcher":         "research_debate",
    "research_manager":        "planning",
    "trader":                  "trade",
    "aggressive_debator":      "risk_debate",
    "conservative_debator":    "risk_debate",
    "neutral_debator":         "risk_debate",
    "portfolio_manager":       "decision",
},
```

Note: `revenium_task_type_map` is a dict-typed key, so `set_config` merges it one level deep (existing pattern).

---

### `tradingagents/revenium/client.py` (service, request-response)

**Analog:** `tradingagents/llm_clients/factory.py` — lazy-import pattern and single-responsibility HTTP dispatch.

**Lazy import / fail-open pattern** (factory.py lines 1-54):
```python
from .base_client import BaseLLMClient

def create_llm_client(provider: str, model: str, base_url: str | None = None, **kwargs) -> BaseLLMClient:
    provider_lower = provider.lower()
    if provider_lower == "anthropic":
        from .anthropic_client import AnthropicClient   # lazy import
        return AnthropicClient(model, base_url, **kwargs)
    ...
    raise ValueError(f"Unsupported LLM provider: {provider}")
```

**`client.py` responsibility:** Thin wrapper around `revenium-metering`'s `ReveniumMetering` (or direct `httpx` POST). Exposes `meter_ai_completion(payload: dict) -> None` and is the only place in the `revenium/` package that imports the external SDK. This isolates the SDK from tests (mock this module).

**Fail-open wrapper pattern** (CLAUDE.md convention applied to every outbound HTTP call):
```python
def meter_ai_completion(self, payload: dict) -> None:
    try:
        self._metering_client.meter_ai_completion(**payload)
    except Exception:  # noqa: BLE001 — fail open, never block the run
        logger.warning("Revenium HTTP call failed: %s", payload.get("agent"), exc_info=True)
```

---

### `tradingagents/revenium/cost_gate.py` (middleware, request-response)

**No close analog exists.** This file implements a budget-checking class that accumulates per-call cost and raises `CostLimitExceeded` at threshold. The closest structural reference is the error taxonomy in `tradingagents/dataflows/errors.py` for the custom exception, and the `StatsCallbackHandler._lock` pattern for thread-safe accumulation.

**Custom exception pattern** (from `tradingagents/dataflows/errors.py` — existing `VendorError` hierarchy):
```python
class CostLimitExceeded(RuntimeError):
    """Raised by ReveniumCostGate when the hard spend limit is crossed.

    Bubbles through LangChain callback invocation into the LangGraph node
    and out of graph.invoke() / graph.stream() — caught by TradingAgentsGraph
    in _run_graph() for clean error surface to the CLI.
    """
    def __init__(self, limit_usd: float, actual_usd: float) -> None:
        super().__init__(
            f"Hard spend limit ${limit_usd:.4f} exceeded (actual: ${actual_usd:.4f})"
        )
        self.limit_usd = limit_usd
        self.actual_usd = actual_usd
```

**Thread-safe accumulator pattern** (from stats_handler.py lines 14-15, 54-56):
```python
self._lock = threading.Lock()
...
with self._lock:
    self._run_cost_usd += estimated_cost
```

---

### `tradingagents/revenium/billing.py` (service, request-response)

**Analog:** `tradingagents/agents/utils/memory.py` — end-of-run emit pattern (store_decision called after graph.invoke succeeds in `_run_graph`).

The billing emitter is called at the same point in `_run_graph` as `self.memory_log.store_decision(...)` (trading_graph.py line 405). The structural pattern: a class instantiated in `TradingAgentsGraph.__init__`, called once at run-end.

**Call site pattern** (trading_graph.py lines 403-409 — emit after successful graph run):
```python
# Store decision for deferred reflection on the next same-ticker run.
self.memory_log.store_decision(
    ticker=company_name,
    trade_date=trade_date,
    final_trade_decision=final_state["final_trade_decision"],
)
```

The billing emitter call follows the same pattern immediately after this, wrapped in fail-open:
```python
try:
    self._billing_emitter.emit_signal_unit(
        trace_id=current_trace_id.get(),
        total_cost_usd=self._revenium_handler.run_total_cost,
    )
except Exception:  # noqa: BLE001 — fail open, never block the run
    logger.warning("Revenium billing emission failed", exc_info=True)
```

Phase 1 scope: billing.py is a stub (D-03 / billing is Phase 4). The file should exist with `emit_signal_unit` defined but no-op (`pass`) so Phase 4 can fill it without topology changes.

---

### `tradingagents/graph/trading_graph.py` (edit — callback seam + contextvar + model fix)

**Analog:** self — the file already has the seam. Three surgical edits:

**Edit 1 — Add `ReveniumCallbackHandler` to callbacks list** (trading_graph.py lines 54-66, `__init__`):
```python
# Existing pattern to replicate:
self.callbacks = callbacks or []
...
if self.callbacks:
    llm_kwargs["callbacks"] = self.callbacks
```

New code inserts before `self.callbacks = callbacks or []`:
```python
from tradingagents.revenium.callback import ReveniumCallbackHandler
from tradingagents.dataflows.config import get_config as _get_config

_rev_handler = ReveniumCallbackHandler.from_config(_get_config())
self._revenium_handler = _rev_handler
self.callbacks = list(callbacks or []) + ([_rev_handler] if _rev_handler.enabled else [])
```

**Edit 2 — Wrap `_run_graph` body in `revenium_run_context`** (trading_graph.py line 362, top of `_run_graph`):
```python
from tradingagents.revenium.context import revenium_run_context

def _run_graph(self, company_name, trade_date, asset_type: str = "stock"):
    with revenium_run_context(
        ticker=company_name,
        trade_date=str(trade_date),
    ) as _trace_id:
        # all existing body here, indented
        ...
```

**Edit 3 — Fix invalid default models** (trading_graph.py uses `self.config["deep_think_llm"]` and `self.config["quick_think_llm"]` at lines 83-93). The fix is in `default_config.py` (see below), not here.

---

### `tradingagents/default_config.py` (edit — model fix L-03)

**Analog:** self. The existing pattern for overriding defaults is to change the value in the dict literal, not patch elsewhere.

**Current broken values** (default_config.py lines 56-57):
```python
"deep_think_llm": "gpt-5.5",
"quick_think_llm": "gpt-5.4-mini",
```

**New values** (L-03 — two providers for Revenium cross-provider story):
```python
"llm_provider": "anthropic",           # demo default: Anthropic for deep-think
"deep_think_llm": "claude-sonnet-4-6", # Anthropic — Research Manager, Portfolio Manager
"quick_think_llm": "gpt-4.1-mini",     # OpenAI — analysts, trader (requires provider split — see note)
```

Note: Current code creates one `llm_provider` for both LLMs. The two-provider story (D-03) requires either (a) a second `quick_think_provider` config key + factory call in `__init__`, or (b) keeping both on Anthropic with `claude-haiku-3-5` as quick-think. The planner should resolve this; the config-key pattern stays the same regardless.

**`_ENV_OVERRIDES` addition** (default_config.py lines 10-21 — add after existing entries):
```python
_ENV_OVERRIDES = {
    ...existing entries...,
    "REVENIUM_METERING_API_KEY":    "revenium_api_key",
    "REVENIUM_METERING_BASE_URL":   "revenium_api_url",
    "REVENIUM_ORGANIZATION_NAME":   "revenium_organization_name",
    "REVENIUM_PRODUCT_NAME":        "revenium_product_name",
    "REVENIUM_SUBSCRIBER_ID":       "revenium_subscriber_id",
}
```

---

### `cli/main.py` (edit — add Revenium handler to callbacks, lines 1053-1062 and 1162)

**Analog:** self. The existing pattern for wiring `stats_handler` is the blueprint.

**Existing wiring pattern** (main.py lines 1041-1059):
```python
stats_handler = StatsCallbackHandler()
...
graph = TradingAgentsGraph(
    selected_analyst_keys,
    config=config,
    debug=True,
    callbacks=[stats_handler],        # ← add revenium_handler here
)
```

**Edit at line 1041-1042** — construct Revenium handler alongside stats handler:
```python
stats_handler = StatsCallbackHandler()
# ReveniumCallbackHandler is a no-op when REVENIUM_METERING_API_KEY is absent (D-05)
from tradingagents.revenium.callback import ReveniumCallbackHandler
revenium_handler = ReveniumCallbackHandler.from_config(config)
```

**Edit at lines 1054-1059** — extend callbacks list:
```python
graph = TradingAgentsGraph(
    selected_analyst_keys,
    config=config,
    debug=True,
    callbacks=[stats_handler] + ([revenium_handler] if revenium_handler.enabled else []),
)
```

**Edit at line 1162** — propagate callbacks to graph args for tool tracking:
```python
# Existing:
args = graph.propagator.get_graph_args(callbacks=[stats_handler])
# New:
_all_handlers = [stats_handler] + ([revenium_handler] if revenium_handler.enabled else [])
args = graph.propagator.get_graph_args(callbacks=_all_handlers)
```

---

### Agent node one-liners (13 files, event-driven)

**Analog:** `tradingagents/agents/analysts/market_analyst.py` — the `create_*(llm)` factory / inner `*_node(state)` pattern.

**Inner node pattern** (market_analyst.py lines 12-94):
```python
def create_market_analyst(llm):

    def market_analyst_node(state):
        current_date = state["trade_date"]
        ...
        return {"messages": [result], "market_report": report}

    return market_analyst_node
```

**One-liner addition** — insert as the **first line of each `*_node(state)` body**:
```python
def market_analyst_node(state):
    from tradingagents.revenium.context import current_agent_name as _rev_agent
    _rev_agent.set("market_analyst")   # D-12: internal graph node name
    current_date = state["trade_date"]
    ...
```

Agent name values (D-12 — use internal LangGraph node names verbatim):

| File | Agent name string |
|------|-------------------|
| `agents/analysts/market_analyst.py` | `"market_analyst"` |
| `agents/analysts/sentiment_analyst.py` | `"sentiment_analyst"` |
| `agents/analysts/news_analyst.py` | `"news_analyst"` |
| `agents/analysts/fundamentals_analyst.py` | `"fundamentals_analyst"` |
| `agents/researchers/bull_researcher.py` | `"bull_researcher"` |
| `agents/researchers/bear_researcher.py` | `"bear_researcher"` |
| `agents/managers/research_manager.py` | `"research_manager"` |
| `agents/trader/trader.py` | `"trader"` |
| `agents/risk_mgmt/aggressive_debator.py` | `"aggressive_debator"` |
| `agents/risk_mgmt/conservative_debator.py` | `"conservative_debator"` |
| `agents/risk_mgmt/neutral_debator.py` | `"neutral_debator"` |
| `agents/managers/portfolio_manager.py` | `"portfolio_manager"` |
| `agents/managers/research_manager.py` (judge node) | `"research_manager"` (same manager) |

Note: `sentiment_analyst.py:69` calls `get_news.func()` directly (D-13 documented exemption). Do not add `@meter_tool` to that call path; document the exemption with a comment on that line.

---

### `scripts/setup_revenium.py` (utility, request-response)

**Analog:** `scripts/smoke_structured_output.py` — closest structural match: standalone CLI script with `argparse`, `main() -> int`, `sys.exit(main())`, module docstring explaining usage.

**Script structure pattern** (smoke_structured_output.py lines 1-22, 105-175):
```python
"""End-to-end smoke for structured-output agents against a real LLM provider.
...
Usage:
    OPENAI_API_KEY=... python scripts/smoke_structured_output.py openai
"""
from __future__ import annotations
import argparse
import sys

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    ...
    return 0  # or 1 on failure

if __name__ == "__main__":
    sys.exit(main())
```

**`setup_revenium.py` responsibility:** Idempotent Org → Subscriber → Product → Subscription provisioning via the Revenium SDK (D-08). Uses the values from D-01..D-03. No `propagate()` call. Exits 0 on success / 1 on first error with a clear human-readable message.

---

### `scripts/validate_metering.py` (utility, request-response)

**Analog:** `scripts/smoke_structured_output.py` — identical script structure; one real API call + assertion rather than structured-output probe.

**Script structure pattern:** Same as `setup_revenium.py` above. Uses `create_llm_client` + a minimal single LLM call, then asserts exactly one Revenium metering event appears in the account (via `client.list_recent_events()`). Exits 0 (PASS) / 1 (FAIL) with explicit output.

**Key assertion pattern** (from `smoke_structured_output.py` lines 156-169 check loop):
```python
failures = 0
for name, text, required in checks:
    for marker in required:
        ok = marker in text
        print(f"  {'PASS' if ok else 'FAIL'}  {name}: contains {marker!r}")
        failures += int(not ok)
if failures:
    print(f"Smoke FAILED: {failures} structure check(s) missing.")
    return 1
print("Smoke PASSED: ...")
return 0
```

---

### `.env.example` (edit)

**Analog:** self. The existing format uses one comment block per integration area (LLM Providers, FRED, AWS Bedrock, etc.).

**Existing block pattern** (.env.example lines 19-21):
```
# FRED (Federal Reserve macro data: rates, inflation, labor, growth). Free key: https://...
#FRED_API_KEY=
```

**New block to append** (after the last existing block):
```
# Revenium AI cost metering (https://revenium.io). Metering is auto-enabled when set;
# auto-disabled (silent no-op) when absent — so tests pass without a real key.
# rev_mk_* = metering key (required for metering and cost controls)
# rev_sk_* = write/management key (provisioned now, consumed in Phase 4)
REVENIUM_METERING_API_KEY=
#REVENIUM_METERING_BASE_URL=https://api.revenium.ai
#REVENIUM_SK_API_KEY=

# Demo identity (D-01..D-03). Override only to change the demo narrative.
#REVENIUM_ORGANIZATION_NAME=Revenium-Research-Desk
#REVENIUM_PRODUCT_NAME=trading-signal
#REVENIUM_SUBSCRIBER_ID=john.demic+trading@revenium.io
```

---

## Shared Patterns

### Fail-open exception handling
**Source:** `cli/stats_handler.py` lines 41-45 (bare `try/except (IndexError, TypeError): return`) + CLAUDE.md conventions
**Apply to:** Every Revenium HTTP call in `callback.py`, `client.py`, `billing.py`
```python
except Exception:  # noqa: BLE001 — fail open, never block the run
    logger.warning("Revenium %s failed, dropping event", operation_name, exc_info=True)
```

### Thread-safe state mutation
**Source:** `cli/stats_handler.py` lines 14, 54-56
**Apply to:** `callback.py` `agent_costs` dict and `run_total_cost` accumulator, `cost_gate.py` `_run_cost_usd`
```python
self._lock = threading.Lock()
...
with self._lock:
    self.tokens_in += usage_metadata.get("input_tokens", 0)
```

### Config key registration
**Source:** `tradingagents/default_config.py` lines 10-21 (`_ENV_OVERRIDES`) and lines 45-135 (`DEFAULT_CONFIG` dict literal)
**Apply to:** All new `revenium_*` config keys — one entry in `_ENV_OVERRIDES` + one default in `DEFAULT_CONFIG`
```python
_ENV_OVERRIDES = {
    ...
    "REVENIUM_METERING_API_KEY": "revenium_api_key",
}
DEFAULT_CONFIG = _apply_env_overrides({
    ...
    "revenium_api_key": os.getenv("REVENIUM_METERING_API_KEY", ""),
})
```

### Module docstring
**Source:** Every existing `tradingagents/` module — triple-quoted docstring at top explaining purpose, design rationale, key invariants
**Apply to:** All new `tradingagents/revenium/*.py` files

### Logger naming
**Source:** `tradingagents/graph/trading_graph.py` line 43, `tradingagents/agents/utils/agent_utils.py` line 49
**Apply to:** All new `tradingagents/revenium/*.py` files
```python
logger = logging.getLogger(__name__)
```

### `from __future__ import annotations`
**Source:** `tradingagents/agents/schemas.py`, `tradingagents/agents/utils/structured.py` (and others per CLAUDE.md)
**Apply to:** Any new file using `X | Y` union syntax or forward references in type annotations

---

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `tradingagents/revenium/cost_gate.py` | middleware | request-response | No cost-accumulation or enforcement-rule polling exists anywhere in the current codebase. Planner should use ARCHITECTURE.md §"Cost Controls" as the design spec. The custom exception pattern is adapted from `dataflows/errors.py` but the gate logic itself is net-new. |

---

## Metadata

**Analog search scope:** `cli/`, `tradingagents/graph/`, `tradingagents/agents/`, `tradingagents/llm_clients/`, `tradingagents/dataflows/`, `scripts/`
**Files scanned:** 14 (stats_handler.py, trading_graph.py, default_config.py, dataflows/config.py, llm_clients/factory.py, agents/analysts/market_analyst.py, agents/utils/agent_utils.py, scripts/smoke_structured_output.py, .env.example, ARCHITECTURE.md, STACK.md, PITFALLS.md, CONTEXT.md, CLAUDE.md)
**Pattern extraction date:** 2026-06-27
