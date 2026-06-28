---
phase: 03-cost-controls
plan: "03"
subsystem: revenium-enforcement-ui
tags: [enforcement, halt-panel, stop_polling, budget-exceeded, cli, tdd, keyless, CTL-02, CTL-03, D-05, D-09]
dependency_graph:
  requires: [03-01-SUMMARY.md]
  provides: [_render_budget_halt_panel, BudgetExceededError catch in CLI, stop_polling teardown both paths, validate_controls.py]
  affects: [cli/main.py, tradingagents/graph/trading_graph.py, scripts/validate_controls.py, tests/test_revenium_enforcement.py]
tech_stack:
  added: []
  patterns: [TDD RED/GREEN for panel tests, Rich Panel+Table for halt display, try/except BudgetExceededError around Live block, finally stop_polling on all exit paths]
key_files:
  created: [scripts/validate_controls.py]
  modified:
    - cli/main.py
    - tradingagents/graph/trading_graph.py
    - tests/test_revenium_enforcement.py
decisions:
  - "BudgetExceededError caught AFTER the Live context exits — except clause runs after with Live exits cleanly on exception propagation (RESEARCH Architecture Patterns)"
  - "stop_polling() in both cli/main.py finally AND _run_graph finally — two independent execution paths require independent teardown"
  - "raise typer.Exit(code=1) from err in except handler — B904 compliance, non-zero exit, no fabricated decision (T-03-08)"
  - "Type annotations removed from _render_budget_halt_panel — BudgetExceededError and ReveniumCallbackHandler not at module level; repo convention prefers no annotation over string-annotated undefined names (F821)"
  - "validate_controls.py exits 0 on missing REVENIUM_CIRCUIT_BREAKER_ENABLED even if REVENIUM_METERING_API_KEY is set — both required for meaningful enforcement assertion (DMO-04)"
metrics:
  duration: "~11 minutes"
  completed: "2026-06-28T16:19:00Z"
  tasks_completed: 3
  files_modified: 4
---

# Phase 03 Plan 03: CLI Halt Panel + stop_polling Teardown + validate_controls.py Summary

**One-liner:** `_render_budget_halt_panel` added to cli/main.py catching `BudgetExceededError` with a Rich red Panel (rule name/spent/limit/per-agent tokens) and non-zero exit; `stop_polling()` wired in both CLI and propagate() finally blocks; `validate_controls.py` timing dry-run ships for demo de-risking.

## Objective

Complete the control-pillar vertical slice (D-05, D-09): catch the `BudgetExceededError` raised by Plan 01's gate, render the on-stage demo halt panel, and tear down the enforcement daemon on every exit path. Ship `validate_controls.py` for the timing dry-run that de-risks the live demo.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| RED  | Failing TestBudgetHaltPanel tests for _render_budget_halt_panel | 749fcff | tests/test_revenium_enforcement.py |
| 1    | CLI halt panel + BudgetExceededError catch + stop_polling in CLI (GREEN) | 52ba8d9 | cli/main.py, tests/test_revenium_enforcement.py |
| 2    | stop_polling() in _run_graph finally after end_run (propagate path) | 4681973 | tradingagents/graph/trading_graph.py |
| 3    | validate_controls.py timing dry-run script | 0f2517a | scripts/validate_controls.py |

## What Was Built

### Task 1 — CLI Halt Panel + Catch + Teardown

**`cli/main.py`:**

- Added `_render_budget_halt_panel(console, err, handler)` module-level helper (placed before `get_user_selections`):
  - Builds a `Table` of per-agent input/output token counts from `handler.agent_costs`
  - Builds a `Text` body with Rule / Spent / Limit / Resets at / Rule ID from `BudgetExceededError` fields
  - Prints a red `Panel` titled "Run Halted — Budget Limit Reached"
  - Prints dashboard reminder (Guardrails > Enforcement Events) and "non-zero status (no trading decision produced)" line
  - Never prints raw key values (T-03-01)
- Wrapped `with Live(layout, refresh_per_second=4):` streaming block in `try:` / `except BudgetExceededError as err:` / `finally:`
  - `except` clause: calls `_render_budget_halt_panel(console, err, revenium_handler)` then `raise typer.Exit(code=1) from err`
  - `finally` clause: calls `stop_polling()` unconditionally (safe no-op if never started)
- Added `from revenium_middleware._core import BudgetExceededError, stop_polling` inside `run_analysis` setup

**`tests/test_revenium_enforcement.py` — extended with `TestBudgetHaltPanel`:**

- `test_render_budget_halt_panel_renders_without_raising`: constructs `BudgetExceededError` directly, verifies no exception on render
- `test_render_budget_halt_panel_content_and_no_key_leakage`: captures `Console(record=True)` output, asserts rule_name/spent/limit/per-agent rows present, asserts no `rev_mk_`/`rev_sk_` substring (T-03-01)

### Task 2 — stop_polling() in _run_graph (propagate path)

**`tradingagents/graph/trading_graph.py`:**

- Added `from revenium_middleware._core import stop_polling` to module-level imports (ruff auto-fixed sort order to place it in the third-party block alongside `langgraph`)
- Added `stop_polling()` in the `_run_graph` `finally` block AFTER `self._revenium_handler.end_run()`, with comment noting the ordering constraint (state-clear before daemon-teardown)

