# Phase 4: CLI Cost Panel & Billing Monetization - Pattern Map

**Mapped:** 2026-06-28
**Files analyzed:** 7 (4 modified, 3 new)
**Analogs found:** 7 / 7

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `cli/main.py` — `_build_cost_panel`, layout 3rd column, `update_display` sig | component | request-response | `cli/main.py` `_render_budget_halt_panel` (lines 481–528) | exact |
| `tradingagents/revenium/callback.py` — extend `on_llm_end`, `end_run` | middleware | event-driven | same file (existing accumulator, lines 476–482 / 257–286) | exact |
| `tradingagents/revenium/billing.py` (NEW) | service | request-response | `tradingagents/revenium/client.py` | role-match |
| `tradingagents/revenium/pricing.py` (NEW) | utility | transform | `tradingagents/llm_clients/capabilities.py` (declarative table) | role-match |
| `tradingagents/graph/trading_graph.py` — billing hooks in `_run_graph` | controller | request-response | same file `_run_graph` (lines 386–479) | exact |
| `tradingagents/default_config.py` — 3 new keys + `_ENV_OVERRIDES` | config | — | same file (lines 10–30, 155–178) | exact |
| `scripts/validate_billing.py` (NEW) | utility/smoke | request-response | `scripts/validate_controls.py` | exact |

---

## Pattern Assignments

### `cli/main.py` — `_build_cost_panel` (new function) + layout + `update_display`

**Analog:** `cli/main.py` `_render_budget_halt_panel` and `create_layout` / `update_display`

**Static predecessor to copy structure from** (lines 481–498):
```python
# cli/main.py:481-498 — _render_budget_halt_panel (exact source for live panel)
def _render_budget_halt_panel(console, err, handler) -> None:
    cost_table = Table(show_header=True, header_style="bold magenta")
    cost_table.add_column("Agent", style="cyan")
    cost_table.add_column("Input Tokens", justify="right")
    cost_table.add_column("Output Tokens", justify="right")
    for agent, counts in sorted(handler.agent_costs.items()):
        cost_table.add_row(
            agent,
            str(counts["input_tokens"]),
            str(counts["output_tokens"]),
        )
    # ...
    console.print(Panel(...))
```

**Live panel upgrades over the static predecessor:**
- Returns a `Panel` (not `console.print`) so it slots into `layout["costs"].update()`
- Adds `cost` and `call_count` columns (Phase 4 schema extension)
- Annotates debate-loop agents with `×N` when `call_count > 1` (D-05/D-06)
- Highlights the most expensive agent in `"bold yellow"` (D-03)
- Sorts by cost descending with a `Total` footer row

**Imports pattern** (lines 1–19 — all already present, no new imports needed):
```python
from rich import box
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
```

**`format_tokens` helper already in scope** (lines 267–271):
```python
def format_tokens(n):
    """Format token count for display."""
    if n >= 1000:
        return f"{n/1000:.1f}k"
    return str(n)
```

**Current layout definition** (lines 251–264) — add `costs` as third column in `upper`:
```python
# cli/main.py:251-264 — create_layout() CURRENT
def create_layout():
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="main"),
        Layout(name="footer", size=3),
    )
    layout["main"].split_column(
        Layout(name="upper", ratio=3), Layout(name="analysis", ratio=5)
    )
    layout["upper"].split_row(
        Layout(name="progress", ratio=2), Layout(name="messages", ratio=3)
    )
    return layout
```

**`update_display` current signature** (line 274) — add `revenium_handler=None` kwarg:
```python
# cli/main.py:274 — current signature
def update_display(layout, spinner_text=None, stats_handler=None, start_time=None):
```

**All `update_display` call sites in `run_analysis`** (lines 1186, 1199, 1205, 1211, 1332, 1356) — each already has `stats_handler=stats_handler, start_time=start_time` in scope; add `revenium_handler=revenium_handler` to all six.

