# Roadmap: TradingAgents x Revenium Demo

## Overview

This roadmap instruments the existing TradingAgents multi-agent LangGraph pipeline with Revenium's four pillars — meter, trace, control, monetize — and delivers a live, repeatable demo arc for Fidelity's FCAT group. Phase 1 fixes the two day-one blockers (invalid model names, missing billing hierarchy) and delivers core metering. Phases 2 and 3 layer on trace analytics and cost controls, which must be experienced in that order for the demo story to land. Phase 4 adds the in-repo CLI cost panel and billing events in parallel with Phase 3. Phase 5 hardens the single-run arc into a rehearsable, stage-reliable demo.

## Phases

**Phase Numbering:**

- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Foundation & Metering** - Fix model blockers, create Revenium attribution hierarchy, and meter every LLM call with agent/provider/billing context (completed 2026-06-27)
- [x] **Phase 2: Trace & Squad Analytics** - Thread trace IDs and parent transaction IDs to expose the debate-loop cost hotspot in Revenium's timeline (completed 2026-06-28)
- [x] **Phase 3: Cost Controls** - Gate the run with an in-process spend counter and wire Revenium enforcement rules so the demo halt is visible on stage (completed 2026-06-28)
- [x] **Phase 4: CLI Cost Panel & Billing Monetization** - Add a live per-agent cost panel to the Rich CLI and emit a priced "cost per trading signal" billing event (completed 2026-06-29)
- [ ] **Phase 5: Demo Narrative & Hardening** - Make the meter → trace → control → monetize arc repeatable, pre-flight checked, and stage-reliable
- [x] **Phase 6: Jentic Tool Metering & Monetization** - Weave Jentic's tool-execution SDK into the news analyst; meter + price every external API call through Revenium's tool-event pipeline (completed 2026-07-03)
- [ ] **Phase 7: Pilot Partner Integrations** - Mock Edgehound / Trinigence / SAIF as Revenium-metered+priced tools/gates; Revenium as the neutral FinOps layer across a multi-partner agentic ecosystem

## Phase Details

### Phase 1: Foundation & Metering

**Goal**: Every LLM call across all agents is metered in Revenium with correct provider labels, per-agent attribution, and billing identifiers — and the graph completes without model-name errors
**Mode:** mvp
**Depends on**: Nothing (first phase)
**Requirements**: FND-01, FND-02, FND-03, FND-04, MTR-01, MTR-02, MTR-03, MTR-04
**Success Criteria** (what must be TRUE):

  1. A full `propagate()` run completes without model-name errors (Anthropic on deep-think agents, OpenAI on quick-think agents)
  2. A single-call validation shows exactly one Revenium event per LLM call, with non-zero token counts, attributed to the demo subscriber (not UNCLASSIFIED)
  3. Revenium's cost breakdown shows two distinct provider labels (Anthropic and OpenAI) for a multi-provider run
  4. Analyst data-fetch tool calls appear in Revenium as separate metered events, making the tool-vs-token cost split visible
  5. Every metered call carries `organizationName`, `productName`, and `subscriber.id` so no events land in UNCLASSIFIED

**Plans**: 3 plansPlans:
**Wave 1**

- [x] 01-01-PLAN.md — Fix model blockers + provider split, install/pin Revenium SDK, register config keys, idempotent attribution-hierarchy setup script (FND-01/02/03)

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 01-02-PLAN.md — Thin end-to-end metering slice: context + client + callback handler wired into the graph; one correctly-attributed metered event proven (FND-04, MTR-01/02)

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 01-03-PLAN.md — Thicken coverage: per-agent contextvars, CLI wiring, @meter_tool on all data-fetch tools, two-provider label verification (MTR-03/04)

**Planning notes:**

- Pre-work A (day 1): Override `DEFAULT_CONFIG` model names with valid IDs (`claude-sonnet-4-6` deep-think, `gpt-4.1-mini` quick-think) before any Revenium code runs
- Pre-work B (day 1): Create Revenium attribution hierarchy (Organization `FCAT-Research-Desk`, Subscriber, Product `trading-signal`, Subscription with pricing) before the first metered call — attribution is not retroactive
- Research flag: Grep `agents/` and `llm_clients/` for `stream` calls to confirm non-streaming before relying on `on_llm_end` for all token counts
- Sentinel check: validate exactly 1 Revenium event per LLM invocation before wiring the full graph (double-counting via dual paths produces 2x wrong cost figures)
- Document the `sentiment_analyst.py:69` `.func` bypass as an explicit `@meter_tool` exemption

