# Architecture Research: Revenium Integration into TradingAgents

**Domain:** AI cost metering / FinOps instrumentation on a multi-agent LangGraph pipeline
**Researched:** 2026-06-26
**Confidence:** HIGH (seam files read directly; Revenium docs and SDK verified from PyPI and readme.io)

---

## Standard Architecture

### System Overview

```
┌──────────────────────────────────────────────────────────────────────┐
│                         Entry Layer                                  │
│  cli/main.py  ──────── TradingAgentsGraph(callbacks=[stats, rev])   │
│  (Rich UI + StatsCallbackHandler + ReveniumCallbackHandler)          │
│  Live cost panel reads from ReveniumCallbackHandler.agent_costs      │
└───────────────────────────────┬──────────────────────────────────────┘
                                │  propagate(ticker, date)
                                ▼
┌──────────────────────────────────────────────────────────────────────┐
│                   Orchestration Layer  (graph/)                      │
│                                                                      │
│  trading_graph.py                                                    │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  propagate() sets a run-scoped contextvars bundle:           │    │
│  │    trace_id  = uuid4()                                       │    │
│  │    run_meta  = {ticker, date, desk/strategy, signal_id}      │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                      │
│  LangGraph StateGraph ──────────────────────────────────────────┐   │
│  [Market/Sentiment/News/Fundamentals Analysts]  (sequential)    │   │
│         ↓                                                       │   │
│  [Bull Researcher] ⇄ [Bear Researcher]  (debate loop)          │   │
│         ↓                                                       │   │
│  [Research Manager] → [Trader]                                  │   │
│         ↓                                                       │   │
│  [Aggr] ⇄ [Conservative] ⇄ [Neutral]  (risk loop)             │   │
│         ↓                                                       │   │
│  [Portfolio Manager] → END                                      │   │
│  ─────────────────────────────────────────────────────────────┘   │
└───────────────────────────────┬──────────────────────────────────────┘
                                │  each agent calls llm.invoke(...)
                                ▼
┌──────────────────────────────────────────────────────────────────────┐
│                  THE SINGLE METERING SEAM                            │
│                                                                      │
│  tradingagents/llm_clients/factory.py  create_llm_client()          │
│                                                                      │
│  Returns BaseLLMClient subclass → .get_llm() → LangChain ChatModel  │
│                                                                      │
│  Revenium attaches here as a LangChain callback:                    │
│    callbacks kwarg is already threaded from TradingAgentsGraph       │
│    through create_llm_client() into every provider's ChatModel.      │
│                                                                      │
│  ReveniumCallbackHandler (extends BaseCallbackHandler):             │
│    on_chat_model_start → capture agent_name from contextvars        │
│    on_llm_end → extract tokens, model, provider, latency            │
│              → read trace_id / squad metadata from contextvars      │
│              → fire meter_ai_completion (async, non-blocking)       │
│              → check cost-control gate (raise if hard limit hit)    │
│              → update self.agent_costs dict (for CLI panel)         │
└──────────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌──────────────────────────────────────────────────────────────────────┐
│                  Revenium Platform (external)                        │
│                                                                      │
│  POST /meter/v2/api/meter_ai_completion                             │
│    { model, provider, inputTokenCount, outputTokenCount,             │
│      traceId, squadId, squadRole, agent,                            │
│      organizationName, subscriber, taskType, totalCost, ... }       │
│                                                                      │
│  GET /meter/v2/api/cost-controls   (enforcement-rule cache)         │
│  POST /meter/v2/api/cost-controls  (define limits)                  │
│  GET /meter/v2/api/analytics       (billing / FinOps view)          │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Component Boundaries

### What Exists and Must Not Change

| Component | File | Role in Integration |
|-----------|------|---------------------|
| `TradingAgentsGraph` | `tradingagents/graph/trading_graph.py` | Already accepts `callbacks: list` kwarg; passes it into `create_llm_client` via `llm_kwargs["callbacks"]`. Zero changes needed for the seam itself. |
| `create_llm_client` | `tradingagents/llm_clients/factory.py` | Already forwards `**kwargs` (including `callbacks`) to every provider client constructor. Supports all 15+ providers uniformly. |
| `BaseLLMClient.__init__` | `tradingagents/llm_clients/base_client.py` | Stores `kwargs`; each provider client passes them to the LangChain ChatModel constructor which accepts `callbacks`. |
| `StatsCallbackHandler` | `cli/stats_handler.py` | Already a `BaseCallbackHandler`. Revenium handler is a second handler in the same list — no modification to the existing handler needed. |

### New Components to Build

| Component | Location | Responsibility |
|-----------|----------|----------------|
| `ReveniumCallbackHandler` | `tradingagents/revenium/callback.py` | Core metering seam. Extends `BaseCallbackHandler`. On `on_llm_end`, reads contextvars for trace metadata + agent role, fires `meter_ai_completion` async, checks cost gate, updates per-agent cost dict. |
| `ReveniumRunContext` | `tradingagents/revenium/context.py` | Holds the `contextvars.ContextVar` bundle for `trace_id`, `run_meta`, `current_agent`. Set at `propagate()` entry. Read inside the callback handler. |
| `ReveniumCostGate` | `tradingagents/revenium/cost_gate.py` | Polls `GET /cost-controls` at run start; re-checks cached limit on each `on_llm_end`; raises `CostLimitExceeded` when a hard limit is crossed. |
| `ReveniumBillingEmitter` | `tradingagents/revenium/billing.py` | On run completion, fires the "trading signal" billing event: total tokens + cost attributed to `desk/strategy` customer, priced as a single metering-element unit. |
| Cost panel in CLI | `cli/main.py` + `cli/stats_handler.py` | Reads `ReveniumCallbackHandler.agent_costs` dict to add a per-agent cost column/table to the existing Rich live-progress display. |
| Config keys | `tradingagents/default_config.py` + `_ENV_OVERRIDES` | `revenium_api_key`, `revenium_api_url`, `revenium_squad_id`, `revenium_customer`, `revenium_product`, `revenium_cost_limit_usd`, `revenium_enabled`. |

---

## Data and Metadata Flow

### How trace_id + agent_role + customer reach each LLM call

The critical question is: at `on_llm_end` inside a LangChain callback, what context is available?

The answer is **Python `contextvars`**, not LangGraph state. Here is why and how:

1. **LangChain callbacks do not receive `AgentState`** — the `on_llm_end` signature gets `LLMResult` + `**kwargs` (which includes `run_id`, `parent_run_id`, `tags`, `metadata`). It does not get the LangGraph node name or state fields directly.

2. **`contextvars.ContextVar` is the correct mechanism.** LangGraph runs each node in the calling thread's context. A `ContextVar` set in `propagate()` before the graph runs is visible inside every node function and every callback invoked during that run — including nested `on_llm_end` calls from debate loops.

3. **Agent name via LangChain `tags` or metadata.** Each agent's LLM can be tagged at construction time. LangChain's `ChatModel` accepts a `tags: list[str]` param that is forwarded to all callbacks as `kwargs["tags"]`. The pattern: at graph-setup time (`TradingAgentsGraph.__init__`), tag each LLM with a role label (e.g., `["agent:market_analyst"]`, `["agent:bull_researcher"]`). The handler reads `kwargs.get("tags", [])` in `on_chat_model_start` to capture the current agent name, storing it in a thread-local/contextvar for the `on_llm_end` pair.

```
propagate(ticker, date)
  │
  ├─ set context: trace_id = uuid4()
  ├─ set context: run_meta = {ticker, date, customer="equity-desk", product="trading-signal"}
  │
  └─ graph.invoke(init_state, config={"callbacks": [stats_handler, revenium_handler]})
         │
         ├─ market_analyst_node()
         │    └─ self.quick_thinking_llm.invoke(prompt)  ← tagged ["agent:market_analyst"]
         │         └─ on_chat_model_start(tags=["agent:market_analyst"])
         │         └─ on_llm_end → reads trace_id, run_meta, agent="market_analyst"
         │                      → POST meter_ai_completion(agent="market_analyst", traceId=..., ...)
         │
         ├─ bull_researcher_node()   [debate round 1]
         │    └─ ... → on_llm_end(agent="bull_researcher", traceId=..., squadRole="bull")
         │
         ├─ bear_researcher_node()   [debate round 1]
         │    └─ ... → on_llm_end(agent="bear_researcher", traceId=..., squadRole="bear")
         │
         └─ portfolio_manager_node()
              └─ ... → on_llm_end(agent="portfolio_manager", traceId=..., squadRole="manager")

  └─ billing_emitter.emit_signal_unit(trace_id, total_cost, customer="equity-desk")
