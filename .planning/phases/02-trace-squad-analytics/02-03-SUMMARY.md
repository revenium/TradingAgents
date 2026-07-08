---
phase: 02-trace-squad-analytics
plan: "03"
subsystem: tracing
tags: [langgraph, contextvars, revenium, callback-handler, parent-chain, trace-id, tdd]

# Dependency graph
requires:
  - phase: 02-trace-squad-analytics/02-01
    provides: Parent-transaction threading and trace enrichment fields (trace_name/trace_type/transaction_name) through Phase 1 callback path
  - phase: 02-trace-squad-analytics/02-02
    provides: Live validate_tracing.py gate + 02-VERIFICATION.md root-cause analysis of GAP-02-01
provides:
  - Handler-instance run-scoped trace state (begin_run/end_run/_last_transaction_id) that survives LangGraph per-node copy_context().run isolation
  - Contextvar fallback path retained for direct non-graph callers (validate_metering.py)
  - Keyless cross-node regression test locking the fix against future regressions
  - Live evidence of single shared trace_id (TRC-01), parent_transaction_id chain (TRC-02), and debate-loop hotspot (TRC-03)
affects: [phase-03-cost-controls, phase-05-demo-hardening]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Handler-instance run-scoped state pattern: shared mutable state on the single long-lived handler instance instead of per-node contextvars for data that must survive LangGraph copy_context().run isolation"
    - "begin_run/end_run lifecycle: trading_graph._run_graph calls begin_run at entry and end_run in a finally inside revenium_run_context so trace state never leaks across runs"
    - "Contextvar as fallback: contextvars remain for non-graph direct callers (validate_metering.py path) while handler-instance state is the primary carrier for graph-executed runs"
    - "Linearisation tradeoff: shared _last_transaction_id serializes parent chain across parallel analyst fan-out into a sequential dependency view; still exposes bull/bear loopback for circular-pattern detection"

key-files:
  created:
    - tests/test_revenium_tracing.py (TestCrossNodeContextIsolation class: 2 new cross-node tests using copy_context().run)
  modified:
    - tradingagents/revenium/callback.py (begin_run/end_run methods; _last_transaction_id/_run_trace_id/_run_meta instance state; on_chat_model_start reads self._last_transaction_id; on_llm_end advances self._last_transaction_id and drops contextvar write)
    - tradingagents/revenium/context.py (docstring updated; ContextVars retained as fallback)
    - tradingagents/graph/trading_graph.py (_run_graph calls begin_run/end_run in try/finally inside revenium_run_context)

key-decisions:
  - "GAP-02-01 fix: run-scoped trace state (trace_id + parent chain) moved from per-node contextvars to shared handler-instance state (begin_run/_last_transaction_id/end_run). Contextvar fallback retained for direct non-graph callers. Linearisation tradeoff accepted per 02-VERIFICATION.md."
  - "begin_run/end_run called in trading_graph._run_graph inside try/finally within revenium_run_context block; end_run always fires even if graph.invoke raises (fail-open posture preserved)."
  - "Live validation temporarily routed deep-think LLM to OpenAI gpt-4.1-mini (no ANTHROPIC_API_KEY in operator .env); default_config.py change was reverted immediately after the run — multi-provider default unchanged in git."

patterns-established:
  - "Handler-instance run-scoped state: for data that must persist across LangGraph per-node copy_context().run boundaries, own it on the single shared handler instance, not in ContextVars"
  - "begin_run/end_run lifecycle protocol: always call in try/finally to prevent trace state leaking between runs"
  - "Contextvar fallback retention: keep ContextVars in context.py as the documented non-graph fallback; do not delete them when promoting to instance state"

requirements-completed: [TRC-01, TRC-02, TRC-03]

# Metrics
duration: ~180min (two sessions: Tasks 1-2 prior session; live verify + closeout current session)
completed: 2026-06-28
---

# Phase 02 Plan 03: Cross-Node Trace Isolation Fix Summary