**Display name mapping already in the file** (lines 64–77) — extend for debate-agent keys:
```python
# cli/main.py:64-77 — existing agent name constants
ANALYST_AGENT_NAMES = {
    "market": "Market Analyst",
    "social": "Sentiment Analyst",
    "news": "News Analyst",
    "fundamentals": "Fundamentals Analyst",
}
# Fixed agents: "Bull Researcher", "Bear Researcher", "Research Manager",
#               "Trader", "Aggressive Analyst", "Neutral Analyst",
#               "Conservative Analyst", "Portfolio Manager"
```

**Agent name mapping for cost panel display** — new `COST_PANEL_DISPLAY_NAMES` dict maps the raw `agent_costs` keys (contextvar strings) to human-readable panel labels:
```python
# New constant — maps current_agent_name contextvar values to display strings
COST_PANEL_DISPLAY_NAMES: dict[str, str] = {
    "market_analyst":       "Market Analyst",
    "sentiment_analyst":    "Sentiment Analyst",
    "news_analyst":         "News Analyst",
    "fundamentals_analyst": "Fundamentals Analyst",
    "bull_researcher":      "Bull Researcher",
    "bear_researcher":      "Bear Researcher",
    "research_manager":     "Research Manager",
    "trader":               "Trader",
    "aggressive_debator":   "Aggressive Analyst",
    "conservative_debator": "Conservative Analyst",
    "neutral_debator":      "Neutral Analyst",
    "portfolio_manager":    "Portfolio Manager",
}
```

**Error handling pattern:** `_build_cost_panel` must always return a valid `Panel` — guard with `if not costs:` and return an empty-state panel. Never raise; the function runs inside the `Live` refresh loop.

---

### `tradingagents/revenium/callback.py` — `on_llm_end` + `end_run` extensions

**Analog:** same file — existing accumulator block (lines 476–482) and `end_run` (lines 257–286)

**Current accumulator** (lines 476–482) — the exact block to extend in-place:
```python
# callback.py:476-482 — CURRENT (Phase 1-3 schema)
with self._lock:
    entry = self.agent_costs.setdefault(
        agent, {"input_tokens": 0, "output_tokens": 0}
    )
    entry["input_tokens"] += input_tokens
    entry["output_tokens"] += output_tokens
    self.run_total_tokens += total_tokens
```

**Extended schema** — replace the block above with:
```python
# callback.py — EXTENDED (Phase 4 schema: adds cost + call_count)
# Import at top of file: from tradingagents.revenium.pricing import compute_cost
local_cost = compute_cost(provider, model, input_tokens, output_tokens)
with self._lock:
    entry = self.agent_costs.setdefault(
        agent, {"input_tokens": 0, "output_tokens": 0, "cost": 0.0, "call_count": 0}
    )
    entry["input_tokens"] += input_tokens
    entry["output_tokens"] += output_tokens
    entry["cost"] += local_cost
    entry["call_count"] += 1
    self.run_total_tokens += total_tokens
```

**`end_run` cleanup extension** (lines 269–280) — add two `.clear()` resets after `_call_state.clear()`:
```python
# callback.py:269-280 — end_run() CURRENT (inside try, under lock)
with self._lock:
    self._run_trace_id = None
    self._run_meta = None
    self._last_transaction_id = ""
    self._call_state.clear()
    self._threads = [t for t in self._threads if t.is_alive()]

# end_run() EXTENDED — add after _call_state.clear():
    self.agent_costs.clear()        # NEW: reset per-agent costs for next run (Pitfall 4)
    self.run_total_tokens = 0       # NEW: reset token counter for next run
```

**Fail-open pattern to keep** (lines 250–255, 269–286):
```python
# Both begin_run and end_run use this identical guard — preserve in the extended end_run
except Exception:  # noqa: BLE001 — fail open, never block the run
    logger.warning(
        "ReveniumCallbackHandler.end_run failed — run-scoped state may not be cleared",
        exc_info=True,
    )
```

**Import to add** at top of `callback.py` (after existing Revenium imports):
```python
from tradingagents.revenium.pricing import compute_cost  # Phase 4 local cost estimate
```