```

### Why not LangGraph `config["metadata"]` or `AgentState`?

- `config["metadata"]` is accessible inside node functions via `RunnableConfig`, but not inside LangChain callbacks — the callback receives a different kwargs set.
- Adding fields to `AgentState` would propagate data through the state dict but nodes would need to explicitly pass it to the LLM call — this is more invasive than needed.
- `contextvars` is the standard mechanism used by OpenTelemetry and other observability libraries for exactly this cross-cutting-concern pattern. It is thread-safe and coroutine-safe.

### Metadata mapping to Revenium fields

| Context Source | Revenium Field | Value |
|----------------|---------------|-------|
| `uuid4()` set at `propagate()` entry | `traceId` | One UUID per `.propagate()` call |
| LangGraph squad concept | `squadId` | Same as `traceId` (one squad per run) |
| LangChain tag on LLM | `agent` | `"market_analyst"`, `"bull_researcher"`, etc. |
| LangChain tag on LLM | `squadRole` | `"analyst"`, `"researcher"`, `"manager"`, `"trader"`, `"risk"` |
| `run_meta["customer"]` from config | `organizationName` / `subscriber` | `"equity-desk"` or user-supplied |
| `run_meta["product"]` from config | product billing field | `"trading-signal"` |
| `on_llm_end` usage_metadata | `inputTokenCount`, `outputTokenCount` | From `AIMessage.usage_metadata` |
| LLM serialized dict | `model`, `provider` | From `serialized["kwargs"]["model_name"]` |
| `on_chat_model_start` / `on_llm_end` timestamps | `requestTime`, `responseTime`, `requestDuration` | Wall-clock timestamps |
| config `taskType` | `taskType` | `"investment-research"` |

---

## Trace / Squad Modeling

### LangGraph topology → Revenium trace/squad shape

One `propagate()` call = one Revenium **trace** + one **squad**.

```
Trace: {traceId}  ticker=NVDA  date=2026-06-26  customer=equity-desk
│
├── Squad: {squadId = traceId}
│    │
│    ├── Step 1: market_analyst        [agent, squadRole=analyst]
│    ├── Step 2: sentiment_analyst     [agent, squadRole=analyst]
│    ├── Step 3: news_analyst          [agent, squadRole=analyst]
│    ├── Step 4: fundamentals_analyst  [agent, squadRole=analyst]
│    │
│    ├── Step 5: bull_researcher  (round 1)   [squadRole=researcher]
│    ├── Step 6: bear_researcher  (round 1)   [squadRole=researcher]
│    ├── Step 7: bull_researcher  (round 2)   [squadRole=researcher]  ← cost hotspot
│    ├── Step 8: bear_researcher  (round 2)   [squadRole=researcher]  ← cost hotspot
│    │
│    ├── Step 9:  research_manager             [squadRole=manager]
│    ├── Step 10: trader                       [squadRole=trader]
│    │
│    ├── Step 11: aggressive_debator (round 1) [squadRole=risk]
│    ├── Step 12: conservative_debator (r1)    [squadRole=risk]
│    ├── Step 13: neutral_debator (r1)         [squadRole=risk]       ← cost hotspot
│    │
│    └── Step 14: portfolio_manager            [squadRole=manager]
│
└── Billing Event: "trading-signal" unit, attributed to customer
```

Debate loop steps get the same `agent` name but a monotonically increasing `transactionId`. Revenium's squad timeline view will show the looping steps as the cost hotspot — this is the demo's "circular communication" insight moment.

---

## Cost Controls: Where the Limit Check Plugs In

Cost controls use Revenium's enforcement-rule system. The check happens inside the callback handler, not as a separate middleware in the LLM call path:

```
on_llm_end:
  1. Extract token counts + compute estimated cost from per-model rate in config
  2. Update self._run_cost_usd += estimated_cost
  3. If self._run_cost_usd > self._soft_limit: emit warning event (visible in CLI)
  4. If self._run_cost_usd > self._hard_limit: raise CostLimitExceeded
  5. POST meter_ai_completion (async, fire-and-forget after limit check)
