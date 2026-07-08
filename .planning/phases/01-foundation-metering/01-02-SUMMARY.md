---
phase: 01-foundation-metering
plan: "02"
subsystem: infra
tags: [revenium, langchain, callback-handler, contextvars, metering, anthropic, openai, tdd]

# Dependency graph
requires:
  - phase: 01-foundation-metering/01-01
    provides: "revenium-python-sdk[langchain] pinned; all revenium_* config keys; attribution_from_config() helper; live Revenium hierarchy (Org DyGMJl, Product DEnNNv, Subscriber l3Pwo5)"
provides:
  - "tradingagents/revenium/context.py — trace_id / agent_name / run_meta contextvars + revenium_run_context manager"
  - "tradingagents/revenium/client.py — fail-open ReveniumClient (lazy SDK import; swallows all exceptions; enabled=False when api_key empty)"
  - "tradingagents/revenium/callback.py — ReveniumCallbackHandler(BaseCallbackHandler), from_config classmethod, one event per on_llm_end, fire-and-forget daemon thread, full attribution"
  - "tradingagents/revenium/billing.py — ReveniumBillingEmitter Phase 4 stub (no-op)"
  - "tradingagents/graph/trading_graph.py — single handler wired in __init__ with dedup guard; _run_graph wrapped in revenium_run_context"
  - "scripts/validate_metering.py — live one-event assertion script with --provider and --model flags"
  - "tests/test_revenium_metering.py — 19 mocked unit tests; pass without live API keys"
  - "FND-04 satisfied: exactly one Revenium event per LLM call, non-zero tokens, attributed (not UNCLASSIFIED), proven both mocked and live"
  - "MTR-01 partial: agent/trace_id/task_type/provider+model carried on every event"
  - "MTR-02 partial: organizationName/productName/subscriber.id carried on every event"
affects:
  - "01-03-PLAN.md (per-agent contextvars, @meter_tool, CLI wiring depend on this callback + context machinery)"
  - "Phase 4 (billing.py ReveniumBillingEmitter stub to be filled in)"
  - "Phase 5 (validate_metering.py doubles as pre-demo sanity check)"

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Contextvars (not threading.local) carry trace_id / agent_name / run_meta across the synchronous LangGraph call tree — context.py is the single producer, callback.py the consumer"
    - "Fail-open client: any exception from the metering SDK is swallowed with noqa: BLE001 annotation; warning logs symbolic name only (never key, never prompts)"
    - "Fire-and-forget: on_llm_end dispatches meter_ai_completion on a background daemon thread — never blocks the next LangGraph node"
    - "Single-handler dedup guard in trading_graph.py: internally-built ReveniumCallbackHandler is only appended when no enabled handler already present in the caller-supplied callbacks list"
    - "ReveniumClient is the only module importing the revenium-metering SDK — lazy import at construction time, clean import with no key set"

key-files:
  created:
    - tradingagents/revenium/context.py
    - tradingagents/revenium/client.py
    - tradingagents/revenium/callback.py
    - tradingagents/revenium/billing.py
    - scripts/validate_metering.py
    - tests/test_revenium_metering.py
  modified:
    - tradingagents/revenium/__init__.py
    - tradingagents/graph/trading_graph.py

key-decisions:
  - "Callback handler path over OTLP: non-streaming LangGraph runs let on_llm_end capture all token data; OTLP not used to prevent double-counting (exactly one metering path)"
  - "Fire-and-forget on daemon thread: meter_ai_completion called in background thread so Revenium latency never blocks graph progression"
  - "Dedup guard at TradingAgentsGraph.__init__: only one enabled ReveniumCallbackHandler appended regardless of what caller passes — critical for Plan 01-03 CLI wiring"
  - "validate_metering.py --provider + --model flags: script resolves a consistent provider/model pair from config to avoid 401s when OpenAI path is used"
  - "Anthropic key 401 path: live validation used openai/gpt-4.1-mini path because ANTHROPIC_API_KEY was invalid; Plan 01-03 needs a valid Anthropic key for the two-provider MTR-04 story"

patterns-established:
  - "context.py pattern: three contextvars (current_trace_id, current_agent_name, current_run_meta) + revenium_run_context manager; set at graph level, read in callback"
  - "Callback test pattern: patch meter_ai_completion, drive on_chat_model_start + on_llm_end, join background threads, assert call_count == on_llm_end_count (1:1 invariant)"

