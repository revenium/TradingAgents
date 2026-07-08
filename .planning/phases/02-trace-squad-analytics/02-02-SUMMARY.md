---
phase: 02-trace-squad-analytics
plan: 02
status: blocked
requirements: [TRC-01, TRC-02, TRC-03]
tasks_complete: 1
tasks_total: 2
self_check: FAILED
gap_ref: 02-VERIFICATION.md#GAP-02-01
---

# Plan 02-02 Summary — Live Tracing Validation

**Outcome: BLOCKED.** Task 1 (build the live validator) completed and is committed. Task 2 (live confirmation against the Revenium account) executed and **failed**, surfacing a real instrumentation bug in the 02-01 trace plumbing. This is the expected, valuable result of a live integration gate — the validator did its job. The phase goal (TRC-01/02/03 live) is **not** met. See `02-VERIFICATION.md` for the full root cause and fix plan.

## Tasks

| Task | Name | Status | Commit |
|------|------|--------|--------|
| 1 | Build `scripts/validate_tracing.py` (live validator) | ✅ Complete | `7fbfb23` |
| 2 | Live verification — record span count N and TRC-03 path | ❌ Blocked (live checks failed) | — |

## Task 1 — what was delivered

`scripts/validate_tracing.py` (277 lines): runs one full `propagate()` with `max_debate_rounds=2`, monkeypatch-captures every metered payload, flushes `graph._revenium_handler._threads`, prints `trace_id=` / `span_count=`, and asserts the single-trace + parent-chain + enrichment-field invariants. Keyless-safe (prints a skip message and exits 0 with no key). Verifications: `ast.parse` ok, `ruff check` clean, `--help` exit 0, keyless run exit 0.

## Task 2 — live run result (BLOCKED)

Command: `python scripts/validate_tracing.py --ticker NVDA --date 2026-06-27` (OpenAI both tiers — ANTHROPIC_API_KEY is the known-invalid placeholder; consistent with the de-scoped single-provider decision). Full log: `02-LIVE-RUN.log`.

`propagate()` completed and captured **20 spans**, but **4/10 checks failed**:

- ❌ `trace_id` empty on first span and **not shared** across the 20 spans → no single trace grouping (TRC-01).
- ❌ `parent_transaction_id` missing on all 19 post-first spans → flat dependency tree (TRC-02).
- ❌ `trace_name` missing live.
- ✅ `trace_type`, `transaction_name`, `agent`, `span_count>=12` all present/correct.

## Root cause (reproduced keyless)

LangGraph runs each node inside its own `copy_context().run(...)`. The `current_parent_transaction_id.set()` performed in one node's `on_llm_end` is invisible to the next node's `on_chat_model_start` (different context copy). The Phase 2 research assumed "synchronous main thread ⇒ contextvar visible to next node," which is false across node boundaries. `trace_id`/`trace_name` are inherited by node copies (set before `invoke()`) but were still empty live, implicating the real `ChatOpenAI` `with_structured_output` path. Full detail + fix in `02-VERIFICATION.md`.

## Next step

Gap closure: `/gsd-plan-phase 2 --gaps` → fix `callback.py`/`context.py`/`trading_graph.py` to hold run-scoped trace state on the shared handler instance → re-run this validator live. Re-running 02-02 alone will not help until the 02-01 instrumentation is fixed.
