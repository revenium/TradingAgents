# Codebase Structure

**Analysis Date:** 2026-06-26

## Directory Layout

```
TradingAgents/
├── tradingagents/                  # Main Python package
│   ├── __init__.py
│   ├── default_config.py           # DEFAULT_CONFIG + env-var overrides (_ENV_OVERRIDES)
│   ├── agents/                     # All agent factories and shared utilities
│   │   ├── __init__.py             # Public re-exports for all create_*() factories
│   │   ├── schemas.py              # Pydantic schemas + render helpers for structured output
│   │   ├── analysts/               # Research-phase data-gathering agents
│   │   │   ├── market_analyst.py
│   │   │   ├── sentiment_analyst.py
│   │   │   ├── news_analyst.py
│   │   │   └── fundamentals_analyst.py
│   │   ├── researchers/            # Bull/Bear debate agents
│   │   │   ├── bull_researcher.py
│   │   │   └── bear_researcher.py
│   │   ├── managers/               # Deep-think decision agents
│   │   │   ├── research_manager.py
│   │   │   └── portfolio_manager.py
│   │   ├── risk_mgmt/              # Risk debate agents
│   │   │   ├── aggressive_debator.py
│   │   │   ├── conservative_debator.py
│   │   │   └── neutral_debator.py
│   │   ├── trader/
│   │   │   └── trader.py
│   │   └── utils/                  # Shared agent infrastructure
│   │       ├── agent_states.py     # AgentState, InvestDebateState, RiskDebateState
│   │       ├── agent_utils.py      # Re-export hub: all tools + language/instrument helpers
│   │       ├── structured.py       # bind_structured + invoke_structured_or_freetext
│   │       ├── memory.py           # TradingMemoryLog (cross-run decision log)
│   │       ├── rating.py           # parse_rating() heuristic
│   │       ├── core_stock_tools.py
│   │       ├── fundamental_data_tools.py
│   │       ├── macro_data_tools.py
│   │       ├── news_data_tools.py
│   │       ├── prediction_markets_tools.py
│   │       ├── technical_indicators_tools.py
│   │       └── market_data_validation_tools.py
│   ├── graph/                      # Orchestration layer
│   │   ├── __init__.py
│   │   ├── trading_graph.py        # TradingAgentsGraph (main public API)
│   │   ├── setup.py                # GraphSetup: StateGraph wiring
│   │   ├── conditional_logic.py    # ConditionalLogic: edge predicates
│   │   ├── analyst_execution.py    # AnalystExecutionPlan, AnalystNodeSpec
│   │   ├── propagation.py          # Propagator: state init + graph args
│   │   ├── signal_processing.py    # SignalProcessor: rating extraction
│   │   ├── reflection.py           # Reflector: Phase-B deferred LLM reflection
│   │   └── checkpointer.py         # SqliteSaver wrappers (crash-resume)
│   ├── dataflows/                  # Data access + vendor routing
│   │   ├── interface.py            # route_to_vendor() + VENDOR_METHODS registry
│   │   ├── config.py               # Process-global config (set_config / get_config)
│   │   ├── errors.py               # VendorError taxonomy
│   │   ├── symbol_utils.py         # Ticker normalization + safe_ticker_component
│   │   ├── y_finance.py            # yfinance vendor implementations
│   │   ├── yfinance_news.py        # yfinance news fetching
│   │   ├── alpha_vantage*.py       # Alpha Vantage vendor modules (stock, news, fundamentals, indicator, common)
│   │   ├── fred.py                 # FRED macro data vendor
│   │   ├── polymarket.py           # Polymarket prediction markets vendor
│   │   ├── reddit.py               # Reddit social data
│   │   ├── stocktwits.py           # StockTwits social data
│   │   ├── stockstats_utils.py     # StockStats indicator helpers
│   │   ├── market_data_validator.py
│   │   └── utils.py                # safe_ticker_component + misc helpers
│   └── llm_clients/                # LLM provider abstraction layer
│       ├── __init__.py
│       ├── factory.py              # create_llm_client() (lazy-import dispatch)
│       ├── base_client.py          # BaseLLMClient ABC
│       ├── capabilities.py         # Declarative per-model quirks table
│       ├── model_catalog.py        # Known models per provider
│       ├── validators.py           # Model validation helpers
│       ├── api_key_env.py          # Provider → API-key env-var mapping
│       ├── openai_client.py        # OpenAI + OpenAI-compatible registry
│       ├── anthropic_client.py
│       ├── google_client.py
│       ├── azure_client.py
│       └── bedrock_client.py
├── cli/                            # Interactive Typer CLI
│   ├── __init__.py
│   ├── main.py                     # Typer app, `analyze` command, Rich live-progress UI
│   ├── models.py                   # Provider/model selection helpers
│   ├── config.py                   # CLI-level config helpers
│   ├── utils.py                    # Prompt helpers (get_ticker, select_analysts, etc.)
│   ├── stats_handler.py            # StatsCallbackHandler (LangChain callback for token/tool tracking)
│   ├── announcements.py            # Version-announcement display
│   └── static/
│       └── welcome.txt
├── tests/                          # pytest suite (unit + integration + smoke)
│   ├── conftest.py                 # Autouse fixtures: placeholder API keys, config reset
│   └── test_*.py                   # One file per concern (60+ test files)
├── scripts/                        # Utility/maintenance scripts
├── assets/                         # Documentation assets
│   └── cli/                        # CLI screenshot assets
├── main.py                         # Minimal scripted run example (NVDA)
├── test.py                         # Legacy scratch file (NOT part of pytest suite)
├── pyproject.toml                  # Package metadata, dependencies, ruff + pytest config
├── requirements.txt                # Pinned requirements
├── uv.lock                         # uv lockfile
├── Dockerfile
├── docker-compose.yml
└── CLAUDE.md                       # Project instructions for Claude
```

