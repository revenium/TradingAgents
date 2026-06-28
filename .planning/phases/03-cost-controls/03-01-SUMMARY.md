---
phase: 03-cost-controls
plan: "01"
subsystem: revenium-enforcement
tags: [enforcement, cost-controls, circuit-breaker, tdd, keyless, BudgetExceededError]
dependency_graph:
  requires: [01-02-SUMMARY.md, 02-03-SUMMARY.md]
  provides: [check_enforcement pre-call gate in on_chat_model_start, BudgetExceededError propagation path]
  affects: [tradingagents/revenium/callback.py, tests/test_revenium_enforcement.py]
tech_stack:
  added: [revenium_middleware._core.check_enforcement, revenium_middleware._core.BudgetExceededError]
  patterns: [pre-call enforcement gate outside fail-open try/except (D-03), keyless cache-seed mock pattern (_seed_rules), importlib.reload module isolation]
key_files:
  created: [tests/test_revenium_enforcement.py]
  modified:
    - tradingagents/revenium/callback.py
decisions:
  - "Enforcement gate placed BEFORE the fail-open try/except in on_chat_model_start — D-03 deliberate exception to the fail-open convention; BudgetExceededError must escape to _run_graph / CLI"
  - "subscriber_credential (PII email) passed to check_enforcement but never logged — T-03-02 mitigation"
  - "REVENIUM_CACHE_DIR added to _reset_enforcement delenv list — prevents _load_cache_from_disk from reading a stale disk file in test isolation"
metrics:
  duration: "~10 minutes"
  completed: "2026-06-28T16:00:49Z"
  tasks_completed: 2
  files_modified: 2
---

# Phase 03 Plan 01: Enforcement Gate in ReveniumCallbackHandler Summary

**One-liner:** `check_enforcement()` wired as a pre-call gate in `on_chat_model_start` outside the fail-open `except` block so a breached Revenium enforce-mode rule raises `BudgetExceededError` and halts the run, proven by 7 keyless unit tests covering the engine and handler propagation paths.

## Objective

Deliver CTL-01 (the enforcement gate raises in real time) and the handler-side half of CTL-02 (the error propagates out) by inserting `check_enforcement()` into `ReveniumCallbackHandler.on_chat_model_start` before the fail-open `try/except`, so a breached enforce-mode cost rule stops the run at the point of the next LLM call.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Keyless enforcement-gate test scaffold (RED) | 87dfa6c | tests/test_revenium_enforcement.py |
| 2 | Wire check_enforcement() gate into on_chat_model_start (GREEN) | c4ad96c | tradingagents/revenium/callback.py |

## What Was Built

### Task 1 — RED Phase: Keyless Test Scaffold

`tests/test_revenium_enforcement.py`:

- `_reset_enforcement` autouse fixture: delenvs all CB env vars, calls `importlib.reload(enforcement)` to reset module-global cache state, calls `stop_polling()` on cleanup.
- `_seed_rules` helper: monkeypatches `enforcement._cached_rules`, `_cache_timestamp=inf`, `_cache_initialized`, and stubs `_ensure_poller_running`/`_fetch_rules` to no-ops — no live keys required.
- `TestEnforcementEngine` (4 tests, all PASS in RED): direct engine tests for breach-raises, bypass-no-op, shadow-mode-no-op, CB-disabled-no-op.
- `TestCallbackHandlerEnforcementGate` (3 tests): `test_budget_exceeded_propagates_from_on_chat_model_start` (RED FAIL — DID NOT RAISE), plus 2 that PASS in RED (no-rule and bypass cases).

### Task 2 — GREEN Phase: Enforcement Gate Wiring

`tradingagents/revenium/callback.py`:

- Added import: `from revenium_middleware._core import BudgetExceededError, check_enforcement  # noqa: F401` in the third-party import block alongside `langchain_core`.
- Inserted `check_enforcement({"subscriber_credential": self._attribution.get("subscriber_id", "")})` BETWEEN the `if not self.enabled: return` guard and the `try:` block in `on_chat_model_start`.
- Updated method docstring to document the CTL-01 enforcement gate and the D-03 deliberate exception to the fail-open convention.
- All 7 tests now pass (GREEN). Full keyless suite: 487 passed, 2 pre-existing failures (unrelated).

## Verification

- `pytest tests/test_revenium_enforcement.py -q`: 7 passed
- `grep -n "check_enforcement(" tradingagents/revenium/callback.py`: gate at line 317, before `try:` at line 322
- `ruff check tradingagents/revenium/callback.py`: only pre-existing F401 (`task_type_for_node` unused — not introduced by this plan)
- Full keyless suite: 487 passed, 2 pre-existing failures, no new failures

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Import sort order for revenium_middleware import**
- **Found during:** Task 2 ruff check
- **Issue:** Adding `from revenium_middleware._core import ...` on its own line between `langchain_core` and `tradingagents.*` created an `I001` import-sort error.
- **Fix:** Moved the import into the same third-party block as `langchain_core` (no blank line separator between them).
- **Files modified:** `tradingagents/revenium/callback.py`
- **Commit:** c4ad96c

None - all other plan steps executed exactly as specified.

## Threat Model Coverage

| Threat ID | Mitigation Applied |
|-----------|-------------------|
| T-03-02 (Info Disclosure: subscriber_credential PII) | `subscriber_credential` passed to `check_enforcement` only; never logged in callback.py — code comment at gate call site |
| T-03-04 (DoS: fail-open swallowing the gate) | Gate placed OUTSIDE the `try` block; `test_budget_exceeded_propagates_from_on_chat_model_start` guards against regression |

## Known Stubs

None. The enforcement gate is fully wired; no placeholder code.

## Self-Check: PASSED

- `tests/test_revenium_enforcement.py` exists: FOUND
- `tradingagents/revenium/callback.py` modified: FOUND (check_enforcement at line 317)
- Commit 87dfa6c (RED): FOUND
- Commit c4ad96c (GREEN): FOUND
