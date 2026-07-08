# Phase 1: Foundation & Metering - Context

**Gathered:** 2026-06-27
**Status:** Ready for planning

<domain>
## Phase Boundary

Fix the two day-one blockers (invalid default model names; missing Revenium attribution hierarchy) and deliver the **metering** pillar: every LLM call — and every analyst data-fetch tool call — is metered to Revenium with per-agent, per-provider, per-task billing context, and a full `propagate()` run completes without model-name errors.

This is the foundation all other pillars depend on (trace, control, monetize). Architecture is settled by research (`.planning/research/`); this phase fills the remaining implementation/value decisions.

**In scope:** FND-01..04, MTR-01..04 (see REQUIREMENTS.md).
**Out of scope:** trace threading / `parentTransactionId` (Phase 2), cost gate / enforcement (Phase 3), CLI cost panel + billing-event emission (Phase 4), demo hardening (Phase 5). Changing trading logic. OTLP. Prompt/completion content capture.

</domain>

<decisions>
## Implementation Decisions

### Locked upstream (research / PROJECT.md — do NOT re-litigate)
- **L-01:** Integration via a custom `ReveniumCallbackHandler` (`BaseCallbackHandler`) on the existing `TradingAgentsGraph(callbacks=...)` seam — NOT OTLP. The two paths must never run simultaneously (double-counting).
- **L-02:** Packages: `revenium-python-sdk[langchain]>=0.1.9` + `revenium-metering>=6.8.2`, pinned. Archived `revenium-middleware-langchain` and per-provider middleware packages are excluded (double-counting).
- **L-03:** Demo models: `claude-sonnet-4-6` (Anthropic, deep-think: Research Manager, Portfolio Manager) + `gpt-4.1-mini` (OpenAI, quick-think: analysts/trader) — gives two distinct provider labels in Revenium. Override the invalid `DEFAULT_CONFIG` IDs (`gpt-5.5`, `gpt-5.4-mini`).
- **L-04:** Cross-cutting identity (`trace_id`, `current_agent_name`, run meta) carried via `contextvars`, not `AgentState` — one-line set at the top of each agent node; no graph topology changes.
- **L-05:** Self-contained `tradingagents/revenium/` package, imported one-way by `trading_graph.py`.

### Attribution values (locked this session — NOT retroactively fixable)
- **D-01:** Organization name = `Revenium-Research-Desk`.
- **D-02:** Subscriber identity = `john.demic+trading@revenium.io` (plus-addressed alias of the project owner — deliverable and controlled; not a placeholder).
- **D-03:** Product = `trading-signal`; price = **$2.00/signal** (≈ $1.20 AI cost + $0.80 margin). Margin must stay positive vs measured run cost — validate actual cost early and adjust price if the ~$1.20 estimate is off.
- **D-04:** Every metered call carries `organizationName`, `productName`, and `subscriber.id` so nothing lands in UNCLASSIFIED (FND-03, MTR-02).

### Metering toggle & resilience
- **D-05:** **Auto-on when key present.** If `REVENIUM_METERING_API_KEY` is set, every `tradingagents analyze` / `propagate()` run meters; if absent, metering is a **silent no-op**. No `--meter` flag. This keeps the test suite green with no keys (DMO-04) and makes the demo "just work".
- **D-06:** **Fail open.** Any Revenium-side error (network, API) logs a warning, drops the event, and lets the trading run continue — matches the repo's `# noqa: BLE001 — fail open` convention. (The Phase 3 cost gate is the deliberate exception that DOES halt; not in this phase.)
- **D-07:** **FND-04 validation = standalone re-runnable script** (e.g. `scripts/validate_metering.py`): makes one metered call and asserts exactly one Revenium event, non-zero tokens, attributed to the demo subscriber (not UNCLASSIFIED). Doubles as a pre-demo sanity check. (A mocked unit test for the "1 event per LLM call" invariant is fine to add for the suite, but the live one-event assertion lives in the script.)

### Account setup
- **D-08:** Hierarchy created by an **idempotent committed script** `scripts/setup_revenium.py` (create/verify Org → Subscriber → Product → Subscription via SDK/API). Re-runnable, version-controlled, documents exact values, rebuildable if the account is reset. (MCP Dev connector may be used ad-hoc, but the script is the source of truth.)
- **D-09:** Credentials in `.env` (gitignored) with documented placeholders added to `.env.example` (`REVENIUM_METERING_API_KEY`, plus base URL / write key vars as needed). Matches existing `python-dotenv` pattern.
- **D-10:** Provision **both** `rev_mk_` (metering) and `rev_sk_` (write/Jobs) keys now. Phase 1–4 only consume `rev_mk_`; `rev_sk_` is staged in case v2 Jobs/ROI gets pulled forward (least-privilege still applies in code — only read what each phase needs).

