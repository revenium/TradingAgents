---
phase: 01-foundation-metering
plan: "03"
subsystem: infra
tags: [revenium, langchain, contextvars, meter-tool, multi-provider, openai, anthropic, metering, tdd]

# Dependency graph
requires:
  - phase: 01-foundation-metering/01-02
    provides: "ReveniumCallbackHandler wired into TradingAgentsGraph; context.py (trace_id/agent_name/run_meta contextvars); fail-open client; dedup guard; validate_metering.py"
  - phase: 01-foundation-metering/01-01
    provides: "revenium-python-sdk[langchain] pinned; revenium_task_type_map; all revenium_* config keys; live attribution hierarchy (Org DyGMJl, Subscriber l3Pwo5, Product DEnNNv)"
provides:
  - "Per-agent identity contextvar (current_agent_name.set) at the top of all 12 agent node functions — events attributed to the exact agent with the correct task_type bucket"
  - "Single ReveniumCallbackHandler wired into cli/main.py (no double-counting across CLI + graph paths)"
  - "@meter_tool on all 12 analyst data-fetch tools across 7 tool modules (cost iceberg: tool cost vs token cost visible in Revenium)"
  - "Documented .func exemption in sentiment_analyst.py (~line 69) — single explicit @meter_tool bypass"
  - "tests/test_revenium_tool_metering.py — mocked tool-event + agent-attribution tests; 29 tests total pass keyless"
  - "scripts/validate_metering.py --multi-provider mode (MTR-04 capability; cross-provider live verification de-scoped per user — see deviations)"
  - "gpt-4.1-mini added to model_catalog.py — RuntimeWarning eliminated"
  - "Critical bug fixed (70d37ed): tool events now POST to prod https://api.revenium.ai/meter endpoint (not localhost:8082)"
  - "MTR-03 satisfied: @meter_tool on all data-fetch tools; tool-vs-token cost split visible in dashboard"
  - "MTR-04 satisfied at single-provider level: per-agent, per-provider LLM labels confirmed distinct (gpt-4.1-mini priced at $0.40/$1.60 per M); cross-provider (Anthropic+OpenAI) verification de-scoped to later phase (see deviation 2)"
affects:
  - "Phase 2 (trace): parentTransactionId threading builds on the same contextvar/callback infrastructure"
  - "Phase 4 (billing): tool pricing (usage_metadata + pricingDimensions for @meter_tool) and $2.00/signal product price follow up here"
  - "Phase 5 (hardening): FRED fail-soft data-vendor chain and trace_id surfacing to stdout are deferred follow-ups"
  - "OpenRouter migration note: demo provider strategy may shift from Anthropic+OpenAI direct to OpenRouter single integration"

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Per-agent contextvar pattern: first line of every agent node body calls current_agent_name.set('<node_name>') using the D-12 name table; import is from tradingagents.revenium.context"
    - "CLI single-handler pattern: one ReveniumCallbackHandler built via from_config(); appended to both TradingAgentsGraph callbacks and get_graph_args callbacks; graph dedup guard prevents double-counting"
    - "@meter_tool placement: decorator wraps the underlying data-fetch function BENEATH @tool, so LangChain @tool remains outermost; meter_tool re-export in tradingagents/revenium/meter_tool.py injects trace_id/agent from contextvars and enforces fail-open"
    - "Prod endpoint configuration: meter_tool.py calls configure(metering_url=<revenium_api_url>+'/meter', api_key=<rev_mk>) before _send_tool_event; without this, the SDK defaults to localhost:8082 (Errno 61)"
    - "LLM-level non-streaming confirmed by grep: no llm.stream/llm.astream/stream=True/streaming=True in agents/ or llm_clients/; graph-level self.graph.stream (trading_graph.py, cli/main.py) is expected and harmless; on_llm_end captures complete token data"

