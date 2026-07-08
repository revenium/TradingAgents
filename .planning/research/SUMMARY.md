# Project Research Summary

**Project:** TradingAgents x Revenium FCAT Demo
**Domain:** AI cost metering / FinOps instrumentation on a multi-agent LangGraph pipeline
**Researched:** 2026-06-26
**Confidence:** HIGH

---

## Executive Summary

This project instruments an existing multi-agent LLM trading-research framework (TradingAgents) with Revenium's cost metering, trace analytics, cost controls, and billing platform to produce a live demo for Fidelity's FCAT group. The demo arc is meter → trace → control → monetize executed in a single ticker run. The workload is genuinely well-suited: TradingAgents generates 10–14 LLM calls per run across multiple providers, with looping bull/bear and risk debates that are the natural cost hotspot Revenium's trace and control pillars showcase. The framework's existing `callbacks=` mechanism in `TradingAgentsGraph` and `llm_clients/factory.py` provides a single, provider-neutral seam that covers all 15+ providers with one handler — making the integration additive, not refactoring.

The recommended integration path is a custom `ReveniumCallbackHandler` (`BaseCallbackHandler` subclass) added to the existing `callbacks` list in `TradingAgentsGraph`. This is the correct choice for this project: TradingAgents uses non-streaming LLM calls (`graph.invoke`, not `graph.stream`), which eliminates the primary risk of the callback path (missing token data on streaming `on_llm_end`). The OTLP/OpenTelemetry alternative offers no advantage here and introduces cost-control gaps (no circuit breaker on OTLP path) and double-counting risk if both paths are activated. `contextvars` carry `trace_id` and agent identity across the full graph without touching `AgentState`, and each agent node function sets a one-line contextvar for identity — 13 one-line changes, zero topology changes.

The critical risks for the demo are front-loaded in pre-work: the Revenium customer/product/attribution hierarchy (Organization, Subscriber, Product, Subscription) must be created before any metering call is made because Revenium attribution is not retroactive — events without identifiers land in UNCLASSIFIED and cannot be reclassified. The default model names in `DEFAULT_CONFIG` (`gpt-5.5`, `gpt-5.4-mini`) do not exist in the OpenAI API and will cause immediate failures; they must be overridden before any integration work begins. With those two items addressed on day one, the integration proceeds along a well-defined dependency chain (client → context → callback → cost gate → CLI panel → billing) that delivers each demo pillar incrementally.

---

## Integration Path Decision: Callback vs. OTLP

This section resolves the cross-cutting tension between research files before the roadmap is built.

