---
phase: 02-trace-squad-analytics
plan: "01"
subsystem: revenium-tracing
tags: [tracing, parent-chain, contextvar, metering, tdd, keyless]
dependency_graph:
  requires: [01-03-SUMMARY.md]
  provides: [parent_transaction_id chain, trace_name/trace_type/transaction_name payload fields]
  affects: [tradingagents/revenium/callback.py, tradingagents/revenium/context.py]
tech_stack:
  added: []
  patterns: [ContextVar token-based set/reset, synchronous-first before background thread, conditional payload field inclusion]
key_files:
  created: [tests/test_revenium_tracing.py]
  modified:
    - tradingagents/revenium/context.py
    - tradingagents/default_config.py
    - tradingagents/revenium/callback.py
decisions:
  - "trace_name truncated to 200 chars (T-02-01 threat mitigation; ticker already path-sanitized upstream)"
  - "current_parent_transaction_id.set() synchronous on main thread before threading.Thread.start() — contextvar writes in threads are invisible to main thread context"
  - "parent_transaction_id omitted entirely (not sent as empty string) for first call of each run — matches Revenium dependency tree expectation"
metrics:
  duration: "~9 minutes"
  completed: "2026-06-28T01:06:15Z"
  tasks_completed: 3
  files_modified: 4
---

# Phase 02 Plan 01: Parent-Chain Tracing and Payload Enrichment Summary

**One-liner:** Parent-transaction-ID chain + trace_name/trace_type/transaction_name payload fields wired into the Revenium callback handler via ContextVar machinery, proven by 8 keyless unit tests.

## Objective

Thread parent-transaction IDs and trace-enrichment fields through the existing Phase 1 Revenium metering path so a propagate() run emits payloads that Revenium can render as a single named trace with a per-agent dependency tree — all provable without a live Revenium key.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Add current_parent_transaction_id ContextVar and revenium_trace_type config key | 87c7f36 | tradingagents/revenium/context.py, tradingagents/default_config.py |
| 2 | Thread parent-tid and add trace enrichment fields in callback handler | 2c860de | tradingagents/revenium/callback.py |
| 3 | Keyless unit suite proving parent chain, enrichment fields, and per-run reset | ab0d1c1 | tests/test_revenium_tracing.py |

## What Was Built

### Task 1 — ContextVar + Config Key

`tradingagents/revenium/context.py`:
- Added `current_parent_transaction_id: contextvars.ContextVar[str]` (internal name `"revenium_parent_transaction_id"`, `default=""`)
- Updated module docstring to enumerate all four ContextVars
- `revenium_run_context`: added `token_parent = current_parent_transaction_id.set("")` on entry and `current_parent_transaction_id.reset(token_parent)` in the finally block — symmetric with the existing trace_id/run_meta pattern

`tradingagents/default_config.py`:
- Added `"REVENIUM_TRACE_TYPE": "revenium_trace_type"` to `_ENV_OVERRIDES`
- Added `"revenium_trace_type": os.getenv("REVENIUM_TRACE_TYPE", "trading-run")` to `DEFAULT_CONFIG` after `revenium_task_type_map`

### Task 2 — Callback Enrichment

`tradingagents/revenium/callback.py`:
- Extended context import to include `current_parent_transaction_id` and `current_run_meta` (combined import block)
- Added `trace_type: str = "trading-run"` parameter to `__init__`, stored as `self._trace_type`
- `from_config` reads `config.get("revenium_trace_type", "trading-run")` and passes to constructor
- `on_chat_model_start`: added `"parent_tid": current_parent_transaction_id.get()` to `_call_state[run_id]` dict (captured on main thread before any transaction_id is generated)
- `on_llm_end`:
  - Added `parent_tid: str = call_state.get("parent_tid", "")` after state retrieval
  - Added `run_meta` read + `trace_name = f"{ticker}-{trade_date_str}"[:200] if ticker else ""`
  - Extracted `transaction_id: str = str(uuid.uuid4())` as local variable before payload dict
  - Added `"transaction_name": agent` to payload dict (always present)
  - Added conditional guards: `if parent_tid:` → `payload["parent_transaction_id"]`; `if trace_name:` → `payload["trace_name"]`; `if self._trace_type:` → `payload["trace_type"]`
  - Added `current_parent_transaction_id.set(transaction_id)` synchronously on main thread BEFORE `threading.Thread(...).start()` — critical ordering constraint

### Task 3 — Keyless Unit Suite

`tests/test_revenium_tracing.py` (303 lines, 8 tests):
- `autouse _reset_contextvars` fixture covering all four ContextVars including `current_parent_transaction_id`
- `handler_with_mock_client` fixture with `meter_ai_completion.side_effect = lambda p: captured.append(p)` and `revenium_trace_type` in config
- `TestParentTransactionChain`: first call omits `parent_transaction_id`; 3-call chain links transaction IDs correctly
- `TestTraceEnrichmentFields`: `transaction_name == agent` for each agent; `trace_name == "{ticker}-{date}"` and `trace_type == "trading-run"` inside context; `trace_name` absent outside context
- `TestParentTransactionIdReset`: `""` before context; non-empty after first on_llm_end; `""` after context exit; `""` after exception

## Verification Results

```
pytest tests/test_revenium_tracing.py -v     → 8 passed
pytest tests/test_revenium_metering.py tests/test_revenium_tool_metering.py -q  → 29 passed (no regressions)
grep -v '^#' callback.py | grep -c "current_parent_transaction_id.set"  → 1 (before thread start)
```

## Deviations from Plan

None — plan executed exactly as written.

Pre-existing ruff lint issues (F401, UP035, B039 in `callback.py`, `context.py`, `meter_tool.py`) were already present in the main branch before this plan; out of scope per CLAUDE.md scope boundary.

## Known Stubs

None. All fields are wired end-to-end through the callback handler and provable via the keyless suite.

## Threat Flags

No new security surface introduced. All fields (transaction_name, trace_name, trace_type) are symbolic values as documented in the plan's threat model. trace_name is capped at 200 characters (T-02-01 mitigation implemented).

## Requirements Satisfied

- TRC-01 (partial): trace_name, trace_type, transaction_name payload fields delivered (live span-count confirmation is Plan 02-02)
- TRC-02: parent_transaction_id chain wired — dependency tree can be constructed by Revenium from these payloads
- TRC-03 (partial): parent chain in place — circular-pattern detection can fire on sequential call chains (live confirmation is Plan 02-02)

## Self-Check

Files verified present:
- [x] tradingagents/revenium/context.py — contains `current_parent_transaction_id`
- [x] tradingagents/default_config.py — contains `revenium_trace_type`
- [x] tradingagents/revenium/callback.py — contains `current_parent_transaction_id.set`, `transaction_name`, conditional payload fields
- [x] tests/test_revenium_tracing.py — 8 unit tests, all passing

Commits verified:
- [x] 87c7f36 — feat(02-01): add current_parent_transaction_id ContextVar and revenium_trace_type config key
- [x] 2c860de — feat(02-01): thread parent-tid and trace enrichment fields through callback handler
- [x] ab0d1c1 — test(02-01): keyless unit suite proving parent chain, enrichment fields, and per-run reset

## Self-Check: PASSED