key-files:
  created:
    - tests/test_revenium_tool_metering.py
  modified:
    - tradingagents/agents/analysts/market_analyst.py
    - tradingagents/agents/analysts/sentiment_analyst.py
    - tradingagents/agents/analysts/news_analyst.py
    - tradingagents/agents/analysts/fundamentals_analyst.py
    - tradingagents/agents/researchers/bull_researcher.py
    - tradingagents/agents/researchers/bear_researcher.py
    - tradingagents/agents/managers/research_manager.py
    - tradingagents/agents/trader/trader.py
    - tradingagents/agents/risk_mgmt/aggressive_debator.py
    - tradingagents/agents/risk_mgmt/conservative_debator.py
    - tradingagents/agents/risk_mgmt/neutral_debator.py
    - tradingagents/agents/managers/portfolio_manager.py
    - tradingagents/agents/utils/core_stock_tools.py
    - tradingagents/agents/utils/technical_indicators_tools.py
    - tradingagents/agents/utils/fundamental_data_tools.py
    - tradingagents/agents/utils/news_data_tools.py
    - tradingagents/agents/utils/macro_data_tools.py
    - tradingagents/agents/utils/prediction_markets_tools.py
    - tradingagents/agents/utils/market_data_validation_tools.py
    - tradingagents/revenium/meter_tool.py
    - tradingagents/llm_clients/model_catalog.py
    - cli/main.py
    - scripts/validate_metering.py

key-decisions:
  - "gpt-4.1-mini added to model_catalog.py to eliminate RuntimeWarning on every OpenAI path run — prerequisite for clean live full-pipeline demo"
  - "Tool-event transport configured to prod /meter endpoint: meter_tool.py calls configure() before _send_tool_event; SDK default of localhost:8082 was a silent failure (Errno 61 Connection refused x39 per run)"
  - "TOOL COST = $0.00 is EXPECTED for Phase 1: @meter_tool sends usage_metadata=None; data-fetch tools have no token cost and no price model. Tool metering in Phase 1 = operational visibility (volume/latency/attribution). Assigning dollar cost to tools (usage_metadata + pricingDimensions) is Phase 4 follow-up"
  - "Cross-provider live verification (Anthropic+OpenAI) de-scoped by user: ANTHROPIC_API_KEY 401d and demo will move to OpenRouter single integration; --multi-provider flag exists and code is correct but was not live-verified two-provider"
  - "FRED fail-soft deferred: macro/news vendor chain RAISES (not returns NO_DATA_AVAILABLE sentinel) when FRED is the sole unconfigured vendor; user workaround = add FRED_API_KEY; proper fail-soft fix deferred to Phase 5"
  - "trace_id not surfaced to stdout: current_trace_id (uuid4) is set in revenium_run_context but never printed; Phase 5 to add --print-trace-id or equivalent for demo dashboard lookup"

patterns-established:
  - "D-12 node-name table: market_analyst, sentiment_analyst, news_analyst, fundamentals_analyst, bull_researcher, bear_researcher, research_manager, trader, aggressive_debator, conservative_debator, neutral_debator, portfolio_manager — these must match revenium_task_type_map keys; confirmed by live run"
  - "Fail-open decorator chain: @tool (outer) → meter_tool wrapper (inner) → underlying function; metering failure does not propagate; tool still returns data or NO_DATA_AVAILABLE sentinel"
  - "Tool-event SDK transport: always call configure(metering_url=..., api_key=...) before using the revenium-metering decorator; never rely on SDK defaults (they point to localhost)"

requirements-completed: [MTR-03, MTR-04]

# Metrics
duration: 180min
completed: 2026-06-27
---

# Phase 01 Plan 03: Full Metering Coverage — Per-Agent Identity, CLI Wiring, Tool Cost Iceberg Summary

**All 12 agent nodes instrumented with per-agent identity contextvars, single ReveniumCallbackHandler wired into CLI (no double-counting), @meter_tool applied to all 12 data-fetch tools for tool-vs-token cost visibility ("cost iceberg"), critical SDK transport bug fixed (tool events now reach prod endpoint), and full NVDA pipeline run verified clean: exit 0, BUY/Overweight decision, 0 metering errors — MTR-03 and MTR-04 satisfied.**

## Performance

- **Duration:** ~180 min
- **Started:** 2026-06-27 (post Plan 01-02 checkpoint approval)
- **Completed:** 2026-06-27
- **Tasks:** 5/5 (Tasks 1-4 auto; Task 5 checkpoint:human-verify — APPROVED after full pipeline run)
- **Files modified:** 24

## Accomplishments

