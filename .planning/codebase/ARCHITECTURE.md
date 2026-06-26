<!-- refreshed: 2026-06-26 -->
# Architecture

**Analysis Date:** 2026-06-26

## System Overview

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│                          Entry Points                                        │
│   CLI (`cli/main.py`)          Script (`main.py`)    Programmatic API        │
└───────────────────────────────────┬─────────────────────────────────────────┘
                                    │
                                    ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                     TradingAgentsGraph                                       │
│                  `tradingagents/graph/trading_graph.py`                      │
│  • Creates LLM clients (deep + quick)                                        │
│  • Builds ToolNodes per analyst category                                     │
│  • Orchestrates setup, propagation, signal extraction, reflection            │
└───────┬──────────────────┬────────────────────┬────────────────────┬─────────┘
        │                  │                    │                    │
        ▼                  ▼                    ▼                    ▼
┌──────────────┐  ┌─────────────────┐  ┌──────────────┐  ┌──────────────────┐
│  GraphSetup  │  │   Propagator    │  │  Reflector   │  │ SignalProcessor  │
│  `setup.py`  │  │`propagation.py` │  │`reflection.py│  │`signal_proc...py`│
│ Wires LangGraph│ │Creates AgentState│ │Phase-B LLM   │  │ parse_rating()   │
│  StateGraph  │  │and graph args   │  │ reflection   │  │(no LLM call now) │
└──────┬───────┘  └─────────────────┘  └──────────────┘  └──────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                    LangGraph StateGraph (AgentState)                         │
│              `tradingagents/agents/utils/agent_states.py`                    │
│                                                                              │
│  [Market/Sentiment/News/Fundamentals Analysts] (sequential, tool loops)      │
│         ↓                                                                    │
│  [Bull Researcher] ⇄ [Bear Researcher] (debate loop, 2*max_debate_rounds)   │
│         ↓                                                                    │
│  [Research Manager] → [Trader]                                               │
│         ↓                                                                    │
│  [Aggressive] ⇄ [Conservative] ⇄ [Neutral] (3*max_risk_discuss_rounds)      │
│         ↓                                                                    │
│  [Portfolio Manager] → END                                                   │
└───────────────────────────────────────────────────────────────────────────────┘
       │                              │
       ▼                              ▼
┌─────────────────────┐   ┌──────────────────────────────────────────────────┐
│   LLM Clients       │   │              Data Layer                          │
│`llm_clients/`       │   │         `tradingagents/dataflows/`               │
│ factory.py routes   │   │  interface.py → vendor routing → yfinance /      │
│ to provider-specific│   │  alpha_vantage / fred / polymarket               │
│ client (Anthropic,  │   └──────────────────────────────────────────────────┘
│ Google, OpenAI, ...) │
└─────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                     Persistence (~/.tradingagents/)                          │
│  Memory log: `memory/trading_memory.md`   (TradingMemoryLog)                │
│  Checkpoints: `cache/checkpoints/<TICKER>.db` (SqliteSaver, opt-in)         │
│  Results: `logs/<TICKER>/TradingAgentsStrategy_logs/full_states_log_*.json`  │
└──────────────────────────────────────────────────────────────────────────────┘
```

## Component Responsibilities