### Phase 2: Trace & Squad Analytics

**Goal**: A full `propagate()` run appears in Revenium as one trace with a per-agent Gantt timeline and the debate loops surfacing as the cost hotspot
**Mode:** mvp
**Depends on**: Phase 1
**Requirements**: TRC-01, TRC-02, TRC-03
**Success Criteria** (what must be TRUE):

  1. A full `propagate()` run appears in Revenium as a single trace/squad with the expected LLM span count and a per-agent Gantt timeline
  2. The bull/bear researcher debate loop and the risk debate loop are visually identified as the cost hotspot in the Revenium trace view
  3. `parentTransactionId` threading produces a visible agent dependency tree (or critical path), not a flat span list

**Plans**: 3 plans (1 gap-closure)

**Wave 1**

- [x] 02-01-PLAN.md — Parent-transaction threading + trace enrichment fields (trace_name/trace_type/transaction_name) through the Phase 1 callback path; keyless unit proof (TRC-01/02/03 payload half)

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 02-02-PLAN.md — Live validate_tracing.py + dashboard confirmation: span count N, dependency tree, debate-loop hotspot (circular or task_type fallback) (TRC-01/02/03 live) — validator shipped; live run caught GAP-02-01

**Wave 3** *(gap closure — blocked on Wave 2; closes GAP-02-01 / unblocks GAP-02-02)*

- [x] 02-03-PLAN.md — Move run-scoped trace state (trace_id + parent chain) off per-node contextvars onto the shared handler instance (begin_run/end_run, _last_transaction_id) so it survives LangGraph copy_context() per-node isolation; keyless cross-node regression test (29/29 tests pass); live re-validation PASSED (trace_id 3f88fe43, 19 spans, 10/10 checks) — closes GAP-02-01, unblocks GAP-02-02 (TRC-03)

**Planning notes:**

- Research flag: `parentTransactionId` chaining across LangGraph loopback conditional edges needs a live integration test — run one full graph, count spans in Revenium trace detail before treating circular pattern detection as demo-reliable
- Fallback: agent-field-based detection still surfaces debate loops as a cost hotspot if `parentTransactionId` loopback behavior is flat; document the fallback before the demo
- Validate by asserting one squad with N expected spans in Revenium trace detail before proceeding to Phase 3
- GAP (02-VERIFICATION.md): the Phase 2 research premise that a synchronous main thread keeps the parent-id contextvar visible to the next node is FALSE — LangGraph runs each node in its own `copy_context().run()`. Run-scoped trace state must live on the shared handler instance, not per-node contextvars. Closed by 02-03.

### Phase 3: Cost Controls

**Goal**: The graph halts mid-run at a configurable spend limit with a graceful CLI error, and Revenium's enforcement dashboard shows the event
**Mode:** mvp
**Depends on**: Phase 2
**Requirements**: CTL-01, CTL-02, CTL-03, CTL-04
**Success Criteria** (what must be TRUE):

  1. Revenium's circuit breaker gates the run — `check_enforcement()` raises a `BudgetExceededError` when an enforce-mode cost rule is breached; demo timing is made reliable operationally (low poll interval, pre-warmed threshold, dry-run validation), not via an in-process counter (per D-01/D-08)
  2. `propagate()` catches the error and surfaces it in the CLI with cost context — the run halts visibly mid-analysis
  3. A Revenium dashboard enforcement event is visible during the run (the audience sees the rule fire on screen)
  4. Cost control rules are confirmed in enforce mode (not shadow) before demo day

**Plans**: 3 plans

**Wave 1**

- [x] 03-01-PLAN.md — Enforcement gate: wire check_enforcement() into on_chat_model_start (before the fail-open try) so a breached enforce-mode rule raises BudgetExceededError; keyless propagation tests (CTL-01/02)
- [x] 03-02-PLAN.md — Provision the enforce-mode cost rule via idempotent setup_revenium.py (_setup_cost_rule, shadowMode:false); document CB .env knobs; finalize CTL-01 reword (CTL-04/03)

**Wave 2** *(blocked on 03-01)*