- D-12 complete: All 12 agent node functions (4 analysts, 2 researchers, 3 risk debaters, research manager, trader, portfolio manager) set `current_agent_name.set("<node_name>")` as their first line — LLM events are now attributed per-agent with the correct task_type bucket (analysis/research_debate/planning/trade/risk_debate/decision).
- D-13 / MTR-03 complete: `@meter_tool` applied to all 12 data-fetch tools (get_stock_data, get_indicators, get_fundamentals, get_balance_sheet, get_cashflow, get_income_statement, get_news, get_global_news, get_insider_transactions, get_macro_indicators, get_prediction_markets, get_verified_market_snapshot) across 7 tool modules; tool events appear in Revenium as separate events distinct from LLM token events (the cost iceberg). Sentiment-analyst .func bypass documented as the single explicit exemption.
- CLI wiring: ReveniumCallbackHandler added to cli/main.py; same single handler instance passed to both TradingAgentsGraph callbacks and get_graph_args — no double-counting path; graph dedup guard confirmed still active.
- Critical transport bug fixed (70d37ed): tool-metering events were silently failing (Errno 61 Connection refused x39) because `configure()` was never called and the SDK defaulted to localhost:8082. `meter_tool.py` now configures the prod `https://api.revenium.ai/meter` endpoint before firing events. Regression test added.
- gpt-4.1-mini added to model_catalog.py: eliminates RuntimeWarning on every OpenAI path run, confirmed by the human after a clean full NVDA pipeline run.
- Live full pipeline verified (NVDA, OpenAI forced): exit 0, BUY/Overweight decision, 0 connection-refused errors, 0 metering errors, 0 model RuntimeWarnings. Dashboard showed per-agent LLM events (distinct agent labels), tool cost iceberg events, gpt-4.1-mini priced ($0.40/M input, $1.60/M output).
- LLM-level non-streaming confirmed by grep: no `llm.stream`, `llm.astream`, `stream=True`, or `streaming=True` in `agents/` or `llm_clients/`; `on_llm_end` reliably captures complete token data.

## Task Commits

Each task was committed atomically:

1. **Task 1: gpt-4.1-mini added to model catalog (prerequisite)** - `b932573` (chore)
2. **Task 1: Per-agent identity contextvar in all 12 agent nodes (D-12)** - `64dd655` (feat)
3. **Task 2: Wire single Revenium handler into CLI path (no double-counting)** - `e12c2a0` (feat)
4. **Task 3: @meter_tool on all 12 analyst data-fetch tools (D-13 / MTR-03)** - `cc3fcca` (feat)
5. **Task 4: --multi-provider mode in validate_metering.py (MTR-04)** - `64c4fc6` (feat)
6. **Critical bug fix: configure tool-event transport to prod /meter endpoint** - `70d37ed` (fix)

**Plan metadata:** (docs commit — `commit_docs: false` in .planning/config.json; .planning/ changes tracked in working tree, not committed to git history)

## Files Created/Modified

