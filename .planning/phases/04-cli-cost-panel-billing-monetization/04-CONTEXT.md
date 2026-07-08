# Phase 4: CLI Cost Panel & Billing Monetization - Context

**Gathered:** 2026-06-28
**Status:** Ready for planning

<domain>
## Phase Boundary

Two deliverables, both layered on Phase 1's metering callback — no change to trading logic:

1. **In-app live cost visibility (CLI-01/02):** the existing Rich CLI shows a live per-agent running cost panel during a run, updating as each agent finishes, with debate-loop agents annotated `×N` so the cost hotspot is visible without opening Revenium.
2. **Monetize pillar (BIL-01/02):** a completed run emits one priced "cost per trading signal" billing event attributed to the desk/strategy customer, and an invoice with margin (price > AI cost) is visible in Revenium's Costs & Revenue dashboard.

This is the "monetize" pillar of the meter→trace→control→monetize demo arc.
</domain>

<decisions>
## Implementation Decisions

### Cost panel content & placement (CLI-01)
- **D-01:** Add a **dedicated live cost panel** to the existing Rich `Live` layout (alongside the Progress panel / stats footer) — do not fold into the footer or the Progress table.
- **D-02:** Show **$ cost as primary, token counts as secondary** per agent; the panel updates as each agent finishes.
- **D-03:** **Highlight the hotspot** — the most expensive agent (highest $) is visually emphasized so "where the money goes" is obvious on stage.
- **D-04:** Feed the panel from the Revenium callback handler's `agent_costs` dict (the same source `_render_budget_halt_panel` already reads), not a parallel accumulator.

### Debate ×N annotation (CLI-02)
- **D-05:** **Collapse repeated debate-loop calls into one row per agent role**, annotated `×N` with summed cost — e.g. `Bull Researcher ×2 — $0.041`. Not one row per call.
- **D-06:** Applies to the agents that run multiple times: bull/bear researchers across debate rounds and the three risk debators (aggressive/conservative/neutral). Single-call agents show no `×N`.

### Pricing & margin model (BIL-01/02)
- **D-07:** Price the trading signal at a **flat $2.00/signal**, **configurable** with `$2.00` as the default (matches the product's deferred D-03 pricing in `setup_revenium.py`).
- **D-08:** **Margin = price − measured AI cost** (fixed price minus the run's actual metered AI cost). This is the "price > cost" number that must surface in Revenium's Costs & Revenue dashboard.

### Billing trigger & halted runs
- **D-09:** Emit **exactly one** billing event after a run **delivers a final Portfolio Manager decision**, from the **graph run-completion (success) path** (the same `trading_graph._run_graph` try/finally region that owns `begin_run`/`end_run`/`stop_polling`).
- **D-10:** **Circuit-breaker-halted runs emit NO billing event** — a signal that was never delivered is not billed (consistent with Phase 3's "no fabricated decision" on `BudgetExceededError`).

### Claude's Discretion
- Exact Rich panel styling (borders, column widths, color of the hotspot highlight) — match the existing CLI's visual language.
- The precise Revenium API/SDK call used to emit the billing/invoice event (metering vs. a dedicated billing endpoint) — for the planner/researcher to determine against the SDK; attribute to the already-provisioned Subscriber/Product.
- Config key name + env override for the configurable signal price (follow `default_config.py` `_ENV_OVERRIDES` convention).
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase scope & requirements
- `.planning/ROADMAP.md` § "Phase 4: CLI Cost Panel & Billing Monetization" — goal, success criteria, planning notes
- `.planning/REQUIREMENTS.md` — CLI-01, CLI-02, BIL-01, BIL-02 definitions

### CLI cost panel (CLI-01/02)
- `cli/main.py` — Rich `Live` layout, Progress panel, stats footer (`layout["footer"]`), and `_render_budget_halt_panel` (line ~481) which already iterates `handler.agent_costs` (the per-agent cost pattern to reuse)
- `cli/stats_handler.py` — `StatsCallbackHandler` (existing token/stat tracking feeding the footer)
- `tradingagents/revenium/callback.py` — `ReveniumCallbackHandler.agent_costs` (per-agent cost accumulation; source of truth for the panel)

### Billing / monetize (BIL-01/02)
- `tradingagents/revenium/client.py` — `ReveniumClient.meter_ai_completion` (existing metering call; billing emit likely a sibling Revenium call)
- `tradingagents/revenium/callback.py` — `begin_run`/`end_run` run lifecycle (billing emit hooks into run completion)
- `tradingagents/graph/trading_graph.py` — `_run_graph` try/finally (run-completion success path where the billing event is emitted; halted runs skip it)
- `scripts/setup_revenium.py` — product `trading-signal` provisioning; note the `$2.00/signal` metered pricing (D-03) was explicitly DEFERRED to this phase
</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `_render_budget_halt_panel` (cli/main.py): already builds a Rich table/panel from `handler.agent_costs` (per-agent cost + token breakdown) — the live cost panel is essentially the streaming sibling of this static halt panel.
- Rich `Live(layout, refresh_per_second=4)` block in `cli/main.py` already drives live UI during the run — the cost panel slots into this existing layout.
- `ReveniumClient.meter_ai_completion` (tradingagents/revenium/client.py): the established Revenium emit path; the billing event reuses the same client/auth.

### Established Patterns
- Per-agent cost lives on the Revenium callback handler (`agent_costs`), keyed by agent name; debate-loop agents already appear multiple times there → `×N` aggregation is a presentation concern over existing data.
- Revenium attribution hierarchy (Org → Subscriber → Product → Subscription) is already provisioned (Phase 1); the billing event attributes to the existing Subscriber/Product (the desk/strategy customer) — no new provisioning.
- Config knobs follow `default_config.py` `DEFAULT_CONFIG` + `_ENV_OVERRIDES` (TRADINGAGENTS_* env overrides) — the configurable signal price follows this.

### Integration Points
- Cost panel: new Rich panel rendered inside the existing `Live` layout, fed by `ReveniumCallbackHandler.agent_costs`.
- Billing emit: hooks into `trading_graph._run_graph` run-completion success path (after a PM decision); gated OFF for `BudgetExceededError`-halted runs.
- Provider-agnostic: billing works regardless of LLM provider; consistent with the planned OpenRouter migration (see deferred).
</code_context>

<specifics>
## Specific Ideas

- Hotspot framing: the demo point of CLI-02 is to make the debate-loop cost hotspot pop in-app — the `×N` collapsed row + highlighted most-expensive agent is the intended "aha" visual.
- Margin story: flat $2.00 − measured AI cost gives a clean, consistent "price > cost" number for the Costs & Revenue dashboard, completing the meter→trace→control→**monetize** arc.
</specifics>

<deferred>
## Deferred Ideas

- **OpenRouter migration** — routing LLM calls through OpenRouter (single integration) is a separate later-phase decision; Phase 4 billing/cost work must stay provider-agnostic so it survives that migration. Do NOT add direct Anthropic API support. (See memory: OpenRouter migration note.)
- None other — discussion stayed within phase scope.
</deferred>

---

*Phase: 4-cli-cost-panel-billing-monetization*
*Context gathered: 2026-06-28*