- [x] 03-03-PLAN.md — CLI halt panel + non-zero exit on BudgetExceededError (no fabricated decision); stop_polling() teardown in both paths; validate_controls.py timing dry-run (CTL-02/03/01)

**Planning notes:**

- Research flag: timing validation — run a stop-watch dry-run to confirm the in-process gate fires before the graph overshoots the threshold
- Confirm `shadow: false` on all cost rules at least 24 hours before the FCAT demo (include in pre-flight checklist, DMO-02)
- Optional: Slack notification on enforcement event fires on a second screen during demo

### Phase 4: CLI Cost Panel & Billing Monetization

**Goal**: Cost is visible in-app during a run (Rich CLI panel with per-agent costs) and a priced "cost per trading signal" billing event with margin is emitted after each completed run
**Mode:** mvp
**Depends on**: Phase 1
**Requirements**: CLI-01, CLI-02, BIL-01, BIL-02
**Success Criteria** (what must be TRUE):

  1. The Rich CLI shows a live per-agent running cost panel during a run — cost updates as each agent finishes
  2. Debate-loop agents are annotated (e.g., `×N`) in the CLI panel so the cost hotspot is visible in-app without opening Revenium
  3. A completed run emits one "cost per trading signal" billing event attributed to the desk/strategy customer
  4. An invoice is generated with margin (price > AI cost) visible in Revenium's Costs & Revenue dashboard

**Plans**: 4 plans (1 live-verification checkpoint)

**Wave 1** *(parallel — no file overlap)*

- [x] 04-01-PLAN.md — Live CLI cost panel: pricing.py local cost lookup, agent_costs cost+call_count schema extension (+ end_run reset), _build_cost_panel with hotspot highlight and ×N collapse wired into the Rich Live layout (CLI-01/CLI-02)
- [x] 04-02-PLAN.md — Billing building blocks + host de-risk: 3 config keys ($2.00 signal price + billing key + profitstream url), TradingSignalBillingEmitter fail-open wrapper around AgenticOutcomeClient, keyless-gated scripts/validate_billing.py smoke (BIL-01)

**Wave 2** *(blocked on 04-02)*

- [x] 04-03-PLAN.md — Wire billing into the graph: instantiate the emitter in TradingAgentsGraph.__init__, create_trading_signal_job at run start, emit exactly one billing event on the success path (none on BudgetExceededError); keyless placement tests (BIL-01/BIL-02)

**Wave 3** *(blocked on 04-01 + 04-03 — live verification checkpoint)*

- [ ] 04-04-PLAN.md — Live end-to-end verify: run validate_billing.py to confirm the profitstream host, then a full live ticker run confirming the cost panel (×N hotspot) and one billing event with positive margin in the Costs & Revenue dashboard (CLI-01/CLI-02/BIL-01/BIL-02)

**Planning notes:**

- CLI panel depends only on Phase 1's callback handler `agent_costs` dict — can be built in parallel with Phase 3
- Billing identifiers are already wired from Phase 1 pre-work — validate margin appears in Revenium dashboard at the start of this phase
- Pricing example: $2.00/signal = $1.20 AI cost + $0.80 margin; configure short billing cycle (5-minute period) for live invoice generation during demo
- ROADMAP **Goal** is in outcome form (not a user story); recommend `/gsd mvp-phase 04` to formalize. Plans carry a derived per-slice user story in the meantime.
- Open question to de-risk in Wave 1: which host serves the Jobs/Outcomes API (api.revenium.io default vs api.prod.ai.hcapp.io). validate_billing.py (04-02) confirms it before the graph wiring (04-03) is exercised live (04-04). Host is config-driven (`revenium_profitstream_url`).
- No new packages — `AgenticOutcomeClient` is already vendored; billing stays provider-agnostic (survives the deferred OpenRouter migration).

### Phase 5: Demo Narrative & Hardening

**Goal**: The meter → trace → control → monetize arc executes as a single rehearsed, pre-flight validated, stage-reliable run on a chosen ticker
**Mode:** mvp
**Depends on**: Phase 3, Phase 4
**Requirements**: DMO-01, DMO-02, DMO-03, DMO-04
**Success Criteria** (what must be TRUE):

  1. A single `demo.py` (or equivalent) script runs the full meter → trace → control → monetize arc on a chosen ticker without manual intervention
  2. A pre-flight script validates model names, API key types, enforce mode, Revenium connectivity, and Slack channel before any run — and fails fast with a human-readable error if anything is wrong
  3. A single provider hiccup does not break the live run (graceful fallback path is exercised in rehearsal)
  4. Repo tests pass without live Revenium or LLM keys — all Revenium calls are mockable and the suite is green on `pytest -m unit`

