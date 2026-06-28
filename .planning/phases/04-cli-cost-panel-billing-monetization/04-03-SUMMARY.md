---
phase: 04-cli-cost-panel-billing-monetization
plan: "03"
subsystem: revenium-billing-graph-hook
tags: [billing, monetize, BIL-01, BIL-02, D-09, D-10, tdd, keyless]
dependency_graph:
  requires:
    - TradingSignalBillingEmitter (tradingagents/revenium/billing.py — plan 04-02)
    - revenium_signal_price / revenium_billing_api_key / revenium_profitstream_url (plan 04-02)
  provides:
    - _billing_emitter instantiated in TradingAgentsGraph.__init__
    - create_trading_signal_job hook in _run_graph (after begin_run, before graph.invoke)
    - emit_billing_event hook in _run_graph (after final_state, before curr_state — D-09)
    - keyless placement tests proving success/halt billing contract (D-10)
  affects:
    - tradingagents/graph/trading_graph.py
    - tests/test_billing_graph_hook.py
tech_stack:
  added: []
  patterns:
    - TDD RED/GREEN (test-first placement tests, then minimal implementation)
    - emit_billing_event inside try after graph.invoke, NOT in finally (D-10 structural guarantee)
    - Daemon-thread fire-and-forget billing I/O (inherited from billing.py — 04-02)
    - Keyless unit tests: __init__ patched via monkeypatch to bypass heavy LLM/graph setup
key_files:
  created:
    - tests/test_billing_graph_hook.py
  modified:
    - tradingagents/graph/trading_graph.py
decisions:
  - "D-09 implemented: exactly one emit_billing_event on the success path, after final_state is populated in both debug and non-debug branches, before self.curr_state = final_state"
  - "D-10 guaranteed structurally: BudgetExceededError from graph.invoke propagates before emit line; no conditional needed"
  - "D-08 wired: create_trading_signal_job called immediately after begin_run so job trace_id matches metering trace_id for margin correlation in Costs & Revenue dashboard"
  - "fail-open posture preserved: end_run / stop_polling remain in finally unconditionally; emit_billing_event is daemon-thread fire-and-forget"
metrics:
  duration: "4 minutes"
  completed: "2026-06-28"
  tasks_completed: 1
  tasks_total: 1
  files_created: 1
  files_modified: 1
---

# Phase 04 Plan 03: Billing Graph Hook Summary

Wired the billing emitter (from plan 04-02) into the graph run lifecycle, completing the monetize slice end to end. A real completed run now emits exactly one priced billing event correlated to its trace_id; circuit-breaker-halted runs emit none by structural guarantee.

## What Was Built

### Task 1: Billing hooks in `_run_graph` + `__init__` instantiation (TDD)

**`tradingagents/graph/trading_graph.py`** — Three changes:

1. **Import** (line 36): `from tradingagents.revenium.billing import TradingSignalBillingEmitter` added to the Revenium import block, alongside `ReveniumCallbackHandler`.

2. **`__init__` instantiation** (line 89): After the `ReveniumCallbackHandler.from_config` / dedup-guard block, added:
   ```python
   self._billing_emitter = TradingSignalBillingEmitter.from_config(self.config)
   ```
   Silent no-op when `revenium_billing_api_key` is empty (DMO-04 keyless).

3. **`_run_graph` hooks** — two placements:
   - After `begin_run` (before `graph.invoke`): `create_trading_signal_job(trace_id, ticker, trade_date)` opens the Revenium Job record correlated to the run's trace_id (D-08/BIL-02).
   - After `final_state` is fully populated in both debug (`stream` + chunk-merge) and non-debug (`graph.invoke`) branches, **before** `self.curr_state = final_state`: `emit_billing_event(trace_id, signal_price=config["revenium_signal_price"])` emits the outcome (D-09/BIL-01). The `finally` block (`end_run` / `stop_polling`) is unchanged.

**D-10 guarantee:** `BudgetExceededError` raised inside `graph.invoke()` propagates before reaching the `emit_billing_event` line. The billing emit is structurally unreachable on the halt path — no `if not halted:` conditional is needed.

