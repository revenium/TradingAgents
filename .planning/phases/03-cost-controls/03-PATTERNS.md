# Phase 3: Cost Controls — Pattern Map

**Mapped:** 2026-06-28
**Files analyzed:** 6 (4 modified, 2 new)
**Analogs found:** 6 / 6

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `tradingagents/revenium/callback.py` | middleware/callback | request-response | `tradingagents/revenium/callback.py` (self) | exact (modify in place) |
| `tradingagents/graph/trading_graph.py` | orchestrator | request-response | `tradingagents/graph/trading_graph.py` (self) | exact (modify in place) |
| `cli/main.py` | CLI entry point | streaming/event-driven | `cli/main.py` (self) | exact (modify in place) |
| `scripts/setup_revenium.py` | provisioning script | CRUD | `scripts/setup_revenium.py` (self) | exact (modify in place) |
| `scripts/validate_controls.py` | validation script | request-response + timing | `scripts/validate_tracing.py` | exact match |
| `tests/test_revenium_enforcement.py` | unit test | N/A | `tests/test_revenium_tracing.py` + `tests/test_revenium_metering.py` | exact match |

---

## Pattern Assignments

### `tradingagents/revenium/callback.py` (middleware, request-response)

**Analog:** Self — modify `on_chat_model_start` in place.

**Current imports block** (lines 61–79):
```python
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
from tradingagents.revenium.context import (
    current_agent_name,
    current_run_meta,
    current_trace_id,
)
```

**Add to imports** — enforcement symbols must be imported at module level:
```python
from revenium_middleware._core import BudgetExceededError, check_enforcement  # noqa: F401
```

**Existing `on_chat_model_start` structure** (lines 291–333) — the seam where the enforcement gate inserts:
```python
def on_chat_model_start(
    self,
    serialized: dict[str, Any],
    messages: list[list[Any]],
    **kwargs: Any,
) -> None:
    if not self.enabled:
        return
    try:
        run_id = str(kwargs.get("run_id", uuid.uuid4()))
        # ... capture model/provider/agent ...
    except Exception:  # noqa: BLE001 — fail open, never block the run
        logger.warning(
            "Revenium on_chat_model_start failed — continuing without capture",
            exc_info=True,
        )
```

**New enforcement gate insertion point** — place BETWEEN the `if not self.enabled: return` guard and the `try:` block. `BudgetExceededError` must NOT be inside the try/except:
```python
def on_chat_model_start(self, serialized, messages, **kwargs):
    if not self.enabled:
        return

    # Enforcement gate — D-03: deliberate exception to the fail-open convention.
    # BudgetExceededError must NOT be caught below; it must propagate to
    # _run_graph / CLI so the run halts cleanly (CTL-01/02).
    # No-op when REVENIUM_CIRCUIT_BREAKER_ENABLED is unset or REVENIUM_BYPASS=true
    # (keeps keyless test suite green — DMO-04).
    check_enforcement({
        "subscriber_credential": self._attribution.get("subscriber_id", ""),
    })

    try:
        # ... existing capture code unchanged ...
    except Exception:  # noqa: BLE001 — fail open, never block the run
        logger.warning("Revenium on_chat_model_start failed ...", exc_info=True)
```

**Anti-pattern — do NOT place `check_enforcement` inside the try block.** `BudgetExceededError` subclasses `Exception` directly and would be silently swallowed.

---

### `tradingagents/graph/trading_graph.py` (orchestrator, request-response)

**Analog:** Self — modify `_run_graph` finally block in place.

**Add to imports** (after the existing `from tradingagents.revenium.callback import ReveniumCallbackHandler` line):
```python
from revenium_middleware._core import stop_polling
```

**Existing `_run_graph` finally block** (lines 470–474):
```python
        finally:
            # Clear run-scoped handler state unconditionally (even if
            # graph.invoke raises) so trace context never bleeds into the
            # next propagate() call.  end_run() is fail-open and never raises.
            self._revenium_handler.end_run()
```