```

**Enforcement-rule polling:** At `propagate()` start, `ReveniumCostGate.load_limits()` calls `GET /cost-controls` to fetch current enforcement rules from Revenium (cached for the run duration). This makes Revenium the authoritative source for limits — the demo operator can change them in Revenium's UI and the next run picks them up.

**CostLimitExceeded propagation:** This exception raised inside `on_llm_end` bubbles up through LangChain's callback invocation chain into the LangGraph node function. The graph stops. `TradingAgentsGraph.propagate()` catches it at the `_run_graph` level and surfaces it as a clean error with cost context to the CLI.

**For the demo:** Set a soft limit (e.g., $0.30) that triggers a yellow warning when debate loops start accumulating, and a hard limit (e.g., $0.60) that visibly stops the run. Restore limits between demo runs.

---

## Billing: Cost Per Trading Signal

A completed run (Portfolio Manager writes `final_trade_decision`) triggers a single billing emission:

```python
# In TradingAgentsGraph._run_graph() after graph.invoke() succeeds:
billing_emitter.emit_signal_unit(
    trace_id=current_trace_id.get(),
    customer=config["revenium_customer"],
    product=config["revenium_product"],
    total_cost_usd=revenium_handler.run_total_cost,
    margin_multiplier=config.get("revenium_margin_multiplier", 1.5),
)
```

The billing emitter posts a `meter_event` or `meter_ai_completion` with `billingSkipped=False` and a `totalCost` that includes the margin. Revenium's FinOps view then shows:

- Raw AI cost (from all the per-call meters)
- Billed revenue (from the signal unit event)
- Gross margin per trading signal

This answers the demo question: "What does it cost to produce one BUY/HOLD/SELL decision, and what do we charge the desk for it?"

---

## In-Repo CLI Cost Panel

The existing `cli/main.py` Rich live-progress display has a `MessageBuffer` class that drives the layout. The cost panel is a second Rich `Table` added to the existing `Layout` alongside the existing stats panel.

**Data source:** `ReveniumCallbackHandler.agent_costs` — a `dict[str, dict]` keyed by agent name with `{tokens_in, tokens_out, cost_usd}` fields, updated on each `on_llm_end` call.

**Update mechanism:** The existing Rich `Live` display already refreshes on a timer. The cost panel reads from the same handler instance that is in the `callbacks` list. No additional wiring needed — the handler is a shared object.

**Display shape:**

```
┌─ Agent Costs (live) ─────────────────────────────────┐
│ Agent               Tokens In  Tokens Out  Cost       │
│ market_analyst      12,400     3,200       $0.022     │
│ bull_researcher     8,100      2,400       $0.015 ×2  │
│ bear_researcher     7,900      2,300       $0.014 ×2  │
│ research_manager    15,200     4,100       $0.043     │
│ trader              6,800      1,900       $0.011     │
│ portfolio_manager   18,300     4,800       $0.058     │
│ ─────────────────────────────────────────────────────│
│ Total               ~90k       ~25k        $0.21      │
│ Run limit: $0.30 (soft) / $0.60 (hard)     [OK]      │
└───────────────────────────────────────────────────────┘
```

The `×2` annotation on debate-loop agents signals the cost hotspot visually, before the audience even looks at Revenium's UI.

---

## Architectural Patterns

### Pattern 1: Callback-First Metering (not middleware-in-path)

**What:** Attach a `BaseCallbackHandler` subclass to every LangChain ChatModel. It intercepts `on_llm_end` and reads usage metadata from the `LLMResult` — no wrapping of the LLM object, no monkey-patching, no proxy.

**When to use:** When all LLM calls already flow through LangChain ChatModel objects (which is true here — all provider clients return a LangChain `ChatModel` from `get_llm()`).

**Trade-offs:** Clean separation. The callback fires after the response is received, so it cannot block the call itself (this is a feature for normal metering; cost-gate enforcement must be done post-response). The existing `callbacks` kwarg flow in `TradingAgentsGraph` means zero changes to agents or the graph topology.

**This is the chosen pattern for TradingAgents.**

### Pattern 2: Contextvars for Cross-Cutting Metadata

**What:** Use `contextvars.ContextVar` to carry trace_id, run_meta, and current_agent_name across the entire LangGraph run without threading them through `AgentState` or function signatures.

**When to use:** When metadata needs to be visible inside deeply nested call sites (LangChain callbacks) that don't share the state type — exactly this case.

**Trade-offs:** No state-type changes. No agent code changes. Invisible to the LangGraph topology. The downside is that context must be explicitly set and cleared (use a context manager in `propagate()`).

### Pattern 3: LLM Tags for Agent Identity

**What:** Pass `tags=["agent:market_analyst"]` to the LangChain ChatModel at construction time (in `TradingAgentsGraph.__init__`). These tags appear in `on_chat_model_start(tags=...)` kwargs, giving the callback handler the current agent's identity without any state plumbing.

**When to use:** When agents share the same LLM object (e.g., all analysts use `quick_thinking_llm`). Tags disambiguate which logical agent is making the call even when the underlying model object is shared.

**Implication for current code:** Currently `TradingAgentsGraph` creates two LLMs (`deep_thinking_llm` and `quick_thinking_llm`) shared across agents. Tags at the LLM-construction level would tag the model, not the agent. Two options:

- Option A: Create per-agent LLM instances (increases object count but gives clean per-agent tags). Minor change to `TradingAgentsGraph.__init__` and `GraphSetup`.
- Option B: Set a `ContextVar` inside each agent factory's node function at the top of the call: `current_agent_name.set("market_analyst")`. The callback reads the contextvar instead of tags.

**Recommendation: Option B.** No new LLM instances, no change to `GraphSetup`. Each agent node function sets the contextvar at its first line. This is a one-line change per agent (13 agents).

---

## Recommended File Structure

```
tradingagents/
└── revenium/                       # new package — all Revenium integration code
    ├── __init__.py                 # exports: ReveniumCallbackHandler, setup_revenium
    ├── callback.py                 # ReveniumCallbackHandler (BaseCallbackHandler subclass)
    ├── context.py                  # ContextVar bundle: trace_id, run_meta, current_agent_name
    ├── cost_gate.py                # ReveniumCostGate: load_limits(), check(), CostLimitExceeded
    ├── billing.py                  # ReveniumBillingEmitter: emit_signal_unit()
    ├── client.py                   # thin HTTP client for Revenium API (meter, cost-controls)
    └── config.py                   # revenium_* config key defaults + _ENV_OVERRIDES additions

