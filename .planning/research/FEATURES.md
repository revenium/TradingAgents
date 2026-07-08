# Feature Research

**Domain:** Revenium capability demo on a multi-agent LLM trading workload (TradingAgents x Revenium, FCAT audience)
**Researched:** 2026-06-26
**Confidence:** HIGH (verified against Revenium Python SDK README, docs.revenium.io sitemap pages, and revenium.readme.io LLM index)

---

## Context: Demo Structure and Audience

The demo is a single live ticker run that walks FCAT (Fidelity's Center for Applied Technology) through four Revenium pillars in order: **meter → trace → control → monetize**. FCAT is a technical R&D group with a trading and FinOps mindset. Credibility requires the demo to feel real (multi-provider, live LLM calls, genuine cost numbers) not scripted.

The workload: TradingAgents' LangGraph pipeline has 10–14 LLM calls per run across up to 4 analysts + 2 debate loops (bull/bear: 2×N rounds) + 3 risk debaters + research manager + trader + portfolio manager. The debate loops are the natural cost hotspot — they are exactly what Revenium's trace and control pillars showcase.

---

## Pillar 1: Metering & Cost Tracking

### What Revenium Can Meter

**Modalities supported:**
- `meter_ai_completion` — LLM completions (input tokens, output tokens, cache read tokens, cache creation tokens, latency, stop reason, model, provider)
- `meter_ai_audio` — audio transcription/TTS/translation
- `meter_ai_images` — image generation/editing
- `meter_ai_video` — video generation/editing
- `meter_tool_event` — tool/function calls (toolName, costUsd, latency, success)
- `meter_event` — generic custom events
- OTLP ingestion — OpenTelemetry logs/metrics/traces (alternative to SDK)

For this demo: only `meter_ai_completion` and `meter_tool_event` are needed.

**Metadata dimensions the app can attach per call:**

| Field | Purpose | Required for Demo? |
|-------|---------|-------------------|
| `agent` | Which agent made the call (e.g., "Market Analyst", "Bull Researcher") | YES — enables per-agent cost breakdown |
| `trace_id` | Groups all calls in one `propagate()` run into one trace | YES — foundation of trace pillar |
| `task_type` | Operation category (e.g., "market-analysis", "risk-debate") | YES — enables cost-by-task view |
| `organizationName` | Customer account (e.g., "Equity Desk A") | YES — billing attribution |
| `productName` | Commercial tier (e.g., "Trading Signal") | YES — links to billing product |
| `subscriber.id` / `subscriber.email` | End customer identity | YES — for invoice generation |
| `environment` | "production" / "demo" | Optional |
| `region` | Cloud region | Optional |
| `response_quality_score` | Custom 0.0–1.0 quality score | Optional |
| `parentTransactionId` | Establishes parent/child call chain for dependency tree | NICE — enables critical path visualization |
| `agenticJobId` | Links all calls to a business outcome / Job | NICE — enables ROI view |

**Integration mechanism for TradingAgents:**

The Python SDK provides:
- `ReveniumCallbackHandler` (LangChain/LangGraph callback) — attaches to the existing LangChain callback infrastructure that `cli/stats_handler.py` already uses. Pass `trace_id` and `agent` per invocation. This is the lowest-effort path.
- `@revenium_metadata` decorator — wraps a function; all LLM calls inside inherit the metadata. Can wrap each `create_*(llm)` agent node factory.
- `@meter_tool` decorator — wraps data-fetching tool functions to meter external service calls with timing and success tracking.
- Direct `usage_metadata` dict on provider SDK calls — fallback for providers not covered by a callback.

**What the app must emit for metering to light up:**
1. `REVENIUM_METERING_API_KEY` env var set
2. One import per provider middleware (`revenium_middleware_anthropic`, `revenium_middleware_openai`, etc.) — auto-initializes on import
3. `trace_id` set to a run-unique string (e.g., `f"{ticker}-{date}-{uuid4().hex[:8]}"`) before graph invocation
4. `agent` set to the agent name at each node — either via `@revenium_metadata` on the node function or via the `ReveniumCallbackHandler`
5. `organizationName`, `productName`, `subscriber` passed for billing dimension

**Cost analytics auto-available once metering is on:**
- Cost by model, provider, agent, task type, product, team, user — no additional config
- Token breakdown: input / output / cache read / cache creation
- Latency by model and vendor
- Tool cost vs token cost comparison ("cost iceberg")
- API key cost tracking

---

### Table Stakes — Metering Pillar

| Feature | Why Expected | Complexity | App Must Emit | Demo Pillar |
|---------|--------------|------------|--------------|-------------|
| Every LLM call metered with model + provider + token counts | FCAT expects cost to be tracked at the call level — this is the baseline | LOW — one import per provider + env var | Provider middleware import, `REVENIUM_METERING_API_KEY` | Metering |
| Per-agent cost attribution (which agent spent what) | The multi-agent story requires agent-level breakdown to be credible | LOW — pass `agent` field per call | `agent` field on each LLM call | Metering |
| Cost visible in Revenium UI during the run | The demo needs live cost numbers on screen | LOW — auto after metering | nothing extra | Metering |
| Multi-provider cost in one view (Anthropic + OpenAI in same run) | Cross-provider normalization is a key Revenium value prop | LOW — provider middlewares handle it | Two provider imports | Metering |
| Tool/function call cost tracking | Analysts call yfinance, alpha_vantage etc — these are tool costs | LOW — `@meter_tool` decorator on tool functions | `@meter_tool` applied to data tools | Metering |

### Differentiators — Metering Pillar

| Feature | Value Proposition | Complexity | App Must Emit | Demo Pillar |
|---------|-------------------|------------|--------------|-------------|
| Live in-CLI cost panel (per-agent running total) | Cost visible in-app, not just in Revenium — richer live demo narrative | MEDIUM — custom Rich panel reading from callback accumulator | `StatsCallbackHandler` extended to accumulate Revenium cost data | Metering |
| Tool vs token cost comparison ("cost iceberg") | Shows that data fetching often dwarfs LLM token costs — surprising insight for a trading audience | LOW — auto after `@meter_tool` on data tools | `@meter_tool` on analyst data fetch functions | Metering |
| Cache token accounting (Anthropic prompt caching) | Demo shows cache savings across debate rounds — cost goes down as rounds repeat | LOW — middleware captures automatically | Nothing extra if using Anthropic prompt caching | Metering |
| Cost by task type (market-analysis vs risk-debate vs research) | Granular view of where in the pipeline money is being spent | LOW — pass `task_type` per node | `task_type` field per agent node | Metering |

### Anti-Features — Metering Pillar

| Feature | Why Skip | What to Do Instead |
|---------|---------|-------------------|
| Audio / video / image metering | TradingAgents uses text-only LLMs; demo would be fabricated | Keep demo to completion + tool metering only |
| Generic event metering (`meter_event`) | Adds complexity without payoff for this demo | Not needed; completions + tool events cover the story |
| OTLP integration | Revenium also accepts OpenTelemetry; valuable in production but adds setup overhead vs the SDK path | Use SDK middleware — it's purpose-built and lower friction |
| Prompt capture (`REVENIUM_CAPTURE_PROMPTS=true`) | Stores raw prompts — raises data-sensitivity questions in a live FCAT demo | Leave disabled; demo on cost/token numbers, not prompt text |

---

## Pillar 2: Traces & Squads

### How Revenium Models a Multi-Agent Workflow

**Traces:** A trace is all AI transactions (completions + tool events) sharing one `trace_id`. The Trace Detail View shows:
- Summary header: total cost, duration, transaction count, success/error ratio, models/providers involved
- Transaction Timeline: Gantt chart per transaction, color-coded by agent, duration + cost per step
- Dependency Tree: parent/child relationships derived from `parentTransactionId` — shows sequential vs parallel vs multi-root patterns; critical path highlighted
- Aggregated breakdowns: cost by model, by provider, input/output token ratios, time by task type

**Squads:** Squads are a higher-level grouping of related executions by conceptual purpose. A squad aggregates multiple trace executions, shows agent contribution metrics (role, tokens, cost, duration per agent), and provides a timeline view suitable for waterfall visualization. Each execution within a squad maps to one `propagate()` run. The squad construct is what gives FCAT the "this desk ran 12 trading analyses this week, here's the cost distribution" view.

**Auto-surfaced insights (no app configuration beyond traceId):**

| Insight | What It Shows | Required Metadata |
|---------|--------------|-------------------|
| Circular Pattern Detection | Detects agent loops (e.g., Bull → Bear → Bull at 2N rounds), counts occurrences, shows wasted cost + duration per loop, severity badge | `trace_id` + `agent` + `parentTransactionId` |
| Critical Path Analysis | Highlights the longest call chain that determined total run duration; marks bottleneck nodes | `parentTransactionId` for dependency tree |
| Anomaly Detection (P75/P95/P99) | Flags traces statistically more expensive or slower than baseline; adapts to actual distribution | `trace_id` (enough volume for percentile calculation) |
| Cost Distribution Scatter | Per-trace cost scatter with percentile lines — surfaces outlier runs | `trace_id` |
| Bottleneck Indicators | Marks transactions running significantly longer than trace average | `trace_id` + `parentTransactionId` |
| Agent Interaction Matrix | Shows which agents call which agents, cost per interaction | `agent` + `parentTransactionId` |

**The debate loop moment:** The bull/bear research debate (2×N rounds of back-and-forth) and the risk debate (3×N rounds) will show up as circular patterns in Revenium's Efficiency tab. This is the "aha" moment of the trace pillar — the cost hotspot is visually obvious without the FCAT audience needing to understand the code.

**What the app must emit for traces to light up:**
1. `trace_id` — one consistent value per `propagate()` call, set before graph invocation and passed through all agent nodes
2. `agent` — distinct per node (e.g., "Market Analyst", "Bull Researcher", "Bear Researcher", "Research Manager", "Trader", "Aggressive Risk", "Conservative Risk", "Neutral Risk", "Portfolio Manager")
3. `parentTransactionId` — each agent's call references the prior agent's `transactionId` (the SDK auto-generates `transactionId`; the app needs to thread the parent through state)
4. `task_type` — labels the operation for aggregation (e.g., "market-analysis", "sentiment-analysis", "research-debate", "risk-debate", "portfolio-decision")

**For Squads:**
- Squads appear automatically if the Revenium account is configured for squad grouping, OR
- The app registers squad executions explicitly via the Squads API — minimum: squad name + execution reference per run

---

### Table Stakes — Traces & Squads Pillar

| Feature | Why Expected | Complexity | App Must Emit | Demo Pillar |
|---------|--------------|------------|--------------|-------------|
| Full run appears as one trace in Revenium | A multi-agent workload that shows as 14 disconnected calls is not a trace demo — it must cohere | LOW — consistent `trace_id` per run | `trace_id` passed to all agent calls | Traces |
| Per-agent cost breakdown in trace view | FCAT needs to see which agent drove cost (debate loops, not analysts) | LOW — `agent` field per call | `agent` on every completion | Traces |
| Transaction timeline / Gantt chart | Visual proof the multi-agent pipeline is sequential with measurable per-step cost | LOW — auto from `trace_id` + `agent` | `trace_id` + `agent` | Traces |
| Circular pattern detection firing on debate loops | This is the "wow" of the trace demo — bull/bear and risk loops flagged as circular patterns | LOW — auto once `parentTransactionId` chains are correct | `parentTransactionId` threaded through state | Traces |

### Differentiators — Traces & Squads Pillar

| Feature | Value Proposition | Complexity | App Must Emit | Demo Pillar |
|---------|-------------------|------------|--------------|-------------|
| Critical path visualization | Shows the longest chain of dependent LLM calls — the portfolio manager's latency driver | MEDIUM — requires `parentTransactionId` correctly wired | `parentTransactionId` per agent call | Traces |
| Anomaly detection flagging expensive runs | If a demo run has an unusually expensive debate, it surfaces automatically as P99 — live drama | LOW — needs enough runs for a distribution; pre-run a few iterations in staging | `trace_id` on all runs | Traces |
| Squad timeline (multi-run waterfall) | Shows the "this desk ran 5 analyses this week" view — maps to a portfolio management team | MEDIUM — requires squad registration or config | Squad name, execution ID per run | Squads |
| Agent interaction matrix | Network graph of which agents called which, with cost weighting — visually striking | MEDIUM — requires `parentTransactionId` for all agent handoffs | `parentTransactionId` | Traces |
| Cost distribution scatter (outlier runs) | "This run was 3x the median cost" — why? Click to open trace | LOW — auto from `trace_id` | `trace_id` | Traces |

### Anti-Features — Traces & Squads Pillar

| Feature | Why Skip | What to Do Instead |
|---------|---------|-------------------|
| Squad timeline with many executions | Requires running many iterations to populate; 2–4 week timeline makes this risky for live demo | Focus on single trace detail; mention squads as the fleet-management view |
| OTLP traces ingestion | Alternative path to traces — adds infra overhead (OpenTelemetry collector) vs SDK path | SDK callback handler is sufficient and lower setup |
| Prompt-level trace content | Capturing full prompts in traces raises data sensitivity questions; not needed to tell the cost story | Show cost + token counts in trace, not raw prompts |

---

## Pillar 3: Cost Controls

### What Revenium's Cost Controls Can Do

**Rule anatomy:**
- **Metric:** Total Cost, Token Count, Error Rate, Requests/Minute, Cost per Transaction, etc.
- **Window:** Daily, weekly, monthly, or quarterly (calendar-aligned UTC); SDK polls every 60 seconds
- **Hard limit:** The enforcement threshold that triggers action
- **Warning threshold:** Optional softer notification before the hard limit
- **Action:** Block (current default for new rules); legacy THROTTLE and WARN_ONLY retained for old rules
- **Scope / filters:** By provider, model, organization, product, agent — can scope rules narrowly
- **Group-by dimension:** Per-customer enforcement (each customer gets their own independent limit)

**Shadow mode:**
- New rules default to shadow mode — logs violations, sends notifications, but does not block
- Best practice: run one full window in shadow before promoting to enforce
- For the demo: create the rule in shadow first, then promote live on stage

**SDK behavior when a rule fires:**
- SDK raises `BudgetExceededError` (catchable) before the AI provider call is made — the call never leaves the app
- Exception includes: `exc.message`, `exc.rule_name`, `exc.current_value`, `exc.threshold`
- Fails open if Revenium is unreachable (uses last cached ruleset)
- Enabled via `REVENIUM_CIRCUIT_BREAKER_ENABLED=true` + `REVENIUM_TEAM_ID`

**Notification channels:**
- Email (no setup required)
- Slack (workspace connection required first)
- Webhook (custom endpoint, optional auth)
- The llms.txt also lists: Discord, Telegram, WhatsApp, Signal, Google Chat, MS Teams, Mattermost, iMessage (from the Hermes blog post context — these may be via a webhook integration layer)

**What fires live in a demo (minimum config):**
1. Create alert: metric = Total Cost, operator = `>`, threshold = `$0.01`, notification = Email — fires within minutes on any usage
2. For cost control enforcement: `REVENIUM_CIRCUIT_BREAKER_ENABLED=true`, create a rule with a per-run cost threshold just above a normal run's cost, trigger by adding an extra debate round

**The demo moment:** Configure a cost control rule set to trigger if a single run exceeds $X. Run TradingAgents with `max_debate_rounds` set high enough to cross the threshold. The graph halts mid-run with a `BudgetExceededError` caught by middleware — the CLI shows the halt message and Revenium's UI shows the enforcement event. This is viscerally demonstrable live.

---

### Table Stakes — Cost Controls Pillar

| Feature | Why Expected | Complexity | App Must Emit | Demo Pillar |
|---------|--------------|------------|--------------|-------------|
| A visible alert firing during the demo run | FCAT expects "control" to mean something observable happening in real time | LOW — one alert rule, Email notification, `$0.01` threshold on any metric | Metering must be live | Controls |
| Enforcement (BudgetExceededError) halting the graph mid-run | The hard demo of control — the graph stops before a runaway analysis completes | MEDIUM — requires `REVENIUM_CIRCUIT_BREAKER_ENABLED`, catching `BudgetExceededError` in the LangGraph node or graph runner | `REVENIUM_CIRCUIT_BREAKER_ENABLED=true`, `REVENIUM_TEAM_ID`, cost control rule configured | Controls |
| Shadow mode shown as the "safe intro" before enforcement | Credible explanation of safe rollout — important for a risk-conscious trading audience | LOW — demo shadow rule logging violations before promoting | Nothing extra; show in Revenium UI | Controls |

### Differentiators — Cost Controls Pillar

| Feature | Value Proposition | Complexity | App Must Emit | Demo Pillar |
|---------|-------------------|------------|--------------|-------------|
| Per-desk / per-customer cost limit | "Equity Desk A has a $50/day cap; if they overspend, only their runs halt" — maps directly to trading-floor org structure | MEDIUM — group-by dimension on rule, `organizationName` per call | `organizationName` scoped per desk | Controls |
| Slack notification firing on stage | Visually dramatic — Slack message appears on a second screen as the run halts | MEDIUM — requires Slack workspace connection in Revenium settings before demo | Slack channel connected | Controls |
| BudgetExceededError surfaced in CLI cost panel | Error visible in the in-repo Rich CLI, not just Revenium UI — shows cost governance is "in the app" | MEDIUM — catch `BudgetExceededError` in `propagate()` wrapper, surface in Rich panel | Integration in `cli/main.py` or `trading_graph.py` | Controls |
| Warning threshold (soft alert before hard stop) | Two-stage alerting: "you are at 80% of your debate budget" then halt — maps to trading-floor escalation | LOW — warning threshold field in rule config | Nothing extra | Controls |

### Anti-Features — Cost Controls Pillar

| Feature | Why Skip | What to Do Instead |
|---------|---------|-------------------|
| Rolling-window throttle (legacy THROTTLE action) | Legacy action; new rules use Block only; demoing a deprecated path creates confusion | Use Block action only |
| Per-model or per-provider scoped rules | Adds configuration complexity without a clear demo payoff — the per-desk story is stronger | Scope rules at the organization/product level |
| Closed fail mode (`REVENIUM_CB_FAIL_MODE=closed`) | Blocks all calls if Revenium is unreachable — high risk for a live demo | Keep fail_mode=open (default); demo reliability > theoretical correctness |
| Notification channels beyond Email + Slack | Discord, Telegram etc. add setup overhead for marginal demo value | Configure Email for silent confirmation, Slack for visible drama |

---

## Pillar 4: Billing & Monetization

### Revenium's Monetization Model

**Object hierarchy:**
1. **Organization** — top-level customer account (e.g., "Fidelity Equity Desk")
2. **Subscriber** — individual user or service account within an org (identified by `id` and `email`)
3. **Credential** — API key reference linking a subscriber to metered calls
4. **Subscription** — links a subscriber to a product with a billing period
5. **Product** — what is being sold; includes pricing dimensions
6. **Invoice** — auto-generated at billing cycle end; exportable as CSV; PDF attached to email

**Pricing dimensions:**
- Pre-built metering elements: Input Tokens, Output Tokens, Character Count, Credits Consumed
- Custom metering elements: any unit definable per product
- Pricing tiers: stacked usage ranges with per-unit rates (e.g., first 1,000 signals at $1.50/signal, then $1.35)
- Recurring charges: fixed monthly/annual fee covering included usage
- Products can combine multiple metrics (charge on input AND output tokens in one product)
- Billing modes: per-tier (standard) or highest-tier-reached (volume incentive)

**Margin and revenue attribution:**
- `productName` maps a metered call to a priced product
- Revenium calculates "True Cost" = token spend + tool costs + human escalation
- Profit margin = revenue (from product pricing) minus True Cost
- Customer Profitability dashboards: cost-to-serve per subscriber
- ROI dashboard: pairs business outcomes (via Jobs API) against all-in costs

**Minimum to show "cost per trading signal with margin":**
1. Create Organization: "Equity Desk A" (2 min in UI)
2. Create Subscriber: `desk-a@fidelity.com` (1 min)
3. Create Product: "Trading Signal" with pricing tier (e.g., $2.00 per signal = $1.20 AI cost + $0.80 margin) (5 min)
4. Create Subscription: link subscriber → product, set billing period (demo: 5-minute cycle for immediate invoice) (2 min)
5. Emit metering events with `organizationName="Equity Desk A"`, `productName="Trading Signal"`, `subscriber.email="desk-a@fidelity.com"` on each `propagate()` call
6. After a run completes, invoice auto-generates — shows AI cost, product price, and margin in Costs & Revenue dashboard

**Jobs API for ROI (optional but powerful):**
- Register each `propagate()` run as an agentic Job with `agenticJobId`, `agenticJobType="trading-signal"`, `agenticJobName="NVDA 2025-06-26"`
- Report outcome after: `executionStatus=SUCCESS`, `outcomeType=CONVERTED` (if the signal triggered a trade), `outcomeValue=<trade value>`
- Enables ROI dashboard: cost per signal vs value of signals that converted to trades
- Requires write-scope API key (`rev_sk_...`)

---

### Table Stakes — Billing/Monetization Pillar

| Feature | Why Expected | Complexity | App Must Emit | Demo Pillar |
|---------|--------------|------------|--------------|-------------|
| A customer (Equity Desk) visible in Revenium with cost attributed to them | FCAT expects "monetize" to mean a real entity seeing a real cost — not just global totals | LOW — Organization + Subscriber creation in UI (pre-demo) | `organizationName` + `subscriber` on every metering call | Billing |
| "Cost per trading signal" unit visible in Revenium | The demo billing unit must be legible as a financial unit the audience understands | MEDIUM — Product with pricing tier, Subscription, invoice generation | `productName` matching the product | Billing |
| Margin shown (price > AI cost) | The "monetize" pillar only lands if profit margin is visible — not just cost | MEDIUM — Product pricing set above AI cost; Costs & Revenue dashboard open | productName + correct pricing setup | Billing |
| Invoice auto-generated for the demo run | Concrete artifact — "here is Equity Desk A's invoice for today's signals" | MEDIUM — short billing cycle (5-minute period) for demo, or pre-generate from a staging run | Subscription active before run | Billing |

### Differentiators — Billing/Monetization Pillar

| Feature | Value Proposition | Complexity | App Must Emit | Demo Pillar |
|---------|-------------------|------------|--------------|-------------|
| Jobs API: trading signal as a billable job with outcome | "This signal cost $1.20 to produce, triggered a $50K trade — ROI 41,666x" — the most powerful FinOps story for a trading audience | HIGH — requires Jobs API integration, outcome reporting after `propagate()` returns, write-scope key | `agenticJobId` per run, outcome reporting post-run | Billing |
| Per-desk cost limit + per-desk invoice | "Each desk gets its own bill and its own cap" — maps to how trading floors actually operate | MEDIUM — multiple Organizations + Subscriptions, group-by on cost control rules | `organizationName` per desk | Billing |
| Profit margin per customer dashboard | Visual: "Equity Desk A generates $X revenue, costs $Y to serve, margin $Z%" | LOW — auto from product pricing + metering | `organizationName` + `productName` | Billing |
| Tiered pricing showing volume discount | "More signals = lower per-signal cost" — incentive model FCAT would recognize | MEDIUM — tiered pricing dimension in product config | Nothing extra beyond productName | Billing |

### Anti-Features — Billing/Monetization Pillar

| Feature | Why Skip | What to Do Instead |
|---------|---------|-------------------|
| Real payment / credit card collection | Out of scope for a demo environment; introduces payment provider setup risk | Show invoice generation and PDF export only |
| Multiple products (e.g., "Basic Signal" vs "Premium Signal") | Adds UI configuration time pre-demo; the single "Trading Signal" product tells a clean story | Configure one product; mention tiering as a future state |
| Full ROI dashboard with many historical runs | Requires runs over time to populate meaningfully; single run won't show a distribution | Pre-populate in staging OR scope to "this is what 30 days of signals looks like" |
| Subscriber self-service / customer-facing portal | Revenium generates invoices and sends email; building a portal is scope creep | Use Revenium's built-in email invoice delivery |
| Coding assistant / GitHub integration billing features | These are for a different use case (developer tooling cost attribution) | Not relevant to trading signal workload |

---

## Feature Dependencies

```
Metering (trace_id + agent on every call)
    └──required-by──> Traces (trace detail, timeline, Gantt)
                          └──required-by──> Circular Pattern Detection
                          └──required-by──> Critical Path Analysis
                          └──required-by──> Anomaly Detection (needs volume)

Metering (organizationName + productName + subscriber)
    └──required-by──> Billing Attribution (per-customer cost)
                          └──required-by──> Invoice Generation
                          └──required-by──> Margin Dashboard

Cost Controls
    └──requires──> Metering active (rules evaluate against metered data)
    └──requires──> REVENIUM_CIRCUIT_BREAKER_ENABLED + REVENIUM_TEAM_ID (for enforcement)

parentTransactionId
    └──enhances──> Traces (flat timeline → dependency tree + critical path)
    └──enables──> Agent Interaction Matrix

agenticJobId (Jobs API)
    └──enhances──> Billing (cost → ROI view)
    └──requires──> write-scope API key (rev_sk_...)

Squads
    └──requires──> Multiple executions of same workflow type
    └──enhances──> Traces (fleet-level view)

In-CLI Cost Panel
    └──requires──> ReveniumCallbackHandler accumulating cost data
    └──enhances──> Metering (cost visible in-app during run)
```

### Dependency Notes

- **Traces require Metering first:** Without `trace_id` on every call, all completions appear as disconnected events. `trace_id` is the foundational dependency for the entire trace pillar.
- **Circular pattern detection requires parentTransactionId:** The Dependency Tree is a flat list without parent references. Circular pattern analysis needs the tree to detect loops. Without `parentTransactionId`, the debate loop story relies only on the agent field showing repeated calls — still visible but less visually dramatic.
- **Billing requires organizationName + productName on metering calls:** These are optional fields in the metering payload but required for the billing pillar. Missing either means Revenium cannot map usage to a subscription.
- **Jobs API enhances but does not block billing:** Invoice generation works without the Jobs API. Jobs adds the ROI view (cost vs outcome value). It is a differentiator, not a dependency.
- **Cost controls require metering to be live:** Rules evaluate against accumulated metered spend. A rule set too early before metering runs will never fire.

---

## MVP Definition for the 2–4 Week Demo

### Phase 1 (v1 — must land for demo to be credible)

- [ ] All LLM calls metered with `agent`, `trace_id`, `task_type`, `organizationName`, `productName`, `subscriber` — **metering pillar foundation**
- [ ] `@meter_tool` on analyst data-fetch functions — **tool cost visibility**
- [ ] `ReveniumCallbackHandler` integrated at `TradingAgentsGraph` level, `trace_id` threaded through AgentState — **enables trace view**
- [ ] One cost alert rule configured and firing on demo run — **controls pillar: table stakes alert**
- [ ] Organization + Subscriber + Product + Subscription configured in Revenium UI (pre-demo) — **billing setup**
- [ ] One live demo run shows: metered calls in UI, full trace timeline, debate loop visible in cost breakdown, invoice generated
- [ ] `BudgetExceededError` caught in graph runner and surfaced gracefully — **controls: enforcement demo**

### Phase 2 (v1.x — add after Phase 1 works end-to-end)

- [ ] `parentTransactionId` threaded through AgentState for dependency tree + circular pattern detection
- [ ] In-CLI Rich cost panel showing live per-agent running cost
- [ ] Slack notification channel for cost control alert (visual drama on stage)
- [ ] Circular pattern detection confirmed firing on debate loops in trace view
- [ ] Margin configured in product pricing, profit margin dashboard visible

### Phase 3 (v2 — defer unless time permits)

- [ ] Jobs API integration — register each run as a Job, report outcome after signal generated
- [ ] Squad registration — multiple runs grouped into a squad for fleet-level view
- [ ] Anomaly detection: pre-run staging runs to build distribution, demo a P99 trace

---

## Feature Prioritization Matrix

| Feature | Demo Value (FCAT) | Implementation Cost | Priority |
|---------|-------------------|--------------------|----------|
| Per-call metering (provider middleware + trace_id) | HIGH | LOW | P1 |
| Per-agent attribution (agent field) | HIGH | LOW | P1 |
| Cost alert firing live | HIGH | LOW | P1 |
| Trace timeline / Gantt in Revenium UI | HIGH | LOW | P1 |
| Billing: customer + product + invoice | HIGH | MEDIUM | P1 |
| BudgetExceededError enforcement (halt) | HIGH | MEDIUM | P1 |
| Margin visible in Costs & Revenue dashboard | HIGH | LOW (config only) | P1 |
| `@meter_tool` on data tools | MEDIUM | LOW | P1 |
| `parentTransactionId` for dependency tree | HIGH | MEDIUM | P2 |
| Circular pattern detection firing on debates | HIGH | MEDIUM (requires parentTransactionId) | P2 |
| In-CLI cost panel | MEDIUM | MEDIUM | P2 |
| Slack notification on halt | MEDIUM | LOW (config only) | P2 |
| Critical path analysis | MEDIUM | MEDIUM (requires parentTransactionId) | P2 |
| Jobs API / ROI view | HIGH | HIGH | P3 |
| Squad timeline (multi-run fleet view) | MEDIUM | HIGH | P3 |
| Anomaly detection (P99 trace) | MEDIUM | HIGH (needs volume) | P3 |
| Tiered product pricing | LOW | LOW | P3 |

---

## Sources

- [Revenium Python SDK README](https://github.com/revenium/revenium-python-sdk) — HIGH confidence; official SDK documentation
- [Revenium llms.txt API index](https://revenium.readme.io/llms.txt) — HIGH confidence; official API reference summary
- [Revenium docs sitemap](https://docs.revenium.io/sitemap.md) — HIGH confidence; official documentation structure
- [Agent instrumentation guide](https://docs.revenium.io/instrument-your-agents/agent-instrumentation-guide.md) — HIGH confidence
- [Anomaly detection / debug traces](https://docs.revenium.io/optimize-performance/predict-and-surface-anomalies.md) — HIGH confidence
- [Cost controls](https://docs.revenium.io/track-and-control-costs/cost-controls.md) — HIGH confidence
- [Budgets and alerts](https://docs.revenium.io/track-and-control-costs/set-budgets-and-alerts.md) — HIGH confidence
- [Customer and credentials model](https://docs.revenium.io/monetize-your-ai/manage-customers-and-credentials.md) — HIGH confidence
- [Usage-based billing tutorial](https://docs.revenium.io/monetize-your-ai/tutorial-build-usage-based-billing.md) — HIGH confidence
- [Invoicing and payments](https://docs.revenium.io/monetize-your-ai/automate-invoicing-and-payments.md) — HIGH confidence
- [Pricing models and products](https://docs.revenium.io/monetize-your-ai/create-pricing-models-and-products.md) — HIGH confidence
- [AI Insights investigators](https://docs.revenium.io/optimize-performance/ai-insights.md) — HIGH confidence
- [Agent outcomes / Jobs API](https://docs.revenium.io/instrument-your-agents/agent-outcomes.md) — HIGH confidence
- [Tool usage metering](https://docs.revenium.io/instrument-your-agents/monitor-agent-tool-usage.md) — HIGH confidence
- [MCP server integration](https://docs.revenium.io/integrations/mcp-server.md) — HIGH confidence

---

*Feature research for: Revenium × TradingAgents FCAT Demo*
*Researched: 2026-06-26*