**Modified finally block — add `stop_polling()` AFTER `end_run()`:**
```python
        finally:
            # Clear run-scoped handler state unconditionally (even if
            # graph.invoke raises) so trace context never bleeds into the
            # next propagate() call.  end_run() is fail-open and never raises.
            self._revenium_handler.end_run()
            # Stop the background enforcement poller so it does not outlive
            # this run. _ensure_poller_running() restarts it on the next
            # propagate() call's first check_enforcement() invocation.
            # Order matters: state clear (end_run) first, then teardown (stop_polling).
            stop_polling()
```

**Key ordering constraint:** `end_run()` must precede `stop_polling()`. `end_run()` clears run-scoped handler state (WR-01/WR-02); `stop_polling()` terminates the daemon thread. Both are fail-open no-ops; both must be in the `finally` block so they run even when `BudgetExceededError` propagates.

**Note on CLI path:** This `finally` only covers the `propagate()` path (`_run_graph`). The CLI path calls `graph.graph.stream()` directly and bypasses `_run_graph`. `stop_polling()` must ALSO be wired in `cli/main.py` — see below.

---

### `cli/main.py` (CLI entry point, streaming/event-driven)

**Analog:** Self — modify `run_analysis` in place.

**Existing imports at top of file** (lines 8–19) — all Rich symbols needed for the halt panel are already imported:
```python
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.live import Live
from rich.console import Console
```

**Existing streaming loop in `run_analysis`** (lines 1131–1303) — current structure:
```python
    with Live(layout, refresh_per_second=4):
        # ... init display, messages, spinner ...
        for chunk in graph.graph.stream(init_agent_state, **args):
            # ... process chunk ...
            trace.append(chunk)

        # ... merge final_state, complete agents ...
        update_display(layout, stats_handler=stats_handler, start_time=start_time)

    # Post-analysis prompts (outside Live context)
    console.print("\n[bold cyan]Analysis Complete![/bold cyan]\n")
```

**New imports to add to `run_analysis`** (add inside the function body at setup, after existing Revenium handler setup):
```python
from revenium_middleware._core import BudgetExceededError, stop_polling
```

**Modified streaming loop — wrap with try/except BudgetExceededError and add finally:**
```python
    try:
        with Live(layout, refresh_per_second=4):
            # ... all existing Live content unchanged ...
            for chunk in graph.graph.stream(init_agent_state, **args):
                # ... existing chunk processing unchanged ...
                trace.append(chunk)
            # ... existing post-stream updates unchanged ...
    except BudgetExceededError as err:
        # Run halted by Revenium enforcement (CTL-02).
        # The Live context has already exited before the except handler runs.
        _render_budget_halt_panel(console, err, revenium_handler)
        raise typer.Exit(code=1)
    finally:
        # Stop the enforcement daemon thread on every exit path (normal + halt).
        # Safe to call unconditionally — no-op if thread was never started.
        stop_polling()
```