| Component | Responsibility | File |
|-----------|----------------|------|
| `TradingAgentsGraph` | Public API: construct, call `.propagate()` | `tradingagents/graph/trading_graph.py` |
| `GraphSetup` | Wire LangGraph `StateGraph` topology, register all nodes and edges | `tradingagents/graph/setup.py` |
| `ConditionalLogic` | Edge predicates: analyst tool loops, debate rounds, risk rounds | `tradingagents/graph/conditional_logic.py` |
| `Propagator` | Build initial `AgentState`; return graph invocation args | `tradingagents/graph/propagation.py` |
| `Reflector` | Phase-B deferred LLM reflection on realized returns | `tradingagents/graph/reflection.py` |
| `SignalProcessor` | Extract 5-tier rating from Portfolio Manager output (heuristic) | `tradingagents/graph/signal_processing.py` |
| `AnalystExecutionPlan` | Map selected analyst keys to node/tool/clear node names | `tradingagents/graph/analyst_execution.py` |
| `checkpointer` | Per-ticker SQLite SqliteSaver for crash-resume | `tradingagents/graph/checkpointer.py` |
| `AgentState` | LangGraph state type: all report fields + debate sub-states | `tradingagents/agents/utils/agent_states.py` |
| Analyst agents | `create_*(llm)` factories; node fn `(state) -> state-delta` | `tradingagents/agents/analysts/` |
| Researcher agents | Bull/Bear debate; read all four reports, write debate state | `tradingagents/agents/researchers/` |
| Research Manager | Deep-think LLM; structured `ResearchPlan`; hands off to Trader | `tradingagents/agents/managers/research_manager.py` |
| Trader | Quick-think LLM; structured `TraderProposal` from research plan | `tradingagents/agents/trader/trader.py` |
| Risk debaters | Aggressive/Conservative/Neutral viewpoints on Trader's proposal | `tradingagents/agents/risk_mgmt/` |
| Portfolio Manager | Deep-think LLM; structured `PortfolioDecision`; final output | `tradingagents/agents/managers/portfolio_manager.py` |
| `TradingMemoryLog` | Append-only markdown log; provides `past_context` to PM | `tradingagents/agents/utils/memory.py` |
| `agent_utils.py` | Re-export hub: all data tools + language/instrument helpers | `tradingagents/agents/utils/agent_utils.py` |
| `structured.py` | `bind_structured` + `invoke_structured_or_freetext` helpers | `tradingagents/agents/utils/structured.py` |
| `schemas.py` | Pydantic schemas + render functions for structured-output agents | `tradingagents/agents/schemas.py` |
| `interface.py` | Vendor routing layer: `route_to_vendor(method, ...)` | `tradingagents/dataflows/interface.py` |
| `errors.py` | Vendor error taxonomy: `NoMarketDataError`, `VendorRateLimitError`, `VendorNotConfiguredError` | `tradingagents/dataflows/errors.py` |
| `symbol_utils.py` | Ticker normalization (forex/crypto/index aliases, path hardening) | `tradingagents/dataflows/symbol_utils.py` |
| `factory.py` | LLM client factory: lazy-import per provider | `tradingagents/llm_clients/factory.py` |
| `capabilities.py` | Declarative per-model API quirks table | `tradingagents/llm_clients/capabilities.py` |
| `DEFAULT_CONFIG` | Single source of truth for all config keys + env-var overrides | `tradingagents/default_config.py` |
| `dataflows/config.py` | Process-global mutable config (`set_config` / `get_config`) | `tradingagents/dataflows/config.py` |

## Pattern Overview

**Overall:** Multi-agent pipeline on a LangGraph `StateGraph` with debate loops and structured output.

**Key Characteristics:**
- The graph is compiled once from a `StateGraph(AgentState)` workflow; analyst set is configurable at compile time via `selected_analysts`.
- Analysts run sequentially (tool loop per analyst: invoke → tool_calls? → ToolNode → invoke → done → clear messages → next analyst).
- Research debate and risk debate are explicit loop-back conditional edges counted against round limits in `ConditionalLogic`.
- Three agents (Research Manager, Trader, Portfolio Manager) use structured output via `bind_structured` + `invoke_structured_or_freetext` with graceful free-text fallback.
- All agent tools are thin wrappers; actual data fetching is vendor-routed through `interface.route_to_vendor`.
- Provider-specific LLM quirks are encoded in `capabilities.py` (declarative table), not scattered `if` ladders.

## Layers

**Entry Layer:**
- Purpose: Accept user input; configure and invoke `TradingAgentsGraph`
- Location: `cli/main.py`, `main.py`
- Contains: Typer CLI, Rich UI, interactive config flow
- Depends on: `TradingAgentsGraph`, `DEFAULT_CONFIG`
- Used by: End users / scripts

**Orchestration Layer:**
- Purpose: Wire and run the LangGraph pipeline; own cross-cutting concerns (memory, checkpoints, reflection)
- Location: `tradingagents/graph/`
- Contains: `TradingAgentsGraph`, `GraphSetup`, `ConditionalLogic`, `Propagator`, `Reflector`, `SignalProcessor`, `checkpointer`
- Depends on: Agent layer, LLM client layer, data layer
- Used by: Entry layer