### Task 3 — validate_controls.py Timing Dry-Run

**`scripts/validate_controls.py` (NEW):**

- Module docstring: live requirements and keyless-mode behavior
- Keyless gate: prints message and exits 0 when either `REVENIUM_METERING_API_KEY` or `REVENIUM_CIRCUIT_BREAKER_ENABLED` is absent (DMO-04)
- `_run_checks` helper copied verbatim from `validate_tracing.py`
- Timed `graph.propagate()` call inside `try/except BudgetExceededError` capturing halt exception and `elapsed_to_halt`
- Checks: halt fired, rule_name non-empty, current_value > 0, threshold > 0, resets_at non-empty, halted within 120s
- Dashboard reminder block (Guardrails > Enforcement Events): action=BLOCK, ruleName, isShadow=false (CTL-04), currentValue > threshold, elapsed seconds
- Masks metering key as `api_key[:12]...` (T-03-01)

## Verification

- `pytest tests/test_revenium_enforcement.py -q`: 9 passed (7 original + 2 new panel tests)
- `pytest -q` (full suite, keyless): 489 passed, 2 pre-existing failures (unrelated to this plan)
- `grep -n "except BudgetExceededError" cli/main.py`: line 1357, wraps stream loop, followed by `typer.Exit(code=1) from err`
- `grep -n "stop_polling" cli/main.py tradingagents/graph/trading_graph.py`: confirmed in both files
- `python scripts/validate_controls.py` (keyless): exits 0
- `ruff check cli/main.py tradingagents/graph/trading_graph.py scripts/validate_controls.py`: all clean

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Import sort order (I001) in cli/main.py**
- **Found during:** Task 1 ruff check
- **Issue:** Inline imports `from revenium_middleware._core import ...` and `from tradingagents.revenium.callback import ...` in wrong order; ruff I001.
- **Fix:** Applied `ruff check --fix` to auto-sort; swapped to third-party before first-party.
- **Files modified:** `cli/main.py`
- **Commit:** 52ba8d9

**2. [Rule 1 - Bug] Import sort order (I001) in trading_graph.py**
- **Found during:** Task 2 ruff check
- **Issue:** `from revenium_middleware._core import stop_polling` placed between existing import blocks; ruff I001.
- **Fix:** Applied `ruff check --fix` to auto-sort; placed in third-party block alongside `langgraph`.
- **Files modified:** `tradingagents/graph/trading_graph.py`
- **Commit:** 4681973

**3. [Rule 2 - Missing functionality] B904 exception chaining for typer.Exit**
- **Found during:** Task 1 ruff check
- **Issue:** `raise typer.Exit(code=1)` inside `except BudgetExceededError` triggers B904 (missing `from err`/`from None`).
- **Fix:** Changed to `raise typer.Exit(code=1) from err` for explicit exception chaining.
- **Files modified:** `cli/main.py`
- **Commit:** 52ba8d9

**4. [Rule 2 - Missing functionality] F821 on type annotations**
- **Found during:** Task 1 ruff check
- **Issue:** `err: "BudgetExceededError"` and `handler: "ReveniumCallbackHandler"` string annotations in `_render_budget_halt_panel` triggered F821 (names not imported at module level).
- **Fix:** Removed type annotations from the function signature. Module-level helpers that reference lazy-imported types use no annotation per repo convention (not every function in cli/main.py has type annotations).
- **Files modified:** `cli/main.py`
- **Commit:** 52ba8d9

## Threat Model Coverage

| Threat ID | Mitigation Applied |
|-----------|-------------------|
| T-03-01 (Info Disclosure: raw key in panel) | `_render_budget_halt_panel` uses only `err.rule_name`, `err.current_value`, `err.threshold`, `err.resets_at`, `err.rule_id` and `handler.agent_costs` — no key fields; `validate_controls.py` masks `api_key[:12]`; tests assert `rev_mk_`/`rev_sk_` absent from output |
| T-03-07 (Info Disclosure: rule+cost on stage) | Accepted per plan — rule name and cost are the demo moment |
| T-03-08 (Repudiation: fabricated decision after halt) | `_render_budget_halt_panel` contains no BUY/HOLD/SELL; except handler calls panel + `raise typer.Exit(code=1)` — no decision is ever printed |
| T-03-SC (Supply-chain) | Accepted — no new packages |

## Known Stubs

None. All three deliverables are fully wired:
- `_render_budget_halt_panel` renders real `BudgetExceededError` fields and real `agent_costs` data
- `stop_polling()` is unconditionally wired in both teardown paths
- `validate_controls.py` runs a real timed propagate() when keys are present

## Threat Flags

None. No new network endpoints, auth paths, file access patterns, or schema changes introduced. All changes are within existing trust boundaries (CLI → display, propagate() → finally, scripts → existing propagate() path).

## Self-Check: PASSED

- `cli/main.py` exists: FOUND (modified)
- `tradingagents/graph/trading_graph.py` exists: FOUND (modified)
- `scripts/validate_controls.py` exists: FOUND (created)
- `tests/test_revenium_enforcement.py` exists: FOUND (extended)
- Commit 749fcff (RED test): FOUND
- Commit 52ba8d9 (GREEN feat): FOUND
- Commit 4681973 (feat propagate path): FOUND
- Commit 0f2517a (feat validate_controls): FOUND