**New `_render_budget_halt_panel` function** — place outside `run_analysis` as a module-level function (after the existing display helpers like `update_display`, before `get_user_selections`). Pattern follows the existing `display_complete_report` helper (line 816) which also uses `Panel` and iterates sections:
```python
def _render_budget_halt_panel(
    console: Console,
    err: "BudgetExceededError",
    handler: "ReveniumCallbackHandler",
) -> None:
    """Render the Rich halt panel for a budget enforcement stop (CTL-02, D-05).

    Shows rule context (name, spent/limit, resets_at, rule_id) and per-agent
    token breakdown from the handler accumulator.  Never prints raw key values
    (repo convention: log symbolic names only).
    """
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

    current = f"${err.current_value:.4f}" if err.current_value is not None else "—"
    threshold = f"${err.threshold:.4f}" if err.threshold is not None else "—"
    resets = err.resets_at or "—"

    body = Text()
    body.append("\nRule:      ", style="bold")
    body.append(err.rule_name or "cost limit")
    body.append("\nSpent:     ", style="bold")
    body.append(current, style="red bold")
    body.append("  /  Limit: ")
    body.append(threshold, style="yellow")
    body.append("\nResets at: ", style="bold")
    body.append(resets)
    body.append("\nRule ID:   ", style="bold")
    body.append(str(err.rule_id or "—"))

    console.print(Panel(
        body,
        title="[bold red]Run Halted — Budget Limit Reached[/bold red]",
        subtitle="Revenium enforcement rule blocked this request",
        border_style="red",
    ))
    console.print("\n[bold]Per-Agent Token Usage:[/bold]")
    console.print(cost_table)
    console.print(
        "\n[dim]Check the Revenium dashboard > Guardrails > Enforcement Events "
        "to see the enforcement event.[/dim]"
    )
    console.print("[yellow]Run exiting with non-zero status (no trading decision produced).[/yellow]")
```

**`BudgetExceededError` field reference** (from `revenium_middleware._core.exceptions`):
- `err.rule_name` — string name of the breached rule
- `err.current_value` — float, current accumulated spend
- `err.threshold` — float, the rule's hard limit
- `err.resets_at` — string ISO timestamp when the window resets
- `err.rule_id` — integer or None, the rule's unique ID

---

### `scripts/setup_revenium.py` (provisioning script, CRUD)

**Analog:** Self — extend with a new `_setup_cost_rule()` function following the `_setup_product()` pattern.

**Existing helper functions** — copy exactly, do not rewrite. All are usable for the cost rule:

`_get` helper (lines 139–155):
```python
def _get(base_url: str, path: str, sk_key: str, params: dict | None = None) -> Any:
    url = f"{base_url.rstrip('/')}{path}"
    resp = requests.get(url, headers=_headers(sk_key), params=params or {}, timeout=15)
    resp.raise_for_status()
    return resp.json()
```

`_post` helper (lines 158–177):
```python
def _post(base_url: str, path: str, sk_key: str, payload: dict) -> Any:
    url = f"{base_url.rstrip('/')}{path}"
    resp = requests.post(url, headers=_headers(sk_key), json=payload, timeout=15)
    resp.raise_for_status()
    return resp.json()
```

`_extract_list` helper (lines 184–206) — handles all Revenium list response shapes (bare array, Spring pagination, HAL, items).

`_handle_http_error` helper (lines 482–494) — standard error printer, never logs the key.

**Existing `_setup_product` idempotency pattern** (lines 315–384) — copy this structure for `_setup_cost_rule`:
```python
def _setup_product(base_url, sk_key, team_id, owner_id, dry_run):
    print(f"  Product: '{PRODUCT_NAME}'")
    if dry_run:
        print(f"    [dry-run] Would GET /products?teamId={team_id} (find by name)")
        print("    [dry-run] Would POST /products {...} if not found")
        return None

    # Lookup by teamId; match by exact name client-side
    try:
        data = _get(base_url, "/products", sk_key, params={"teamId": team_id})
        for prod in _extract_list(data):
            if prod.get("name") == PRODUCT_NAME:
                product_id = str(prod.get("id", ""))
                print(f"    exists (id={product_id or 'n/a'})")
                return product_id or None
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 404:
            pass  # No products yet — fall through to create
        else:
            _handle_http_error("Product lookup", exc)
            return None

    # Create
    try:
        result = _post(base_url, "/products", sk_key, { ... })
        product_id = str(result.get("id", ""))
        print(f"    created (id={product_id or 'n/a'})")
        return product_id or None
    except requests.HTTPError as exc:
        _handle_http_error("Product create", exc)
        return None
```