**Run-scoped trace_id and parent_transaction_id chain moved from per-node ContextVars to shared ReveniumCallbackHandler instance state (begin_run/_last_transaction_id/end_run), closing GAP-02-01 and proving TRC-01/TRC-02/TRC-03 live with trace_id 3f88fe43-ef6c-4ec3-b1ee-8a89b3b4dd79, 19 spans, 10/10 checks.**

## Performance

- **Duration:** ~180 min (split across two sessions)
- **Started:** 2026-06-28T00:00:00Z (approximate, Tasks 1-2)
- **Completed:** 2026-06-28T05:03:24Z
- **Tasks:** 3 (2 auto/TDD + 1 human-verify checkpoint)
- **Files modified:** 4 (callback.py, context.py, trading_graph.py, test_revenium_tracing.py)

## Accomplishments

- Diagnosed and fixed GAP-02-01: LangGraph's per-node `copy_context().run()` isolation was silently discarding `current_parent_transaction_id.set()` calls between nodes, breaking the parent chain and making every span appear as an independent root in the Revenium trace view
- Moved run-scoped trace state (`trace_id`, `run_meta`, `last_transaction_id`) onto the single shared `ReveniumCallbackHandler` instance via `begin_run()`/`end_run()` lifecycle methods; `_last_transaction_id` is advanced under `self._lock` in `on_llm_end` so every subsequent span carries the prior span's transaction ID as its parent
- Added keyless `TestCrossNodeContextIsolation` regression tests (2 tests, `copy_context().run` per node) confirming the fix guards the cross-node boundary without any live keys
- Live re-validation passed: `scripts/validate_tracing.py --ticker NVDA --date 2026-06-27` exited 0 with `trace_id=3f88fe43-ef6c-4ec3-b1ee-8a89b3b4dd79`, `span_count=19`, 10/10 local checks PASS; Revenium dashboard confirmed single grouped trace + per-agent Gantt (TRC-01), parent-arrow dependency tree (TRC-02), and debate-loop hotspot visible via `task_type=research_debate` (TRC-03)

## Task Commits

Each task was committed atomically:

1. **Task 1: Add keyless cross-node regression test (RED)** - `7a4476a` (test)
2. **Task 2: Move run-scoped trace state onto handler instance (GREEN)** - `826084f` (feat)
3. **Task 3: Live re-validation against Revenium dashboard** - no source commit (human-verify checkpoint; gate satisfied by operator approval)

## Files Created/Modified

- `tests/test_revenium_tracing.py` - Added `TestCrossNodeContextIsolation` class with 2 cross-node tests; updated `TestParentTransactionIdReset.test_parent_tid_resets_to_empty_after_context` to remove the now-invalid contextvar-write assertion after `on_llm_end`; 10 total tests (8 existing + 2 new)
- `tradingagents/revenium/callback.py` - Added `self._last_transaction_id`, `self._run_trace_id`, `self._run_meta` instance state in `__init__`; added `begin_run(trace_id, ticker, trade_date)` and `end_run()` fail-open methods; `on_chat_model_start` reads `self._last_transaction_id` under `self._lock`; `on_llm_end` resolves `trace_id`/`run_meta` from instance state (contextvar fallback), advances `self._last_transaction_id`, removes the `current_parent_transaction_id.set()` contextvar write
- `tradingagents/revenium/context.py` - Docstring updated to note handler-instance state is now the primary parent-chain carrier; all ContextVars and `revenium_run_context` retained unchanged as fallback for direct non-graph callers
- `tradingagents/graph/trading_graph.py` - `_run_graph` calls `self._revenium_handler.begin_run(_trace_id, company_name, str(trade_date))` at entry and `self._revenium_handler.end_run()` in a `finally` inside the `revenium_run_context` block

## Decisions Made

