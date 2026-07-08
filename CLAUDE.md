<!-- GSD:project-start source:PROJECT.md -->
## Project

**TradingAgents × Revenium Demo**

An integration of **Revenium** (AI cost-management / FinOps platform) into the existing **TradingAgents** multi-agent LLM trading-research framework, built to **fully demonstrate Revenium's capabilities** on a real agentic workload. It is the CTO's hands-on vehicle for getting familiar with the agentic-trading problem space ahead of an engagement with **Fidelity's FCAT** group, and the artifact used to **demo Revenium live** to the FCAT team. TradingAgents' trading logic stays intact; the work is instrumentation, control, and a demo narrative layered on top.

**Core Value:** A single live ticker run tells the complete Revenium story end to end — **meter → trace → control → monetize** — on a genuinely agentic, multi-provider trading workload. If everything else is cut, that one run must land for FCAT.

### Constraints

- **Tech stack**: Python, LangGraph/LangChain, Revenium Python SDK/middleware. Integration must respect the existing multi-provider abstraction — no hardcoding a provider in agents or clients (per repo conventions).
- **Providers**: Multi-provider in the demo (e.g., different agents on Anthropic vs OpenAI) to show Revenium's cross-provider cost view; balanced against live-demo reliability.
- **Timeline**: ~2–4 weeks of runway to the FCAT demo — room to build all four pillars plus polish.
- **Demo reliability**: Live-on-stage; the single-run arc must be repeatable and resilient (graceful fallback if a provider hiccups).
- **Revenium environment**: Targets a Revenium instance/account for live data (a Revenium MCP dev connector is available in this environment) — exact account/org and credentials to be confirmed.
- **Test discipline**: Repo tests must pass without live API keys (mocked); Revenium calls must be mockable and not required for the suite to pass.
<!-- GSD:project-end -->

<!-- GSD:stack-start source:codebase/STACK.md -->
## Technology Stack