**Agent Layer:**
- Purpose: Implement each agent's reasoning logic as a `create_*(llm)` factory returning `(state) -> state-delta`
- Location: `tradingagents/agents/`
- Contains: Analysts (`analysts/`), Researchers (`researchers/`), Managers (`managers/`), Risk (`risk_mgmt/`), Trader (`trader/`), shared utils (`utils/`)
- Depends on: Data tools from `agent_utils.py`; LLM passed in at construction
- Used by: Orchestration layer

**Data Layer:**
- Purpose: Vendor-neutral data access; route to yfinance / alpha_vantage / fred / polymarket based on config
- Location: `tradingagents/dataflows/`
- Contains: `interface.py` (router), vendor modules, `config.py`, `errors.py`, `symbol_utils.py`
- Depends on: External vendor SDKs; process-global config
- Used by: Agent tool functions in `agents/utils/*_tools.py`

**LLM Client Layer:**
- Purpose: Provide a uniform `BaseLLMClient.get_llm()` interface across all providers
- Location: `tradingagents/llm_clients/`
- Contains: `factory.py`, provider clients (`anthropic_client.py`, `openai_client.py`, `google_client.py`, `azure_client.py`, `bedrock_client.py`), `capabilities.py`, `model_catalog.py`
- Depends on: Provider SDKs (lazily imported); `capabilities.py` for quirk flags
- Used by: Orchestration layer

**Persistence Layer:**
- Purpose: Cross-run learning via decision log; crash-resume via SQLite checkpoints
- Location: `~/.tradingagents/` (runtime); `tradingagents/agents/utils/memory.py`, `tradingagents/graph/checkpointer.py`
- Contains: `TradingMemoryLog`, `SqliteSaver` wrappers
- Depends on: Filesystem; LangGraph checkpoint API
- Used by: Orchestration layer

## Data Flow

### Primary Request Path

1. **Entry** — `cli/main.py` or `main.py` calls `TradingAgentsGraph(config=...).propagate(ticker, date)` (`tradingagents/graph/trading_graph.py:321`)
2. **Memory pre-check** — `_resolve_pending_entries(ticker)`: fetch returns for prior pending log entries, generate reflections, batch-write (`trading_graph.py:269`)
3. **State init** — `Propagator.create_initial_state(ticker, date, ...)` builds blank `AgentState`; `instrument_context` resolved once via `resolve_instrument_identity` (`propagation.py:18`)
4. **Graph invoke** — `self.graph.invoke(init_agent_state, **args)` runs the full StateGraph (`trading_graph.py:396`)
5. **Analyst phase** — each selected analyst loops: LLM call → tool_calls present → `ToolNode` executes data fetch via `route_to_vendor` → LLM call again → no tool_calls → clear messages node → next analyst (`setup.py:107-124`)
6. **Research debate** — `Bull Researcher` and `Bear Researcher` alternate via conditional edges until `count >= 2 * max_debate_rounds`; `Research Manager` (deep-think + structured output) arbitrates (`conditional_logic.py:52`)
7. **Trader** — reads research plan; emits structured `TraderProposal` with action/price/sizing (`agents/trader/trader.py`)
8. **Risk debate** — Aggressive / Conservative / Neutral rotate via conditional edges until `count >= 3 * max_risk_discuss_rounds` (`conditional_logic.py:63`)
9. **Portfolio Manager** — deep-think LLM; structured `PortfolioDecision`; writes `final_trade_decision` to state (`agents/managers/portfolio_manager.py`)
10. **Signal extraction** — `SignalProcessor.process_signal` calls `parse_rating(final_trade_decision)` deterministically (`signal_processing.py:29`)
11. **State log** — `_log_state` writes `full_states_log_{date}.json` to `~/.tradingagents/logs/<TICKER>/TradingAgentsStrategy_logs/` (`trading_graph.py:419`)
12. **Memory write** — `TradingMemoryLog.store_decision` appends pending entry to `trading_memory.md` (`trading_graph.py:405`)
13. **Return** — `(final_state, decision_string)` to caller

### Checkpoint Resume Path

1. `checkpoint_enabled=True` in config causes `TradingAgentsGraph.propagate` to open a `SqliteSaver` for the ticker (`trading_graph.py:337`)
2. Graph is recompiled with `workflow.compile(checkpointer=saver)`
3. `thread_id(ticker, date)` is injected into `config["configurable"]` — same date resumes, new date starts fresh
4. On success, `clear_checkpoint` deletes thread rows from the SQLite DB (`checkpointer.py:76`)