**New constants to add** at module level (near existing `ORG_NAME`, `PRODUCT_NAME`):
```python
DEMO_RULE_NAME = "TradingAgents Demo Budget"
DEMO_RULE_HARD_LIMIT = 1.00    # $1.00 DAILY — tune per timing dry-run
DEMO_RULE_WARN_THRESHOLD = 0.50
```

**PATCH helper needed** — `_setup_product` only uses GET and POST; the cost rule idempotency path also needs PATCH for existing shadow-mode rules. Add alongside `_post`:
```python
def _patch(base_url: str, path: str, sk_key: str, payload: dict) -> Any:
    url = f"{base_url.rstrip('/')}{path}"
    resp = requests.patch(url, headers=_headers(sk_key), json=payload, timeout=15)
    resp.raise_for_status()
    return resp.json()
```

**New `_setup_cost_rule` function** — call it after `_setup_subscription` in `main()`:
```python
def _setup_cost_rule(base_url: str, sk_key: str, team_id: str, dry_run: bool) -> bool:
    """Create or verify the enforce-mode cost rule (CTL-04, D-06).

    Idempotency: look up by name, create if missing, PATCH to enforce mode
    if found in shadow mode.  Returns True on success or dry-run.
    """
    print(f"  Cost rule: '{DEMO_RULE_NAME}' (TOTAL_COST DAILY ${DEMO_RULE_HARD_LIMIT})")
    if dry_run:
        print(f"    [dry-run] Would GET /ai/cost-controls?teamId={team_id} (find by name)")
        print("    [dry-run] Would POST /ai/cost-controls {...shadowMode:false...} if not found")
        print("    [dry-run] Would PATCH /ai/cost-controls/{id} {shadowMode:false} if in shadow mode")
        return True

    try:
        data = _get(base_url, "/ai/cost-controls", sk_key, params={"teamId": team_id})
        for rule in _extract_list(data):
            if rule.get("name") == DEMO_RULE_NAME or rule.get("label") == DEMO_RULE_NAME:
                rule_id = str(rule.get("id", ""))
                shadow = rule.get("shadowMode", True)
                enabled = rule.get("enabled", False)
                if not shadow and enabled:
                    print(f"    exists in enforce mode (id={rule_id}) — OK")
                    return True
                try:
                    _patch(base_url, f"/ai/cost-controls/{rule_id}", sk_key,
                           {"shadowMode": False, "enabled": True})
                    print(f"    updated to enforce mode (id={rule_id})")
                    return True
                except requests.HTTPError as exc:
                    _handle_http_error("Cost rule PATCH", exc)
                    return False
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 404:
            pass  # No rules yet — fall through to create
        else:
            _handle_http_error("Cost rule lookup", exc)
            return False

    try:
        result = _post(base_url, "/ai/cost-controls", sk_key, {
            "name": DEMO_RULE_NAME,
            "description": (
                "Demo cost gate for FCAT — enforce mode. "
                "Scoped to Revenium-Research-Desk org. "
                "Halts the run mid-debate for the control pillar demo."
            ),
            "metricType": "TOTAL_COST",
            "windowType": "DAILY",
            "action": "BLOCK",
            "groupBy": "AGENT",
            "hardLimit": DEMO_RULE_HARD_LIMIT,
            "warnThreshold": DEMO_RULE_WARN_THRESHOLD,
            "shadowMode": False,
            "enabled": True,
            "filters": [
                {"dimension": "ORGANIZATION", "operator": "IS", "value": ORG_NAME},
            ],
            "teamId": team_id,
            "notificationChannelIds": [],
        })
        rule_id = str(result.get("id", ""))
        print(f"    created in enforce mode (id={rule_id or 'n/a'})")
        return True
    except requests.HTTPError as exc:
        _handle_http_error("Cost rule create", exc)
        return False
```

