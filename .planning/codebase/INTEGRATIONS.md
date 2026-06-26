# External Integrations

**Analysis Date:** 2026-06-26

## APIs & External Services

All data vendor calls are routed through `tradingagents/dataflows/interface.py` via `route_to_vendor(method, ...)`. Vendor selection is driven by `config["data_vendors"]` (category-level) and `config["tool_vendors"]` (tool-level override). Comma-separated values enable ordered fallback. Requests are NEVER silently routed to a vendor the user did not configure.

**Market Data:**
- **Yahoo Finance (yfinance)** - Default vendor for stock data, technical indicators, fundamentals, news, insider transactions
  - SDK/Client: `yfinance` >=1.4.1 Python package
  - Auth: None (public API)
  - Implementation: `tradingagents/dataflows/y_finance.py`, `tradingagents/dataflows/yfinance_news.py`
  - Used by: `get_stock_data`, `get_indicators`, `get_fundamentals`, `get_balance_sheet`, `get_cashflow`, `get_income_statement`, `get_news`, `get_global_news`, `get_insider_transactions`

- **Alpha Vantage** - Premium alternate vendor for all stock/fundamental/news data
  - SDK/Client: Direct HTTP via `requests`; base URL `https://www.alphavantage.co/query`
  - Auth: `ALPHA_VANTAGE_API_KEY` env var
  - Implementation: `tradingagents/dataflows/alpha_vantage_common.py`, `tradingagents/dataflows/alpha_vantage_stock.py`, `tradingagents/dataflows/alpha_vantage_fundamentals.py`, `tradingagents/dataflows/alpha_vantage_indicator.py`, `tradingagents/dataflows/alpha_vantage_news.py`
  - Errors: `AlphaVantageNotConfiguredError`, `AlphaVantageRateLimitError` (subtypes of `VendorNotConfiguredError`, `VendorRateLimitError`)

**Macro Data:**
- **FRED (Federal Reserve Economic Data)** - Macro series: rates, yields, CPI, GDP, unemployment, VIX, dollar index
  - SDK/Client: Direct HTTP via `requests`; base URL `https://api.stlouisfed.org/fred`
  - Auth: `FRED_API_KEY` env var (free key at stlouisfed.org)
  - Implementation: `tradingagents/dataflows/fred.py`
  - Supports: curated alias map (`fed_funds_rate`, `cpi`, `10y_treasury`, etc.) plus raw FRED series IDs

**Prediction Markets:**
- **Polymarket** - Market-implied event probabilities (Fed decisions, elections, macro)
  - SDK/Client: Direct HTTP via `requests`; public Gamma API `https://gamma-api.polymarket.com`
  - Auth: None (keyless public API)
  - Implementation: `tradingagents/dataflows/polymarket.py`
  - Used by: `get_prediction_markets` tool

**Social Data:**
- **Reddit** - Ticker-specific discussion posts from wallstreetbets, stocks, investing subreddits
  - SDK/Client: Direct HTTP via `urllib`; RSS feed `https://www.reddit.com/r/{sub}/search.rss`
  - Auth: None (public RSS; identified User-Agent `tradingagents/0.2`)
  - Implementation: `tradingagents/dataflows/reddit.py`
  - Note: JSON search endpoint is WAF-blocked (403); RSS fallback is used by default; single 429 retry with Retry-After honor

- **StockTwits** - Per-symbol message stream with sentiment labels (Bullish/Bearish)
  - SDK/Client: Direct HTTP via `urllib`; `https://api.stocktwits.com/api/2/streams/symbol/{ticker}.json`
  - Auth: None (public API)
  - Implementation: `tradingagents/dataflows/stocktwits.py`

## LLM Providers

All LLM clients are created via `tradingagents/llm_clients/factory.py:create_llm_client(provider, model, ...)`. Native APIs (Anthropic, Google) use dedicated langchain integrations; all other providers route through `OpenAIClient` via the OpenAI-compatible provider registry in `tradingagents/llm_clients/openai_client.py:OPENAI_COMPATIBLE_PROVIDERS`.

Per-model API quirks (tool_choice support, structured output method, reasoning_content roundtrip) are declared in `tradingagents/llm_clients/capabilities.py` — not in client code.

**Native API Clients:**
- **Anthropic Claude** - `langchain_anthropic.ChatAnthropic`; `ANTHROPIC_API_KEY`; supports `effort` param on Opus/Sonnet 4.5+
  - Client: `tradingagents/llm_clients/anthropic_client.py`
  - Models: Claude Opus 4.8, Claude Sonnet 4.6, Claude Haiku 4.5, etc.

- **Google Gemini** - `langchain_google_genai.ChatGoogleGenerativeAI`; `GOOGLE_API_KEY`; supports `thinking_level` mapped to Gemini 3 `thinking_level` / Gemini 2.5 `thinking_budget`
  - Client: `tradingagents/llm_clients/google_client.py`
  - Models: Gemini 3.5 Flash, Gemini 3.1 Pro, Gemini 2.5 Pro, etc.

- **AWS Bedrock** - `langchain_aws.ChatBedrockConverse` (optional extra); AWS credential chain (env vars, `~/.aws/credentials`, IAM role); `AWS_DEFAULT_REGION` required
  - Client: `tradingagents/llm_clients/bedrock_client.py`
  - Install: `pip install "tradingagents[bedrock]"`

