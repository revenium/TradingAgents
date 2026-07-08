# Phase 4: CLI Cost Panel & Billing Monetization - Research

**Researched:** 2026-06-28
**Domain:** Rich CLI live panel + Revenium Jobs/Outcomes billing API
**Confidence:** HIGH (CLI panel), MEDIUM (billing API — core path verified via SDK source; profitstream host needs live confirmation)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Add a **dedicated live cost panel** to the existing Rich `Live` layout (alongside the Progress panel / stats footer) — do not fold into the footer or the Progress table.
- **D-02:** Show **$ cost as primary, token counts as secondary** per agent; the panel updates as each agent finishes.
- **D-03:** **Highlight the hotspot** — the most expensive agent (highest $) is visually emphasized so "where the money goes" is obvious on stage.
- **D-04:** Feed the panel from the Revenium callback handler's `agent_costs` dict (the same source `_render_budget_halt_panel` already reads), not a parallel accumulator.
- **D-05:** **Collapse repeated debate-loop calls into one row per agent role**, annotated `×N` with summed cost — e.g. `Bull Researcher ×2 — $0.041`. Not one row per call.
- **D-06:** Applies to the agents that run multiple times: bull/bear researchers across debate rounds and the three risk debaters (aggressive/conservative/neutral). Single-call agents show no `×N`.
- **D-07:** Price the trading signal at a **flat $2.00/signal**, **configurable** with `$2.00` as the default.
- **D-08:** **Margin = price − measured AI cost** (fixed price minus the run's actual metered AI cost).
- **D-09:** Emit **exactly one** billing event after a run **delivers a final Portfolio Manager decision**, from the **graph run-completion (success) path** in `trading_graph._run_graph`.
- **D-10:** **Circuit-breaker-halted runs emit NO billing event.**

### Claude's Discretion
- Exact Rich panel styling (borders, column widths, color of the hotspot highlight) — match the existing CLI's visual language.
- The precise Revenium API/SDK call used to emit the billing/invoice event — attribute to the already-provisioned Subscriber/Product.
- Config key name + env override for the configurable signal price (follow `default_config.py` `_ENV_OVERRIDES` convention).

### Deferred Ideas (OUT OF SCOPE)
- **OpenRouter migration** — provider-agnostic billing is required; do NOT add Anthropic-API-specific cost logic.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| CLI-01 | The existing Rich CLI shows a live per-agent running cost panel during a run | Layout extension confirmed; `agent_costs` public attr already on handler; see § CLI Panel Anatomy |
| CLI-02 | Debate-loop agents are annotated (e.g. ×N) in the panel so the cost hotspot is visible in-app | `call_count` field needed in `agent_costs` entries; see § ×N Annotation |
| BIL-01 | A completed run emits one "cost per trading signal" billing event attributed to the desk/strategy customer | `AgenticOutcomeClient.create_job + report_outcome` path confirmed; see § Billing API Path |
| BIL-02 | An invoice is generated with margin (price > AI cost) visible in Revenium's Costs & Revenue dashboard | `outcome_value=2.00` populates Revenue column; margin = Revenue − AI cost; see § Margin on Dashboard |
</phase_requirements>

---

## Summary

Phase 4 has two distinct delivery areas that share no coupling: (1) the in-app live cost panel (CLI-01/02) is a UI-only change layered on the already-populated `agent_costs` accumulator the callback handler built for this purpose, and (2) the billing/monetization event (BIL-01/02) uses Revenium's Jobs/Outcomes API — a vendor-supplied `AgenticOutcomeClient` already present in `revenium_middleware.agentic_outcomes` — to post a $2.00 revenue record that Revenium pairs with the run's AI costs to show margin.

The CLI side is low-risk: the data source exists, the streaming update mechanism (`Rich.Live`) is running, and `_render_budget_halt_panel` is a near-identical static predecessor. The main change is adding a third column to the `upper` row of the layout and extending `agent_costs` entries with `cost` and `call_count` fields.

The billing side has one confirmed-path item (the Jobs/Outcomes API) and one open question (which profitstream host to use: `api.revenium.io` vs `api.prod.ai.hcapp.io`). The approach is: at run start call `create_job` with the run's `trace_id` as `agenticJobId`, and after PM decision call `report_outcome` with `outcome_value=signal_price`. Circuit-breaker-halted runs skip `report_outcome`. Attribution flows through the existing `trace_id` correlation. Margin surfaces automatically in Revenium's Costs & Revenue dashboard once revenue and cost events both land.

**Primary recommendation:** Use `AgenticOutcomeClient` (already vendored in `revenium_middleware.agentic_outcomes`) for billing; extend `agent_costs` with `cost` + `call_count` for the live panel; add a 3rd column to the Rich `upper` row; create `tradingagents/revenium/billing.py` as the fail-open wrapper.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Live cost panel rendering | CLI layer (`cli/main.py`) | — | Panel is purely presentation; data source is already on the handler instance |
| Per-agent cost accumulation | `ReveniumCallbackHandler` (callback layer) | — | Handler owns `agent_costs`; adding `cost`+`call_count` fields is a pure extension |
| Model price lookup (local) | `tradingagents/revenium/` (new `pricing.py` or inline in callback) | — | Provider-agnostic; needed for synchronous `$` display before Revenium responds |
| Billing event emission | `tradingagents/revenium/billing.py` (new) | `AgenticOutcomeClient` from `revenium_middleware` | Fail-open wrapper; graph layer calls it; no CLI coupling |
| Billing trigger hook | `tradingagents/graph/trading_graph._run_graph` | — | Owns the success-vs-halted decision; matches D-09/D-10 |
| Signal price config | `tradingagents/default_config.py` | — | Follows `_ENV_OVERRIDES` pattern; single source of truth |

---

## Standard Stack

### Core (already installed — no new packages)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `rich` | >=14.0.0 | Live layout, Table, Panel, Text | Already driving the CLI Live block |
| `revenium_middleware` | installed | `AgenticOutcomeClient` for Jobs/Outcomes billing | Vendored SDK; `agentic_outcomes.py` is the exact module needed |
| `revenium_metering` | 6.8.2 | `ReveniumMetering` AI completions (existing) | Unmodified; billing goes through a different path |
| `threading` | stdlib | Fail-open background emit for billing (matches existing metering pattern) | Consistent with the fire-and-forget pattern already in callback.py |

**No new pip installs required.** All dependencies are already present.

## Package Legitimacy Audit

No new packages to install in this phase. All libraries used are already in `uv.lock` and verified in prior phases.

---

## CLI Panel Anatomy

### Current Layout Structure

```python
# cli/main.py — create_layout()
layout.split_column(
    Layout(name="header", size=3),
    Layout(name="main"),
    Layout(name="footer", size=3),
)
layout["main"].split_column(
    Layout(name="upper", ratio=3),
    Layout(name="analysis", ratio=5),
)
layout["upper"].split_row(
    Layout(name="progress", ratio=2),
    Layout(name="messages", ratio=3),
)
```

### Required Layout Change (D-01)

Add `costs` as a third column in `upper`:

```python
layout["upper"].split_row(
    Layout(name="progress", ratio=2),
    Layout(name="costs", ratio=2),    # NEW
    Layout(name="messages", ratio=3),
)
```

This places the cost panel between Progress and Messages. The ratios (2:2:3) keep the panels roughly even while slightly favouring the message log.

### `update_display` Signature Addition

```python
def update_display(layout, spinner_text=None, stats_handler=None, start_time=None,
                   revenium_handler=None):   # NEW kwarg
    ...
    # Render cost panel when revenium_handler is provided and enabled
    if revenium_handler and revenium_handler.enabled:
        layout["costs"].update(_build_cost_panel(revenium_handler))
    else:
        layout["costs"].update(Panel("[dim]Revenium cost tracking not enabled[/dim]",
                                     title="AI Costs", border_style="grey50"))
```

All call sites pass `revenium_handler=revenium_handler` (already available in `run_analysis` as `revenium_handler`).

### `_build_cost_panel` function (new in `cli/main.py`)

```python
def _build_cost_panel(handler) -> Panel:
    """Build the live per-agent cost panel (CLI-01/02, D-01..D-06).

    Source: handler.agent_costs — dict keyed by agent name,
    value: {"input_tokens": int, "output_tokens": int,
            "cost": float, "call_count": int}

    Collapses debate-loop agents to one row with ×N annotation (D-05).
    Highlights the most expensive agent in bold/colour (D-03).
    """
    table = Table(show_header=True, header_style="bold magenta",
                  box=box.SIMPLE_HEAD, expand=True, padding=(0, 1))
    table.add_column("Agent", style="cyan", ratio=3)
    table.add_column("Cost", justify="right", style="green", ratio=2)
    table.add_column("Tokens", justify="right", style="dim", ratio=2)

    costs = handler.agent_costs   # {name: {cost, input_tokens, output_tokens, call_count}}
    if not costs:
        return Panel("[dim]No agent completions yet...[/dim]",
                     title="AI Costs", border_style="cyan")

    # Find hotspot for highlight (D-03)
    max_agent = max(costs, key=lambda k: costs[k].get("cost", 0.0))

    run_total = sum(v.get("cost", 0.0) for v in costs.values())
    for agent, data in sorted(costs.items(), key=lambda x: x[1].get("cost", 0.0), reverse=True):
        n = data.get("call_count", 1)
        label = f"{agent} ×{n}" if n > 1 else agent       # D-05/D-06
        cost = data.get("cost", 0.0)
        tokens = data.get("input_tokens", 0) + data.get("output_tokens", 0)
        cost_str = f"${cost:.4f}"
        tok_str = format_tokens(tokens)                    # reuse existing helper
        style = "bold yellow" if agent == max_agent else ""
        table.add_row(label, cost_str, tok_str, style=style)

    # Total row
    table.add_row("─" * 20, "─" * 8, "─" * 8, style="dim")
    table.add_row("[bold]Total[/bold]", f"[bold]${run_total:.4f}[/bold]", "", style="")
    return Panel(table, title="[bold]AI Costs[/bold]", border_style="cyan", padding=(0, 1))
```

---

## `agent_costs` Schema Extension

### Current (Phase 1–3)

```python
entry = self.agent_costs.setdefault(agent, {"input_tokens": 0, "output_tokens": 0})
entry["input_tokens"] += input_tokens
entry["output_tokens"] += output_tokens
```

### Required Extension (Phase 4)

```python
entry = self.agent_costs.setdefault(
    agent, {"input_tokens": 0, "output_tokens": 0, "cost": 0.0, "call_count": 0}
)
entry["input_tokens"] += input_tokens
entry["output_tokens"] += output_tokens
entry["cost"] += _compute_local_cost(model, provider, input_tokens, output_tokens)
entry["call_count"] += 1
```

This is purely additive — `_render_budget_halt_panel` reads only `input_tokens` and `output_tokens`, which are still present.

---

## Local Cost Computation

Revenium calculates AI cost asynchronously (metering events are fire-and-forget). The live panel needs a synchronous dollar estimate. The approach is a small lookup table for the demo models, falling back to 0 for unknowns.

```python
# tradingagents/revenium/pricing.py  (new file, ~30 lines)
# [ASSUMED] prices based on training data — confirm against official pages before release

_PER_MILLION: dict[tuple[str, str], tuple[float, float]] = {
    # (provider, model_substring): (input_$/1M, output_$/1M)
    ("anthropic", "claude-sonnet-4"):  (3.00, 15.00),   # claude-sonnet-4-6
    ("openai",    "gpt-4.1-mini"):     (0.40,  1.60),
    ("openai",    "gpt-4o-mini"):      (0.15,  0.60),
    ("openai",    "gpt-4o"):           (5.00, 15.00),
}

def compute_cost(provider: str, model: str, input_tokens: int, output_tokens: int) -> float:
    """Return a best-effort local cost estimate in USD. Returns 0.0 if model unknown."""
    key = _lookup_key(provider.lower(), model.lower())
    if key is None:
        return 0.0
    inp_rate, out_rate = _PER_MILLION[key]
    return (input_tokens * inp_rate + output_tokens * out_rate) / 1_000_000.0
```

**Important:** Tag the prices `[ASSUMED]` in the module docstring. The demo's margin story uses Revenium's server-side cost calculation (which is authoritative) — the local estimate only drives the in-app panel display. If the local estimate is $1.18 and Revenium says $1.21, the panel is close enough for the demo. The Costs & Revenue dashboard uses Revenium's number.

---

## ×N Annotation Implementation

`call_count` increments in `on_llm_end` on every completion for an agent. The debate-loop agents (bull_researcher, bear_researcher, aggressive_debator, conservative_debator, neutral_debator) will accumulate `call_count > 1` naturally over multiple rounds. Single-call agents (market_analyst, portfolio_manager, etc.) always have `call_count == 1` after their single LLM call. The panel applies the `×N` suffix only when `call_count > 1` (D-06).

**Agent name mapping note:** `current_agent_name.get()` returns the raw agent name from the contextvar (e.g. `"bull_researcher"`, `"portfolio_manager"`). The panel display should map these to human-readable names using the existing `ANALYST_AGENT_NAMES` mapping or a new display map (since debate agents are not in `ANALYST_AGENT_NAMES`).

---

## Billing API Path

### Mechanism: Jobs/Outcomes API

The `revenium_middleware` package already ships `AgenticOutcomeClient` in `agentic_outcomes.py`. This is the exact module for the billing pillar.

**Flow (two API calls per completed run):**

1. **Create Job** — at run start, inside `_run_graph` after `begin_run`:
   ```python
   # POST https://api.revenium.io/profitstream/v2/api/jobs
   billing_emitter.create_trading_signal_job(
       agentic_job_id=_trace_id,       # correlates with metering trace_id
       name=f"trading-signal-{ticker}-{trade_date}",
       job_type="trading-signal",
   )
   ```

2. **Report Outcome** — on the SUCCESS path (after `graph.invoke()` returns, before `finally`), inside `_run_graph`:
   ```python
   # POST https://api.revenium.io/profitstream/v2/api/jobs/{trace_id}/outcome
   billing_emitter.emit_billing_event(
       agentic_job_id=_trace_id,
       signal_price=config["revenium_signal_price"],   # default 2.00
       reported_by=config["revenium_subscriber_id"],
   )
   ```

3. **BudgetExceededError path** — `BudgetExceededError` propagates before `graph.invoke()` returns; `emit_billing_event` never runs (D-10).

### `AgenticOutcomeClient` Call Signatures

```python
# From revenium_middleware/agentic_outcomes.py — [VERIFIED: SDK source]
client.create_job(
    agentic_job_id: str,       # required — our trace_id
    name: str = None,
    type: str = None,
    environment: str = None,
    dry_run: bool = False,
)

client.report_outcome(
    agentic_job_id: str,       # required — same trace_id
    payload: dict,             # see below
    dry_run: bool = False,
)
# payload shape (confirmed from AgenticOutcomeClient source + CLI schema):
{
    "result": "SUCCESS",           # required: SUCCESS | FAILED | CANCELLED
    "outcomeType": "CONVERTED",    # standard billing type
    "outcomeValue": 2.00,          # signal price (configurable, D-07)
    "outcomeCurrency": "USD",
    "reportedBy": subscriber_id,   # attribution
    "metadata": {"ticker": ticker, "trade_date": str(trade_date)},
}
```

### New Module: `tradingagents/revenium/billing.py`

Purpose: fail-open wrapper around `AgenticOutcomeClient` for the trading signal use case.

```python
class TradingSignalBillingEmitter:
    """Fail-open billing emitter for completed trading signals (BIL-01/02).

    Wraps AgenticOutcomeClient so any Jobs/Outcomes API failure is logged
    as a warning and never blocks or corrupts a trading run.

    Disabled when billing_api_key is absent (silent no-op, same contract
    as ReveniumClient/callback).
    """

    def __init__(self, api_key: str, profitstream_base_url: str,
                 team_id: str = "", subscriber_id: str = "") -> None: ...

    @classmethod
    def from_config(cls, config: dict) -> TradingSignalBillingEmitter: ...

    @property
    def enabled(self) -> bool: ...

    def create_trading_signal_job(self, trace_id: str, ticker: str, trade_date: str) -> None:
        """Create the job record at run start. Fail-open, background thread."""

    def emit_billing_event(self, trace_id: str, signal_price: float,
                           reported_by: str = "") -> None:
        """Emit SUCCESS outcome with outcomeValue=signal_price. Fail-open, background thread."""
```

The emitter is instantiated in `TradingAgentsGraph.__init__` (alongside `ReveniumCallbackHandler`) and stored as `self._billing_emitter`. `_run_graph` calls it at the two hook points.

---

## Profitstream Host Resolution

### Current State (Open Question)

Two different hosts have been encountered for Revenium's management/billing API:

| Host | Confirmed Via | Used For |
|------|--------------|---------|
| `https://api.prod.ai.hcapp.io/profitstream/v2/api` | `setup_revenium.py` + Phase 1 live verification | Org/Product/Subscription CRUD (management) |
| `https://api.revenium.io` | `agentic_outcomes.py` SDK default | Jobs/Outcomes write path |

**[ASSUMED]:** These may be different backends for different purposes. `api.revenium.io` may serve metering + jobs writes, while `api.prod.ai.hcapp.io` serves management CRUD. This needs verification against the live account before implementation.

**Recommended approach:** Make `profitstream_base_url` configurable as a new config key `revenium_profitstream_url` (env: `REVENIUM_PROFITSTREAM_BASE_URL`) defaulting to `"https://api.revenium.io"` (the SDK default). If the live account requires `api.prod.ai.hcapp.io`, the operator sets the env var. Document this in `.env.example`.

### Billing API Key

Jobs/Outcomes write calls require `x-api-key` auth. Based on Phase 3 findings:
- `rev_mk_*` keys are 403 on the enforcement feed (write-scope endpoints require `rev_sk_*`)
- Jobs writes are likely the same: `rev_sk_*` required

New config key: `revenium_billing_api_key` → `REVENIUM_BILLING_API_KEY`. Falls back to `REVENIUM_SK_API_KEY` if not set separately. When absent, the billing emitter is disabled (silent no-op). Document clearly that `REVENIUM_BILLING_API_KEY` is a `rev_sk_*` key, not `rev_mk_*`.

`AgenticOutcomeSettings.outcome_api_key` can accept this key (it falls back to `api_key` if not set, but the default `api_key` in `AgenticOutcomeSettings` should be the `rev_sk_*` key for outcome calls).

---

## Config Keys to Add (DEFAULT_CONFIG + _ENV_OVERRIDES)

All follow the existing `default_config.py` pattern:

```python
# In DEFAULT_CONFIG:
"revenium_signal_price":       float(os.getenv("TRADINGAGENTS_SIGNAL_PRICE", "2.00")),
"revenium_billing_api_key":    os.getenv("REVENIUM_BILLING_API_KEY", ""),
"revenium_profitstream_url":   os.getenv("REVENIUM_PROFITSTREAM_BASE_URL", "https://api.revenium.io"),

# In _ENV_OVERRIDES:
"TRADINGAGENTS_SIGNAL_PRICE":      "revenium_signal_price",
"REVENIUM_BILLING_API_KEY":        "revenium_billing_api_key",
"REVENIUM_PROFITSTREAM_BASE_URL":  "revenium_profitstream_url",
```

The `_coerce` function already handles float (it's an existing type in `DEFAULT_CONFIG`), so `revenium_signal_price` needs its default to be a float literal (`2.00` not `"2.00"`) to trigger correct coercion.

---

## Margin on Dashboard (BIL-02)

### How Revenium Constructs the Margin View

- **AI Costs**: Sum of `totalCost` (or calculated token cost) from all `ai/completions` metering events for the run's `trace_id`. Already flowing from Phase 1.
- **Revenue**: The `outcomeValue` ($2.00) from `report_outcome`. Attributed to the run via `agenticJobId = trace_id`.
- **Margin**: Revenium's Costs & Revenue dashboard shows `Revenue − AI Costs`. With `signal_price = 2.00` and typical AI cost ~$0.30–$1.50 for a full run, margin will be positive and visible.

### Dashboard Latency

Revenue/cost data should appear in the Costs & Revenue dashboard within seconds of the HTTP POST (metering is near-real-time). The "5-minute billing cycle" from the roadmap refers to generating an actual invoice document, not the dashboard metrics refresh. For the FCAT demo, **showing the Costs & Revenue dashboard** (real-time metrics) is sufficient — invoice generation is a separate concern that requires a short billing period configured on the product's plan.

**[ASSUMED]** The Costs & Revenue dashboard in the Revenium UI shows revenue+margin from job outcomes in near-real-time without requiring a billing cycle to close. If the demo requires an actual PDF/invoice download, the product plan's billing period must be shortened — this would be done via `PATCH /profitstream/v2/api/products/{id}` with `{"plan": {"period": "MINUTE", "periodCount": 5}}`. This is LOW confidence and likely OUT OF SCOPE for the FCAT demo; flag as open question.

---

## `setup_revenium.py` Extension

A new `_setup_pricing` step is needed to configure product pricing (D-07). Options:

**Option A (recommended): No product pricing config needed** — the $2.00 signal price is carried entirely in `report_outcome.outcomeValue`. The product plan doesn't need pricing dimensions for the Jobs/Outcomes approach. The Costs & Revenue dashboard shows job revenue directly.

**Option B (optional, for future-proofing)**: Configure a `pricingDimension` on the product via the management API: `PATCH /products/{id}` with a per-signal pricing dimension. This would auto-price metering events tagged with `operation_subtype="trading-signal"`. This is NOT needed for the Phase 4 Jobs/Outcomes approach but could be added to `setup_revenium.py` as a future step.

**Recommendation: Implement Option A.** Keep `setup_revenium.py` focused on provisioning the hierarchy; pricing is fully carried by the runtime `outcomeValue`.

---

## Architecture Patterns

### Recommended Project Structure (new files)

```
tradingagents/revenium/
├── billing.py          # NEW — TradingSignalBillingEmitter fail-open wrapper
├── pricing.py          # NEW — local model price lookup for live panel (optional: inline in callback)
├── callback.py         # MODIFIED — agent_costs schema extension + call_count
├── client.py           # unmodified
├── config.py           # MODIFIED — attribution_from_config stays; no change needed
└── context.py          # unmodified

cli/
└── main.py             # MODIFIED — layout (3rd column), _build_cost_panel, update_display sig

tradingagents/
├── default_config.py   # MODIFIED — 3 new config keys + _ENV_OVERRIDES entries
└── graph/
    └── trading_graph.py  # MODIFIED — instantiate billing_emitter + 2 hook calls in _run_graph
```

### Anti-Patterns to Avoid

- **Don't call `report_outcome` in the `finally` block** — the finally runs even on BudgetExceededError (D-10 requires NO billing event on halted runs). The billing call must be inside the `try` block, after `graph.invoke()` succeeds.
- **Don't block the graph node on billing I/O** — same fire-and-forget discipline as metering (background thread + fail-open). The billing call happens after `graph.invoke()` already returned, so blocking isn't a graph performance issue, but a timeout could still delay CLI feedback. Use a background thread.
- **Don't hard-code provider names in the cost lookup** — the local `pricing.py` lookup must use the `provider` string from `_detect_provider(serialized)` which can be `"openai"`, `"anthropic"`, `"unknown"`. Fall back to 0.0 for unknown.
- **Don't add a second Revenium client instance** — `TradingSignalBillingEmitter` uses `AgenticOutcomeClient` (a separate SDK client for a different API surface). It does NOT wrap `ReveniumClient`/`ReveniumMetering`. These are parallel, non-overlapping clients.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Jobs/Outcomes billing emit | Custom HTTP client for `/profitstream/v2/api/jobs` | `AgenticOutcomeClient` from `revenium_middleware.agentic_outcomes` | Already implements retry, 409 idempotency, team-ID resolution, and auth header |
| Rich live layout | Custom terminal output / ASCII table printing | `Rich.Live` + `Rich.Layout` (already running in the CLI) | Handles cursor management, refresh rate, and concurrent updates cleanly |
| Per-agent token-to-cost conversion | Querying Revenium's model pricing API at runtime | Static `pricing.py` lookup table | Async API round-trip would block the panel; static table is fast, accurate for demo models, and easy to update |

---

## Common Pitfalls

### Pitfall 1: `report_outcome` in `finally` block bills halted runs

**What goes wrong:** If `report_outcome` is placed in the `finally` block alongside `end_run()`/`stop_polling()`, it fires even when `BudgetExceededError` propagates, violating D-10.

**How to avoid:** Place `emit_billing_event` inside the `try` block, immediately after `graph.invoke()` (or the merged-chunk loop in debug mode) returns successfully. `BudgetExceededError` raises from inside `graph.invoke()` and propagates before reaching the billing call.

**Code pattern:**
```python
try:
    self._billing_emitter.create_trading_signal_job(_trace_id, company_name, str(trade_date))
    self._revenium_handler.begin_run(_trace_id, ...)
    ...
    final_state = self.graph.invoke(init_agent_state, **args)
    ...
    # Only reached when graph completes without BudgetExceededError
    self._billing_emitter.emit_billing_event(
        _trace_id, self.config.get("revenium_signal_price", 2.00)
    )
    ...
finally:
    self._revenium_handler.end_run()
    stop_polling()
```

### Pitfall 2: Calling `update_display` without `revenium_handler` after signature change

**What goes wrong:** There are multiple `update_display(layout, ...)` calls in `run_analysis`. If any are missed, the costs panel slot is empty.

**How to avoid:** Add `revenium_handler=None` as a keyword-only argument with a safe default (renders "not enabled" panel). All call sites in `run_analysis` already have access to `revenium_handler` in scope.

**Warning sign:** A blank "AI Costs" panel (not an error) when Revenium is enabled — means `revenium_handler` was not passed to that call site.

### Pitfall 3: Wrong profitstream host for Jobs API

**What goes wrong:** `AgenticOutcomeClient` defaults to `https://api.revenium.io` for `profitstream_base_url`. If the Revenium account's jobs endpoint is at `api.prod.ai.hcapp.io`, creates/outcomes return 404 or 403 silently (fail-open swallows them).

**How to avoid:** Test `create_job` against the live account in the first wave before writing the full billing flow. Use a dedicated `scripts/validate_billing.py` (Wave 1 or Wave 2) that calls `create_job` + `report_outcome` with `dry_run=False` against the live account and reports success/failure. Log the response (not the key).

**Warning sign:** No jobs appearing in the Revenium jobs list after `create_job` runs — wrong host.

### Pitfall 4: `call_count` not in existing `agent_costs` entries on handler reuse

**What goes wrong:** If a `ReveniumCallbackHandler` is reused across multiple runs (e.g., in a multi-run CLI session), `agent_costs` accumulates across runs. The `×N` count would be misleading.

**How to avoid:** `end_run()` already clears `_call_state`. Add `self.agent_costs.clear()` and `self.run_total_tokens = 0` to `end_run()` (the current code does NOT clear these). This is also needed to prevent cost bleed across runs.

**Warning sign:** Panel shows `×5` for bull researcher on a single-round run — means prior run data was not cleared.

### Pitfall 5: `revenium_signal_price` type coercion in `_ENV_OVERRIDES`

**What goes wrong:** `_coerce` uses `isinstance(reference, float)` to detect float keys. If `revenium_signal_price` defaults to `2.00` (a Python float literal), coercion works. If it defaults to the string `"2.00"` (from `os.getenv`), `_coerce` treats it as a `str` and `float("2.00")` is never called.

**How to avoid:** Define the default as `2.00` (float, not string). Pattern: `"revenium_signal_price": 2.00,` in `DEFAULT_CONFIG`. The env override then coerces `"2.00"` → `2.00` via `_coerce`.

---

## Code Examples

### Existing `_render_budget_halt_panel` (static predecessor to live panel)

```python
# cli/main.py:481 — [VERIFIED: codebase read]
def _render_budget_halt_panel(console, err, handler) -> None:
    cost_table = Table(show_header=True, header_style="bold magenta")
    cost_table.add_column("Agent", style="cyan")
    cost_table.add_column("Input Tokens", justify="right")
    cost_table.add_column("Output Tokens", justify="right")
    for agent, counts in sorted(handler.agent_costs.items()):
        cost_table.add_row(agent, str(counts["input_tokens"]), str(counts["output_tokens"]))
```

The live panel is the streaming sibling: same source (`handler.agent_costs`), same structure, adds `cost`+`call_count` columns.

### `AgenticOutcomeClient.create_job` and `report_outcome`

```python
# revenium_middleware/agentic_outcomes.py — [VERIFIED: SDK source]
client.create_job(
    agentic_job_id="<trace_id>",
    name="trading-signal-NVDA-2026-06-28",
    type="trading-signal",
    environment="production",
)

client.report_outcome(
    agentic_job_id="<trace_id>",
    payload={
        "result": "SUCCESS",
        "outcomeType": "CONVERTED",
        "outcomeValue": 2.00,
        "outcomeCurrency": "USD",
        "reportedBy": "john.demic+trading@revenium.io",
        "metadata": {"ticker": "NVDA", "trade_date": "2026-06-28"},
    },
)
```

`_post_with_retry` in `AgenticOutcomeClient` handles 429/502/503/504 with exponential backoff and retries up to `outcome_retry_attempts=10` times. Max retry delay is capped at 90s.

### `agent_costs` extension in `on_llm_end`

```python
# tradingagents/revenium/callback.py — [VERIFIED: codebase read, extension shown]
from tradingagents.revenium.pricing import compute_cost  # new module

# ... inside on_llm_end, after token extraction:
local_cost = compute_cost(provider, model, input_tokens, output_tokens)

with self._lock:
    entry = self.agent_costs.setdefault(
        agent, {"input_tokens": 0, "output_tokens": 0, "cost": 0.0, "call_count": 0}
    )
    entry["input_tokens"] += input_tokens
    entry["output_tokens"] += output_tokens
    entry["cost"] += local_cost
    entry["call_count"] += 1
    self.run_total_tokens += total_tokens
```

### `end_run` extension (Pitfall 4 fix)

```python
# tradingagents/revenium/callback.py — end_run()
with self._lock:
    self._run_trace_id = None
    self._run_meta = None
    self._last_transaction_id = ""
    self._call_state.clear()
    self.agent_costs.clear()           # NEW: reset for next run
    self.run_total_tokens = 0           # NEW: reset for next run
    self._threads = [t for t in self._threads if t.is_alive()]
```

---

## State of the Art

| Old Approach | Current Approach | Impact |
|--------------|------------------|--------|
| `organization_id` (DEPRECATED field) | `organization_name` | Already using correct field; no change |
| Manual HTTP for jobs API | `AgenticOutcomeClient` with retry + team-ID resolution | Use the SDK — it handles all edge cases |
| Billing separate from metering | Jobs/Outcomes correlated via `agenticJobId = trace_id` | Revenium links revenue to AI cost automatically |

**Deprecated/outdated:**
- `organization_id` field in `ai_create_completion_params.py`: already marked DEPRECATED; the callback already uses `organization_name`. No action.
- `product_id` field: same, already using `product_name`.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `api.revenium.io/profitstream/v2/api/jobs` is the correct host for the Jobs/Outcomes write path (as defaulted in `agentic_outcomes.py`) | Billing API Path | Jobs calls silently succeed but land in wrong system; no revenue appears in dashboard. Fix: set `REVENIUM_PROFITSTREAM_BASE_URL` env var |
| A2 | `rev_sk_*` key is required for `create_job`/`report_outcome` (metering-only `rev_mk_*` keys may be 403) | Billing API Key | Billing emit fails (fail-open, silently logged). Fix: set `REVENIUM_BILLING_API_KEY` to the `rev_sk_*` key |
| A3 | Revenium Costs & Revenue dashboard shows job outcome revenue in near-real-time (seconds, not waiting for billing cycle close) | Margin on Dashboard | Dashboard doesn't show margin during the live demo. Fix: trigger a billing cycle close manually or shorten billing period on the product plan |
| A4 | Local model pricing for claude-sonnet-4-6: $3.00/1M input, $15.00/1M output | Local Cost Computation | Panel $ values are inaccurate — cosmetic only; Revenium's server-side calculation is the authoritative number |
| A5 | Local model pricing for gpt-4.1-mini: $0.40/1M input, $1.60/1M output | Local Cost Computation | Same as A4 — cosmetic |
| A6 | `api.prod.ai.hcapp.io/profitstream/v2/api` (the confirmed management host) is for Org/Subscriber/Product/Subscription CRUD only, NOT for Jobs writes | Profitstream Host Resolution | If wrong: `api.revenium.io` 404s; must switch `REVENIUM_PROFITSTREAM_BASE_URL` to `api.prod.ai.hcapp.io/profitstream/v2/api` |

---

## Open Questions (RESOLVED)

1. **Which profitstream host for the Jobs API?**
   - What we know: `api.revenium.io` is the default in `agentic_outcomes.py`; `api.prod.ai.hcapp.io/profitstream/v2/api` is confirmed working for management CRUD (Phase 1).
   - What's unclear: Whether `api.revenium.io` also serves the Jobs endpoints.
   - Recommendation: Add `scripts/validate_billing.py` (Wave 1 of this phase) that calls `create_job` + `report_outcome` against both hosts and confirms which returns 200/201. Do this before writing the full billing integration.
   - **RESOLVED:** De-risked by wave ordering — `scripts/validate_billing.py` (04-02, Wave 1) confirms the host before the graph wiring in 04-03 (Wave 2). Host is config-driven via `revenium_profitstream_url`, so resolution is an env change, not a code change.

2. **Does BIL-02 require a closed billing period or does the dashboard show real-time revenue?**
   - What we know: Revenium's Costs & Revenue dashboard shows AI costs in near-real-time. The job outcome adds revenue.
   - What's unclear: Whether the Revenium platform generates a "Costs & Revenue" view from live events or only after a billing cycle closes.
   - Recommendation: [ASSUMED] near-real-time. If the demo reveals it isn't, add a product plan update step to set a short billing period. Flag this as the demo's risk #1.
   - **RESOLVED:** Assumed near-real-time; live confirmation gated in 04-04 Task 2 (human-verify). If a closed period proves necessary, shorten the product plan billing period for the demo. Logged as demo risk A3.

3. **Does `_build_cost_panel` need an agent display-name mapper?**
   - What we know: `agent_costs` keys are the raw contextvar names (e.g. `"bull_researcher"`, `"portfolio_manager"`). The existing `ANALYST_MAPPING` in `cli/main.py` covers analysts only.
   - Recommendation: Add a `COST_PANEL_DISPLAY_NAMES` dict in `cli/main.py` mapping all 12 agent keys to human-readable names, matching the `FIXED_AGENTS` and `ANALYST_MAPPING` display strings.
   - **RESOLVED:** `COST_PANEL_DISPLAY_NAMES` dict added in 04-01 Task 2.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `revenium_middleware.agentic_outcomes.AgenticOutcomeClient` | BIL-01/02 | ✓ | `revenium_python_sdk-0.1.9` | — |
| `revenium_metering` 6.8.2 | CLI panel (existing metering) | ✓ | 6.8.2 | — |
| `rich` | CLI panel | ✓ | >=14.0.0 | — |
| Revenium write-scope key (`rev_sk_*`) | Jobs/Outcomes API | Unknown (env-dependent) | — | Billing disabled (fail-open), panel still works |
| `REVENIUM_BILLING_API_KEY` or `REVENIUM_SK_API_KEY` env var | BIL-01 live | Unknown | — | Billing emitter no-op; BIL-01/02 fail silently |

**Missing dependencies with no fallback:** None that block code execution.

**Missing dependencies with fallback:** A billing API key is required for live BIL-01/02 validation. Without it, the emitter is disabled and all billing tests must be mocked.

---

## Security Domain

`security_enforcement: true` per `.planning/config.json`. ASVS Level 1 applies.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | N/A (no new auth surface; existing `x-api-key` pattern unchanged) |
| V3 Session Management | No | N/A |
| V4 Access Control | No | N/A |
| V5 Input Validation | Yes (LOW risk) | Signal price comes from `DEFAULT_CONFIG` after env coercion; not user-supplied at runtime. `float()` coercion already handled by `_coerce` |
| V6 Cryptography | No | API keys in `.env` (not committed); same pattern as all prior phases |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| API key disclosure in logs | Information Disclosure | Follow repo convention: never log API key values; log only symbolic names and result codes (already enforced in `billing.py` docstring) |
| Billing event replay / double-billing | Tampering | Each run gets a unique `trace_id`; `create_job` uses `accept_409=True` (idempotent re-run safe); `report_outcome` is immutable once posted (Revenium platform enforces) |
| Signal price manipulation via env var | Tampering | `TRADINGAGENTS_SIGNAL_PRICE` is operator-controlled (deployment env); not user input. No additional validation required at ASVS L1 |

---

## Project Constraints (from CLAUDE.md)

| Directive | Impact on Phase 4 |
|-----------|------------------|
| Multi-provider abstraction — no hardcoding a provider in agents or clients | `pricing.py` uses `provider` string from `_detect_provider()`; no Anthropic-specific code paths |
| Config via `default_config.py` `_ENV_OVERRIDES` | All 3 new config keys follow the `_ENV_OVERRIDES` pattern |
| Tests must pass without live API keys | `TradingSignalBillingEmitter.enabled` is `False` when `billing_api_key` absent; all billing calls are mockable via `AgenticOutcomeClient` injection |
| Never log secrets | `billing.py` docstring and code follow "log symbolic names only" convention |
| `snake_case` for functions, `PascalCase` for classes | `TradingSignalBillingEmitter`, `compute_cost`, `_build_cost_panel` |
| Factory functions prefix `create_` | Not applicable (billing emitter is a class, not a factory in the agent sense) |
| `from __future__ import annotations` in modules with union types | Use in `billing.py` and `pricing.py` |
| GSD workflow enforcement | Phase is planned via GSD; no direct edits without a GSD workflow |

---

## Sources

### Primary (HIGH confidence)
- `tradingagents/revenium/callback.py` — `agent_costs` schema, `begin_run`/`end_run`, existing accumulator; read directly
- `cli/main.py` — `create_layout()`, `update_display()`, `_render_budget_halt_panel()`, `run_analysis()`; read directly
- `.venv/lib/python3.11/site-packages/revenium_middleware/agentic_outcomes.py` — `AgenticOutcomeClient` API; read directly
- `.venv/lib/python3.11/site-packages/revenium_metering/types/ai_create_completion_params.py` — metering fields; read directly
- `.venv/lib/python3.11/site-packages/revenium_metering/resources/events.py` — `events.create()` API; read directly
- `tradingagents/graph/trading_graph.py` — `_run_graph` structure, `begin_run`/`end_run` hook points; read directly
- `tradingagents/default_config.py` — `_ENV_OVERRIDES` pattern, existing config keys; read directly
- `scripts/setup_revenium.py` — management API host, product provisioning state, "pricing deferred" note; read directly
- `.planning/STATE.md` — Phase 1 decisions, confirmed hosts, deferred items; read directly
- `revenium` CLI schema — `revenium jobs outcome`, `revenium models pricing`, all commands; verified via `revenium schema --output json`

### Secondary (MEDIUM confidence)
- `revenium_middleware/agentic_outcomes.py` `AgenticOutcomeSettings.profitstream_base_url = "https://api.revenium.io"` — default host for jobs API; vendor-supplied

### Tertiary (LOW confidence)
- Model pricing estimates (A4, A5) — from training data; verify against official Anthropic/OpenAI pricing pages before release

---

## Metadata

**Confidence breakdown:**
- CLI panel (CLI-01/02): HIGH — data source exists, layout extensible, static predecessor confirms the pattern
- Billing API path (BIL-01/02): MEDIUM — `AgenticOutcomeClient` confirmed in SDK; host and key type need live validation
- Margin/dashboard behavior (BIL-02): LOW-MEDIUM — inferred from Revenium's Jobs/Outcomes purpose; not verified live

**Research date:** 2026-06-28
**Valid until:** 2026-07-28 (Revenium SDK is actively developed; re-verify `agentic_outcomes.py` API if SDK is updated)
