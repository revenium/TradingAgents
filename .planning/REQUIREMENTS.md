# Requirements: TradingAgents × Revenium Demo

**Defined:** 2026-06-26
**Core Value:** A single live ticker run tells the complete Revenium story end to end — meter → trace → control → monetize — on a genuinely agentic, multi-provider trading workload.

## v1 Requirements

Requirements for the FCAT demo. Each maps to a roadmap phase.

### Foundation

- [x] **FND-01**: Demo config overrides the invalid default model names with valid current IDs (Anthropic for deep-think agents, OpenAI for quick-think agents) so a full run completes without model errors
- [x] **FND-02**: Revenium SDK packages (`revenium-python-sdk[langchain]`, `revenium-metering`) are installed and pinned; archived/double-counting packages are excluded
- [x] **FND-03**: The Revenium attribution hierarchy (Organization "Revenium-Research-Desk", Subscriber, Product "trading-signal", Subscription with pricing) is created before any metered call
- [x] **FND-04**: A single-call validation confirms exactly one Revenium event per LLM call, with non-zero token counts, attributed to the demo subscriber (not UNCLASSIFIED)

### Metering

- [x] **MTR-01**: Every LLM call across all agents is metered to Revenium with agent name, trace_id, task_type, and provider/model
- [x] **MTR-02**: Every metered call carries billing identifiers (organizationName, productName, subscriber.id)
- [x] **MTR-03**: Analyst data-fetch tools are metered (`@meter_tool`) so tool cost vs token cost is visible (the "cost iceberg"), with the sentiment-analyst `.func` bypass documented as an explicit exemption
- [x] **MTR-04**: A multi-provider run shows correct, distinct provider labels (Anthropic vs OpenAI) in Revenium's cost breakdown

### Trace & Squad Analytics

- [x] **TRC-01**: A full `propagate()` run appears in Revenium as one trace/squad with a per-agent Gantt timeline and the expected LLM span count
- [x] **TRC-02**: `parentTransactionId` is threaded across the graph so the agent dependency tree / critical path is visible
- [x] **TRC-03**: Circular-pattern detection fires on the bull/bear and risk debate loops, surfacing them as the cost hotspot

### Cost Controls

- [x] **CTL-01**: Revenium's circuit breaker gates the run — the middleware `check_enforcement()` pre-call hook (wired into the callback handler) raises `BudgetExceededError` when an enforce-mode cost rule is breached. Demo timing is made reliable **operationally** (low `REVENIUM_CB_POLL_INTERVAL_SECONDS`, pre-warmed/low threshold, dry-run validation), not via an in-process spend counter. _(Reworded in Phase 3 discussion — see 03-CONTEXT.md D-01/D-08: full reliance on Revenium enforcement, no client-side gate.)_
- [x] **CTL-02**: A breached rule raises `BudgetExceededError`, caught in `propagate()`/CLI and surfaced gracefully with cost context (the scripted mid-run halt)
- [x] **CTL-03**: A Revenium cost rule fires visibly during a run (dashboard enforcement event; optional Slack notification on a second screen)
- [x] **CTL-04**: Cost-control rules are confirmed in enforce (not shadow) mode ahead of the demo

### Billing & Monetization

- [x] **BIL-01**: A completed run emits one "cost per trading signal" billing event attributed to the desk/strategy customer
- [x] **BIL-02**: An invoice is generated with margin (price > AI cost) visible in Revenium's Costs & Revenue dashboard

### In-Repo CLI Surface

- [x] **CLI-01**: The existing Rich CLI shows a live per-agent running cost panel during a run
- [x] **CLI-02**: Debate-loop agents are annotated (e.g. ×N) in the panel so the cost hotspot is visible in-app

### Demo Narrative & Hardening

- [ ] **DMO-01**: A repeatable single-run demo script walks the meter → trace → control → monetize arc on a chosen ticker
- [ ] **DMO-02**: A pre-flight checklist/script validates model names, API keys/key types, enforce mode, Revenium connectivity, and Slack before the demo
- [ ] **DMO-03**: Graceful provider fallback so a single provider hiccup does not break the live run
- [ ] **DMO-04**: Repo tests pass without live Revenium/LLM keys — all Revenium calls are mockable and not required for the suite

### Jentic Tool Metering & Monetization

- [x] **JEN-01**: The Jentic async SDK (`search`→`load`→`execute`) is integrated via a sync wrapper (async→sync bridge), with `jentic` declared in pyproject/uv.lock and `JENTIC_AGENT_API_KEY` wired as a config key + `_ENV_OVERRIDES` entry; fail-soft (returns the `NO_DATA_AVAILABLE` sentinel on any Jentic error, never crashes the run)
- [x] **JEN-02**: A metered Jentic-backed tool (`@meter_tool`) is wired into the news analyst so each `execute()` emits exactly one Revenium tool event (`toolId`, `durationMs`, `success`) to `/v2/tool/events`, and each call is priced via a server-side per-call Revenium `ToolResource` registration (`POST /v2/api/tools`, `pricing.elements[].aggregationType=COUNT`, `ToolResource.toolId` matching the emitted `toolId`) so tool cost shows in dollars
- [x] **JEN-03**: The Jentic client is mockable — the full test suite passes with no `JENTIC_AGENT_API_KEY` and no network (DMO-04 discipline); tests assert the tool event payload, fail-soft sentinel, and async→sync bridge
- [x] **JEN-04**: A gated live-verify script proves a real metered+priced `execute()` end-to-end once a news API is credentialed in the user's Jentic account — PASSED 3/3 (2026-07-03): `validate_jentic.py` ran a real NewsAPI `getEverything` execute + fired 1 `jentic:news` tool event; `ToolResource` ($0.05/call COUNT) registered on `api.prod.ai.hcapp.io`. (Operator dashboard glance for the per-call cost is the final visual.)