- `tradingagents/agents/analysts/market_analyst.py` — `current_agent_name.set("market_analyst")` at top of node body
- `tradingagents/agents/analysts/sentiment_analyst.py` — `current_agent_name.set("sentiment_analyst")`; `.func` bypass documented as D-13 exemption
- `tradingagents/agents/analysts/news_analyst.py` — `current_agent_name.set("news_analyst")`
- `tradingagents/agents/analysts/fundamentals_analyst.py` — `current_agent_name.set("fundamentals_analyst")`
- `tradingagents/agents/researchers/bull_researcher.py` — `current_agent_name.set("bull_researcher")`
- `tradingagents/agents/researchers/bear_researcher.py` — `current_agent_name.set("bear_researcher")`
- `tradingagents/agents/managers/research_manager.py` — `current_agent_name.set("research_manager")`
- `tradingagents/agents/trader/trader.py` — `current_agent_name.set("trader")`
- `tradingagents/agents/risk_mgmt/aggressive_debator.py` — `current_agent_name.set("aggressive_debator")`
- `tradingagents/agents/risk_mgmt/conservative_debator.py` — `current_agent_name.set("conservative_debator")`
- `tradingagents/agents/risk_mgmt/neutral_debator.py` — `current_agent_name.set("neutral_debator")`
- `tradingagents/agents/managers/portfolio_manager.py` — `current_agent_name.set("portfolio_manager")`
- `tradingagents/agents/utils/core_stock_tools.py` — `@meter_tool` on get_stock_data, get_verified_market_snapshot
- `tradingagents/agents/utils/technical_indicators_tools.py` — `@meter_tool` on get_indicators
- `tradingagents/agents/utils/fundamental_data_tools.py` — `@meter_tool` on get_fundamentals, get_balance_sheet, get_cashflow, get_income_statement
- `tradingagents/agents/utils/news_data_tools.py` — `@meter_tool` on get_news, get_global_news
- `tradingagents/agents/utils/macro_data_tools.py` — `@meter_tool` on get_macro_indicators, get_insider_transactions
- `tradingagents/agents/utils/prediction_markets_tools.py` — `@meter_tool` on get_prediction_markets
- `tradingagents/agents/utils/market_data_validation_tools.py` — `@meter_tool` on market data validation tools
- `tradingagents/revenium/meter_tool.py` — Thin adapter re-exporting meter_tool with trace_id/agent contextvar injection + prod endpoint configuration; fail-open wrapper
- `tradingagents/llm_clients/model_catalog.py` — Added gpt-4.1-mini entry with pricing ($0.40/$1.60 per M tokens) and capabilities
- `cli/main.py` — Single ReveniumCallbackHandler via from_config(); appended to TradingAgentsGraph callbacks and get_graph_args callbacks; comment documents single-source/dedup semantics
- `scripts/validate_metering.py` — Extended with `--multi-provider` flag; two-provider probe (Anthropic + OpenAI) with distinct-label assertion
- `tests/test_revenium_tool_metering.py` — Mocked tool-event test (one event per decorated tool call, carrying tool name + trace_id), keyless-zero variant, agent-attribution test (market_analyst→analysis, bull_researcher→research_debate)

## Decisions Made

1. **gpt-4.1-mini added to model_catalog.py as Phase 1 prerequisite:** RuntimeWarning fired on every OpenAI path run and was visible in the live demo environment. Added before any other tasks since it was a noise source that would undermine demo credibility.
2. **Tool-event endpoint must be explicitly configured:** The revenium-metering SDK `@meter_tool` decorator defaults to localhost:8082 for its internal transport. Without calling `configure(metering_url=..., api_key=...)`, all tool events fail silently with Errno 61. This is a non-obvious SDK behavior not caught by unit tests — only a live full-pipeline run reveals it (39 connection-refused errors per run).
3. **TOOL COST = $0.00 is correct for Phase 1:** `@meter_tool` sends `usage_metadata=None`. Data-fetch tools have no token cost and no per-call price model. Tool metering in Phase 1 delivers operational visibility (volume, latency, attribution per agent). Assigning dollar cost to tools requires Phase 4 work: add `usage_metadata` with custom dimensions and configure `pricingDimensions` on the Revenium product.
4. **Cross-provider live verification de-scoped by user:** `ANTHROPIC_API_KEY` returned 401 during this plan. The user decided the demo will move to OpenRouter (single integration point for all providers) rather than Anthropic+OpenAI direct. The `--multi-provider` flag exists and the code is correct, but two-provider live verification was not completed. Phase 1 is proven on the OpenAI/gpt-4.1-mini path.
5. **FRED_API_KEY added as immediate workaround for data-layer crashes:** When FRED is the sole macro vendor and unconfigured, `route_to_vendor` raises (does not return `NO_DATA_AVAILABLE` sentinel), crashing full runs with exit 1. The user added a FRED_API_KEY as the immediate fix. The underlying fail-soft fix is deferred to Phase 5.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Critical Bug] Tool events silently failing to localhost:8082 — configured to prod endpoint**
- **Found during:** Task 5 (live full-pipeline run verification); 39 Errno 61 Connection refused errors per run
- **Issue:** The revenium-metering SDK `@meter_tool` decorator (and its internal `_send_tool_event`) defaults to posting to `http://localhost:8082` unless explicitly configured. The `configure()` call was never made, so every tool event in the live run failed silently with Errno 61. Unit tests mock the HTTP layer and cannot catch this — only a live full-pipeline run reveals it.
- **Fix:** `tradingagents/revenium/meter_tool.py` now calls `configure(metering_url=get_config().get("revenium_api_url", "https://api.revenium.ai") + "/meter", api_key=<rev_mk>)` before `_send_tool_event`. Verified endpoint `https://api.revenium.ai/meter/v2/tool/events` returns 403 (auth) rather than 404 (wrong path) — correct route. Regression test added to `tests/test_revenium_tool_metering.py` asserting no localhost:8082 calls when key is set.
- **Files modified:** `tradingagents/revenium/meter_tool.py`, `tests/test_revenium_tool_metering.py`
- **Committed in:** `70d37ed`