---

### `tradingagents/revenium/billing.py` (NEW)

**Analog:** `tradingagents/revenium/client.py`

**Module structure to copy from `client.py`** (lines 1–38):
```python
# client.py:1-38 — module docstring + imports pattern
"""Thin fail-open HTTP client wrapping the revenium-metering SDK.
...
Key invariants:
- ...
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class ReveniumClient:
    """..."""
    def __init__(self, *, api_key: str, api_url: str) -> None: ...

    @property
    def enabled(self) -> bool:
        """True when a non-empty API key was supplied and the SDK initialised."""
        return bool(self._api_key) and self._sdk_client is not None

    def meter_ai_completion(self, payload: dict) -> None:
        """...(fail-open)..."""
        if not self.enabled:
            return
        try:
            self._sdk_client.ai.create_completion(**payload)
        except Exception:  # noqa: BLE001 — fail open, never block the run
            logger.warning(
                "Revenium metering failed for agent %r — event dropped",
                payload.get("agent", "unknown"),
                exc_info=True,
            )
```

**Lazy import pattern from `client.py`** (lines 66–76) — mirror this for `AgenticOutcomeClient`:
```python
# client.py:66-76 — lazy SDK import inside __init__
if api_key:
    try:
        from revenium_metering import ReveniumMetering  # lazy import (D-05)
        self._sdk_client = ReveniumMetering(api_key=api_key, base_url=api_url)
    except Exception:  # noqa: BLE001 — fail open, never block the run
        logger.warning(
            "Revenium SDK initialisation failed — metering disabled",
            exc_info=True,
        )
        self._sdk_client = None
```

**Background thread pattern from `callback.py`** (lines 489–519) — fire-and-forget for billing calls:
```python
# callback.py:489-519 — fire-and-forget background thread pattern
def _meter_safe(_payload: dict, _agent: str = agent) -> None:
    try:
        self._client.meter_ai_completion(_payload)
    except Exception:  # noqa: BLE001 — fail open, never block the run
        logger.warning(
            "Revenium background metering failed for agent %r — dropped",
            _agent,
            exc_info=True,
        )
t = threading.Thread(
    target=_meter_safe,
    args=(payload,),
    daemon=True,
    name=f"rev-meter-{agent[:16]}",
)
t.start()
```

**`from_config` factory pattern from `callback.py`** (lines 187–206):
```python
# callback.py:187-206 — from_config classmethod (standard factory pattern)
@classmethod
def from_config(cls, config: dict) -> ReveniumCallbackHandler:
    """Build a handler from a TradingAgents config dict (the primary API)."""
    attr = attribution_from_config(config)
    client = ReveniumClient(api_key=attr["api_key"], api_url=attr["api_url"])
    task_type_map: dict[str, str] = config.get("revenium_task_type_map", {})
    trace_type: str = config.get("revenium_trace_type", "trading-run")
    return cls(client=client, attribution=attr, task_type_map=task_type_map, trace_type=trace_type)
```

**`AgenticOutcomeClient` constructor and call signatures** (from `.venv/lib/python3.11/site-packages/revenium_middleware/agentic_outcomes.py`):
```python
# agentic_outcomes.py:29-38 — AgenticOutcomeSettings (frozen dataclass)
@dataclass(frozen=True)
class AgenticOutcomeSettings:
    api_key: str
    meter_base_url: str = "https://api.revenium.io"
    profitstream_base_url: str = "https://api.revenium.io"
    team_id: str = ""
    outcome_api_key: Optional[str] = None  # rev_sk_* key for jobs write path
    outcome_retry_attempts: int = 10
    outcome_retry_max_seconds: float = 90.0

# agentic_outcomes.py:195-221 — create_job() signature
def create_job(
    self,
    agentic_job_id: str,      # required — use trace_id
    *,
    name: Optional[str] = None,
    type: Optional[str] = None,
    environment: Optional[str] = None,
    dry_run: bool = False,
) -> Dict[str, Any]: ...

# agentic_outcomes.py:224-239 — report_outcome() signature
def report_outcome(
    self, agentic_job_id: str, payload: Dict[str, Any], *, dry_run: bool = False
) -> None: ...
# payload: {"result": "SUCCESS", "outcomeType": "CONVERTED",
#           "outcomeValue": 2.00, "outcomeCurrency": "USD",
#           "reportedBy": subscriber_id,
#           "metadata": {"ticker": ticker, "trade_date": str(trade_date)}}
```