### Pilot Partner Integrations

- [x] **PIL-01**: Edgehound is mocked as a Revenium-metered + priced tool (decision-intelligence: thesis / entry-exit / conviction) wired into the pipeline (research/trader); each call emits a tool event + its own per-call `ToolResource` price; config-gated + keyless-mockable
- [x] **PIL-02**: Trinigence is mocked as a Revenium-metered + priced strategy-generation tool (NL → strategy); config-gated + keyless-mockable
- [x] **PIL-03**: SAIF is mocked as a Revenium-metered + priced safety/assurance **gate** on the Portfolio Manager decision (pass/flag governance check, not a data tool); config-gated + keyless-mockable
- [x] **PIL-04**: All three partners are local mocks (no live deps), each with a colon-free `toolId` + per-call COUNT `ToolResource` registered via `setup_revenium.py` (upsert); full suite passes with no keys/network (DMO-04)

## v2 Requirements

Deferred — only if time permits after the v1 arc is solid (research P3).

### ROI & Fleet

- **JOBS-01**: Each run registered as a billable job with a `CONVERTED` outcome and value for an ROI view (requires write-scope key)
- **SQUAD-01**: Multiple runs grouped into a squad / fleet-level view
- **ANOM-01**: Anomaly detection across staged runs (needs a baseline distribution)

## Out of Scope

Explicitly excluded to prevent scope creep.

| Feature | Reason |
|---------|--------|
| OTLP / OpenTelemetry integration | Callback path chosen; OTLP lacks circuit breaker and risks double-counting if combined |
| Prompt / completion content capture | Not needed for the cost story; avoids sensitive-data handling |
| Audio / video / image metering | TradingAgents is text-only |
| Bedrock / `ChatBedrockConverse` provider verification | Anthropic + OpenAI tell the multi-provider story cleanly; Bedrock not required |
| Changing TradingAgents' trading/decision logic | This is an instrumentation + demo project, not a trading-quality project |
| Bespoke analytics dashboard | Revenium's product UI is the analytics surface (plus the in-repo CLI panel) |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| FND-01 | Phase 1 — Foundation & Metering | Complete |
| FND-02 | Phase 1 — Foundation & Metering | Complete |
| FND-03 | Phase 1 — Foundation & Metering | Complete |
| FND-04 | Phase 1 — Foundation & Metering | Complete |
| MTR-01 | Phase 1 — Foundation & Metering | Complete |
| MTR-02 | Phase 1 — Foundation & Metering | Complete |
| MTR-03 | Phase 1 — Foundation & Metering | Complete |
| MTR-04 | Phase 1 — Foundation & Metering | Complete |
| TRC-01 | Phase 2 — Trace & Squad Analytics | Complete |
| TRC-02 | Phase 2 — Trace & Squad Analytics | Complete |
| TRC-03 | Phase 2 — Trace & Squad Analytics | Complete |
| CTL-01 | Phase 3 — Cost Controls | Complete |
| CTL-02 | Phase 3 — Cost Controls | Complete |
| CTL-03 | Phase 3 — Cost Controls | Complete |
| CTL-04 | Phase 3 — Cost Controls | Complete |
| BIL-01 | Phase 4 — CLI Cost Panel & Billing Monetization | Complete |
| BIL-02 | Phase 4 — CLI Cost Panel & Billing Monetization | Complete |
| CLI-01 | Phase 4 — CLI Cost Panel & Billing Monetization | Complete |
| CLI-02 | Phase 4 — CLI Cost Panel & Billing Monetization | Complete |
| DMO-01 | Phase 5 — Demo Narrative & Hardening | Pending |
| DMO-02 | Phase 5 — Demo Narrative & Hardening | Pending |
| DMO-03 | Phase 5 — Demo Narrative & Hardening | Pending |
| DMO-04 | Phase 5 — Demo Narrative & Hardening | Pending |
| PIL-01 | Phase 7 — Pilot Partner Integrations | Complete |
| PIL-02 | Phase 7 — Pilot Partner Integrations | Complete |
| PIL-03 | Phase 7 — Pilot Partner Integrations | Complete |
| PIL-04 | Phase 7 — Pilot Partner Integrations | Complete |

**Coverage:**
- v1 requirements: 22 total
- Mapped to phases: 22/22
- Unmapped: 0

---
*Requirements defined: 2026-06-26*
*Last updated: 2026-06-26 after roadmap creation — traceability table populated*
