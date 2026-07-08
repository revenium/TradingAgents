---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: milestone_complete
last_updated: 2026-07-03T20:02:09.755Z
last_activity: 2026-07-03 -- Phase 07 execution started
progress:
  total_phases: 7
  completed_phases: 4
  total_plans: 19
  completed_plans: 18
  percent: 57
stopped_at: Milestone complete (Phase 07 was final phase)
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-26)

**Core value:** A single live ticker run tells the complete Revenium story end to end — meter → trace → control → monetize — on a genuinely agentic, multi-provider trading workload. If everything else is cut, that one run must land for FCAT.
**Current focus:** Milestone complete

## Current Position

Phase: 07
Plan: Not started
Status: Milestone complete
Last activity: 2026-07-03

Progress: [█████████░] 88%

## Performance Metrics

**Velocity:**

- Total plans completed: 12
- Average duration: -
- Total execution time: 0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 02 | 3 | - | - |
| 03 | 3 | - | - |
| 04 | 3 | - | - |
| 07 | 3 | - | - |

**Recent Trend:**

- Last 5 plans: -
- Trend: -

*Updated after each plan completion*
| Phase 01-foundation-metering P01 | 90 | 5 tasks | 8 files |
| Phase 01-foundation-metering P02 | 120 | 5 tasks | 8 files |
| Phase 01-foundation-metering P03 | 180 | 5 tasks | 24 files |
| Phase 02-trace-squad-analytics P03 | 180 | 3 tasks | 4 files |
| Phase 06-jentic-tool-metering-monetization P01 | 12 | 3 tasks | 5 files |
| Phase 06-jentic-tool-metering-monetization P02 | 7 | 3 tasks | 4 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- Foundation: Callback handler path chosen over OTLP — non-streaming graph means `on_llm_end` captures all token data; OTLP has no circuit breaker
- Foundation: `revenium-python-sdk[langchain]` 0.1.9 only — `revenium-middleware-langchain` (archived) must NOT be installed alongside (double-counting)
- Foundation: Anthropic (deep-think) + OpenAI (quick-think) for multi-provider demo story — other providers labeled "openai" by handler
- [Phase 01-01]: Use claude-sonnet-4-6 (deep-think/Anthropic) and gpt-4.1-mini (quick-think/OpenAI); provider split via config keys
- [Phase 01-01]: Revenium Platform API is https://api.prod.ai.hcapp.io/profitstream/v2/api with x-api-key auth; tenant/team scoping; separate from metering hot-path host api.revenium.ai
- [Phase 01-01]: Product pricing deferred to Phase 4: Product created with SUBSCRIPTION/MONTH plan only; $2.00/signal metered pricing is Phase 4 monetize work
- [Phase 01-01]: FRONT-1385 filed: Revenium Platform API host, auth, and scoping are undocumented in public API reference; create-subscription doc 404s
- [Phase 01-02]: Single metering path via callback handler (no OTLP); dedup guard in TradingAgentsGraph ensures exactly one ReveniumCallbackHandler regardless of caller-supplied list
- [Phase 01-02]: Fire-and-forget on daemon thread — meter_ai_completion never blocks next LangGraph node; fail-open on all SDK exceptions
- [Phase 01-02]: validate_metering.py --provider/--model flags resolve consistent provider+model pair from config; live run confirmed trace_id 5fb9569b via openai/gpt-4.1-mini (Anthropic key invalid — Plan 01-03 prerequisite)
- [Phase 01-02]: gpt-4.1-mini missing from capabilities.py/model_catalog — RuntimeWarning on OpenAI path; must add in Plan 01-03 (multi-provider labels task)
- [Phase 01-foundation-metering]: MTR-03 satisfied: @meter_tool on all 12 data-fetch tools; tool-vs-token cost iceberg visible in Revenium dashboard per-agent
- [Phase 01-foundation-metering]: MTR-04 capability delivered; cross-provider live verification de-scoped by user — demo moving to OpenRouter single integration; --multi-provider flag exists and code is correct
- [Phase 01-foundation-metering]: Critical fix (70d37ed): revenium-metering @meter_tool defaults to localhost:8082; must call configure() before _send_tool_event to target prod https://api.revenium.ai/meter endpoint
- [Phase 01-foundation-metering]: TOOL COST = $0.00 is correct for Phase 1; tool events have no token cost, no price model; dollar cost assignment is Phase 4 work (usage_metadata + pricingDimensions)
- [Phase 01-foundation-metering]: FRED fail-soft deferred: route_to_vendor raises when FRED sole unconfigured vendor; user workaround = add FRED_API_KEY; Phase 5 must make macro/news vendor chain fail-soft
- [Phase 01-foundation-metering]: Phase 1 complete: 3/3 plans delivered, all 8 requirements (FND-01..04, MTR-01..04) satisfied; full NVDA pipeline proven clean (exit 0, 0 metering errors, BUY decision)
- [Phase 02-03]: GAP-02-01 fix: run-scoped trace state (trace_id + parent chain) moved from per-node contextvars to shared handler-instance state (begin_run/_last_transaction_id/end_run). Contextvar fallback retained for direct non-graph callers. Linearisation tradeoff accepted per 02-VERIFICATION.md.
- [Phase 02-03]: begin_run/end_run called in trading_graph._run_graph inside try/finally within revenium_run_context block; end_run always fires even if graph.invoke raises (fail-open posture preserved).
- [Phase 06-01]: requires-python tightened to >=3.11 (jentic requires >=3.11; runtime was already 3.11); jentic_agent_api_key defaults to empty string (not placeholder) so config gate returns NO_DATA_AVAILABLE immediately without network calls.
- [Phase ?]: Force-set os.environ JENTIC_AGENT_API_KEY from config inside _do_jentic_news (not setdefault) to allow test config key to override conftest monkeypatch
- [Phase ?]: patch jentic.Jentic targets source module namespace because _do_jentic_news lazy-imports Jentic inside the async body