**`main()` extension** — after the existing four provisioning calls (lines 576–596), add:
```python
    # 5. Cost rule (enforce-mode, TOTAL_COST DAILY $1.00 — CTL-04, D-06)
    ok = _setup_cost_rule(base_url, sk_key, team_id, args.dry_run)
    if not args.dry_run and not ok:
        failures += 1
```

**Note on host:** The cost rule CREATE uses the same management base URL as the rest of `setup_revenium.py` (`https://api.prod.ai.hcapp.io/profitstream/v2/api`). Do NOT use the enforcement polling URL (`https://api.revenium.ai`). The existing `base_url` variable in `main()` is correct.

---

### `scripts/validate_controls.py` (NEW — validation script, request-response + timing)

**Analog:** `scripts/validate_tracing.py` — copy the full skeleton verbatim, then adapt.

**Module docstring pattern** (from `validate_tracing.py` lines 1–49):
```python
"""Live end-to-end controls validation for Revenium + TradingAgents.

Timing dry-run: runs one full TradingAgentsGraph.propagate() call, measures
where in the run the BudgetExceededError halt fires, and checks enforcement
readiness (compiled rules, percentUsed, shadowMode).

  CTL-01  Halt fires during the run — check_enforcement() raised BudgetExceededError
          and the run stopped before completion.
  CTL-04  Enforce mode confirmed — breached rule has shadowMode:false.
  TIMING  Reports which agent triggered the halt and elapsed seconds to halt.

Requirements:
  - REVENIUM_METERING_API_KEY set to a valid rev_mk_* key
  - REVENIUM_CIRCUIT_BREAKER_ENABLED=true
  - REVENIUM_TEAM_ID=DZxzEl
  - REVENIUM_CB_POLL_INTERVAL_SECONDS=5 (for reliable timing)
  - At least one LLM provider key

Usage:
    REVENIUM_METERING_API_KEY=rev_mk_... REVENIUM_CIRCUIT_BREAKER_ENABLED=true \\
    REVENIUM_TEAM_ID=DZxzEl REVENIUM_CB_POLL_INTERVAL_SECONDS=5 \\
    OPENAI_API_KEY=... python scripts/validate_controls.py

    # Keyless mode (no CB key → skips live assertions and exits 0):
    python scripts/validate_controls.py
"""
```