**`tests/test_billing_graph_hook.py`** — 2 keyless unit tests (`@pytest.mark.unit`):

- `test_billing_emit_once_on_success` — patches `TradingAgentsGraph.__init__` to skip heavy LLM/graph setup; replaces `_billing_emitter` and `_revenium_handler` with `MagicMock`; patches `graph.invoke` to return a synthetic `final_state`; asserts `create_trading_signal_job` called once, `emit_billing_event` called once with `signal_price == config["revenium_signal_price"]`, `end_run` called once.

- `test_no_billing_emit_on_budget_exceeded_error` — same fixture; patches `graph.invoke` to raise `BudgetExceededError`; asserts `create_trading_signal_job` called once, `emit_billing_event` NOT called, `end_run` called once (finally fired).

## Verification Results

| Check | Result |
|-------|--------|
| `pytest tests/test_billing_graph_hook.py -q` | 2 passed |
| `pytest tests/test_billing_graph_hook.py tests/test_revenium_enforcement.py tests/test_revenium_tracing.py -q` | 24 passed |
| `pytest -m unit -q` (full suite) | 353 passed, 1 pre-existing deepseek failure, 1 bedrock skip |
| `ruff check tradingagents/graph/trading_graph.py` | clean |
| `grep -n "emit_billing_event" trading_graph.py` inside try, NOT in finally | verified (line 478; finally at line 503) |
| `grep -n "TradingSignalBillingEmitter.from_config" trading_graph.py` | confirmed (line 89 in `__init__`) |

Pre-existing failure: `test_temperature_config.py::TestTemperatureForwarding::test_temperature_reaches_client_when_set[deepseek-deepseek-chat]` — unrelated to this plan (deepseek provider; was failing before these changes, documented in 04-02 SUMMARY).

## TDD Gate Compliance

| Gate | Commit | Status |
|------|--------|--------|
| RED — failing tests | `01680c8` | `test(04-03): add failing placement tests for billing graph hooks (RED)` |
| GREEN — implementation | `4ae236f` | `feat(04-03): wire billing emitter into TradingAgentsGraph lifecycle (GREEN)` |

Both gate commits present in order. No REFACTOR pass required (no cleanup needed).

## Deviations from Plan

None — plan executed exactly as written. The billing emit placement matches the PATTERNS.md `<-- billing emit_billing_event goes HERE` annotation.

## Security / Threat Coverage

| Threat ID | Mitigation Applied |
|-----------|-------------------|
| T-04-06 (Repudiation / Tampering — double-billing or billing a halted run) | Exactly one emit on success path (D-09); `BudgetExceededError` propagates before emit line (D-10). `create_job` uses the unique per-run trace_id (idempotent re-run safety via SDK 409 handling in 04-02). |
| T-04-07 (DoS via blocking emit) | `emit_billing_event` dispatches on a daemon thread (inherited from `billing.py`); `end_run`/`stop_polling` remain in `finally` and always fire. |

## Known Stubs

None. All production code paths are fully wired. The `= {}` / `= []` patterns flagged in the stub scan are pre-existing initialized variables in `trading_graph.py` and intentional MagicMock return values in the test fixture — not production stubs.

## Threat Flags

None. No new network endpoints, auth paths, or schema changes beyond the billing emit path that was already in the plan's threat model.

## Commits

| Task | Commit | Files |
|------|--------|-------|
| Task 1 (RED) | `01680c8` | `tests/test_billing_graph_hook.py` |
| Task 1 (GREEN) | `4ae236f` | `tradingagents/graph/trading_graph.py` |

## Self-Check: PASSED

- `tradingagents/graph/trading_graph.py` — exists, contains `TradingSignalBillingEmitter`, `create_trading_signal_job`, `emit_billing_event`
- `tests/test_billing_graph_hook.py` — exists, 2 tests all passing
- Commits `01680c8` (RED) and `4ae236f` (GREEN) — both verified in `git log`