### Pending Todos

None yet.

### Roadmap Evolution

- Phase 7 added (2026-07-03): Pilot Partner Integrations — mock Edgehound/Trinigence/SAIF as Revenium metered+priced tools (SAIF as a PM safety/assurance gate). ALL MOCKED, metered+priced, colon-free toolIds, reuse Phase 6 pattern. Ready to plan in a FRESH session (/gsd-discuss-phase 7 or /gsd-plan-phase 7).

- Phase 6 added (2026-07-03): Jentic Tool Metering & Monetization — weave Jentic's tool-execution SDK into the news analyst; meter + price every external API call via Revenium's `/v2/tool/events` pipeline. Mode: mvp, depends on Phase 1. Spike complete (jentic==0.10.0; execute() returns no cost → price per-call server-side via Revenium metering-element-definition). Live verification gated on user credentialing a news API in Jentic. Phase 5 (demo hardening) still open/unplanned.

### Blockers/Concerns

- **[RESOLVED - 01-01] Day-one blocker:** `DEFAULT_CONFIG` model names (`gpt-5.5`, `gpt-5.4-mini`) replaced with valid IDs
- **[RESOLVED - 01-01] Day-one blocker:** Revenium attribution hierarchy provisioned (Org DyGMJl, Subscriber l3Pwo5, Product DEnNNv, Subscription lR2kQl)
- **[RESOLVED - 01-02] Phase 1 validation gate:** Non-streaming confirmed; on_llm_end captures all token data; 19 mocked tests + live trace_id 5fb9569b verified
- **[DE-SCOPED - 01-03] ANTHROPIC_API_KEY invalid:** User decision: demo will move to OpenRouter single integration; Anthropic+OpenAI direct two-provider verification not pursued; --multi-provider flag exists in validate_metering.py
- **[RESOLVED - 01-03] gpt-4.1-mini not in capabilities.py/model_catalog:** Added in b932573; RuntimeWarning eliminated; live full-pipeline run clean
- **[FIXED - 02-03 Tasks 1-2] Phase 2 trace gap:** Handler-instance run-scoped state deployed (begin_run/end_run/_last_transaction_id in callback.py; begin_run/end_run called in trading_graph._run_graph try/finally). Keyless cross-node regression test added and passing (29/29 tests). Awaiting live re-validation in Task 3 (operator must run scripts/validate_tracing.py with live keys + confirm Revenium dashboard TRC-01/02/03). Commits: 7a4476a (RED test), 826084f (GREEN fix).
- **Pre-demo:** Cost control rules must be in enforce mode (not shadow) 24h before FCAT
- **[RESOLVED - quick 260628-j4w] GAP-CTL03-01 in-process enforcement halt:** Root-caused live as missing CONFIG, not an SDK bug. Fix = set `REVENIUM_ENFORCEMENT_BASE_URL=https://api.revenium.ai/profitstream` (the enforcement compiled-rules feed is under the `/profitstream` context path) + use a Revenium key with enforcement-READ scope (a `rev_sk_` write key works for both metering and the enforcement fetch; metering-only `rev_mk_` is 403 on the feed). Proven end-to-end: unpatched SDK `check_enforcement()` raises `BudgetExceededError` with this config. Documented in `.env.example` + `validate_controls.py`; keyless test for `_get_enforcement_base_url()` added. **Pre-demo operator action:** set both in `.env`, and pre-warm ~30-60s (compiled feed recompiles on a ~30s cadence). See [[revenium-enforcement-feed-mismatch]].