**`_run_checks` helper** — copy verbatim from `validate_tracing.py` lines 58–68:
```python
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

**`main()` skeleton** — follow `validate_tracing.py` lines 71–277 exactly for structure:
```python
def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--ticker", default="NVDA", help="Ticker symbol to analyse.")
    parser.add_argument("--date", default="2026-06-27", help="Analysis date YYYY-MM-DD.")
    args = parser.parse_args()

    from dotenv import load_dotenv
    load_dotenv()

    from tradingagents.default_config import DEFAULT_CONFIG
    config = dict(DEFAULT_CONFIG)

    # Gate: enforcement keys must be set for live assertions.
    # Keyless mode exits 0 so CI never breaks on missing credentials.
    import os
    cb_enabled = os.getenv("REVENIUM_CIRCUIT_BREAKER_ENABLED", "").lower() in ("1", "true")
    api_key: str = config.get("revenium_api_key", "")
    if not api_key or not cb_enabled:
        print("no REVENIUM_METERING_API_KEY or REVENIUM_CIRCUIT_BREAKER_ENABLED — keyless mode")
        return 0

    from tradingagents.graph.trading_graph import TradingAgentsGraph
    from revenium_middleware._core.exceptions import BudgetExceededError

    graph = TradingAgentsGraph(config=config)

    print(f"\nValidating Revenium cost controls — {datetime.now(timezone.utc).isoformat()}")
    print(f"  Ticker       : {args.ticker}")
    print(f"  Trade date   : {args.date}")
    print(f"  Metering key : {api_key[:12]}... (hidden)")
    print()

    # Capture halt details
    halt_exception: BudgetExceededError | None = None
    elapsed_to_halt: float | None = None
    start_time = time.time()

    try:
        graph.propagate(args.ticker, args.date)
    except BudgetExceededError as err:
        halt_exception = err
        elapsed_to_halt = time.time() - start_time
        print(f"  BudgetExceededError raised after {elapsed_to_halt:.1f}s — "
              f"rule={err.rule_name!r} spent={err.current_value} limit={err.threshold}")
    except Exception as exc:  # noqa: BLE001 — fail open, surface in checks
        print(f"  ERROR: propagate() raised unexpected: {exc}")

    # Enforcement readiness check — read compiled rules from cache/API
    # (import enforcement module to inspect _cached_rules for a live readiness check)

    checks: list[tuple[str, bool]] = []
    checks.append(("BudgetExceededError raised (run halted by enforcement)", halt_exception is not None))

    if halt_exception is not None:
        checks.append(("rule_name is non-empty", bool(halt_exception.rule_name)))
        checks.append(("current_value > 0", (halt_exception.current_value or 0) > 0))
        checks.append(("threshold > 0", (halt_exception.threshold or 0) > 0))
        checks.append(("resets_at is non-empty", bool(halt_exception.resets_at)))
        checks.append((
            f"Halted within 120s (got {elapsed_to_halt:.1f}s)" if elapsed_to_halt else "Timing: n/a",
            elapsed_to_halt is not None and elapsed_to_halt < 120,
        ))

    passed, failed = _run_checks(checks)
    print()

    # Dashboard reminder
    if halt_exception is not None:
        print("Confirm in the Revenium dashboard (Guardrails -> Enforcement Events):")
        print(f"  1. An enforcement event with action=BLOCK and ruleName={halt_exception.rule_name!r}")
        print("  2. isShadow=false (enforce mode confirmed — CTL-04)")
        print(f"  3. currentValue > threshold ({halt_exception.current_value} > {halt_exception.threshold})")
        print(f"  4. Elapsed time to halt: {elapsed_to_halt:.1f}s (target: mid-debate ~20-60s)")
        print()

    if failed == 0:
        print(f"Controls PASSED: {passed}/{passed + failed} checks.")
        return 0
    else:
        print(f"Controls FAILED: {failed}/{passed + failed} check(s) failed.")
        return 1
```

**Additional imports needed at top of file** (beyond `validate_tracing.py`):
```python
import time
from datetime import datetime, timezone
```

---

### `tests/test_revenium_enforcement.py` (NEW — unit tests)

**Analog:** `tests/test_revenium_tracing.py` (autouse fixture pattern) + `tests/test_revenium_metering.py` (handler construction pattern).

**Module docstring pattern** (from `test_revenium_metering.py` lines 1–19):
```python
"""Tests for the Revenium enforcement gate — check_enforcement wiring in the callback handler.

All tests are unit-level (marker: unit) and pass without any live
REVENIUM_METERING_API_KEY or REVENIUM_CIRCUIT_BREAKER_ENABLED.
All Revenium enforcement checks are mocked via _seed_rules().

Key invariants validated:
- check_enforcement() raises BudgetExceededError for a breached enforce-mode rule.
- check_enforcement() is a no-op when REVENIUM_BYPASS=true.
- shadowMode:true rules never block, even when breached.
- BudgetExceededError from check_enforcement() propagates OUT of on_chat_model_start
  (is NOT caught by the fail-open except block).
- REVENIUM_CIRCUIT_BREAKER_ENABLED unset → check_enforcement() is a no-op.
"""
```

**`_reset_enforcement` autouse fixture** — the core pattern for enforcement module isolation (from RESEARCH.md §Code Examples):
```python
import importlib
import pytest
from revenium_middleware._core import enforcement
from revenium_middleware._core.exceptions import BudgetExceededError