## Directory Purposes

**`tradingagents/agents/analysts/`:**
- Purpose: Data-gathering agents that run in the first phase of the pipeline
- Contains: One file per analyst type; each exports a `create_<name>_analyst(llm)` factory
- Key files: `market_analyst.py`, `sentiment_analyst.py`, `news_analyst.py`, `fundamentals_analyst.py`

**`tradingagents/agents/researchers/`:**
- Purpose: Bull/Bear debate agents that read all four analyst reports and argue for/against investment
- Contains: `bull_researcher.py`, `bear_researcher.py`
- Key files: Each exports `create_bull_researcher(llm)` / `create_bear_researcher(llm)`

**`tradingagents/agents/managers/`:**
- Purpose: Deep-think decision agents that use structured output (Pydantic schemas)
- Contains: `research_manager.py`, `portfolio_manager.py`
- Key files: Both use `bind_structured` + `invoke_structured_or_freetext` from `utils/structured.py`

**`tradingagents/agents/risk_mgmt/`:**
- Purpose: Three-way risk debate (aggressive / conservative / neutral perspectives on the Trader's proposal)
- Contains: `aggressive_debator.py`, `conservative_debator.py`, `neutral_debator.py`

**`tradingagents/agents/utils/`:**
- Purpose: Shared infrastructure used by all agent factories
- Contains: State types, tool re-exports, structured-output helpers, memory log, rating parser
- Key files: `agent_states.py` (state types), `agent_utils.py` (single import point for all tools), `structured.py` (structured output helpers), `memory.py` (cross-run log)

**`tradingagents/graph/`:**
- Purpose: Orchestration — wire the LangGraph graph, run it, extract results
- Contains: Public API class, graph setup, edge predicates, state initialization, signal extraction, reflection, checkpointing
- Key files: `trading_graph.py` (entry point), `setup.py` (topology), `conditional_logic.py` (loop control)

**`tradingagents/dataflows/`:**
- Purpose: Vendor-neutral data access layer
- Contains: Router, vendor implementations, config, error types, symbol normalization
- Key files: `interface.py` (must be the only data-fetch entry point from agent tools), `config.py` (process-global config), `errors.py` (error taxonomy), `symbol_utils.py` (ticker normalization)

**`tradingagents/llm_clients/`:**
- Purpose: Uniform LLM client abstraction across providers
- Contains: Factory, provider clients, capability table, model catalog
- Key files: `factory.py` (always use this, never import provider clients directly), `capabilities.py` (add model quirks here)

**`cli/`:**
- Purpose: Interactive command-line interface with Rich UI
- Contains: Typer app, model/config selection, live progress display, token stats
- Key files: `main.py` (CLI app), `utils.py` (prompt helpers), `stats_handler.py` (LangChain callback)

**`tests/`:**
- Purpose: Full pytest suite; no live API keys needed (conftest autouses placeholder key fixtures)
- Contains: ~60 test files, one per concern; `conftest.py` with shared fixtures
- Key files: `conftest.py`, `test_signal_processing.py`, `test_vendor_routing.py`, `test_structured_agents.py`

## Key File Locations

**Entry Points:**
- `cli/main.py`: Interactive CLI entry point (`tradingagents` console script)
- `main.py`: Scripted minimal run (not production; useful for debugging)
- `tradingagents/graph/trading_graph.py`: `TradingAgentsGraph` — main programmatic API

**Configuration:**
- `tradingagents/default_config.py`: `DEFAULT_CONFIG` — single source of truth for all config keys and `TRADINGAGENTS_*` env-var overrides
- `tradingagents/dataflows/config.py`: `set_config` / `get_config` — process-global runtime config

**Core State:**
- `tradingagents/agents/utils/agent_states.py`: `AgentState`, `InvestDebateState`, `RiskDebateState`

**Schema Definitions:**
- `tradingagents/agents/schemas.py`: All Pydantic schemas (`ResearchPlan`, `TraderProposal`, `PortfolioDecision`, `SentimentReport`) + render functions

**Data Routing:**
- `tradingagents/dataflows/interface.py`: `route_to_vendor` — the only correct way to call data vendors from agent tools

**LLM Factory:**
- `tradingagents/llm_clients/factory.py`: `create_llm_client` — always use this; never import provider clients directly

**Model Quirks:**
- `tradingagents/llm_clients/capabilities.py`: Add new model capability entries here

**Testing Fixtures:**
- `tests/conftest.py`: Autouse fixtures that inject placeholder API keys and reset global dataflows config between tests

## Naming Conventions

**Files:**
- Snake_case for all Python files: `trading_graph.py`, `agent_states.py`, `bull_researcher.py`
- Agent files named after the agent role: `market_analyst.py`, `portfolio_manager.py`
- Test files prefixed `test_`: `test_vendor_routing.py`, `test_structured_agents.py`

**Directories:**
- Lowercase, short, descriptive: `analysts/`, `risk_mgmt/`, `llm_clients/`, `dataflows/`

**Functions/Classes:**
- Agent factories: `create_<role>(llm)` — e.g. `create_market_analyst`, `create_portfolio_manager`
- Node functions (closures): named after role — `market_analyst_node`, `portfolio_manager_node`
- Public classes: PascalCase — `TradingAgentsGraph`, `GraphSetup`, `ConditionalLogic`, `AgentState`
- Config keys: `snake_case` strings matching `DEFAULT_CONFIG` keys
- Env vars: `TRADINGAGENTS_<KEY>` — mapped in `default_config._ENV_OVERRIDES`

**Schemas:**
- Pydantic models: PascalCase noun — `ResearchPlan`, `TraderProposal`, `PortfolioDecision`
- Render helpers: `render_<schema_snake_case>(instance)` — e.g. `render_pm_decision`

## Where to Add New Code

**New Analyst Type:**
- Implement: `tradingagents/agents/analysts/<name>_analyst.py` — `create_<name>_analyst(llm)` factory
- Register node spec: Add to `ANALYST_NODE_SPECS` in `tradingagents/graph/analyst_execution.py`
- Wire tool node: Add corresponding entry in `TradingAgentsGraph._create_tool_nodes()` in `tradingagents/graph/trading_graph.py`
- Add conditional predicate: Add `should_continue_<key>(state)` to `ConditionalLogic` in `tradingagents/graph/conditional_logic.py`
- Register in setup: Add to `analyst_factories` dict in `GraphSetup.setup_graph` in `tradingagents/graph/setup.py`
- Export: Add to `tradingagents/agents/__init__.py`
- State field: Add `<name>_report` to `AgentState` in `tradingagents/agents/utils/agent_states.py` and to `Propagator.create_initial_state` and `TradingAgentsGraph._log_state`
- Tests: `tests/test_analyst_execution.py` for plan-building; new `tests/test_<name>_analyst.py` for node logic

**New Data Vendor:**
- Implement: `tradingagents/dataflows/<vendor>.py` — vendor functions that raise from `errors.py` taxonomy
- Register: Add to `VENDOR_METHODS` dict in `tradingagents/dataflows/interface.py`
- Add to `VENDOR_LIST` in `tradingagents/dataflows/interface.py`
- Config: Add to `data_vendors` defaults in `tradingagents/default_config.py` where applicable
- Tests: `tests/test_vendor_routing.py` for routing; new `tests/test_<vendor>.py` for vendor logic (mock network)

**New LLM Provider:**
- Implement: `tradingagents/llm_clients/<provider>_client.py` — extend `BaseLLMClient`
- Register: Add `if provider_lower == "<provider>":` branch in `tradingagents/llm_clients/factory.py` OR add to the OpenAI-compatible provider registry in `tradingagents/llm_clients/openai_client.py`
- Model catalog: Add known models in `tradingagents/llm_clients/model_catalog.py`
- API key mapping: Add to `tradingagents/llm_clients/api_key_env.py`
- Quirks: Add capability entries to `tradingagents/llm_clients/capabilities.py` as needed
- Tests: `tests/test_provider_registry.py`

**New Config Key:**
- Add default to `DEFAULT_CONFIG` in `tradingagents/default_config.py`
- Add `"TRADINGAGENTS_<KEY>": "<key>"` row to `_ENV_OVERRIDES` in the same file
- No other files need changes for env-var support

**New Agent Tool:**
- Implement: `tradingagents/agents/utils/<category>_tools.py` — `@tool` decorated function calling `route_to_vendor`
- Re-export: Add to `tradingagents/agents/utils/agent_utils.py` imports and `__all__`
- Wire to ToolNode: Add to the appropriate analyst's tool list in `TradingAgentsGraph._create_tool_nodes()` in `tradingagents/graph/trading_graph.py`

**New Test:**
- Location: `tests/test_<concern>.py`
- Must not require live API keys (use `conftest.py` autouse fixtures)
- Mark appropriately: `@pytest.mark.unit` / `@pytest.mark.integration` / `@pytest.mark.smoke`

**Utilities:**
- Shared data helpers: `tradingagents/dataflows/utils.py`
- Shared agent helpers: `tradingagents/agents/utils/agent_utils.py` (add to `__all__`)
- CLI helpers: `cli/utils.py`

## Special Directories

**`.planning/`:**
- Purpose: GSD planning documents (codebase maps, phase plans)
- Generated: By GSD commands
- Committed: Yes (planning artifacts)

**`tradingagents.egg-info/`:**
- Purpose: Editable install metadata generated by `pip install -e .`
- Generated: Yes
- Committed: No (in .gitignore)

**`~/.tradingagents/` (runtime, not in repo):**
- Purpose: Per-user persistence: decision log, cache, checkpoint DBs, result JSON files
- Generated: Yes (at runtime by `TradingAgentsGraph`)
- Committed: No

**`.venv/`:**
- Purpose: Python virtual environment (uv + python3.11 recommended per project memory)
- Generated: Yes
- Committed: No

**`assets/cli/`:**
- Purpose: Screenshot/image assets for README documentation
- Generated: No
- Committed: Yes

---

*Structure analysis: 2026-06-26*