### Quick Tasks Completed

| # | Description | Date | Commit | Directory |
|---|-------------|------|--------|-----------|
| 260628-j4w | GAP-CTL03-01: configure enforcement base URL + key scope so the in-process circuit breaker fires | 2026-06-28 | b4e1815 | [260628-j4w-gap-ctl03-01-configure-enforcement-base-](./quick/260628-j4w-gap-ctl03-01-configure-enforcement-base-/) |
| 260628-nce | GAP-04-BIL: fix billing outcome payload (executionStatus + JSON-string metadata) + host-only profitstream URL; live report_outcome PASS 3/3 | 2026-06-28 | d6802b2 | [260628-nce-gap-04-bil-fix-billing-outcome-payload-e](./quick/260628-nce-gap-04-bil-fix-billing-outcome-payload-e/) |
| 260629-enf | GAP-04-TEAM: wire REVENIUM_TEAM_ID into config so billing jobs/outcomes record under demo team vQgNV5 (not personal 5oWd65); live PASS, team-scoped | 2026-06-29 | d6b8457 | [260629-enf-gap-04-team-wire-revenium-team-id-into-c](./quick/260629-enf-gap-04-team-wire-revenium-team-id-into-c/) |
| 260629-mde | GAP-04-LINK: billing uses existing rev_sk_ key (no separate billing key); per-agent metering tagged extra_body agenticJobId=trace_id so cost rolls up under the job → margin. 522 keyless pass | 2026-06-29 | 223b076 | [260629-mde-gap-04-link-billing-uses-rev-sk-key-per-](./quick/260629-mde-gap-04-link-billing-uses-rev-sk-key-per-/) |
| 260629-qwz | Fix multi-provider base_url leak: gate backend_url per role (pass only when role provider==llm_provider primary, else None) so Anthropic deep-think stops 404ing on OpenAI host. Unblocks two-provider demo. 524 keyless pass | 2026-06-29 | f797b2d, 2925157 | [260629-qwz-fix-multi-provider-base-url-leak-only-pa](./quick/260629-qwz-fix-multi-provider-base-url-leak-only-pa/) |
| 260701-d0h | Broaden pricing.py cost table (4→16 entries: gpt-4.1/gpt-5/o-series + claude opus/sonnet/haiku) + longest-substring-match compute_cost (order-independent) so CLI panel stops showing $0.00 for demo models. 551 keyless pass | 2026-07-01 | ae5fde5, 09b773f | [260701-d0h-broaden-pricing-py-local-cost-table-to-c](./quick/260701-d0h-broaden-pricing-py-local-cost-table-to-c/) |

## Deferred Items

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| v2 | JOBS-01: billable job registration with ROI view | Deferred | Init |
| v2 | SQUAD-01: fleet-level squad grouping | Deferred | Init |
| v2 | ANOM-01: anomaly detection across staged runs | Deferred | Init |

## Session Continuity

Last session: 2026-07-03T14:59:02.470Z
Stopped at: Completed Phase 06 Plan 01 — proceeding to Plan 02
Resume file: None