requirements-completed: [FND-04, MTR-01, MTR-02]

# Metrics
duration: 120min
completed: 2026-06-27
---

# Phase 01 Plan 02: Thin End-to-End Metering Slice Summary

**Context machinery + fail-open ReveniumCallbackHandler wired as the single handler into TradingAgentsGraph, proven with trace_id 5fb9569b-a7d5-4b61-87d5-58da2e8d8b8b: exactly one attributed event per OpenAI LLM call visible in the Revenium dashboard (Org Revenium-Research-Desk, subscriber john.demic+trading@revenium.io, 10/10 assertion checks passed).**

## Performance

- **Duration:** ~120 min
- **Started:** 2026-06-27 (post Plan 01-01 checkpoint approval)
- **Completed:** 2026-06-27
- **Tasks:** 5/5 (Tasks 1-4 auto; Task 5 checkpoint:human-verify — APPROVED)
- **Files modified:** 8

## Accomplishments

- FND-04: Single-call validation script (`scripts/validate_metering.py`) confirmed exactly one Revenium event per LLM call with non-zero input/output token counts, subscriber `john.demic+trading@revenium.io`, org `Revenium-Research-Desk`, product `trading-signal` — not UNCLASSIFIED. Both mocked tests (19 passing, no live key) and live assertion (10/10 checks) confirm the invariant.
- MTR-01/MTR-02 partial: every metered event carries `agent`, `traceId`, `taskType`, `provider`, `model`, `organizationName`, `productName`, and `subscriber.id` — full attribution from construction time through the callback chain.
- TradingAgentsGraph integration: single `ReveniumCallbackHandler` instance built in `__init__`, appended to callbacks only when enabled, with dedup guard for caller-supplied handlers; `_run_graph` body wrapped in `revenium_run_context` so every agent call carries the same trace UUID.
- Fail-open and no-op proven: `enabled=False` when `REVENIUM_METERING_API_KEY` absent; `on_llm_end` makes zero client calls and does not raise; backend exceptions swallowed without halting the trading run.

## Task Commits

Each task was committed atomically:

1. **Task 1: Context machinery + fail-open Revenium HTTP client (TDD RED)** - `d584909` (test)
2. **Task 1: Context machinery + fail-open Revenium HTTP client (TDD GREEN)** - `7382713` (feat)
3. **Task 2: ReveniumCallbackHandler — one attributed event per LLM call** - `830e260` (feat)
4. **Task 3: Wire single ReveniumCallbackHandler into TradingAgentsGraph + billing stub** - `2cf4837` (feat)
5. **Task 4: Live validation script + complete mocked test suite (FND-04)** - `bd0599c` (feat)
6. **Task 5: Post-checkpoint fix — pair model with provider in validate_metering** - `8f5f728` (fix)

**Plan metadata:** (docs commit — `commit_docs: false` in .planning/config.json; .planning/ changes tracked in working tree, not committed to git history)

## Files Created/Modified

- `tradingagents/revenium/context.py` - Three contextvars (`current_trace_id`, `current_agent_name`, `current_run_meta`) + `revenium_run_context` context manager; sets a uuid4 trace_id for the graph run duration
- `tradingagents/revenium/client.py` - `ReveniumClient` class with lazy SDK import; `meter_ai_completion(payload)` swallows all exceptions (fail-open, noqa BLE001); `enabled` property false when api_key empty
- `tradingagents/revenium/callback.py` - `ReveniumCallbackHandler(BaseCallbackHandler)` with `from_config` classmethod; captures provider/model in `on_chat_model_start`; fires exactly one event per `on_llm_end` fire-and-forget on a background thread; `agent_costs` accumulator for Phase 4 CLI panel
- `tradingagents/revenium/billing.py` - `ReveniumBillingEmitter` Phase 4 stub; `emit_signal_unit()` is a no-op; not called from `_run_graph` this phase
- `tradingagents/revenium/__init__.py` - Updated to re-export `ReveniumCallbackHandler`
- `tradingagents/graph/trading_graph.py` - Handler built in `__init__`; dedup guard on append; `_run_graph` wrapped in `with revenium_run_context(...)`
- `scripts/validate_metering.py` - Live one-event assertion script; `--provider` and `--model` flags; `main() -> int`; 10-check assertion loop; doubles as pre-demo sanity check
- `tests/test_revenium_metering.py` - 19 mocked unit tests: keyless no-op, 1-event invariant, attribution checks, context integration, dedup guard, billing stub