**Plans**: TBD

**Planning notes:**

- Set `REVENIUM_LOG_LEVEL=WARNING` for demo to suppress debug noise
- Pre-warm yfinance cache same day as demo with the chosen ticker
- Confirm `memory_log_max_entries` is bounded to avoid long memory-log parse time on demo run
- DMO-04 (tests pass without live keys) is the final test-discipline gate — must be green before FCAT

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 (parallel with 3) → 5

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Foundation & Metering | 3/3 | Complete   | 2026-06-27 |
| 2. Trace & Squad Analytics | 3/3 | Complete    | 2026-06-28 |
| 3. Cost Controls | 3/3 | Complete    | 2026-06-28 |
| 4. CLI Cost Panel & Billing Monetization | 3/4 | Complete    | 2026-06-29 |
| 5. Demo Narrative & Hardening | 0/? | Not started | - |
| 6. Jentic Tool Metering & Monetization | 3/3 | Complete   | 2026-07-03 |
| 7. Pilot Partner Integrations | 0/? | Not started | - |

### Phase 6: Jentic Tool Metering & Monetization

**Goal**: A live TradingAgents run has the news analyst fetch external data through Jentic's `execute()` API, with every Jentic tool call metered by Revenium as a tool event and priced via a per-call Revenium tool price model — demonstrating Revenium's tool-usage metering + monetization on real third-party API calls (extends MTR-03).
**Mode:** mvp
**Depends on**: Phase 1 (tool-metering foundation — `@meter_tool` → `/v2/tool/events`)
**Requirements**: JEN-01, JEN-02, JEN-03, JEN-04
**Success Criteria** (what must be TRUE):

  1. The news analyst calls a Jentic-executed external API during a run; each `execute()` emits exactly one Revenium tool event (`toolId`, `durationMs`, `success`) visible in the Revenium tool dashboard
  2. Each Jentic tool call is priced via a server-side per-call Revenium `ToolResource` registration (`POST /v2/api/tools`, `pricing.elements[].aggregationType=COUNT`, `ToolResource.toolId` matching the emitted tool-event `toolId`) — NOT `metering-element-definitions` — so tool cost shows in dollars in the Revenium Tools view
  3. The full test suite passes with NO Jentic or Revenium keys — the Jentic client is mockable (DMO-04 discipline)
  4. Live end-to-end verified once a news API is credentialed in the user's Jentic account (live verification gated on that prereq)

**Plans**: 3 plans (1 live-verification checkpoint)

**Wave 1**

- [x] 06-01-PLAN.md — Foundation: declare jentic dep + regen uv.lock, 5 jentic_* config keys + env overrides, keyless conftest guard, package-legitimacy checkpoint (JEN-01)

**Wave 2** *(blocked on 06-01)*

- [x] 06-02-PLAN.md — Metered Jentic news tool (sync wrapper + async bridge + fail-soft), TDD unit suite, agent_utils re-export, conditional news-analyst wiring; keyless suite green (JEN-01/02-code/03)

**Wave 3** *(blocked on 06-02 — operator-gated live steps)*

- [x] 06-03-PLAN.md — Server-side per-call ToolResource pricing in setup_revenium.py + gated scripts/validate_jentic.py + operator live-verify checkpoint (JEN-02-pricing/JEN-04)

**Planning notes:**