**Imports for `billing.py`**:
```python
from __future__ import annotations

import logging
import threading
from typing import Any

logger = logging.getLogger(__name__)
```

---

### `tradingagents/revenium/pricing.py` (NEW)

**Analog:** `tradingagents/llm_clients/capabilities.py` — declarative per-model table

**Module docstring + frozen dataclass table pattern** (capabilities.py lines 1–60):
```python
# capabilities.py:1-60 — module docstring and frozen dataclass table pattern
"""Declarative per-model capability table for OpenAI-compatible providers.

This is the single place that knows which model IDs ...
Pattern adapted from the per-model compat: flags ...
"""
from __future__ import annotations

import re
from dataclasses import dataclass

@dataclass(frozen=True)
class ModelCapabilities:
    """What an OpenAI-compatible model accepts at the API level."""
    supports_tool_choice: bool
    ...

_DEEPSEEK_THINKING = ModelCapabilities(...)  # named constant pattern
```

**Pricing table structure to follow** — use a dict keyed by `(provider, model_substring)` tuple:
```python
# pricing.py — table pattern modelled on capabilities.py _BY_PATTERN approach
_PER_MILLION: dict[tuple[str, str], tuple[float, float]] = {
    # (provider_lower, model_substring_lower): (input_$/1M, output_$/1M)
    # [ASSUMED] prices from training data — verify against official pricing pages
    ("anthropic", "claude-sonnet-4"):  (3.00, 15.00),
    ("openai",    "gpt-4.1-mini"):     (0.40,  1.60),
    ("openai",    "gpt-4o-mini"):      (0.15,  0.60),
    ("openai",    "gpt-4o"):           (5.00, 15.00),
}
```

**`_detect_provider` helper already in `callback.py`** (lines 89–105) — reuse same `provider` string values (`"anthropic"`, `"openai"`, `"google"`, `"unknown"`):
```python
# callback.py:89-105 — _detect_provider (provider labels that pricing.py must handle)
def _detect_provider(serialized: dict[str, Any]) -> str:
    id_parts = " ".join(str(p).lower() for p in serialized.get("id", []))
    for candidate in ("anthropic", "openai", "google", "bedrock", "azure", "ollama"):
        if candidate in id_parts:
            return candidate
    return "unknown"
```

**Module imports** (copy `from __future__ import annotations` pattern from `callback.py` line 61):
```python
from __future__ import annotations
```

---

### `tradingagents/graph/trading_graph.py` — `_run_graph` billing hooks

**Analog:** same file `_run_graph` (lines 386–479)

**Current `_run_graph` try/finally skeleton** (lines 386–479) — billing hooks slot into this structure:
```python
# trading_graph.py:386-479 — _run_graph() — the success-vs-halted path
def _run_graph(self, company_name, trade_date, asset_type: str = "stock"):
    with revenium_run_context(ticker=company_name, trade_date=str(trade_date)) as _trace_id:
        try:
            self._revenium_handler.begin_run(_trace_id, company_name, str(trade_date))
            # ... init state ...

            if self.debug:
                trace = []
                for chunk in self.graph.stream(init_agent_state, **args):
                    ...
                    trace.append(chunk)
                final_state = {}
                for chunk in trace:
                    final_state.update(chunk)
            else:
                final_state = self.graph.invoke(init_agent_state, **args)

            # <-- billing emit_billing_event goes HERE (after graph completes, before finally)
            # Only reachable if graph.invoke() did NOT raise BudgetExceededError

            self.curr_state = final_state
            self._log_state(trade_date, final_state)
            self.memory_log.store_decision(...)
            ...
            return final_state, self.process_signal(final_state["final_trade_decision"])
        finally:
            self._revenium_handler.end_run()
            stop_polling()
```