cli/
└── cost_panel.py                   # Rich Table builder for per-agent cost display
                                    # reads ReveniumCallbackHandler.agent_costs
```

The `revenium/` package is self-contained. It does not import from `agents/` or `graph/` — only from `langchain_core.callbacks` and stdlib. `trading_graph.py` imports from it (one-way dependency: graph → revenium, not the reverse).

---

## Build Order (Dependencies Between Pieces)

```
Step 1: Revenium API client + config keys
        tradingagents/revenium/client.py
        tradingagents/revenium/config.py
        default_config.py additions (revenium_* keys + _ENV_OVERRIDES)
        → No dependencies on other new code. Testable in isolation (mock HTTP).

Step 2: Context machinery
        tradingagents/revenium/context.py
        → Depends on Step 1 config. Zero LangGraph dependency.
        → Add one-line contextvar set to each agent node function (13 files).
        → Add propagate() entry/exit context manager in trading_graph.py.

Step 3: ReveniumCallbackHandler (core metering seam)
        tradingagents/revenium/callback.py
        → Depends on Steps 1 + 2 (client, context).
        → Wire into TradingAgentsGraph.__init__ callbacks list.
        → At this point: metering fires on every LLM call. Trace/squad appears in Revenium.

Step 4: Cost gate
        tradingagents/revenium/cost_gate.py
        → Depends on Steps 1 + 3 (client + callback handler for run cost accumulation).
        → Integrate into callback handler's on_llm_end.
        → Demo: set limits in Revenium UI, watch run halt.