@pytest.fixture(autouse=True)
def _reset_enforcement(monkeypatch):
    """Isolate enforcement module state across tests."""
    for var in (
        "REVENIUM_CIRCUIT_BREAKER_ENABLED",
        "REVENIUM_BYPASS",
        "REVENIUM_CB_FAIL_MODE",
        "REVENIUM_TEAM_ID",
        "REVENIUM_METERING_API_KEY",
    ):
        monkeypatch.delenv(var, raising=False)
    importlib.reload(enforcement)
    yield
    enforcement.stop_polling()
```

**`_seed_rules` helper** — injects rules into the enforcement cache without any network call:
```python
def _seed_rules(monkeypatch, rules: list, *, initialized: bool = True) -> None:
    """Inject rules into the enforcement cache, bypassing the network poller."""
    monkeypatch.setattr(enforcement, "_cached_rules", list(rules))
    monkeypatch.setattr(enforcement, "_cache_timestamp", float("inf"))
    monkeypatch.setattr(enforcement, "_cache_initialized", initialized)
    monkeypatch.setattr(enforcement, "_ensure_poller_running", lambda: None)
    monkeypatch.setattr(enforcement, "_fetch_rules", lambda: None)
```

**Handler construction pattern** — copy from `test_revenium_tracing.py` lines 89–111:
```python
@pytest.fixture
def handler_with_mock_client():
    """Return (handler, captured) where captured accumulates metered payloads."""
    from tradingagents.revenium.callback import ReveniumCallbackHandler

    captured: list[dict] = []
    mock_client = MagicMock()
    mock_client.meter_ai_completion.side_effect = lambda p: captured.append(p)

    handler = ReveniumCallbackHandler.from_config({
        "revenium_api_key": "rev_mk_test",
        "revenium_api_url": "https://api.revenium.ai",
        "revenium_organization_name": "Revenium-Research-Desk",
        "revenium_product_name": "trading-signal",
        "revenium_subscriber_id": "john.demic+trading@revenium.io",
        "revenium_task_type_map": {},
    })
    handler._client = mock_client
    return handler, captured
```

**`_make_serialized` helper** — copy verbatim from `test_revenium_metering.py` lines 50–55:
```python
def _make_serialized(model: str = "gpt-4.1-mini", provider: str = "openai") -> dict:
    return {
        "id": [f"langchain_{provider}", "chat_models", f"Chat{provider.capitalize()}"],
        "kwargs": {"model_name": model},
    }
```

**Test class structure** — follow the class-based grouping in `test_revenium_metering.py`:
```python
class TestEnforcementEngine:
    """Direct tests for check_enforcement() and stop_polling()."""
    @pytest.mark.unit
    def test_check_enforcement_raises_when_rule_breached(monkeypatch): ...
    @pytest.mark.unit
    def test_bypass_env_disables_enforcement(monkeypatch): ...
    @pytest.mark.unit
    def test_shadow_mode_rule_does_not_block(monkeypatch): ...
    @pytest.mark.unit
    def test_cb_disabled_env_is_noop(monkeypatch): ...

class TestCallbackHandlerEnforcementGate:
    """BudgetExceededError propagation from on_chat_model_start."""
    @pytest.mark.unit
    def test_budget_exceeded_propagates_from_on_chat_model_start(...): ...
    @pytest.mark.unit
    def test_normal_call_proceeds_when_no_rule_breached(...): ...
    @pytest.mark.unit
    def test_bypass_disables_gate_in_callback(...): ...
```

**Key assertion pattern for propagation test:**
```python
with pytest.raises(BudgetExceededError):
    handler.on_chat_model_start(serialized, [], run_id="test-run-id")
```

---

## Shared Patterns

### Fail-Open Convention (with the Deliberate Exception)

**Source:** `tradingagents/revenium/callback.py` lines 329–333 (on_chat_model_start) and lines 494–499 (on_llm_end)

**Apply to:** All `try/except` blocks added in Phase 3

**Standard pattern:**
```python
except Exception:  # noqa: BLE001 — fail open, never block the run
    logger.warning(
        "Revenium <method> failed — continuing without ...",
        exc_info=True,
    )