**`__init__` handler instantiation pattern** (lines 74–83) — mirror this for `_billing_emitter`:
```python
# trading_graph.py:74-83 — existing handler instantiation (mirror pattern for billing)
_rev_handler = ReveniumCallbackHandler.from_config(self.config)
self._revenium_handler = _rev_handler
_caller_has_enabled_rev = any(
    isinstance(h, ReveniumCallbackHandler) and h.enabled
    for h in (callbacks or [])
)
if _rev_handler.enabled and not _caller_has_enabled_rev:
    self.callbacks = list(callbacks or []) + [_rev_handler]
else:
    self.callbacks = list(callbacks or [])
```

**Import block** (lines 1–46) — add `TradingSignalBillingEmitter` import alongside `ReveniumCallbackHandler`:
```python
# trading_graph.py:36-37 — current Revenium imports
from tradingagents.revenium.callback import ReveniumCallbackHandler
from tradingagents.revenium.context import revenium_run_context
# Add:
from tradingagents.revenium.billing import TradingSignalBillingEmitter
```

**`create_trading_signal_job` hook placement** — inside the `try` block, immediately after `begin_run`:
```python
# After: self._revenium_handler.begin_run(_trace_id, company_name, str(trade_date))
# Add:
self._billing_emitter.create_trading_signal_job(
    trace_id=_trace_id,
    ticker=company_name,
    trade_date=str(trade_date),
)
```

**`emit_billing_event` hook placement** — inside `try`, after the `final_state` merge (both debug and non-debug paths produce `final_state`), BEFORE the `return`:
```python
# After: final_state = {...} is fully populated (both debug and non-debug paths)
# BEFORE: self.curr_state = final_state
# Add:
self._billing_emitter.emit_billing_event(
    trace_id=_trace_id,
    signal_price=self.config.get("revenium_signal_price", 2.00),
)
```

**Critical placement rule** (from RESEARCH.md Pitfall 1): `emit_billing_event` MUST be in the `try` block after `graph.invoke()` / the debug trace merge, never in `finally`. `BudgetExceededError` raises inside `graph.invoke()` and propagates before reaching the billing call.

---

### `tradingagents/default_config.py` — 3 new config keys

**Analog:** same file — existing Revenium config block (lines 152–178) and `_ENV_OVERRIDES` (lines 10–30)

**Existing Revenium keys pattern** (lines 155–178) — add three new keys after `revenium_trace_type`:
```python
# default_config.py:155-178 — existing Revenium config block (copy style)
"revenium_api_key":            os.getenv("REVENIUM_METERING_API_KEY", ""),
"revenium_api_url":            os.getenv("REVENIUM_METERING_BASE_URL", "https://api.revenium.ai"),
"revenium_organization_name":  "Revenium-Research-Desk",
"revenium_product_name":       "trading-signal",
"revenium_subscriber_id":      "john.demic+trading@revenium.io",
"revenium_trace_type":         os.getenv("REVENIUM_TRACE_TYPE", "trading-run"),
# NEW Phase 4 keys:
"revenium_signal_price":       2.00,    # float literal — _coerce needs isinstance(ref, float)
"revenium_billing_api_key":    os.getenv("REVENIUM_BILLING_API_KEY", ""),
"revenium_profitstream_url":   os.getenv("REVENIUM_PROFITSTREAM_BASE_URL", "https://api.revenium.io"),
```