### Phase-B Deferred Reflection

1. At start of a new run for the same ticker, `_resolve_pending_entries` queries `TradingMemoryLog` for pending same-ticker entries
2. `_fetch_returns` fetches realized price returns via yfinance (`trading_graph.py:224`)
3. `Reflector.reflect_on_final_decision` calls the quick-think LLM for a 2-4 sentence prose reflection (`reflection.py:31`)
4. `TradingMemoryLog.batch_update_with_outcomes` atomically writes reflections and marks entries resolved

**State Management:**
- `AgentState` extends LangGraph `MessagesState` (Annotated dict); fields accumulate through nodes
- Sub-states `InvestDebateState` and `RiskDebateState` are nested TypedDicts within `AgentState`
- Adding a field requires updating `AgentState` in `agents/utils/agent_states.py`, `Propagator.create_initial_state`, and `_log_state` in `trading_graph.py`

## Key Abstractions

**`create_*(llm)` Factory Pattern:**
- Purpose: Every agent is a closure factory. Call it with an LLM; get back a node function `(state: AgentState) -> dict` (state delta).
- Examples: `tradingagents/agents/analysts/market_analyst.py`, `tradingagents/agents/researchers/bull_researcher.py`, `tradingagents/agents/managers/portfolio_manager.py`
- Pattern: `def create_X(llm): def node(state) -> dict: ... return node`

**Vendor Router (`route_to_vendor`):**
- Purpose: All data fetching flows through a single dispatch function that reads `config["data_vendors"]` and `config["tool_vendors"]` to choose the ordered vendor chain.
- File: `tradingagents/dataflows/interface.py:161`
- Pattern: `route_to_vendor("get_stock_data", ticker, start, end)` — never call vendor modules directly from agent tools.

**Structured Output with Fallback (`bind_structured` + `invoke_structured_or_freetext`):**
- Purpose: Centralize `with_structured_output(Schema)` wrapping and free-text fallback for Research Manager, Trader, and Portfolio Manager.
- File: `tradingagents/agents/utils/structured.py`
- Pattern: Call `bind_structured(llm, Schema, "Agent Name")` at factory time; call `invoke_structured_or_freetext(structured_llm, plain_llm, prompt, render_fn, "Agent Name")` inside the node.

**`ModelCapabilities` Declarative Table:**
- Purpose: Per-model API quirks (tool_choice support, json_mode vs json_schema, reasoning content roundtrip) live in one frozen dataclass table, not `if` ladders in client code.
- File: `tradingagents/llm_clients/capabilities.py`
- Pattern: Add a model entry to the table; client code reads `get_capabilities(model_name)`.

**`TradingMemoryLog` (Cross-Run Learning):**
- Purpose: Append-only markdown log of decisions; resolved entries inject past lessons into the Portfolio Manager prompt via `past_context`.
- File: `tradingagents/agents/utils/memory.py`
- Pattern: `store_decision` at run end; `get_past_context(ticker)` at run start for PM prompt injection.

## Entry Points

**CLI:**
- Location: `cli/main.py` — Typer `app` with `analyze` command
- Triggers: `tradingagents` console script or `python -m cli.main`
- Responsibilities: Interactive provider/model/ticker selection, Rich live-progress UI, `StatsCallbackHandler` for token tracking, calls `TradingAgentsGraph.propagate`

**Scripted:**
- Location: `main.py`
- Triggers: `python main.py`
- Responsibilities: Minimal example run (NVDA, hardcoded date), useful for quick debugging

**Programmatic API:**
- Location: `tradingagents/graph/trading_graph.py` (`TradingAgentsGraph`)
- Triggers: `import tradingagents; TradingAgentsGraph(...).propagate(ticker, date)`
- Responsibilities: Full public API; supports `selected_analysts`, `config`, `callbacks`, `debug`

## Architectural Constraints