- **Handler-instance state over ContextVars:** ContextVars are per-context copies in LangGraph's per-node `copy_context().run()` isolation model, making cross-node state writes invisible to subsequent nodes. Instance state on the single shared handler is the only mechanism that survives this isolation without framework changes.
- **Linearisation tradeoff accepted:** `self._last_transaction_id` (a single advancing pointer under a lock) serialises the parent chain across potentially-parallel analyst fan-out into a sequential dependency view. This is accepted per `02-VERIFICATION.md` and still exposes the bull/bear/bull repetition pattern needed for circular-pattern detection in Revenium.
- **Contextvar fallback retained:** `current_parent_transaction_id` and all other ContextVars in `context.py` are NOT removed. `validate_metering.py` and other direct (non-graph) callers rely on the `revenium_run_context` + contextvar path. The handler-instance path is primary for graph runs; the contextvar path remains the documented fallback.
- **begin_run/end_run fail-open:** Both methods wrap their body in `except Exception` and are no-ops when the handler is disabled, preserving the existing fail-open posture. `end_run()` runs in a `finally` so trace state never leaks across runs even when `graph.invoke` raises.

## Deviations from Plan

### Environment Gap During Live Validation

**1. [Operator environment] Temporary OpenAI deep-think routing for live validation run**
- **Found during:** Task 3 (live re-validation)
- **Issue:** The operator's `.env` had no `ANTHROPIC_API_KEY`. The production default config uses Anthropic (`claude-sonnet-4-6`) for the deep-think role. The first live attempt with the default config produced 13 spans and 9/10 local checks PASS but FAILED the "propagate completed without exception" check due to the missing Anthropic key (an environment gap, not a defect in the fix). TRC-01 and TRC-02 invariants passed on that first run.
- **Fix:** Operator made a temporary, uncommitted edit to `default_config.py` to route the deep-think role to `gpt-4.1-mini` (OpenAI) for the single validation run. This edit was reverted immediately after the run. The production multi-provider default (deep-think=Anthropic, quick-think=OpenAI) is unchanged in git.
- **Impact:** The successful live run used OpenAI for all agent roles. The TRC-01/TRC-02/TRC-03 fixes are provider-agnostic (handler-instance state, not model-specific). The single-trace + parent-chain invariants hold regardless of provider.
- **Files modified:** None committed (temporary, reverted)

---

**Total deviations:** 1 (operator environment gap, resolved via temporary provider override; no source code changes)
**Impact on plan:** The fix itself is complete and correct. Live validation was successful on the second attempt. The environment gap (missing ANTHROPIC_API_KEY) is a pre-demo prerequisite already noted in STATE.md blockers.

## Issues Encountered

- **Cross-node contextvar isolation:** The root cause (LangGraph `copy_context().run()` per node) was already documented in `02-VERIFICATION.md` before this plan started; no additional investigation was needed. The fix was straightforward once the mechanism was confirmed keyless via the RED test.
- **`TestParentTransactionIdReset` assertion update:** The existing test asserted `current_parent_transaction_id.get() != ""` immediately after `on_llm_end` — an assertion that became invalid once the contextvar write was removed. This was identified as a required update in the plan and handled in Task 2 without any scope ambiguity.

## Known Stubs

None. All instrumentation is fully wired; no placeholder values or TODO stubs in the files modified by this plan.

## Threat Flags

No new security-relevant surfaces introduced. This plan modifies only internal handler state management (no new network endpoints, no new auth paths, no new file access). The metering payload content (symbolic identifiers only, no secrets or prompt bodies) is unchanged. The existing D-06 invariant (no api_key or prompt content in logs/payloads) was verified in code review.

## Next Phase Readiness

- **Phase 02 complete:** GAP-02-01 is closed; TRC-01, TRC-02, TRC-03 all confirmed live. Phase 2 success criteria are fully met.
- **Phase 03 (Cost Controls) can proceed:** The parent-chain dependency tree in Revenium is now accurate; the enforcement event triggered by CTL-01/CTL-02 will appear correctly attributed in the trace view.
- **Pre-demo:** Operator must have `ANTHROPIC_API_KEY` set in `.env` before any demo run that uses the default multi-provider config (deep-think=Anthropic). This is an environment prerequisite, not a code issue.
- **No blockers for Phase 3.**

---
*Phase: 02-trace-squad-analytics*
*Completed: 2026-06-28*