### Metering labels & scope
- **D-11:** **`task_type` taxonomy = pipeline-stage granular:** `analysis`, `research_debate`, `planning`, `trade`, `risk_debate`, `decision`. The two debate stages are distinct buckets — this pre-stages the Phase 2 "debate loops are the cost hotspot" story.
- **D-12:** **Agent label = internal graph node names** (`market_analyst`, `bull_researcher`, `bear_researcher`, `research_manager`, `trader`, `risk_*`, `portfolio_manager`, …). 1:1 with code, no mapping table to maintain.
- **D-13:** **`@meter_tool` on ALL analyst data-fetch tools** (every `get_*` market/fundamentals/news/sentiment tool) for the fullest "cost iceberg" (tool cost vs token cost). The `sentiment_analyst.py:69` `.func` bypass is the **one explicit documented exemption** (it calls `get_news.func()` directly, bypassing the `@tool` wrapper — a data-fetch, not an LLM call; document, don't force-fix).

### Claude's Discretion
- Module layout within `tradingagents/revenium/` (file names beyond the package), where exactly the model-name override lives (a demo config dict vs env overrides via `TRADINGAGENTS_*`), and the precise contextvar wiring — all follow research's architecture and repo conventions.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project planning (read first)
- `.planning/PROJECT.md` — project intent, core value, Key Decisions table
- `.planning/REQUIREMENTS.md` — FND-01..04, MTR-01..04 acceptance criteria for this phase
- `.planning/ROADMAP.md` §"Phase 1" — goal, success criteria, planning notes (pre-work A/B, sentinel checks)
- `.planning/STATE.md` — accumulated decisions, day-one blockers, validation gates

### Research (HIGH confidence — the architecture is settled here)
- `.planning/research/SUMMARY.md` — callback-vs-OTLP resolution, mandatory pre-work, build order, phase-by-phase implications
- `.planning/research/STACK.md` — exact packages/versions, provider-label matrix
- `.planning/research/ARCHITECTURE.md` — component breakdown, contextvar pattern, integration seams
- `.planning/research/PITFALLS.md` — double-counting, UNCLASSIFIED attribution, model names, race conditions, shadow mode
- `.planning/research/FEATURES.md` — P1/P2/P3 feature split

### Codebase maps
- `.planning/codebase/ARCHITECTURE.md`, `INTEGRATIONS.md`, `STACK.md`, `CONVENTIONS.md`, `CONCERNS.md`, `TESTING.md`

### External
- Revenium docs / LLM reference: https://revenium.readme.io/llms.txt
- Revenium MCP Dev connector — available in this environment for ad-hoc account work (the committed `scripts/setup_revenium.py` is the source of truth, per D-08)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `cli/stats_handler.py` (`StatsCallbackHandler`, 76 lines) — the exact `BaseCallbackHandler` blueprint for `ReveniumCallbackHandler`; already collects token/tool usage via LangChain callbacks.
- `tradingagents/graph/trading_graph.py:54,66,78-80` — `callbacks` param already plumbed: stored as `self.callbacks`, injected into `llm_kwargs["callbacks"]`. The drop-in seam — add the Revenium handler alongside `stats_handler`.
- `cli/main.py:1053-1062,1147-1162` — CLI constructs the graph with `callbacks=[stats_handler]` and passes callbacks into `propagator.get_graph_args(...)` for tool execution tracking. This is where the Revenium handler gets added for the CLI path.
- `tradingagents/llm_clients/factory.py` — single funnel where all provider ChatModels are constructed; callbacks flow through here to every provider (provider-neutral).
- `tradingagents/default_config.py` — `DEFAULT_CONFIG` + `_ENV_OVERRIDES` (`TRADINGAGENTS_*`); the model-name override (L-03) attaches here / via a demo config dict.

### Established Patterns
- Fail-open convention: `# noqa: BLE001 — fail open, never block the run` — D-06 follows it.
- No hardcoded providers/models in agents or clients; provider quirks live in `llm_clients/capabilities.py`. Revenium attaches to the abstraction, never bakes in a provider.
- `get_config()` read at call time, not import time; `set_config()` merges one level deep.

### Integration Points
- New `tradingagents/revenium/` package, imported one-way by `trading_graph.py` (L-05).
- One-line `contextvars` set at the top of each agent node fn for `current_agent_name` (L-04) — 13 one-line edits, no topology change.
- `@meter_tool` decorator applied to data-fetch tools surfaced through `agents/utils/agent_utils.py` (D-13).

### ⚠ Correction to research wording (planner: verify, don't trust the phrasing)
- SUMMARY.md / ARCHITECTURE.md state the graph is "non-streaming (`graph.invoke`, not `graph.stream`)". **This is imprecise:** `trading_graph.py:384` and `cli/main.py:1166` DO call `self.graph.stream(...)` — but that is LangGraph **graph-level** state streaming, not **LLM token-level** streaming. No `llm.stream`/`astream` exists, so `on_llm_end` still receives complete token data and the callback-path conclusion holds. Phase 1 research-flag (grep for `stream`) should confirm **no LLM-level streaming**; the graph-level `.stream()` is expected and harmless. If LLM-level streaming is ever introduced, add a tiktoken fallback in `on_llm_end`.

</code_context>

<specifics>
## Specific Ideas

- User (project owner / CTO) wants two Mermaid architecture diagrams produced alongside this context as a comprehension + FCAT-communication aid (not Phase 1 implementation work):
  1. **TradingAgents-only** — Revenium-agnostic view of the multi-agent LangGraph pipeline, to learn the system and explain it to FCAT.
  2. **TradingAgents + Revenium (final state)** — the same pipeline annotated with all integration points assuming every pillar (meter/trace/control/monetize) is implemented.
  Delivered separately in the discussion; see `01-ARCHITECTURE-DIAGRAMS.md` in this phase dir.

</specifics>

<deferred>
## Deferred Ideas

- **`rev_sk_` write-scope usage / Jobs API / ROI view** — key is provisioned now (D-10) but consumption is v2 (JOBS-01), not this phase.
- **Provider-split granularity beyond deep/quick** — current split (Anthropic deep-think, OpenAI quick-think) is locked; finer per-agent provider routing is not needed for the demo.
- All Phase 2–5 work (trace threading, cost gate, CLI panel, billing-event emission, demo hardening) — explicitly out of Phase 1.

</deferred>

---

*Phase: 1-Foundation & Metering*
*Context gathered: 2026-06-27*