## Languages
- Python 3.11 - All application code (venv at `.venv/`, requires Python >=3.10 per `pyproject.toml`)
- None (single-language codebase)
## Runtime
- CPython 3.11.15 (pinned via `uv` + `.venv/pyvenv.cfg`)
- `uv` 0.11.17 - used for venv creation and dependency resolution
- `setuptools` >=80.9.0 - build backend
- Lockfile: `uv.lock` (present, committed)
- Install (dev): `pip install ".[dev]"` — installs `ruff` and `pytest`
- Install (Bedrock): `pip install ".[bedrock]"` — optional, adds `langchain-aws`
## Frameworks
- `langgraph` >=0.4.8 - Multi-agent graph orchestration; `StateGraph`, `ToolNode`, `MessagesState` (`tradingagents/graph/`)
- `langchain-core` >=0.3.81 - Message types, prompt templates, callbacks (`langchain_core.messages`)
- `langchain-openai` >=0.3.23 - `ChatOpenAI` / `AzureChatOpenAI` base for OpenAI-compatible providers (`tradingagents/llm_clients/openai_client.py`)
- `langchain-anthropic` >=0.3.15 - `ChatAnthropic` base for Anthropic provider (`tradingagents/llm_clients/anthropic_client.py`)
- `langchain-google-genai` >=4.0.0 - `ChatGoogleGenerativeAI` base for Google provider (`tradingagents/llm_clients/google_client.py`)
- `langchain-experimental` >=0.3.4 - Supplementary LangChain tools
- `typer` >=0.21.0 - CLI framework; entry point `tradingagents = "cli.main:app"` (`cli/main.py`)
- `rich` >=14.0.0 - Live progress UI, formatted output (`cli/`)
- `questionary` >=2.1.0 - Interactive prompts for provider/model/ticker selection (`cli/`)
- `pytest` >=8.0 - Test runner; config in `pyproject.toml` `[tool.pytest.ini_options]`
- `pytest-subtests` >=0.13 - Subtest support
- Tests in `tests/`; markers: `unit`, `integration`, `smoke`
- `ruff` >=0.15 - Linting and import sorting; config in `pyproject.toml` `[tool.ruff]`
- `setuptools` >=80.9.0 - Build backend; packages: `tradingagents*`, `cli*`
## Key Dependencies
- `langgraph-checkpoint-sqlite` >=2.0.0 - Per-ticker SQLite checkpoint/resume (`tradingagents/graph/checkpointer.py`)
- `pandas` >=2.3.0 - DataFrame manipulation for market data; used throughout `tradingagents/dataflows/`
- `yfinance` >=1.4.1 - Default market data vendor (OHLCV, fundamentals, news) (`tradingagents/dataflows/y_finance.py`, `tradingagents/dataflows/yfinance_news.py`)
- `python-dotenv` >=1.0.0 - `.env` file loading
- `requests` >=2.32.4 - HTTP client for Alpha Vantage, FRED, Polymarket APIs
- `stockstats` >=0.6.5 - Technical indicator computation on top of yfinance data (`tradingagents/dataflows/stockstats_utils.py`)
- `backtrader` >=1.9.78.123 - Backtesting framework (declared dependency, minimal active use in current codebase)
- `redis` >=6.2.0 - Declared dependency; no active usage found in source (likely reserved for future caching)
- `parsel` >=1.10.0 - HTML/CSS selector parsing (declared; no active call sites found in current source)
- `pytz` >=2025.2 - Timezone handling
- `tqdm` >=4.67.1 - Progress bars
- `typing-extensions` >=4.14.0 - Backported type hints
- `langchain-aws` >=1.5.0 - AWS Bedrock support; `ChatBedrockConverse` via Converse API (`tradingagents/llm_clients/bedrock_client.py`); install with `pip install ".[bedrock]"`
## Configuration
- `.env` file at repo root (not committed; example at `.env.example`)
- `python-dotenv` loads it at startup
- Config is centralized in `tradingagents/default_config.py` as `DEFAULT_CONFIG` dict
- `TRADINGAGENTS_*` env vars listed in `_ENV_OVERRIDES` override any config key at process start; coerced to the default's type
- Key overridable vars: `TRADINGAGENTS_LLM_PROVIDER`, `TRADINGAGENTS_DEEP_THINK_LLM`, `TRADINGAGENTS_QUICK_THINK_LLM`, `TRADINGAGENTS_LLM_BACKEND_URL`, `TRADINGAGENTS_OUTPUT_LANGUAGE`, `TRADINGAGENTS_MAX_DEBATE_ROUNDS`, `TRADINGAGENTS_MAX_RISK_ROUNDS`, `TRADINGAGENTS_CHECKPOINT_ENABLED`, `TRADINGAGENTS_TEMPERATURE`
- Runtime config lives in `tradingagents/dataflows/config.py` as a process-global dict; `set_config()` merges dicts one level deep, `get_config()` returns a deep copy
- Storage paths default to `~/.tradingagents/` (logs, cache, memory)
- `pyproject.toml` — single config file for build system, project metadata, pytest, and ruff
- Build backend: `setuptools.build_meta`
- No `setup.cfg` or `setup.py`
## Platform Requirements
- Python >=3.10 (3.11 in active use per `.venv/pyvenv.cfg`)
- `uv` for venv management
- At least one LLM provider API key set in `.env`
- Docker-capable: `Dockerfile` and `docker-compose.yml` present at repo root
- Writes persistent data to `~/.tradingagents/` (decision log, checkpoints, cache)
- No web server; runs as CLI (`tradingagents analyze`) or scripted (`python main.py`)
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