Step 5: CLI cost panel
        cli/cost_panel.py
        cli/main.py additions (add panel to Layout)
        → Depends on Step 3 (reads handler.agent_costs).
        → No Revenium API calls — purely local data from the handler.

Step 6: Billing emission
        tradingagents/revenium/billing.py
        → Depends on Steps 1 + 3 (client + run total cost from handler).
        → Call from trading_graph._run_graph() after graph.invoke() succeeds.
        → Demo: show "cost per trading signal" + margin in Revenium FinOps view.
```

Steps 1-3 are the critical path for the meter→trace demo pillar. Steps 4 and 6 are the control and monetize pillars respectively. Step 5 (CLI panel) is independent of Step 6 and can be built alongside Step 3.

---

## Integration Points

### The Single Metering Seam

The metering seam is the `callbacks` kwarg path:

```
cli/main.py
  TradingAgentsGraph(callbacks=[StatsCallbackHandler(), ReveniumCallbackHandler()])
    trading_graph.py __init__:
      llm_kwargs["callbacks"] = self.callbacks
      create_llm_client(..., callbacks=...) → BaseLLMClient.__init__(kwargs=...)
        AnthropicClient / GoogleClient / OpenAIClient / ...
          ChatAnthropic(callbacks=...) / ChatOpenAI(callbacks=...) / ...
            ← every LLM call fires callbacks