**The tension:** PITFALLS warns that the LangChain `on_llm_end` callback path can miss token data on streaming calls (real LangChain bugs, issues #34057 and #30429), and in those sections recommends the OTLP/provider-level OTel path as immune. STACK and ARCHITECTURE both recommend the callback path as primary.

**Resolution: The callback path is correct for this project. OTLP is not needed and must not be combined with the callback path.**

TradingAgents uses `graph.invoke()` (non-streaming) throughout. ARCHITECTURE explicitly documents this: Anti-Pattern 4 states "Current graph runs non-streaming (`graph.invoke`, not `graph.stream`)." The streaming token-count bug in `on_llm_end` does not apply. The callback path retains all its advantages:

- Circuit breaker / `BudgetExceededError` enforcement (only available on the callback path — not on OTLP)
- Native `agent`, `trace_id`, and billing metadata fields (first-class in `ReveniumCallbackHandler`; require manual span tagging in OTLP)
- Zero extra infrastructure (no OTel collector, no exporter config)
- Direct fit with the existing `TradingAgentsGraph(callbacks=...)` pattern

**The one streaming open item:** Verify in Phase 1 (grep codebase for `stream`) that no agent or client uses streaming. This is expected to confirm non-streaming — it is a validation step, not an expected finding.

**Rule: Do not run both paths simultaneously.** `ReveniumCallbackHandler` and any Revenium OTLP/OTel instrumentation must never be active at the same time for the same LLM call. If OTLP is needed in the future (e.g., streaming is adopted), disable the callback handler first.

---

## Mandatory Pre-Work (Blocks All Phase 1 Code)

**Pre-work A: Fix model names in demo config.**
Create a demo-specific config override dict with valid, currently-available model IDs. `DEFAULT_CONFIG` values (`gpt-5.5`, `gpt-5.4-mini`) cause immediate API failures before any Revenium code runs. Suggested demo models: `claude-sonnet-4-6` (Anthropic, deep-think: Research Manager, Portfolio Manager), `gpt-4.1-mini` (OpenAI, quick-think: analysts). These two providers will show correct provider labels in Revenium — Anthropic via native `ChatAnthropic`, OpenAI via direct `ChatOpenAI`. Validate by running `python main.py` with explicit overrides before touching Revenium code.

**Pre-work B: Create Revenium customer/product/attribution hierarchy.**
In the Revenium UI (or via the Revenium MCP connector available in this environment): create Organization `"FCAT-Research-Desk"`, Subscriber `desk-a@fidelity.com`, Product `"trading-signal"` with a pricing tier (e.g., $2.00/signal = $1.20 AI cost + $0.80 margin), and Subscription linking them. Confirm the Revenium account credentials and API key type (`rev_mk_` for metering, `rev_sk_` for Jobs API write operations). Wire all three identifiers (`organizationName`, `productName`, `subscriber.id`) into the very first metering test call. Verify non-UNCLASSIFIED attribution in Revenium UI before proceeding. This cannot be done retroactively.

---

## Key Findings

### Recommended Stack

Two packages added to the TradingAgents venv: `revenium-python-sdk[langchain]>=0.1.9` and `revenium-metering>=6.8.2`. The `[langchain]` extra installs `ReveniumCallbackHandler`, which is the same `BaseCallbackHandler` contract as the existing `StatsCallbackHandler`. The standalone `revenium-middleware-langchain` package is archived (v0.1.3, no new features since June 2026) and must not be installed alongside the unified SDK — this is one of the documented double-counting paths.

For the FCAT multi-provider story: native `ChatAnthropic` and direct `ChatOpenAI` are the two providers to use in the demo — they receive correct provider labels in Revenium. The 15 OpenAI-compatible base-URL providers (xAI, DeepSeek, OpenRouter, etc.) are all labeled "openai" by the callback handler; this is a Revenium limitation. Running Anthropic on deep-think agents and OpenAI on quick-think agents cleanly demonstrates cross-provider cost attribution.

**Core technologies:**
- `revenium-python-sdk[langchain]` 0.1.9: primary integration — `ReveniumCallbackHandler` drops into `TradingAgentsGraph(callbacks=[stats, revenium])` with zero changes to the existing seam
- `revenium-metering` 6.8.2: transitive dep; also provides `@meter_tool` decorator for analyst data-fetch functions and `AgenticOutcomeClient` for Jobs API (Phase 3 defer)
- `python-dotenv` (already in project): loads `REVENIUM_METERING_API_KEY` from `.env`

**Do not use:**
- `revenium-middleware-langchain` (archived) — superseded; causes double-counting if installed alongside SDK
- OTLP/OpenTelemetry path — no circuit breaker, more setup, double-counting risk if combined with callback path
- Individual provider middleware imports (`revenium_middleware_openai`, `revenium_middleware_anthropic`) alongside `ReveniumCallbackHandler` — wraps raw provider SDK not LangChain; will double-meter

### Expected Features

**Must have (P1 — metering and billing foundation):**
- Every LLM call metered with `agent`, `trace_id`, `task_type`, `organizationName`, `productName`, `subscriber` — prerequisite for all other pillars
- `@meter_tool` on analyst data-fetch functions — surfaces "cost iceberg" (data vs token costs)
- Full `propagate()` run appears as one trace in Revenium with per-agent Gantt timeline
- One cost alert rule firing visibly during the demo run
- `BudgetExceededError` caught and surfaced gracefully — enforcement halts the graph mid-run
- Invoice auto-generated with margin visible in Costs & Revenue dashboard

**Should have (P2 — trace depth and in-app cost visibility):**
- `parentTransactionId` threading → circular pattern detection on debate loops (the "aha" moment), critical path analysis, agent interaction matrix
- In-CLI Rich cost panel showing live per-agent running cost
- Slack notification for cost control alert (visual on second screen)
- Margin dashboard visible in Revenium

**Defer (P3 — only if time permits after P1+P2 polished):**
- Jobs API — register each run as a billable job with outcome for ROI view (requires write-scope key)
- Squad registration — multiple runs grouped for fleet-level view (needs run volume to populate)
- Anomaly detection — needs pre-run staging iterations for a distribution

**Never build:**
- OTLP integration, prompt capture, audio/video/image metering

### Architecture Approach

The `tradingagents/revenium/` package is self-contained and imported one-way by `trading_graph.py`. The `ReveniumCallbackHandler` attaches to the existing `callbacks=` kwarg path that already flows from `TradingAgentsGraph.__init__` through `create_llm_client` into every provider's LangChain ChatModel. `contextvars` carry `trace_id`, `run_meta`, and `current_agent_name` across the full graph without touching `AgentState`. Each agent node function sets a one-line contextvar at its top — 13 one-line changes, no topology changes. Post-run, a `ReveniumBillingEmitter` fires a single "trading signal" billing event after `graph.invoke()` succeeds.

**Major components:**
1. `tradingagents/revenium/callback.py` — `ReveniumCallbackHandler`: fires `meter_ai_completion` async (fire-and-forget) in `on_llm_end`; checks cost gate post-response; maintains `agent_costs` dict for CLI panel
2. `tradingagents/revenium/context.py` — `ContextVar` bundle (`trace_id`, `run_meta`, `current_agent_name`) set at `propagate()` entry; visible in all callbacks without state threading
3. `tradingagents/revenium/cost_gate.py` — loads enforcement rules from Revenium at run start; implements in-process spend counter for reliable demo timing; raises `CostLimitExceeded` at hard limit
4. `tradingagents/revenium/billing.py` — fires "trading signal" unit billing event post-run with margin multiplier
5. `cli/cost_panel.py` — Rich `Table` reading `handler.agent_costs`; added to existing `Layout` alongside stats panel

**Build order within the integration:** client + config → context machinery + one-line contextvar sets in agents → `ReveniumCallbackHandler` wired into `TradingAgentsGraph` → cost gate → CLI panel (parallel with cost gate) → billing emitter.

### Critical Pitfalls

1. **Double-counting via dual metering paths** — Installing archived `revenium-middleware-langchain` alongside the unified SDK, or activating OTLP instrumentation while the callback handler is also wired, generates two metering events per LLM call and makes demo cost figures 2x wrong. Prevention: use exactly one path (callback handler); verify with single-call sanity check (1 Revenium event per LLM invocation) before wiring the full graph.

2. **Missing billing identifiers → UNCLASSIFIED attribution, not retroactively fixable** — Events without `subscriber.id`, `productName`, and `organizationName` land in UNCLASSIFIED permanently. Prevention: create Revenium Organization/Subscriber/Product/Subscription before writing any instrumentation code; wire all three identifiers into the first test call; validate in Revenium UI immediately.

3. **Speculative default model names cause immediate pre-Revenium failure** — `DEFAULT_CONFIG` sets `gpt-5.5` and `gpt-5.4-mini`, which do not exist in the OpenAI API. The graph fails at the first analyst node before any Revenium code executes. Prevention: override both model keys with valid current IDs in demo config before any integration work begins.

4. **Cost control race condition — enforcement fires after the expensive node, not before** — Revenium server-side enforcement has network round-trip latency (200ms–2s); OTel batch export adds up to 5 seconds by default. The graph can overshoot the threshold before enforcement fires. Prevention: implement an in-process spend counter in `ReveniumCostGate` that gates execution locally; use Revenium enforcement as the audit/backstop.

5. **Shadow mode confusion on stage** — Cost control rules in shadow (observe-only) mode allow the graph to run through the threshold without halting. Prevention: switch rules to enforce mode ≥24h before the demo; include a pre-demo checklist item confirming `shadow: false` via the rules API.

---

## Implications for Roadmap

### Phase 1: Foundation — Demo Config, Revenium Setup, and Core Metering

**Rationale:** Fixes both blockers (invalid models, missing billing hierarchy) and delivers the metering pillar, which every other pillar depends on. Cannot demo any Revenium capability without this.
**Delivers:** Every LLM call metered in Revenium with correct provider label, per-agent attribution, and billing identifiers. Single test call shows exactly one Revenium event with non-zero token counts attributed to the demo subscriber. `@meter_tool` on data-fetch functions shows tool vs token cost split.
**Addresses:** All P1 metering features; `@meter_tool` on analyst tools.
**Avoids:** Pitfalls 3 (model names), 7 (billing identifiers), 8 (API key type), 1 (double-counting via validation).
**Research flag:** Standard patterns — no additional research needed. `StatsCallbackHandler` is the blueprint for the callback handler.

### Phase 2: Trace and Squad Analytics

**Rationale:** `trace_id` already flows from Phase 1. Phase 2 adds `parentTransactionId` to enable the dependency tree, circular pattern detection, and critical path analysis. Circular pattern detection on the debate loops is the demo's "aha" moment — the cost hotspot becomes visually obvious without the audience reading code.
**Delivers:** Full trace timeline in Revenium (Gantt per agent); circular pattern detection firing on bull/bear and risk debate loops; critical path visualization. Full `propagate()` run appears as one squad with the expected LLM span count.
**Implements:** `parentTransactionId` threading (one new field in `AgentState` or via contextvar); squad registration.
**Avoids:** Pitfall 4 (trace fragmentation) — validate by asserting one squad with N expected spans in Revenium trace detail before proceeding.
**Research flag:** `parentTransactionId` chaining across LangGraph loopback conditional edges needs a live integration test. Plan for a trace-continuity verification step — run one full graph, count spans in Revenium.

### Phase 3: Cost Controls

**Rationale:** Requires metering live (Phase 1) and is most compelling after the audience has seen the trace showing debate loops as the cost driver (Phase 2). Enforcement demo lands hardest when the audience already understands the cost pattern being controlled.
**Delivers:** In-process spend counter gates the graph at a configurable hard limit. `BudgetExceededError` caught in `TradingAgentsGraph.propagate()` and surfaced in CLI with cost context. Revenium dashboard shows the enforcement event. Slack notification fires on second screen.
**Implements:** `ReveniumCostGate` (load limits at run start, check in `on_llm_end`); soft/hard limit display in CLI; `BudgetExceededError` catch and recovery path in `trading_graph.py`.
**Avoids:** Pitfall 5 (race condition — in-process counter is real-time gate); Pitfall 6 (shadow mode — enforce mode confirmed 24h before demo with stop-watch dry-run).
**Research flag:** Standard patterns. Timing validation via stop-watch dry-run is the key verification.

### Phase 4: CLI Cost Panel and Billing Monetization Polish

**Rationale:** CLI cost panel depends only on the callback handler (Phase 1) and can be built in parallel with Phase 3. Billing polish (margin dashboard, short billing cycle for live invoice) rounds out the monetize pillar. Together these ensure cost is visible both in-app and in Revenium.
**Delivers:** Live per-agent cost table in the Rich CLI with `×N` annotation on debate-loop agents; invoice auto-generated with margin visible; `ReveniumBillingEmitter` fires post-run with margin multiplier.
**Implements:** `cli/cost_panel.py` Rich Table reading `handler.agent_costs`; `ReveniumBillingEmitter` post-run call; margin multiplier config key; short billing cycle (5-minute period) for demo invoice generation.
**Avoids:** Pitfall 7 (billing identifiers already wired from Phase 1 pre-work — validate margin appears in dashboard at start of this phase).
**Research flag:** Standard patterns. Jobs API (P3 defer) would need write-scope key format verification if time permits.

### Phase 5: Demo Narrative and Hardening

**Rationale:** All four pillars must work end-to-end in a repeatable, rehearsed run before the FCAT presentation. Rough edges that are acceptable in development become visible failures on stage with a technical audience.
**Delivers:** A repeatable single-run demo script with pre-flight checks; graceful provider fallback; demo config pinned to valid model IDs; enforce mode confirmed; Revenium UI tabs open and positioned; dry-run timing confirmed; full meter → trace → control → monetize arc rehearsed.
**Implements:** Pre-flight validation script (model names, API keys, enforce mode, Revenium connectivity, Slack channel); `REVENIUM_LOG_LEVEL=WARNING` for demo; `memory_log_max_entries=200` to bound memory-log parse time; yfinance cache pre-warmed same day.
**Avoids:** All pitfalls — this phase is the verification pass across all of them.
**Research flag:** No research needed. Demo rehearsal is the validation.

### Phase Ordering Rationale

- Phase 1 before everything: metering is the foundational dependency for all other pillars, and billing identifiers must exist before the first metering call (attribution is not retroactive).
- Phase 2 before Phase 3: circular pattern detection gives the audience the context ("the debate loops are the cost driver") that makes the enforcement demo in Phase 3 land with meaning.
- Phase 4 in parallel with Phase 3: the CLI cost panel only depends on Phase 1's callback handler; building it alongside Phase 3 ensures it is ready for the enforcement demo.
- Phase 5 last: cannot harden what is not yet functional.

### Research Flags

Phases needing deeper verification during planning:
- **Phase 1:** Grep codebase for `stream` calls to confirm non-streaming. Expected to find nothing, but must be verified before relying on `on_llm_end` for all token counts.
- **Phase 2:** `parentTransactionId` threading across LangGraph loopback conditional edges is the architectural unknown. Run a live integration test (one full graph run, count spans in Revenium trace detail) before treating circular pattern detection as reliable for the demo.

Phases with standard patterns (no additional research needed):
- **Phase 1 (callback handler, config, contextvar):** `StatsCallbackHandler` is the exact blueprint; established patterns.
- **Phase 3 (cost controls):** In-process counter is standard; Revenium SDK circuit breaker docs are complete.
- **Phase 4 (CLI panel, billing emitter):** Rich layout patterns established; billing emitter is a single API call.
- **Phase 5 (demo hardening):** No research — execution and rehearsal.

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Package names, versions, and LangChain compatibility verified against PyPI JSON API and official GitHub README. Provider coverage matrix verified. No dependency conflicts with TradingAgents' pinned versions. |
| Features | HIGH | All four pillar features confirmed against Revenium docs sitemap, llms.txt API index, and official SDK README. P1/P2/P3 priority split grounded in dependency order. |
| Architecture | HIGH | Integration seams read directly from codebase files. `contextvars` pattern is well-established for cross-cutting observability. One open item: `parentTransactionId` behavior across loopback edges needs live verification. |
| Pitfalls | HIGH | LangChain streaming bugs verified from upstream GitHub. Trace fragmentation pattern verified from Langfuse issue. Billing UNCLASSIFIED behavior verified from Revenium tutorial. Default model names verified from codebase. |

**Overall confidence:** HIGH

### Gaps to Address

- **Streaming usage (must verify in Phase 1):** Grep `agents/` and `llm_clients/` for `stream` calls. Expected: none. If found: add tiktoken fallback token estimation to `ReveniumCallbackHandler.on_llm_end`.

- **`ChatBedrockConverse` callback coverage (MEDIUM confidence):** Provider coverage matrix rates Bedrock as covered but `ChatBedrockConverse` (Converse API subclass) was not explicitly verified against callback handler provider detection. For the demo, Bedrock is not required — the Anthropic + OpenAI pair tells the multi-provider story cleanly. Defer Bedrock verification.

- **Revenium account credentials and key types:** Metering key (`rev_mk_*`) and, if Jobs API is used, write-scope key (`rev_sk_*`) must be confirmed before Phase 1 begins. Use the Revenium MCP connector available in this environment for ad-hoc account setup.

- **`parentTransactionId` field behavior:** Whether chaining this field across LangGraph loopback edges produces a dependency tree vs. a flat list needs live testing in Phase 2. Fallback: agent-field-based detection still surfaces the debate loops as a cost hotspot, just with less visual drama.

- **Sentiment analyst `.func` bypass:** `sentiment_analyst.py:69` calls `get_news.func()` directly, bypassing the `@tool` wrapper. This is a data-fetch call, not an LLM call — it does not affect token metering. But if `@meter_tool` is applied to `get_news` expecting to capture a tool event, this bypass will miss it. Document the exemption explicitly in Phase 1.

---

## Sources

### Primary (HIGH confidence)

- PyPI JSON API for all Revenium packages — version numbers, archive notices, dependency graphs
- `revenium-python-sdk` GitHub README — provider support matrix, LangChain integration, circuit breaker, env vars, metadata fields
- Revenium docs (`docs.revenium.io`) — billing tutorial, customer/credentials model, cost controls, agent instrumentation guide, tool metering, OTLP integration, agent outcomes/Jobs API
- `revenium.readme.io/llms.txt` — full API index
- TradingAgents codebase files read directly — `trading_graph.py`, `factory.py`, `base_client.py`, `stats_handler.py`, `agent_states.py`, `default_config.py`, `conditional_logic.py`
- LangChain upstream issues #34057, #30429 — streaming `llm_output` gap
- Langfuse issue #10962 — LangGraph interrupt-resume trace fragmentation

### Secondary (MEDIUM confidence)

- Revenium OTLP integration docs (partially loaded) — OTLP endpoint URLs, OTel env var names, authorization header percent-encoding caveat
- Revenium billing/monetization pages (partially loaded) — products, metering elements, subscriber attribution, invoice generation
- Last9 blog — LangGraph async context loss and orphaned span patterns
- `.planning/codebase/CONCERNS.md` — known codebase issues (global config singleton, `.func` bypass, speculative model names)

### Tertiary (LOW confidence, needs validation)

- Revenium `ChatBedrockConverse` callback coverage — rated covered but Converse API subclass not explicitly verified; validate in Phase 1 if Bedrock is used
- Revenium Jobs API write-scope key availability in the demo account — referenced in docs but not confirmed

---

*Research completed: 2026-06-26*
*Ready for roadmap: yes*