## Naming Patterns
- `snake_case.py` throughout (`agent_utils.py`, `symbol_utils.py`, `trading_graph.py`)
- Test files: `test_<feature>.py` (e.g., `test_vendor_routing.py`, `test_signal_processing.py`)
- Config/default file: `default_config.py` (singular, top-level module)
- `snake_case` for all functions: `get_stock_data`, `normalize_symbol`, `parse_rating`
- Agent factory functions always prefixed `create_`: `create_market_analyst(llm)`, `create_trader(llm)`, `create_portfolio_manager(llm)`
- Data tool functions: `get_<data_type>` pattern: `get_stock_data`, `get_indicators`, `get_fundamentals`
- Render helpers: `render_<schema>`: `render_pm_decision`, `render_research_plan`, `render_trader_proposal`
- `snake_case` for all locals and module-level: `structured_llm`, `instrument_context`, `trade_date`
- Private module-level constants: `_RATING_LABEL_RE`, `_BY_ID`, `_ENV_OVERRIDES` (leading underscore)
- Public module-level constants: `RATINGS_5_TIER`, `VENDOR_METHODS`, `DEFAULT_CONFIG`, `TOOLS_CATEGORIES` (ALL_CAPS)
- `PascalCase` for all classes: `VendorError`, `NoMarketDataError`, `TradingMemoryLog`, `ModelCapabilities`
- Pydantic schemas: PascalCase with descriptive noun phrase: `ResearchPlan`, `TraderProposal`, `PortfolioDecision`, `SentimentReport`
- Enums: PascalCase class name, ALL_CAPS members: `PortfolioRating.BUY`, `TraderAction.HOLD`, `SentimentBand.MILDLY_BULLISH`
- Logger always named at module level: `logger = logging.getLogger(__name__)`
## Code Style
- Ruff lint only — `ruff format` is intentionally NOT applied repo-wide (see `pyproject.toml` comment)
- `line-length = 100` (configured but E501 is ignored in lint, so formatter ownership is deferred)
- Match surrounding style; never run a mass reformat
- Config: `pyproject.toml` `[tool.ruff.lint]`
- `select = ["E", "W", "F", "I", "B", "UP", "C4", "SIM"]` — pyflakes + pycodestyle + isort + bugbear + pyupgrade + comprehensions
- `ignore = ["E501"]` — line length is formatter-owned, not linted
- `**/__init__.py` ignores `F401` (intentional re-exports are expected there)
- `noqa` comments include an explanation: `# noqa: BLE001 — fail open, never block the run`
- Used in all newer modules where type annotations contain forward references or `X | Y` union syntax on Python 3.10 target
- Files: `errors.py`, `structured.py`, `schemas.py`, `capabilities.py`, `rating.py`, `symbol_utils.py`, `research_manager.py`, `trader.py`, `portfolio_manager.py`
## Import Organization
- No path aliases; all internal imports use the full `tradingagents.*` package path
- `combine-as-imports = true` in isort config — vendor re-exports in `interface.py` group combined imports in a single block
- `tradingagents/agents/__init__.py` — re-exports all agent factory functions
- `tradingagents/agents/utils/agent_utils.py` — public surface for all tool functions (declared via `__all__`); agents import tools from here, not from the individual tool files
- `tradingagents/agents/utils/__init__.py` style: `F401` suppressed on `__init__.py` by ruff rule
- `tradingagents/llm_clients/factory.py` imports provider modules inside `if` branches to avoid pulling in heavy SDKs at import time
## Error Handling
- Router catches by base type (behavior-based), not vendor-specific type
- New vendors raise these or a thin named subclass (e.g., `AlphaVantageRateLimitError(VendorRateLimitError)`)
- `VendorNotConfiguredError` also extends `ValueError` for backwards-compat with existing `except ValueError` callers
- Use `ValueError` for invalid configuration or parameter values: `raise ValueError(f"unknown analyst key: {analyst_key}")`
- Use domain-specific errors from `errors.py` for data-layer conditions
- Never raise bare `Exception`
- When all vendors exhaust, `route_to_vendor` returns a string `"NO_DATA_AVAILABLE: ..."` rather than raising; agents treat this as a "no data" signal and must not fabricate numbers
## Logging
- `logger.debug(...)` — for non-blocking retries and identity-resolution failures
- `logger.warning(...)` — for structured-output fallbacks and broken-primary-vendor events
- Never log secrets or API keys; log only symbolic model names / vendor names
- Log both the cause and the vendor name when a primary fails: `logger.warning("...", exc, vendor_name)`
## Comments
- Every module-level file has a triple-quoted docstring explaining purpose, design rationale, and key invariants
- Example (`errors.py`): explains the hierarchy shape and the behavioral router-reaction model
- Example (`capabilities.py`): explains the declarative table rationale vs. `if` ladders
- Explain *why*, not *what*: `# noqa: BLE001 — fail open, never block the run`
- Issue number references common for regression fixes: `# #988: with yfinance pinned...`
- Private constants documented inline: `_BY_ID: dict[str, ModelCapabilities] = {...}  # Exact-ID matches take precedence`
- All public functions and methods use return-type annotations and parameter annotations
- Pydantic `Field(description=...)` strings serve as both runtime docs and LLM output instructions
## Function Design
- Outer function does expensive setup (binding structured output)
- Inner function is the LangGraph node: `(state) -> state-delta dict`
- No classes for agents; factories always return callables
- Every structured output schema has a paired `render_<schema>` function that converts it back to markdown
- Schemas: `ResearchPlan`/`render_research_plan`, `TraderProposal`/`render_trader_proposal`, `PortfolioDecision`/`render_pm_decision`, `SentimentReport`/`render_sentiment_report`
- Schema field `description=` strings are the model's output instructions — keep them precise and schema-consistent
- Model capability quirks → `llm_clients/capabilities.py` `_BY_ID` and `_BY_PATTERN` dicts
- Provider API key mappings → `llm_clients/api_key_env.py`
- Env-var → config-key overrides → `default_config.py` `_ENV_OVERRIDES`
- Vendor method dispatch → `dataflows/interface.py` `VENDOR_METHODS`
## Module Design
- Public API declared via `__all__` where needed: `agents/utils/agent_utils.py` lists all tool names
- `__init__.py` files re-export agents and clients so callers use one import path
- `F401` suppressed on `__init__.py` to allow intentional re-export without lint noise
- `from tradingagents.dataflows.config import get_config` for runtime reads inside any module
- `set_config(dict)` merges one level deep (dict values merge; scalar values replace)
- Always call `get_config()` at call time, not at import time — config may change between calls
- Never hardcode model names or provider behavior in agent code
- Model quirks belong in `llm_clients/capabilities.py`, not in client code or agent prompts
- New providers added to the factory's provider registry; not as new `if` branches in agent files
- Every report-producing agent must call `get_language_instruction()` and append it to the system message
- `test_i18n_coverage.py` parametrizes over `REPORT_AGENTS` and asserts the call is present in source
- Internal agent debate stays in English regardless of `output_language` config
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