**`_coerce` float handling** (lines 33–41) — `revenium_signal_price` default MUST be `2.00` (float literal), not `"2.00"` (string), for coercion to fire correctly:
```python
# default_config.py:33-41 — _coerce (shows why float literal is required)
def _coerce(value: str, reference):
    """Coerce env-var string to the type of the existing default value."""
    if isinstance(reference, bool):
        return value.strip().lower() in ("true", "1", "yes", "on")
    if isinstance(reference, int) and not isinstance(reference, bool):
        return int(value)
    if isinstance(reference, float):
        return float(value)   # <-- only fires when default is a float, not a str
    return value
```

**`_ENV_OVERRIDES` entries to add** (lines 10–30 for context) — add three entries in the Revenium block:
```python
# default_config.py:22-30 — existing Revenium _ENV_OVERRIDES (append after these)
"REVENIUM_METERING_API_KEY":    "revenium_api_key",
"REVENIUM_METERING_BASE_URL":   "revenium_api_url",
"REVENIUM_ORGANIZATION_NAME":   "revenium_organization_name",
"REVENIUM_PRODUCT_NAME":        "revenium_product_name",
"REVENIUM_SUBSCRIBER_ID":       "revenium_subscriber_id",
"REVENIUM_TRACE_TYPE":          "revenium_trace_type",
# NEW Phase 4:
"TRADINGAGENTS_SIGNAL_PRICE":       "revenium_signal_price",
"REVENIUM_BILLING_API_KEY":         "revenium_billing_api_key",
"REVENIUM_PROFITSTREAM_BASE_URL":   "revenium_profitstream_url",
```

---

### `scripts/validate_billing.py` (NEW)

**Analog:** `scripts/validate_controls.py` (exact role-match)

**Module-level structure** (validate_controls.py lines 1–56) — copy verbatim, adapt docstring:
```python
# validate_controls.py:1-56 — module docstring + _run_checks helper (copy structure)
"""Live end-to-end billing validation for Revenium + TradingAgents.

Calls AgenticOutcomeClient.create_job() and report_outcome() against the
live account, validates HTTP 200/201, and reports the job_id for dashboard
confirmation...

Requirements:
  - REVENIUM_BILLING_API_KEY set to a rev_sk_* key
  - REVENIUM_PROFITSTREAM_BASE_URL (optional; defaults to https://api.revenium.io)
  ...
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone


def _run_checks(checks: list[tuple[str, bool]]) -> tuple[int, int]:
    """Print PASS/FAIL for each check tuple and return (passed, failed) counts."""
    passed, failed = 0, 0
    for name, ok in checks:
        label = "PASS" if ok else "FAIL"
        print(f"  {label}  {name}")
        if ok:
            passed += 1
        else:
            failed += 1
    return passed, failed
```

**`main()` structure** (validate_controls.py lines 58–179) — copy the keyless-gate + argparse pattern:
```python
# validate_controls.py:58-100 — main() structure (argparse + load_dotenv + keyless gate)
def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--ticker", default="NVDA", ...)
    parser.add_argument("--date", default="2026-06-27", ...)
    args = parser.parse_args()

    import os
    from dotenv import load_dotenv
    load_dotenv()
    from tradingagents.default_config import DEFAULT_CONFIG
    config = dict(DEFAULT_CONFIG)

    # Keyless gate — exits 0 so CI never breaks (DMO-04)
    api_key: str = config.get("revenium_billing_api_key", "")
    if not api_key:
        print("no REVENIUM_BILLING_API_KEY — keyless mode, skipping live assertions")
        return 0

    # Late imports (after load_dotenv)
    from revenium_middleware.agentic_outcomes import AgenticOutcomeClient, AgenticOutcomeSettings
    ...
```

**Check list pattern** (validate_controls.py lines 139–175):
```python
# validate_controls.py:139-175 — checks list + _run_checks + summary pattern
checks: list[tuple[str, bool]] = []
checks.append(("create_job returned 200/201 (job created)", job_ok))
checks.append(("report_outcome returned 200/201 (outcome recorded)", outcome_ok))
checks.append(("job_id matches trace_id (correlation confirmed)", job_id_matches))

print("Billing checks:")
passed, failed = _run_checks(checks)
print()

if failed == 0:
    print(f"Billing PASSED: {passed}/{passed + failed} checks.")
    return 0
else:
    print(f"Billing FAILED: {failed}/{passed + failed} check(s) failed.")
    return 1

if __name__ == "__main__":
    sys.exit(main())
```