## Decisions Made

1. **Single metering path (callback-only, no OTLP):** Verified by grep that no `opentelemetry`/`otlp` import exists in `revenium/` or `trading_graph.py`. Dual-path would produce 2x cost figures (T-02-04).
2. **Dedup guard semantics:** Internally-built handler only appended if no already-enabled `ReveniumCallbackHandler` exists in the caller-supplied list. Plan 01-03 relies on this so the CLI can pass its own handler without doubling.
3. **Provider-model consistency in validate_metering.py:** Script originally always used the deep-think model regardless of `--provider`. Added `--model` flag and auto-resolution from config so `--provider openai` correctly resolves to `gpt-4.1-mini` (post-checkpoint fix `8f5f728`).
4. **Live validation path: OpenAI over Anthropic:** The `ANTHROPIC_API_KEY` in the test environment was invalid (401). Validation ran successfully via `--provider openai` instead. This does not affect metering correctness — the handler is provider-agnostic.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] validate_metering.py always used deep-think model regardless of --provider flag**
- **Found during:** Task 5 (live human verification); `--provider openai` selected but the script sent the claude model name, causing OpenAI to 401
- **Issue:** `validate_metering.py` hardcoded the LLM construction to read `deep_think_llm` and `deep_think_provider` from config without respecting the `--provider` CLI argument. When `--provider openai` was passed, the provider changed but the model name remained `claude-sonnet-4-6`, causing OpenAI to reject the request.
- **Fix:** Rewrote provider/model selection in `validate_metering.py` to resolve a consistent (provider, model) pair: if `--provider` matches `deep_think_provider`, use `deep_think_llm`; if it matches `quick_think_provider`, use `quick_think_llm`; added `--model` override flag for manual specification. Default remains `anthropic/claude-sonnet-4-6`.
- **Files modified:** `scripts/validate_metering.py`
- **Committed in:** `8f5f728`

---

**Total deviations:** 1 auto-fixed (Rule 1 - Bug)
**Impact on plan:** Fix was necessary for the live validation checkpoint to run. No scope creep; metering logic itself was unaffected — the bug was only in the validation script's LLM construction path.

## Issues Encountered

- **ANTHROPIC_API_KEY invalid (401):** The test environment's Anthropic key returned "invalid x-api-key" during the first live validation attempt. Switched to `--provider openai` (which required the provider/model pairing fix above). The Anthropic key issue is NOT fixed in this plan — see Open Follow-ups below.
- **RuntimeWarning for gpt-4.1-mini:** Running validation via OpenAI triggered `RuntimeWarning: Model 'gpt-4.1-mini' is not in the known model list for provider 'openai'`. This is a pre-existing gap in `capabilities.py` / `model_catalog.py` and does not affect metering correctness, but will be visible during demo runs.

## Live Validation Result (Task 5 — Human Approved)

```
Command:  scripts/validate_metering.py --provider openai
Result:   Metering PASSED: 10/10 checks
trace_id: 5fb9569b-a7d5-4b61-87d5-58da2e8d8b8b
Provider: openai / gpt-4.1-mini
Dashboard confirmed: org Revenium-Research-Desk, product trading-signal,
  subscriber john.demic+trading@revenium.io, non-zero input+output tokens,
  agent market_analyst, task_type set, NOT UNCLASSIFIED.
Double-count guard: exactly ONE event (not two).
```

## Test Suite Results

**Mocked (no live keys):** `REVENIUM_METERING_API_KEY= .venv/bin/python -m pytest tests/test_revenium_metering.py -q`

- **Result:** 19 passed in 0.10s — exit 0
- **Coverage:** keyless no-op (enabled=False, zero client calls, no raise), 1-event-per-call invariant (call_count == on_llm_end count, loop N times), attribution payload (non-empty org/product/subscriber + correct agent/traceId/taskType), context integration, dedup guard, billing stub

**Pre-existing failures (not caused by this plan):**