```

**The deliberate exception (D-03):** `BudgetExceededError` must NOT be caught by the fail-open block. Place `check_enforcement()` BEFORE the `try` block so `BudgetExceededError` escapes naturally.

### Rich Panel Rendering

**Source:** `cli/main.py` lines 831–874 (`display_complete_report`) and lines 496–504 (`Panel` usage in `update_display`)

**Apply to:** `_render_budget_halt_panel` in `cli/main.py`

**Pattern for a status panel:**
```python
console.print(Panel(
    content,
    title="[bold red]Title Text[/bold red]",
    subtitle="subtitle text",
    border_style="red",
))
```

**Pattern for a data table with `Table`:**
```python
table = Table(show_header=True, header_style="bold magenta")
table.add_column("Column", style="cyan")
table.add_column("Value", justify="right")
for key, val in data.items():
    table.add_row(key, str(val))
console.print(table)
```

### Provisioning Script: Idempotent Create-or-Verify

**Source:** `scripts/setup_revenium.py` lines 213–384 (`_setup_organization`, `_setup_product`)

**Apply to:** `_setup_cost_rule` in `scripts/setup_revenium.py`

**Pattern:**
1. `_get` with scope params → `_extract_list` → match by name client-side
2. If found: check state (shadowMode/enabled) → return OK or `_patch`
3. If 404: fall through to `_post` create
4. Other HTTP errors: `_handle_http_error` → return False
5. Always: `print(f"    exists/created/updated (id={id})")` for human confirmation

### Enforcement Module Isolation in Tests

**Source:** `tests/test_revenium_tracing.py` lines 35–51 (`_reset_contextvars` autouse fixture)

**Apply to:** `_reset_enforcement` autouse fixture in `tests/test_revenium_enforcement.py`

**Pattern:** `importlib.reload(enforcement)` + `monkeypatch.delenv` for all enforcement env vars + `enforcement.stop_polling()` in yield cleanup.

### Keyless Gate in Validation Scripts

**Source:** `scripts/validate_tracing.py` lines 109–113 and `scripts/validate_metering.py` lines 258–265

**Apply to:** `scripts/validate_controls.py`

**Pattern:**
```python
api_key: str = config.get("revenium_api_key", "")
if not api_key:
    print("no REVENIUM_METERING_API_KEY — keyless mode, skipping live assertions")
    return 0
```

### Validation Script: `_run_checks` + Dashboard Reminder

**Source:** `scripts/validate_tracing.py` lines 58–68 and 250–263

**Apply to:** `scripts/validate_controls.py`

**Pattern:** Accumulate `(name: str, ok: bool)` tuples in a list, call `_run_checks()`, print dashboard checklist after, print `PASSED`/`FAILED` summary with count.

---

## No Analog Found

None. All six files have close analogs in the existing codebase.

---

## Metadata

**Analog search scope:** `tradingagents/revenium/`, `tradingagents/graph/`, `cli/`, `scripts/`, `tests/`
**Files scanned:** 8 source files read in full
**Pattern extraction date:** 2026-06-28

**Critical sequencing facts for planner:**
1. `check_enforcement()` call must be BEFORE the `try` block in `on_chat_model_start` — this is the most common pitfall.
2. `stop_polling()` must appear in BOTH `_run_graph` finally (propagate path) AND `run_analysis` finally (CLI path) — these are two independent execution paths.
3. `stop_polling()` must come AFTER `end_run()` in the `_run_graph` finally block — state clear before teardown.
4. `BudgetExceededError` is caught in the CLI's outer `except` (after the `Live()` context exits), NOT inside the `with Live(...)` block.
5. The management API host (`api.prod.ai.hcapp.io`) and the enforcement polling host (`api.revenium.ai`) are different — the setup script uses the management host (already correct in the existing `base_url` variable).