- **Azure OpenAI** - `langchain_openai.AzureChatOpenAI`; requires `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_DEPLOYMENT_NAME`
  - Client: `tradingagents/llm_clients/azure_client.py`

**OpenAI-Compatible Providers (via `OpenAIClient`):**

| Provider key | Base URL | Auth env var |
|---|---|---|
| `openai` | `api.openai.com` (Responses API) | `OPENAI_API_KEY` |
| `xai` | `https://api.x.ai/v1` | `XAI_API_KEY` |
| `deepseek` | `https://api.deepseek.com` | `DEEPSEEK_API_KEY` |
| `qwen` | `https://dashscope-intl.aliyuncs.com/compatible-mode/v1` | `DASHSCOPE_API_KEY` |
| `qwen-cn` | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `DASHSCOPE_CN_API_KEY` |
| `glm` | `https://api.z.ai/api/paas/v4/` | `ZHIPU_API_KEY` |
| `glm-cn` | `https://open.bigmodel.cn/api/paas/v4/` | `ZHIPU_CN_API_KEY` |
| `minimax` | `https://api.minimax.io/v1` | `MINIMAX_API_KEY` |
| `minimax-cn` | `https://api.minimaxi.com/v1` | `MINIMAX_CN_API_KEY` |
| `openrouter` | `https://openrouter.ai/api/v1` | `OPENROUTER_API_KEY` |
| `mistral` | `https://api.mistral.ai/v1` | `MISTRAL_API_KEY` |
| `kimi` (Moonshot) | `https://api.moonshot.ai/v1` | `MOONSHOT_API_KEY` |
| `groq` | `https://api.groq.com/openai/v1` | `GROQ_API_KEY` |
| `nvidia` | `https://integrate.api.nvidia.com/v1` | `NVIDIA_API_KEY` |
| `ollama` | `http://localhost:11434/v1` (overridable via `OLLAMA_BASE_URL`) | None (keyless) |
| `openai_compatible` | User-supplied `backend_url` | `OPENAI_COMPATIBLE_API_KEY` (optional) |

Special wire-format subclasses:
- `DeepSeekChatOpenAI` (`tradingagents/llm_clients/openai_client.py`) — echoes `reasoning_content` back on assistant turns (required by DeepSeek V4 thinking models)
- `MinimaxChatOpenAI` (`tradingagents/llm_clients/openai_client.py`) — sends `reasoning_split=True` via `extra_body` for M2.x models

## Data Storage

**Databases:**
- **SQLite** (per-ticker checkpoint files) - Opt-in LangGraph resume; one file per ticker at `~/.tradingagents/cache/checkpoints/<TICKER>.db`
  - Client: `langgraph-checkpoint-sqlite` >=2.0.0 (`SqliteSaver`)
  - Connection: `tradingagents/graph/checkpointer.py`
  - Enabled via: `config["checkpoint_enabled"] = True` or `TRADINGAGENTS_CHECKPOINT_ENABLED=true`

**File Storage:**
- **Local filesystem** — all persistence to `~/.tradingagents/`
  - Decision log: `~/.tradingagents/memory/trading_memory.md` (append-only markdown)
  - Cache dir: `~/.tradingagents/cache/`
  - Logs/results: `~/.tradingagents/logs/`
  - Managed by: `tradingagents/agents/utils/memory.py` (`TradingMemoryLog`)

**Caching:**
- `redis` >=6.2.0 is declared in `pyproject.toml` but no active usage found in source. Likely reserved for future caching layer.

## Authentication & Identity

**Auth Provider:**
- None — no user authentication system; tool is a local research framework
- Each LLM provider authenticates via its own API key env var (see LLM Providers table above)
- AWS Bedrock uses the standard AWS credential chain (no single key env var)

## Monitoring & Observability

**Error Tracking:**
- None (no Sentry, Datadog, etc.)

**Logs:**
- Python `logging` module throughout; `logger = logging.getLogger(__name__)` pattern
- LangGraph token/tool usage tracked via LangChain callbacks in `cli/stats_handler.py` (`TradingAgentsStats`) — passed to `TradingAgentsGraph(callbacks=...)`
- No structured log shipping

## CI/CD & Deployment

**Hosting:**
- Local process or Docker container; `Dockerfile` and `docker-compose.yml` at repo root
- No cloud deployment config found

**CI Pipeline:**
- No CI config files found (no `.github/workflows/`, no `.circleci/`, etc.)

## Environment Configuration

**Required env vars (at least one LLM provider key):**
- Pick one: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`, `XAI_API_KEY`, `DEEPSEEK_API_KEY`, `OPENROUTER_API_KEY`, or other per-provider key

**Optional data provider keys:**
- `ALPHA_VANTAGE_API_KEY` — required only when `data_vendors` includes `alpha_vantage`
- `FRED_API_KEY` — required only when `macro_data` vendor is `fred` (default); free at stlouisfed.org

**Optional AWS env vars (Bedrock only):**
- `AWS_DEFAULT_REGION` (default: `us-west-2`)
- `AWS_PROFILE` (optional)

**Secrets location:**
- `.env` file at repo root (not committed; see `.env.example` and `.env.enterprise.example`)

## Webhooks & Callbacks

**Incoming:**
- None — no webhook endpoints; framework is a CLI/library, not a server

**Outgoing:**
- None — all external calls are request/response (LLM APIs, data vendors), not webhook-based

---

*Integration audit: 2026-06-26*