**2. [Finding - Architectural] MTR-04 cross-provider live verification de-scoped by user**
- **Found during:** Task 5 (Anthropic key returned 401 during live validation attempt)
- **Issue:** `ANTHROPIC_API_KEY` was invalid (401). Plan 01-03 required a valid Anthropic key for the two-provider (Anthropic + OpenAI) label verification in Revenium. This was flagged as an open blocker in Plan 01-02 but remained unresolved.
- **User decision:** The demo strategy will move to OpenRouter (single integration that routes to multiple providers) rather than Anthropic+OpenAI direct. The user accepted Phase 1 as proven on OpenAI/gpt-4.1-mini alone. The `--multi-provider` flag in `validate_metering.py` exists and the code path is correct.
- **Impact:** MTR-04 is marked complete at the capability level (code + flag + test assertion) but live cross-provider verification was not performed. The distinct-provider-label story for FCAT will be demonstrated via OpenRouter in a later phase.
- **Not a deviation rule case:** This is a user-directed scope change, not an auto-fix.

**3. [Finding - Data Layer] FRED fail-soft gap causes intermittent full-run crashes**
- **Found during:** Task 5 (live full-pipeline run); runs with missing FRED_API_KEY exited 1
- **Issue:** When FRED is the sole macro/news data vendor and `FRED_API_KEY` is absent, `route_to_vendor` raises `FredNotConfiguredError` / `ValueError` rather than returning the `NO_DATA_AVAILABLE` sentinel. This is inconsistent with the repo's documented error-handling convention (all-vendors-exhausted should return `NO_DATA_AVAILABLE`, not raise). The `@meter_tool` decorator correctly re-raises (fail-open = transparent), so metering is not the cause — it is a pre-existing data-layer gap.
- **Resolution:** User added `FRED_API_KEY` as immediate workaround. The run completed cleanly with a valid key.
- **Deferred:** Proper fix (make macro/news vendor chain fail-soft to `NO_DATA_AVAILABLE` when no vendor is configured) is a Phase 5 hardening item (demo-reliability risk). Logged in deferred-items.

**4. [Finding - Observability] trace_id not surfaced to stdout**
- **Found during:** Task 5 (human needed to locate events by time window in the Revenium dashboard)
- **Issue:** The `current_trace_id` (uuid4, set by `revenium_run_context`) is used in every metered event but is never printed or logged at the start/end of a run. Dashboard lookup requires a time-window search rather than direct trace_id lookup.
- **Deferred:** Phase 5 hardening — consider adding `--print-trace-id` CLI flag or a log line at run start/end for demo convenience.

---

**Total deviations:** 1 critical auto-fixed (Rule 1 - Bug), 3 findings documented (scoping, data layer, observability)
**Impact on plan:** The transport bug fix was essential — without it, all tool events were silently lost even though the @meter_tool decorator appeared to work. The user-directed MTR-04 scope change does not affect Phase 1 completeness. The FRED fail-soft gap is a pre-existing data-layer issue that becomes a demo reliability risk; the FRED_API_KEY workaround keeps Phase 1 solid.

## Issues Encountered

- **ANTHROPIC_API_KEY invalid (401):** Blocked the two-provider live verification path. Resolved by user decision to de-scope cross-provider direct verification in favor of OpenRouter migration (later phase).
- **FRED_API_KEY required for full-pipeline run:** `route_to_vendor` raises (not returns NO_DATA_AVAILABLE) when FRED is unconfigured. User added the key as a workaround. Phase 5 hardening should make the macro/news vendor chain fail-soft.
- **Tool events going to localhost:8082 (critical):** 39 Errno 61 Connection refused per full run, invisible in unit tests. Fixed in 70d37ed. Lesson: live integration run is essential for SDK-transport correctness — mocked tests cannot catch default-endpoint bugs.
- **TOOL COST = $0.00 briefly confused as a bug:** Clarified by design — tool events have no token cost and no price model in Phase 1. Dollar cost assignment requires Phase 4 work (usage_metadata + pricingDimensions).