```

**This path already exists and already works for `StatsCallbackHandler`.** The only addition is appending a second handler to the list.

### Seam Coverage

| Provider | Covered by callbacks path? |
|----------|---------------------------|
| Anthropic (`ChatAnthropic`) | Yes — langchain_anthropic honors callbacks |
| Google (`ChatGoogleGenerativeAI`) | Yes — langchain_google_genai honors callbacks |
| OpenAI + all OpenAI-compatible | Yes — langchain_openai honors callbacks |
| Azure OpenAI | Yes — langchain_openai AzureChatOpenAI honors callbacks |
| AWS Bedrock | Yes — langchain_aws ChatBedrockConverse honors callbacks |

All 15+ providers in the existing registry are covered with one seam. This is the architecture's core strength: no per-provider metering code.

### Conventions Respected

- **Multi-provider neutrality**: The metering code lives in `tradingagents/revenium/`, not in any provider client. No `if provider == "anthropic"` logic.
- **No model hardcoding**: Cost-per-token rates can be fetched from Revenium's model catalog via API, or stored in a `revenium/` config table (not in `capabilities.py`, which is provider-quirk territory).
- **Config pattern**: New keys follow the `DEFAULT_CONFIG` + `_ENV_OVERRIDES` pattern. `REVENIUM_API_KEY` maps to `revenium_api_key`.
- **Test discipline**: All Revenium HTTP calls are behind the `client.py` abstraction. Tests mock the client. `revenium_enabled=False` in test config silences all metering without code changes.
- **Fail-open**: Metering failures (network error posting to Revenium) must not block the trading run. The handler catches exceptions from `client.meter()` with `# noqa: BLE001 — fail open, never block the run`.