**`sys.path` insert pattern** (setup_revenium.py line 74) — needed when running from `scripts/` directory:
```python
# setup_revenium.py:74 — sys.path insert for running from scripts/ outside package install
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
```

---

## Shared Patterns

### Fail-open wrapper
**Source:** `tradingagents/revenium/client.py` lines 83–108
**Apply to:** `billing.py` all public methods (`create_trading_signal_job`, `emit_billing_event`)
```python
# client.py:83-108 — the canonical fail-open pattern for all Revenium I/O
def meter_ai_completion(self, payload: dict) -> None:
    if not self.enabled:
        return
    try:
        self._sdk_client.ai.create_completion(**payload)
    except Exception:  # noqa: BLE001 — fail open, never block the run
        logger.warning(
            "Revenium metering failed for agent %r — event dropped",
            payload.get("agent", "unknown"),
            exc_info=True,
        )
```

### Background thread fire-and-forget
**Source:** `tradingagents/revenium/callback.py` lines 489–519
**Apply to:** `billing.py` — both `create_trading_signal_job` and `emit_billing_event` dispatch on daemon threads. Note: billing calls happen AFTER `graph.invoke()` returns, so blocking isn't a graph-node performance issue, but a timeout could delay CLI feedback. Background thread is still the correct pattern.
```python
# callback.py:510-519 — daemon thread pattern
t = threading.Thread(
    target=_meter_safe,
    args=(payload,),
    daemon=True,
    name=f"rev-meter-{agent[:16]}",
)
t.start()
```

### `enabled` property guard
**Source:** `tradingagents/revenium/client.py` lines 79–81 and `callback.py` lines 212–215
**Apply to:** `billing.py` — all methods begin with `if not self.enabled: return`
```python
# client.py:79-81
@property
def enabled(self) -> bool:
    """True when a non-empty API key was supplied and the SDK initialised."""
    return bool(self._api_key) and self._sdk_client is not None
```

### `from_config` classmethod factory
**Source:** `tradingagents/revenium/callback.py` lines 187–206
**Apply to:** `billing.py` — `TradingSignalBillingEmitter.from_config(config)` reads `revenium_billing_api_key`, `revenium_profitstream_url`, `revenium_subscriber_id` from the config dict.

### Keyless smoke-script gate
**Source:** `scripts/validate_controls.py` lines 92–98 and `scripts/validate_tracing.py` lines 108–113
**Apply to:** `scripts/validate_billing.py`
```python
# validate_controls.py:92-98 — keyless gate (copy exactly for validate_billing.py)
api_key: str = config.get("revenium_api_key", "")
if not api_key or not cb_enabled:
    print("no REVENIUM_METERING_API_KEY or REVENIUM_CIRCUIT_BREAKER_ENABLED — keyless mode, skipping live assertions")
    return 0
```

### `noqa` comment convention
**Source:** `tradingagents/revenium/callback.py` lines 251, 326, 356, 521
**Apply to:** every broad `except Exception` in `billing.py`
```python
except Exception:  # noqa: BLE001 — fail open, never block the run
```

### Log symbolic names only
**Source:** `tradingagents/revenium/client.py` line 104, `callback.py` line 494
**Apply to:** `billing.py` — log only `trace_id`, `ticker`, `signal_price` values; never log `api_key` or HTTP response body.

---

## No Analog Found

All files have analogs. No entries in this section.

---

## Metadata

**Analog search scope:** `cli/`, `tradingagents/revenium/`, `tradingagents/graph/`, `tradingagents/llm_clients/`, `tradingagents/default_config.py`, `scripts/`, `.venv/lib/python3.11/site-packages/revenium_middleware/`
**Files read:** 10 source files
**Pattern extraction date:** 2026-06-28
