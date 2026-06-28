---
phase: 04-cli-cost-panel-billing-monetization
plan: "02"
subsystem: revenium-billing
tags: [billing, monetize, BIL-01, fail-open, keyless, jobs-outcomes]
dependency_graph:
  requires: []
  provides:
    - TradingSignalBillingEmitter (tradingagents/revenium/billing.py)
    - revenium_signal_price / revenium_billing_api_key / revenium_profitstream_url config keys
    - scripts/validate_billing.py keyless-gated smoke
  affects:
    - tradingagents/default_config.py
    - tradingagents/graph/trading_graph.py (plan 04-03 will add hook calls)
tech_stack:
  added: []
  patterns:
    - Lazy SDK import (AgenticOutcomeClient) mirroring ReveniumClient.__init__
    - Daemon-thread fire-and-forget for billing I/O (matches callback.py pattern)
    - enabled property + from_config factory (canonical Revenium client contract)
    - Keyless-gated smoke script (mirrors validate_controls.py / validate_tracing.py)
key_files:
  created:
    - tradingagents/revenium/billing.py
    - scripts/validate_billing.py
    - tests/test_billing_emitter.py
  modified:
    - tradingagents/default_config.py
decisions:
  - "D-07 implemented: revenium_signal_price=2.00 (float literal) with TRADINGAGENTS_SIGNAL_PRICE env override"
  - "Lazy import of AgenticOutcomeClient inside __init__ (not at module level) keeps module importable when SDK absent"
  - "Per-trace-id metadata (_job_meta dict) stored synchronously in create_trading_signal_job; read in emit_billing_event"
  - "validate_billing.py uses direct AgenticOutcomeClient (not emitter) to surface PASS/FAIL per check rather than swallowing"
metrics:
  duration: "20 minutes (estimated)"
  completed: "2026-06-28"
  tasks_completed: 2
  tasks_total: 2
  files_created: 3
  files_modified: 1
---

# Phase 04 Plan 02: Billing Config Keys + TradingSignalBillingEmitter Summary

Delivered the billing building blocks for the monetize pillar (BIL-01): three new DEFAULT_CONFIG keys with `_ENV_OVERRIDES` wiring, a fail-open `TradingSignalBillingEmitter` wrapping `AgenticOutcomeClient`, a keyless-gated `scripts/validate_billing.py` smoke for host de-risk, and a full keyless unit-test suite.

## What Was Built

### Task 1: Config keys + TradingSignalBillingEmitter

**`tradingagents/default_config.py`** — Added three new keys after `revenium_trace_type`:

- `"revenium_signal_price": 2.00` — float literal (required for `_coerce` to trigger on `TRADINGAGENTS_SIGNAL_PRICE` override)
- `"revenium_billing_api_key": os.getenv("REVENIUM_BILLING_API_KEY", "")` — `rev_sk_*` write-scope key
- `"revenium_profitstream_url": os.getenv("REVENIUM_PROFITSTREAM_BASE_URL", "https://api.revenium.io")`

Added three `_ENV_OVERRIDES` entries: `TRADINGAGENTS_SIGNAL_PRICE`, `REVENIUM_BILLING_API_KEY`, `REVENIUM_PROFITSTREAM_BASE_URL`.

**`tradingagents/revenium/billing.py`** — Full rewrite of the Phase 1 stub. `TradingSignalBillingEmitter` class with:

- `__init__`: lazy import of `AgenticOutcomeClient` / `AgenticOutcomeSettings`; sets `_client=None` on failure
- `from_config(cls, config)`: reads the three config keys; factory analog of `ReveniumCallbackHandler.from_config`
- `enabled` property: `bool(api_key) and _client is not None`
- `create_trading_signal_job(trace_id, ticker, trade_date)`: stores metadata synchronously; dispatches `create_job` on daemon thread; fail-open
- `emit_billing_event(trace_id, signal_price, reported_by="")`: reads stored metadata; dispatches `report_outcome` with `result=SUCCESS, outcomeType=CONVERTED, outcomeValue=signal_price`; fail-open

**`tests/test_billing_emitter.py`** — 9 keyless unit tests (all `@pytest.mark.unit`):
- Float default and env-override coercion (Pitfall 5)
- Disabled gate: `enabled is False` with empty key; no threads spawned
- Mocked client: `create_job` called with correct `agentic_job_id`; `report_outcome` payload shape validated (`outcomeValue`, `result`, `metadata`)
- Fail-open: both methods return `None` when the mock client raises

### Task 2: scripts/validate_billing.py keyless-gated live smoke

**`scripts/validate_billing.py`** — Modeled on `validate_controls.py`:

- `_run_checks` helper prints PASS/FAIL per check
- `main()`: argparse (`--ticker`, `--date`); `load_dotenv()`; keyless gate (exits 0, prints skip message when key absent); constructs `AgenticOutcomeClient` directly; calls `create_job + report_outcome`; prints resolved host and trace_id for dashboard confirmation
- Returns 0 on all checks pass, 1 on failure
- Never prints the api key or raw response body

**`tests/test_billing_emitter.py` (extended)** — Added `test_validate_billing_keyless_exits_zero` confirming `main()` returns 0 and prints the keyless-skip line when `REVENIUM_BILLING_API_KEY` is unset.

## Verification Results

| Check | Result |
|-------|--------|
| `pytest tests/test_billing_emitter.py -q` | 9 passed |
| `env -u REVENIUM_BILLING_API_KEY python scripts/validate_billing.py` | exits 0 |
| `ruff check tradingagents/revenium/billing.py tradingagents/default_config.py` | clean |
| `ruff check scripts/validate_billing.py` | clean |
| `DEFAULT_CONFIG["revenium_signal_price"]` is `float(2.00)` | verified |
| `pytest -m unit -q` (full suite) | 328 passed, 1 pre-existing deepseek failure |

Pre-existing failure: `test_temperature_config.py::TestTemperatureForwarding::test_temperature_reaches_client_when_set[deepseek-deepseek-chat]` — unrelated to this plan (deepseek provider temperature routing; was failing before this plan's changes).

## Deviations from Plan

None — plan executed exactly as written.

The `billing.py` stub class (`ReveniumBillingEmitter`) was replaced wholesale by `TradingSignalBillingEmitter`; this is the intended Phase 4 implementation, not a deviation.

## Security / Threat Coverage

| Threat ID | Mitigation Applied |
|-----------|-------------------|
| T-04-03 (info disclosure) | billing.py docstring states key-never-logged invariant; logger args are only symbolic (trace_id, ticker, signal_price, result codes). Verified by code review. |
| T-04-04 (DoS via blocking emit) | Both public methods dispatch on daemon threads; return immediately after thread.start(). Emitter is no-op when disabled. |

## Commits

| Task | Commit | Files |
|------|--------|-------|
| Task 1 | `f57f58b` | `tradingagents/default_config.py`, `tradingagents/revenium/billing.py`, `tests/test_billing_emitter.py` |
| Task 2 | `6cd534a` | `scripts/validate_billing.py`, `tests/test_billing_emitter.py` |

## Self-Check: PASSED

- `tradingagents/revenium/billing.py` — exists, contains `TradingSignalBillingEmitter`
- `scripts/validate_billing.py` — exists, contains `create_job`
- `tests/test_billing_emitter.py` — exists, 9 tests all passing
- Commits `f57f58b` and `6cd534a` — both verified in `git log`