- `tests/test_ollama_base_url.py::test_resolver_does_not_affect_other_providers` — requires `DEEPSEEK_API_KEY`, pre-existing
- `tests/test_temperature_config.py::TestTemperatureForwarding::test_temperature_reaches_client_when_set[deepseek-deepseek-chat]` — requires `DEEPSEEK_API_KEY`, pre-existing

These 2 DeepSeek failures are out-of-scope for this plan and were present before Plan 01-01.

## Open Follow-ups for Plan 01-03

| Item | Priority | Notes |
|------|----------|-------|
| Add `gpt-4.1-mini` to `capabilities.py` / `model_catalog.py` | High | RuntimeWarning fires on every OpenAI validate_metering run; Plan 01-03 touches multi-provider labeling — fold it in there |
| Verify / replace `ANTHROPIC_API_KEY` | High (MTR-04 blocker) | Plan 01-03 must show Anthropic vs OpenAI distinct provider labels (MTR-04); the demo subscriber's Anthropic key returned 401 in this plan's live validation. A valid Anthropic key is a hard prerequisite for Plan 01-03's multi-provider verification checkpoint |
| Thicken coverage to all 12 agents + tools | Plan 01-03 scope | Per-agent contextvars (`set_agent_context` at each node entry), `@meter_tool` on all data-fetch tools in `agent_utils.py`, CLI wiring, two-provider label verification (MTR-03/MTR-04) |

## Known Stubs

- `tradingagents/revenium/billing.py` — `ReveniumBillingEmitter.emit_signal_unit()` is a no-op. Phase 4 (monetize pillar) fills in the real billing event emission. Not called from `_run_graph` yet.

## Threat Surface Scan

All T-02-xx mitigations applied and verified:

- **T-02-01 (info disclosure via logs):** `on_llm_end` logs only symbolic agent/operation names; API key and request prompts never logged. Verified by code inspection and `noqa: BLE001` annotations.
- **T-02-02 (subscriber PII):** Subscriber email (`john.demic+trading@revenium.io`) intentionally sent to trusted Revenium account over TLS only.
- **T-02-03 (DoS via synchronous metering):** `meter_ai_completion` dispatched on a background daemon thread; `on_llm_end` never awaits the HTTP round-trip.
- **T-02-04 (double metering path):** Grep confirms zero `opentelemetry`/`otlp` imports in `tradingagents/revenium/` and `trading_graph.py`. Mocked test asserts 1:1 invariant.
- **T-02-05 (UNCLASSIFIED events):** Attribution test asserts non-empty `organizationName`, `productName`, `subscriber.id`. Live validation confirmed not UNCLASSIFIED in dashboard.

No new threat surface beyond what the plan's threat model already covers.

## Next Phase Readiness

**Plan 01-03 (thicken coverage) is unblocked for code work:**
- Callback handler, context machinery, and run-context wrapping are in place
- `revenium_task_type_map` covers all 12 LangGraph node names (from Plan 01-01)
- Dedup guard allows Plan 01-03 to pass its own handler without doubling

**Hard prerequisites before Plan 01-03 live verification checkpoint:**
1. Valid `ANTHROPIC_API_KEY` — needed for the two-provider MTR-04 story (Anthropic deep-think vs OpenAI quick-think distinct labels in Revenium dashboard)
2. `gpt-4.1-mini` entry in `capabilities.py` / `model_catalog.py` — suppress RuntimeWarning before demo runs

## Self-Check: PASSED

- FOUND: .planning/phases/01-foundation-metering/01-02-SUMMARY.md
- FOUND: d584909 (test — TDD RED)
- FOUND: 7382713 (feat — context + client)
- FOUND: 830e260 (feat — callback handler)
- FOUND: 2cf4837 (feat — graph wiring + billing stub)
- FOUND: bd0599c (feat — validation script + mocked tests)
- FOUND: 8f5f728 (fix — provider/model pairing in validate_metering)
- FOUND: tradingagents/revenium/context.py
- FOUND: tradingagents/revenium/client.py
- FOUND: tradingagents/revenium/callback.py
- FOUND: tradingagents/revenium/billing.py
- FOUND: scripts/validate_metering.py
- FOUND: tests/test_revenium_metering.py

---
*Phase: 01-foundation-metering*
*Completed: 2026-06-27*