## Live Validation Result (Task 5 — Human Approved)

```
Full pipeline run: main.py, NVDA, OpenAI forced (gpt-4.1-mini), FRED_API_KEY present
Result: exit 0, Decision = BUY/Overweight on NVDA
Metering health: 0 connection-refused, 0 metering errors, 0 model RuntimeWarning, 0 tracebacks
Dashboard confirmed: per-agent LLM events (distinct agent labels), tool cost iceberg events captured,
  gpt-4.1-mini priced ($0.40/M input, $1.60/M output)

validate_metering.py --provider openai: 10/10 checks, one attributed event
LLM-level streaming grep: PASS (no llm.stream/astream/stream=True/streaming=True in agents/ or llm_clients/)
```

## Test Suite Results

**Mocked (no live keys):** `REVENIUM_METERING_API_KEY= .venv/bin/python -m pytest tests/test_revenium_tool_metering.py tests/test_revenium_metering.py -q`

- **Result:** 29 passed in 0.55s — exit 0
- **Coverage (test_revenium_tool_metering.py):** tool-event test (one event per decorated call with tool name + trace_id), keyless-zero variant (no events, identical return value), agent-attribution test (market_analyst→taskType=analysis, bull_researcher→taskType=research_debate), localhost:8082 regression test (no localhost calls when key is set and prod endpoint is configured)
- **Coverage (test_revenium_metering.py):** 19 tests from Plan 01-02 — all still passing; no regressions

**Pre-existing failures (not caused by this plan):**

- `tests/test_ollama_base_url.py::test_resolver_does_not_affect_other_providers` — requires `DEEPSEEK_API_KEY`, pre-existing
- `tests/test_temperature_config.py::TestTemperatureForwarding::test_temperature_reaches_client_when_set[deepseek-deepseek-chat]` — requires `DEEPSEEK_API_KEY`, pre-existing

These 2 DeepSeek failures are out-of-scope for all Phase 1 plans and were present before Plan 01-01.

## Phase-4 Follow-ups (Tool Dollar Cost)

The following work is intentionally deferred to Phase 4 (monetize pillar):

| Item | Phase | Notes |
|------|-------|-------|
| Assign dollar cost to tool events (`usage_metadata` + `pricingDimensions` on Revenium product) | Phase 4 | Tool events currently show $0.00; volume/latency/attribution is visible but no dollar value |
| `$2.00/signal` product pricing (priced billing event per completed run) | Phase 4 | Product `trading-signal` (DEnNNv) has SUBSCRIPTION/MONTH plan only; priced per-signal billing deferred since Plan 01-01 |
| `ReveniumBillingEmitter.emit_signal_unit()` no-op stub in `tradingagents/revenium/billing.py` | Phase 4 | Stub created in Plan 01-02; to be filled in during Phase 4 monetization work |

## Phase-5 Follow-ups (Demo Hardening)

| Item | Phase | Notes |
|------|-------|-------|
| Make macro/news vendor chain fail-soft (return NO_DATA_AVAILABLE instead of raising when all vendors unconfigured) | Phase 5 | Current behavior: FRED unconfigured raises FredNotConfiguredError; demo runs exit 1 without FRED_API_KEY |
| Surface trace_id to stdout at run start/end | Phase 5 | Enables direct dashboard lookup by trace_id instead of time-window search; nice-to-have for demo verification |

## OpenRouter Migration Note

The user has indicated the demo provider strategy will shift from Anthropic+OpenAI direct to OpenRouter (single integration point routing to multiple providers). This affects:

- **MTR-04 live verification:** Was not completed two-provider (Anthropic 401'd). The `--multi-provider` flag in `validate_metering.py` exists but was not live-verified against two distinct provider labels. With OpenRouter, the provider label in Revenium events may appear as "openai" (base-URL routing) rather than "anthropic" — the cross-provider cost-breakdown story may need re-framing.
- **Phase 2 planning:** `parentTransactionId` threading should be validated against the actual provider(s) chosen for the demo, not against the Anthropic+OpenAI assumption baked into PATTERNS.md.
- **`validate_metering.py --multi-provider`:** The Anthropic probe in this flag will 401 in the current environment. If moving to OpenRouter, the script may need a `--openrouter` mode or the existing Anthropic probe may need updating.

## Revenium CLI Note

The `revenium` CLI (homebrew, `/opt/homebrew/bin/revenium`) is available in this environment and was used during Plan 01-03 to confirm gpt-4.1-mini pricing (via `revenium models lookup`). It covers jobs, outcomes, guardrails, metrics, and pricing — a useful accelerator for Phases 2-4 without needing to hit the Platform API directly from scripts.

## Known Stubs

- `tradingagents/revenium/billing.py` — `ReveniumBillingEmitter.emit_signal_unit()` is a no-op. Phase 4 (monetize pillar) fills in the real billing event emission.
- Tool cost in Revenium = $0.00 — expected behavior for Phase 1. Phase 4 will add `usage_metadata` + `pricingDimensions` to assign dollar cost to tool events.

## Threat Surface Scan

All T-03-xx mitigations applied and verified by live full-pipeline run:

- **T-03-01 (duplicate handler / 2x cost):** Single ReveniumCallbackHandler reused across CLI callbacks, get_graph_args, and graph wiring; dedup guard in trading_graph.py confirmed active; dashboard showed exactly one LLM event per call (not two).
- **T-03-02 (info disclosure via meter_tool logs):** tool-metering adapter logs only the tool name (symbolic); never logs key material, ticker-sensitive data, or full request payloads. `noqa: BLE001` annotation on fail-open catch.
- **T-03-03 (metering blocking data fetch):** @meter_tool decorator is fail-open; existing tool tests confirmed identical behavior with no key. Live run: data-fetch tools returned data normally even when tool events were failing (pre-fix state).
- **T-03-04 (wrong agent label / misattributed cost):** D-12 node-name strings match revenium_task_type_map keys (confirmed by agent-attribution unit test and live dashboard view with distinct agent labels).
- **T-03-SC (supply-chain):** No new packages installed in this plan; `revenium-metering` was already pinned and verified in Plan 01-01.

No new threat surface beyond what the plan's threat model covers.

## Next Phase Readiness

**Phase 2 (Trace & Squad Analytics) is unblocked for planning:**
- All 12 agents have per-agent identity contextvars — parentTransactionId threading in Phase 2 can use the same contextvar infrastructure
- Single handler is the sole metering path — no dual-path complications for Phase 2 trace threading
- Live full-pipeline run clean (exit 0, 0 errors) — stable foundation for Phase 2 span-count validation

**Phase 1 complete: all 3 plans delivered (01-01/02/03). All Phase 1 requirements satisfied:**
- FND-01 through FND-04: model names, SDK, attribution hierarchy, single-call validation
- MTR-01/MTR-02: per-agent + billing attribution on every LLM event
- MTR-03: @meter_tool on all data-fetch tools, cost iceberg visible
- MTR-04: per-provider labels confirmed for OpenAI path; cross-provider (Anthropic+OpenAI) live demo deferred to OpenRouter migration

**Pre-Phase 2 considerations:**
- Decide on OpenRouter vs Anthropic+OpenAI direct for the demo provider strategy (affects MTR-04 live story and Phase 2 span attribution)
- Confirm `FRED_API_KEY` is present in the demo environment (avoid Phase 5 fail-soft gap during Phase 2 live runs)
- Note: `parentTransactionId` loopback behavior across LangGraph conditional edges needs a live integration test before Phase 2 commits to the debate-loop cost-hotspot story (flagged as Phase 2 research flag in ROADMAP.md)

## Self-Check: PASSED

- FOUND: .planning/phases/01-foundation-metering/01-03-SUMMARY.md (this file)
- FOUND: b932573 (chore — gpt-4.1-mini to model catalog)
- FOUND: 64dd655 (feat — per-agent contextvar in 12 nodes)
- FOUND: e12c2a0 (feat — CLI handler wiring)
- FOUND: cc3fcca (feat — @meter_tool on 12 data-fetch tools)
- FOUND: 64c4fc6 (feat — --multi-provider mode)
- FOUND: 70d37ed (fix — prod /meter endpoint)
- FOUND: tests/test_revenium_tool_metering.py (29 tests pass keyless)

---
*Phase: 01-foundation-metering*
*Completed: 2026-06-27*
