# Technology Stack

**Analysis Date:** 2026-06-26

## Languages

**Primary:**
- Python 3.11 - All application code (venv at `.venv/`, requires Python >=3.10 per `pyproject.toml`)

**Secondary:**
- None (single-language codebase)

## Runtime

**Environment:**
- CPython 3.11.15 (pinned via `uv` + `.venv/pyvenv.cfg`)

**Package Manager:**
- `uv` 0.11.17 - used for venv creation and dependency resolution
- `setuptools` >=80.9.0 - build backend
- Lockfile: `uv.lock` (present, committed)
- Install (dev): `pip install ".[dev]"` — installs `ruff` and `pytest`
- Install (Bedrock): `pip install ".[bedrock]"` — optional, adds `langchain-aws`

## Frameworks

**Core:**
- `langgraph` >=0.4.8 - Multi-agent graph orchestration; `StateGraph`, `ToolNode`, `MessagesState` (`tradingagents/graph/`)
- `langchain-core` >=0.3.81 - Message types, prompt templates, callbacks (`langchain_core.messages`)
- `langchain-openai` >=0.3.23 - `ChatOpenAI` / `AzureChatOpenAI` base for OpenAI-compatible providers (`tradingagents/llm_clients/openai_client.py`)
- `langchain-anthropic` >=0.3.15 - `ChatAnthropic` base for Anthropic provider (`tradingagents/llm_clients/anthropic_client.py`)
- `langchain-google-genai` >=4.0.0 - `ChatGoogleGenerativeAI` base for Google provider (`tradingagents/llm_clients/google_client.py`)
- `langchain-experimental` >=0.3.4 - Supplementary LangChain tools

**CLI:**
- `typer` >=0.21.0 - CLI framework; entry point `tradingagents = "cli.main:app"` (`cli/main.py`)
- `rich` >=14.0.0 - Live progress UI, formatted output (`cli/`)
- `questionary` >=2.1.0 - Interactive prompts for provider/model/ticker selection (`cli/`)

**Testing:**
- `pytest` >=8.0 - Test runner; config in `pyproject.toml` `[tool.pytest.ini_options]`
- `pytest-subtests` >=0.13 - Subtest support
- Tests in `tests/`; markers: `unit`, `integration`, `smoke`

**Build/Dev:**
- `ruff` >=0.15 - Linting and import sorting; config in `pyproject.toml` `[tool.ruff]`
- `setuptools` >=80.9.0 - Build backend; packages: `tradingagents*`, `cli*`

## Key Dependencies

**Critical:**
- `langgraph-checkpoint-sqlite` >=2.0.0 - Per-ticker SQLite checkpoint/resume (`tradingagents/graph/checkpointer.py`)
- `pandas` >=2.3.0 - DataFrame manipulation for market data; used throughout `tradingagents/dataflows/`
- `yfinance` >=1.4.1 - Default market data vendor (OHLCV, fundamentals, news) (`tradingagents/dataflows/y_finance.py`, `tradingagents/dataflows/yfinance_news.py`)
- `python-dotenv` >=1.0.0 - `.env` file loading
- `requests` >=2.32.4 - HTTP client for Alpha Vantage, FRED, Polymarket APIs

**Infrastructure:**
- `stockstats` >=0.6.5 - Technical indicator computation on top of yfinance data (`tradingagents/dataflows/stockstats_utils.py`)
- `backtrader` >=1.9.78.123 - Backtesting framework (declared dependency, minimal active use in current codebase)
- `redis` >=6.2.0 - Declared dependency; no active usage found in source (likely reserved for future caching)
- `parsel` >=1.10.0 - HTML/CSS selector parsing (declared; no active call sites found in current source)
- `pytz` >=2025.2 - Timezone handling
- `tqdm` >=4.67.1 - Progress bars
- `typing-extensions` >=4.14.0 - Backported type hints

**Optional:**
- `langchain-aws` >=1.5.0 - AWS Bedrock support; `ChatBedrockConverse` via Converse API (`tradingagents/llm_clients/bedrock_client.py`); install with `pip install ".[bedrock]"`

## Configuration

**Environment:**
- `.env` file at repo root (not committed; example at `.env.example`)
- `python-dotenv` loads it at startup
- Config is centralized in `tradingagents/default_config.py` as `DEFAULT_CONFIG` dict
- `TRADINGAGENTS_*` env vars listed in `_ENV_OVERRIDES` override any config key at process start; coerced to the default's type
- Key overridable vars: `TRADINGAGENTS_LLM_PROVIDER`, `TRADINGAGENTS_DEEP_THINK_LLM`, `TRADINGAGENTS_QUICK_THINK_LLM`, `TRADINGAGENTS_LLM_BACKEND_URL`, `TRADINGAGENTS_OUTPUT_LANGUAGE`, `TRADINGAGENTS_MAX_DEBATE_ROUNDS`, `TRADINGAGENTS_MAX_RISK_ROUNDS`, `TRADINGAGENTS_CHECKPOINT_ENABLED`, `TRADINGAGENTS_TEMPERATURE`
- Runtime config lives in `tradingagents/dataflows/config.py` as a process-global dict; `set_config()` merges dicts one level deep, `get_config()` returns a deep copy
- Storage paths default to `~/.tradingagents/` (logs, cache, memory)

**Build:**
- `pyproject.toml` — single config file for build system, project metadata, pytest, and ruff
- Build backend: `setuptools.build_meta`
- No `setup.cfg` or `setup.py`

## Platform Requirements

**Development:**
- Python >=3.10 (3.11 in active use per `.venv/pyvenv.cfg`)
- `uv` for venv management
- At least one LLM provider API key set in `.env`

**Production:**
- Docker-capable: `Dockerfile` and `docker-compose.yml` present at repo root
- Writes persistent data to `~/.tradingagents/` (decision log, checkpoints, cache)
- No web server; runs as CLI (`tradingagents analyze`) or scripted (`python main.py`)

---

*Stack analysis: 2026-06-26*