- **Threading:** Single-threaded event loop (LangGraph runs synchronously). `analyst_concurrency_limit` config key is plumbed through to `AnalystExecutionPlan` but the current implementation runs analysts sequentially (concurrency_limit=1 default).
- **Global state:** `tradingagents/dataflows/config.py` holds a process-global `_config` dict mutated by `set_config`. `TradingAgentsGraph.__init__` calls `set_config(self.config)` at construction — not thread-safe for concurrent graph instances with different configs.
- **Circular imports:** None detected, but `agent_utils.py` is a central re-export hub that many modules import; adding new imports there can pull in heavy deps.
- **Provider multi-instance:** `create_llm_client` lazily imports provider SDKs — safe for collection at test time without API keys. Clients are instantiated once per `TradingAgentsGraph`.
- **Config immutability:** `get_config()` returns a `deepcopy`; `set_config` merges one level deep for dict-typed keys, replaces scalars. Nested-dict overrides beyond one level are not merged.

## Anti-Patterns

### Calling vendor modules directly from agent tools

**What happens:** Importing and calling `tradingagents.dataflows.y_finance.get_YFin_data_online` directly in a tool function.
**Why it's wrong:** Bypasses vendor routing — fallback logic, rate-limit handling, and user-configured vendor selection are skipped.
**Do this instead:** Always call `route_to_vendor("get_stock_data", ...)` from `tradingagents/dataflows/interface.py`. Agent tool functions in `tradingagents/agents/utils/*_tools.py` already follow this pattern.

### Hardcoding model names or provider behavior in agents or clients

**What happens:** Adding an `if model == "deepseek-reasoner":` block in client code or agent prompts.
**Why it's wrong:** Breaks multi-provider portability; the quirk is invisible to callers and invisible in the single source of truth.
**Do this instead:** Add a row to `tradingagents/llm_clients/capabilities.py` (for API quirks) or `tradingagents/llm_clients/model_catalog.py` (for model lists).

### Hand-rolling structured output calls in new agents

**What happens:** Calling `llm.with_structured_output(Schema)` inline in an agent factory without the fallback wrapper.
**Why it's wrong:** Providers that don't support structured output will raise at runtime; there is no graceful degradation.
**Do this instead:** Use `bind_structured` + `invoke_structured_or_freetext` from `tradingagents/agents/utils/structured.py`.

### Adding config keys without an `_ENV_OVERRIDES` entry

**What happens:** Defining a new key in `DEFAULT_CONFIG` without a corresponding row in `_ENV_OVERRIDES` in `tradingagents/default_config.py`.
**Why it's wrong:** The key cannot be set via environment variable; users must edit code or pass a dict.
**Do this instead:** Add a `"TRADINGAGENTS_FOO": "foo"` row to `_ENV_OVERRIDES` alongside the new key in `DEFAULT_CONFIG`.

## Error Handling

**Strategy:** Vendor errors are caught at the routing layer (`interface.route_to_vendor`) and either trigger fallback to the next vendor or return a sentinel string `"NO_DATA_AVAILABLE: ..."` that agents report as unavailable rather than hallucinating.

**Patterns:**
- `NoMarketDataError` → try next vendor in chain; if all exhausted, return `NO_DATA_AVAILABLE` sentinel string
- `VendorRateLimitError` → skip to next vendor, log warning
- `VendorNotConfiguredError` → skip to next vendor, log warning, surface original error if no vendor can serve the call
- Other exceptions → log warning with vendor name, try next vendor; re-raise first error if all vendors fail
- Structured-output failures → `invoke_structured_or_freetext` catches any exception, logs warning, retries as plain `llm.invoke`

## Cross-Cutting Concerns

**Logging:** `logging.getLogger(__name__)` throughout; no structured logging framework. Key log points: vendor fallback events, structured-output fallback, checkpoint resume/clear.
**Validation:** Ticker path-traversal hardening in `tradingagents/dataflows/symbol_utils.py` (`safe_ticker_component`); model validation in `BaseLLMClient.warn_if_unknown_model` (warn-only, not blocking). Config type coercion in `default_config._coerce`.
**Authentication:** No auth in the framework itself; API keys are read from environment variables (mapped in `tradingagents/llm_clients/api_key_env.py`). `VendorNotConfiguredError` is raised when a required key is absent.
**i18n:** `get_language_instruction()` in `tradingagents/agents/utils/agent_utils.py` appends a language directive to all report-facing agent prompts when `config["output_language"] != "English"`. Internal debate stays English. Coverage guarded by `tests/test_i18n_coverage.py`.

---

*Architecture analysis: 2026-06-26*