## System Overview
```text
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
- The graph is compiled once from a `StateGraph(AgentState)` workflow; analyst set is configurable at compile time via `selected_analysts`.
- Analysts run sequentially (tool loop per analyst: invoke → tool_calls? → ToolNode → invoke → done → clear messages → next analyst).
- Research debate and risk debate are explicit loop-back conditional edges counted against round limits in `ConditionalLogic`.
- Three agents (Research Manager, Trader, Portfolio Manager) use structured output via `bind_structured` + `invoke_structured_or_freetext` with graceful free-text fallback.
- All agent tools are thin wrappers; actual data fetching is vendor-routed through `interface.route_to_vendor`.
- Provider-specific LLM quirks are encoded in `capabilities.py` (declarative table), not scattered `if` ladders.
## Layers
- Purpose: Accept user input; configure and invoke `TradingAgentsGraph`
- Location: `cli/main.py`, `main.py`
- Contains: Typer CLI, Rich UI, interactive config flow
- Depends on: `TradingAgentsGraph`, `DEFAULT_CONFIG`
- Used by: End users / scripts
- Purpose: Wire and run the LangGraph pipeline; own cross-cutting concerns (memory, checkpoints, reflection)
- Location: `tradingagents/graph/`
- Contains: `TradingAgentsGraph`, `GraphSetup`, `ConditionalLogic`, `Propagator`, `Reflector`, `SignalProcessor`, `checkpointer`
- Depends on: Agent layer, LLM client layer, data layer
- Used by: Entry layer
- Purpose: Implement each agent's reasoning logic as a `create_*(llm)` factory returning `(state) -> state-delta`
- Location: `tradingagents/agents/`
- Contains: Analysts (`analysts/`), Researchers (`researchers/`), Managers (`managers/`), Risk (`risk_mgmt/`), Trader (`trader/`), shared utils (`utils/`)
- Depends on: Data tools from `agent_utils.py`; LLM passed in at construction
- Used by: Orchestration layer
- Purpose: Vendor-neutral data access; route to yfinance / alpha_vantage / fred / polymarket based on config
- Location: `tradingagents/dataflows/`
- Contains: `interface.py` (router), vendor modules, `config.py`, `errors.py`, `symbol_utils.py`
- Depends on: External vendor SDKs; process-global config
- Used by: Agent tool functions in `agents/utils/*_tools.py`
- Purpose: Provide a uniform `BaseLLMClient.get_llm()` interface across all providers
- Location: `tradingagents/llm_clients/`
- Contains: `factory.py`, provider clients (`anthropic_client.py`, `openai_client.py`, `google_client.py`, `azure_client.py`, `bedrock_client.py`), `capabilities.py`, `model_catalog.py`
- Depends on: Provider SDKs (lazily imported); `capabilities.py` for quirk flags
- Used by: Orchestration layer
- Purpose: Cross-run learning via decision log; crash-resume via SQLite checkpoints
- Location: `~/.tradingagents/` (runtime); `tradingagents/agents/utils/memory.py`, `tradingagents/graph/checkpointer.py`
- Contains: `TradingMemoryLog`, `SqliteSaver` wrappers
- Depends on: Filesystem; LangGraph checkpoint API
- Used by: Orchestration layer
## Data Flow
### Primary Request Path
### Checkpoint Resume Path
### Phase-B Deferred Reflection
- `AgentState` extends LangGraph `MessagesState` (Annotated dict); fields accumulate through nodes
- Sub-states `InvestDebateState` and `RiskDebateState` are nested TypedDicts within `AgentState`
- Adding a field requires updating `AgentState` in `agents/utils/agent_states.py`, `Propagator.create_initial_state`, and `_log_state` in `trading_graph.py`
## Key Abstractions
- Purpose: Every agent is a closure factory. Call it with an LLM; get back a node function `(state: AgentState) -> dict` (state delta).
- Examples: `tradingagents/agents/analysts/market_analyst.py`, `tradingagents/agents/researchers/bull_researcher.py`, `tradingagents/agents/managers/portfolio_manager.py`
- Pattern: `def create_X(llm): def node(state) -> dict: ... return node`
- Purpose: All data fetching flows through a single dispatch function that reads `config["data_vendors"]` and `config["tool_vendors"]` to choose the ordered vendor chain.
- File: `tradingagents/dataflows/interface.py:161`
- Pattern: `route_to_vendor("get_stock_data", ticker, start, end)` — never call vendor modules directly from agent tools.
- Purpose: Centralize `with_structured_output(Schema)` wrapping and free-text fallback for Research Manager, Trader, and Portfolio Manager.
- File: `tradingagents/agents/utils/structured.py`
- Pattern: Call `bind_structured(llm, Schema, "Agent Name")` at factory time; call `invoke_structured_or_freetext(structured_llm, plain_llm, prompt, render_fn, "Agent Name")` inside the node.
- Purpose: Per-model API quirks (tool_choice support, json_mode vs json_schema, reasoning content roundtrip) live in one frozen dataclass table, not `if` ladders in client code.
- File: `tradingagents/llm_clients/capabilities.py`
- Pattern: Add a model entry to the table; client code reads `get_capabilities(model_name)`.
- Purpose: Append-only markdown log of decisions; resolved entries inject past lessons into the Portfolio Manager prompt via `past_context`.
- File: `tradingagents/agents/utils/memory.py`
- Pattern: `store_decision` at run end; `get_past_context(ticker)` at run start for PM prompt injection.
## Entry Points
- Location: `cli/main.py` — Typer `app` with `analyze` command
- Triggers: `tradingagents` console script or `python -m cli.main`
- Responsibilities: Interactive provider/model/ticker selection, Rich live-progress UI, `StatsCallbackHandler` for token tracking, calls `TradingAgentsGraph.propagate`
- Location: `main.py`
- Triggers: `python main.py`
- Responsibilities: Minimal example run (NVDA, hardcoded date), useful for quick debugging
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
### Hardcoding model names or provider behavior in agents or clients
### Hand-rolling structured output calls in new agents
### Adding config keys without an `_ENV_OVERRIDES` entry
## Error Handling
- `NoMarketDataError` → try next vendor in chain; if all exhausted, return `NO_DATA_AVAILABLE` sentinel string
- `VendorRateLimitError` → skip to next vendor, log warning
- `VendorNotConfiguredError` → skip to next vendor, log warning, surface original error if no vendor can serve the call
- Other exceptions → log warning with vendor name, try next vendor; re-raise first error if all vendors fail
- Structured-output failures → `invoke_structured_or_freetext` catches any exception, logs warning, retries as plain `llm.invoke`
## Cross-Cutting Concerns
<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->
## Project Skills

No project skills found. Add skills to any of: `.claude/skills/`, `.agents/skills/`, `.cursor/skills/`, `.github/skills/`, or `.codex/skills/` with a `SKILL.md` index file.
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->



<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