---

## Anti-Patterns

### Anti-Pattern 1: Per-Provider Metering Wrappers

**What people do:** Write a `ReveniumAnthropicClient`, `ReveniumOpenAIClient`, etc., each wrapping the underlying provider client to intercept calls.

**Why it's wrong:** Duplicates code across all 15+ providers. Breaks when a new provider is added. Violates the repo's multi-provider-neutrality constraint. Already solved by the callbacks path.

**Do this instead:** One `ReveniumCallbackHandler` in the callbacks list. Covers all providers.

### Anti-Pattern 2: Storing trace_id in AgentState

**What people do:** Add `trace_id: str` to `AgentState` and thread it through every node function's state delta.

**Why it's wrong:** Requires changing `AgentState`, `Propagator.create_initial_state`, `_log_state`, and every agent factory's return dict — significant diff for zero functional benefit since callbacks cannot read state.

**Do this instead:** `contextvars.ContextVar` set once in `propagate()` before `graph.invoke()`.

### Anti-Pattern 3: Synchronous Metering in the Call Path

**What people do:** POST to Revenium synchronously inside `on_llm_end`, blocking the next LangGraph node from starting until the HTTP call completes.

**Why it's wrong:** Each LLM call adds 50–200ms network latency to the run. For a 14-step pipeline with debate loops this adds seconds of wall time. Bad for demo pacing.

**Do this instead:** Fire-and-forget with `asyncio.ensure_future` or a background thread from a thread pool. The cost accumulation and gate check (local arithmetic) run synchronously; only the HTTP POST is offloaded.

### Anti-Pattern 4: Checking Cost Controls on Every Token Stream Event

**What people do:** Hook `on_llm_new_token` (streaming callback) to check limits token-by-token.

**Why it's wrong:** Current graph runs non-streaming (`graph.invoke`, not `graph.stream`). Even in streaming mode, per-token callbacks fire hundreds of times per call and the limit check is cheap enough to do once per call.

**Do this instead:** Check cost gate once in `on_llm_end` after usage_metadata is available.

---

## Sources

- Revenium API schema: https://revenium.readme.io/reference/meter_ai_completion (verified 2026-06-26)
- Revenium OTLP integration: https://docs.revenium.io/integrations/otlp-integration (verified 2026-06-26)
- Revenium PyPI org (12 packages): https://pypi.org/org/revenium/ (verified 2026-06-26)
- `revenium-middleware-langchain` PyPI (archived; recommend `revenium-python-sdk`): https://pypi.org/project/revenium-middleware-langchain/ (verified 2026-06-26)
- `revenium-middleware-openai` usage pattern + metadata fields: https://pypi.org/project/revenium-middleware-openai/ (verified 2026-06-26)
- Codebase seams read directly: `tradingagents/llm_clients/factory.py`, `tradingagents/llm_clients/base_client.py`, `tradingagents/graph/trading_graph.py`, `cli/stats_handler.py`, `tradingagents/agents/utils/agent_states.py`, `tradingagents/default_config.py`

---

*Architecture research for: Revenium integration into TradingAgents*
*Researched: 2026-06-26*