- Spike (`jentic==0.10.0`): async SDK `search → load → execute`; `ExecuteResponse{success, status_code, output, error, step_results, inputs}` returns NO cost/latency/tokens — measure duration ourselves; price per-call server-side.
- Revenium tool event (`_send_tool_event` → POST `{url}/v2/tool/events`) has NO price field — pricing is Revenium-side via a **`ToolResource`** registered at `POST /v2/api/tools` with `pricing.elements:[{name, unitPrice, aggregationType:"COUNT"}]`, whose `toolId` must equal the emitted tool-event `toolId` (research-corrected; NOT `/v2/api/metering-element-definitions`, which is analytics-dimension metadata).
- Build API-agnostic: target op-id / search-query driven by config, so it can target any credentialed API. Only `anthropic`/`openai`/`fred` are credentialed today; the user will credential a news API in the Jentic dashboard, which swaps in via config with zero code change.
- Async→sync bridge: sync `@meter_tool` func that does `asyncio.run(client.execute(...))` internally; fail-soft (return NO_DATA sentinel, never crash the run — matches vendor-router convention).
- Prereqs: add `jentic` to `pyproject.toml`/`uv.lock`; add `JENTIC_AGENT_API_KEY` config key + `_ENV_OVERRIDES` entry; user credentials a news API in Jentic + creates the Revenium tool price model.
- Keyless: mock `jentic.Jentic` so the suite is green without the key; ship a live-verify script gated on the news-API prereq.
- Requirements: JEN-01 Jentic SDK sync-wrapper + config/env; JEN-02 metered+priced tool wired into news analyst; JEN-03 keyless mockable (DMO-04); JEN-04 live end-to-end verification (gated).

### Phase 7: Pilot Partner Integrations

**Goal**: Three pilot-partner services are integrated into the demo as **mocked, Revenium-metered AND priced** tools/gates — extending the Phase 6 tool-metering+monetization pattern to a multi-partner agentic ecosystem so Revenium is shown as the neutral FinOps layer across partners.
**Mode:** mvp
**Depends on**: Phase 6 (reuses `@meter_tool` + `ToolResource` per-call pricing pattern)
**Requirements**: PIL-01, PIL-02, PIL-03, PIL-04
**Success Criteria** (what must be TRUE):

  1. A run with partners enabled emits **3 distinct partner tool events** in Revenium — Edgehound (decision-intelligence), Trinigence (strategy-generation), SAIF (safety/assurance gate) — each with its own per-call `ToolResource` price
  2. Each mock returns plausible, domain-appropriate output; **SAIF is modeled as a safety/assurance GATE** on the Portfolio Manager decision (pass/flag governance beat), NOT a data tool
  3. Config-gated (per-partner enable flags) + keyless-mockable — full suite green with NO keys and NO network (DMO-04)
  4. Each partner's `ToolResource` is registered (colon-free `toolId`s) with per-call COUNT pricing via `setup_revenium.py` (upsert path)

**Plans**: 3 plans

Plans:
- [ ] 07-01-PLAN.md — Edgehound decision-intelligence mock tool (metered+priced, wired into market analyst)
- [ ] 07-02-PLAN.md — Trinigence NL→strategy mock tool (metered+priced, wired into market analyst)
- [ ] 07-03-PLAN.md — SAIF assurance gate on PM decision (metered+priced) + 3-partner ToolResource registration + combined keyless integration test

**Planning notes (scoping locked 2026-07-03):**

- **ALL MOCKED** (user decision): all three are local `@meter_tool` mocks — NO live partner deps, NO Jentic dependency for these (Jentic route needs an OpenAPI spec credentialed in Jentic; not worth it for mocks + stage reliability). Reuse Phase 6 analogs: `jentic_news_tools.py` for a mock tool, `register_jentic_tool`/`_update_tool_pricing` for the ToolResource, config keys + `_ENV_OVERRIDES` + keyless conftest.
- **METERED + PRICED** (user decision): each partner gets its own `ToolResource` per-call price (colon-free toolIds, e.g. `edgehound_decision`, `trinigence_strategy`, `saif_assurance` — Revenium UI rejects ':').
- Partner shapes differ: **Edgehound** = decision-intelligence tool (thesis/entry-exit/conviction) wired into research/trader; **Trinigence** = NL→strategy generation tool; **SAIF** = pre-finalization **safety/assurance gate** on the PM decision (a check node/hook, not a data fetch — different integration point).
- What each is: Edgehound (edgehound.com — AI decision-intelligence for capital markets, HAS an API but we mock it), Trinigence (docs.trinigence.com — NL→trading strategies + backtesting, no public API), SAIF (saifautonomy.com — safety/assurance for autonomous/physical-AI systems, consultative, no API).
- Requirements: PIL-01 Edgehound mock tool (metered+priced); PIL-02 Trinigence mock tool (metered+priced); PIL-03 SAIF mock assurance-gate (metered+priced) on PM decision; PIL-04 config-gated + keyless-mockable + ToolResources registered (upsert, colon-free).
