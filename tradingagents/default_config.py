import os

_TRADINGAGENTS_HOME = os.path.join(os.path.expanduser("~"), ".tradingagents")

# Single source of truth for env-var → config-key overrides. To expose
# a new config key for environment-based override, add a row here — no
# entry-point script changes required. Coercion is driven by the type
# of the existing default, so users can keep writing plain strings in
# their .env file.
_ENV_OVERRIDES = {
    "TRADINGAGENTS_LLM_PROVIDER":             "llm_provider",
    "TRADINGAGENTS_DEEP_THINK_LLM":           "deep_think_llm",
    "TRADINGAGENTS_QUICK_THINK_LLM":          "quick_think_llm",
    "TRADINGAGENTS_DEEP_THINK_PROVIDER":      "deep_think_provider",
    "TRADINGAGENTS_QUICK_THINK_PROVIDER":     "quick_think_provider",
    "TRADINGAGENTS_LLM_BACKEND_URL":          "backend_url",
    "TRADINGAGENTS_OUTPUT_LANGUAGE":          "output_language",
    "TRADINGAGENTS_MAX_DEBATE_ROUNDS":        "max_debate_rounds",
    "TRADINGAGENTS_MAX_RISK_ROUNDS":          "max_risk_discuss_rounds",
    "TRADINGAGENTS_CHECKPOINT_ENABLED":       "checkpoint_enabled",
    "TRADINGAGENTS_BENCHMARK_TICKER":         "benchmark_ticker",
    "TRADINGAGENTS_TEMPERATURE":              "temperature",
    # Revenium metering — env vars map to revenium_* config keys
    "REVENIUM_METERING_API_KEY":    "revenium_api_key",
    "REVENIUM_METERING_BASE_URL":   "revenium_api_url",
    "REVENIUM_ORGANIZATION_NAME":   "revenium_organization_name",
    "REVENIUM_PRODUCT_NAME":        "revenium_product_name",
    "REVENIUM_SUBSCRIBER_ID":       "revenium_subscriber_id",
    "REVENIUM_TRACE_TYPE":          "revenium_trace_type",
    # Revenium billing / monetize pillar (Phase 4, D-07, BIL-01)
    "TRADINGAGENTS_SIGNAL_PRICE":       "revenium_signal_price",
    # rev_sk_* write key — used for billing (jobs/outcomes) and enforcement reads.
    # Replaces the narrower REVENIUM_BILLING_API_KEY alias (GAP-04-LINK).
    "REVENIUM_SK_API_KEY":              "revenium_sk_api_key",
    "REVENIUM_BILLING_API_KEY":         "revenium_billing_api_key",
    "REVENIUM_PROFITSTREAM_BASE_URL":   "revenium_profitstream_url",
    "REVENIUM_TEAM_ID":                 "revenium_team_id",
    # Jentic tool metering / monetization (Phase 6, JEN-01)
    "JENTIC_TOOL_ENABLED":   "jentic_tool_enabled",
    "JENTIC_AGENT_API_KEY":  "jentic_agent_api_key",
    "JENTIC_OP_ID":          "jentic_op_id",
    "JENTIC_SEARCH_QUERY":   "jentic_search_query",
    "JENTIC_TOOL_ID":        "jentic_tool_id",
    # Edgehound decision-intelligence tool (Phase 7, PIL-01)
    "EDGEHOUND_TOOL_ENABLED": "edgehound_tool_enabled",
    "EDGEHOUND_TOOL_ID":      "edgehound_tool_id",
}


def _coerce(value: str, reference):
    """Coerce env-var string to the type of the existing default value."""
    if isinstance(reference, bool):
        return value.strip().lower() in ("true", "1", "yes", "on")
    if isinstance(reference, int) and not isinstance(reference, bool):
        return int(value)
    if isinstance(reference, float):
        return float(value)
    return value


def _apply_env_overrides(config: dict) -> dict:
    """Apply TRADINGAGENTS_* env vars to the config dict in-place."""
    for env_var, key in _ENV_OVERRIDES.items():
        raw = os.environ.get(env_var)
        if raw is None or raw == "":
            continue
        config[key] = _coerce(raw, config.get(key))
    return config


DEFAULT_CONFIG = _apply_env_overrides({
    "project_dir": os.path.abspath(os.path.join(os.path.dirname(__file__), ".")),
    "results_dir": os.getenv("TRADINGAGENTS_RESULTS_DIR", os.path.join(_TRADINGAGENTS_HOME, "logs")),
    "data_cache_dir": os.getenv("TRADINGAGENTS_CACHE_DIR", os.path.join(_TRADINGAGENTS_HOME, "cache")),
    "memory_log_path": os.getenv("TRADINGAGENTS_MEMORY_LOG_PATH", os.path.join(_TRADINGAGENTS_HOME, "memory", "trading_memory.md")),
    # Optional cap on the number of resolved memory log entries. When set,
    # the oldest resolved entries are pruned once this limit is exceeded.
    # Pending entries are never pruned. None disables rotation entirely.
    "memory_log_max_entries": None,
    # LLM settings
    # llm_provider is the backward-compatible fallback; prefer the per-role
    # provider keys (deep_think_provider / quick_think_provider) which drive
    # the two distinct create_llm_client calls in TradingAgentsGraph.__init__.
    "llm_provider": "openai",
    "deep_think_llm": "claude-sonnet-4-6",       # Anthropic — Research Manager, Portfolio Manager
    "quick_think_llm": "gpt-4.1-mini",           # OpenAI — analysts, trader
    # Provider split: deep-think runs Anthropic, quick-think runs OpenAI to
    # produce two distinct provider labels in Revenium's cross-provider view
    # (MTR-04). Each falls back to llm_provider when unset.
    "deep_think_provider": "anthropic",
    "quick_think_provider": "openai",
    # When None, each provider's client falls back to its own default endpoint
    # (api.openai.com for OpenAI, generativelanguage.googleapis.com for Gemini, ...).
    # The CLI overrides this per provider when the user picks one. Keeping a
    # provider-specific URL here would leak (e.g. OpenAI's /v1 was previously
    # being forwarded to Gemini, producing malformed request URLs).
    "backend_url": None,
    # Provider-specific thinking configuration
    "google_thinking_level": None,      # "high", "minimal", etc.
    "openai_reasoning_effort": None,    # "medium", "high", "low"
    "anthropic_effort": None,           # "high", "medium", "low"
    # Sampling temperature, forwarded to every provider when set. None leaves
    # each provider at its own default. Lower values reduce run-to-run
    # variation on models that honor it; reasoning models largely ignore it
    # and no setting makes LLM output bit-identical across runs (see README).
    "temperature": None,
    # Checkpoint/resume: when True, LangGraph saves state after each node
    # so a crashed run can resume from the last successful step.
    "checkpoint_enabled": False,
    # Output language for analyst reports and final decision
    # Internal agent debate stays in English for reasoning quality
    "output_language": "English",
    # Debate and discussion settings
    "max_debate_rounds": 1,
    "max_risk_discuss_rounds": 1,
    "max_recur_limit": 100,
    "analyst_concurrency_limit": 1,
    # News / data fetching parameters
    # Increase for longer lookback strategies or to broaden macro coverage;
    # decrease to reduce token usage in agent prompts.
    "news_article_limit": 20,             # max articles per ticker (ticker-news)
    "global_news_article_limit": 10,      # max articles for global/macro news
    "global_news_lookback_days": 7,       # macro news lookback window
    # Search queries used by get_global_news for macro headlines. Extend or
    # replace to broaden geographic / sector coverage.
    "global_news_queries": [
        "Federal Reserve interest rates inflation",
        "S&P 500 earnings GDP economic outlook",
        "geopolitical risk trade war sanctions",
        "ECB Bank of England BOJ central bank policy",
        "oil commodities supply chain energy",
    ],
    # Data vendor configuration
    # Category-level configuration (default for all tools in category).
    # The configured value is the exact vendor chain — requests are NOT silently
    # routed to vendors you didn't choose. For ordered fallback, list several,
    # e.g. "yfinance,alpha_vantage". "default" uses all available vendors.
    "data_vendors": {
        "core_stock_apis": "yfinance",       # Options: alpha_vantage, yfinance
        "technical_indicators": "yfinance",  # Options: alpha_vantage, yfinance
        "fundamental_data": "yfinance",      # Options: alpha_vantage, yfinance
        "news_data": "yfinance",             # Options: alpha_vantage, yfinance
        "macro_data": "fred",                # Options: fred (needs FRED_API_KEY)
        "prediction_markets": "polymarket",  # Options: polymarket (keyless)
    },
    # Tool-level configuration (takes precedence over category-level)
    "tool_vendors": {
        # Example: "get_stock_data": "alpha_vantage",  # Override category default
    },
    # Benchmark for alpha calculation in the reflection layer.
    # ``benchmark_ticker`` (when set) overrides the suffix map for all
    # tickers; leave it None to use ``benchmark_map`` for auto-detection
    # based on the ticker's exchange suffix. SPY remains the US default
    # so the reflection label keeps reading "Alpha vs SPY" for US tickers
    # while non-US tickers get their regional index automatically.
    "benchmark_ticker": None,
    "benchmark_map": {
        ".NS":  "^NSEI",       # NSE India (Nifty 50)
        ".BO":  "^BSESN",      # BSE India (Sensex)
        ".T":   "^N225",       # Tokyo (Nikkei 225)
        ".HK":  "^HSI",        # Hong Kong (Hang Seng)
        ".L":   "^FTSE",       # London (FTSE 100)
        ".TO":  "^GSPTSE",     # Toronto (TSX Composite)
        ".AX":  "^AXJO",       # Australia (ASX 200)
        ".SS":  "000001.SS",   # Shanghai (SSE Composite)
        ".SZ":  "399001.SZ",   # Shenzhen (SZSE Component)
        "":     "SPY",         # default for US-listed tickers (no suffix)
    },
    # Revenium metering — auto-enabled when revenium_api_key is non-empty (D-05).
    # Key starts with rev_mk_* (metering key). When absent, the callback handler
    # is a silent no-op so tests and offline runs are unaffected.
    "revenium_api_key":            os.getenv("REVENIUM_METERING_API_KEY", ""),
    "revenium_api_url":            os.getenv("REVENIUM_METERING_BASE_URL", "https://api.revenium.ai"),
    # Attribution hierarchy — locked demo values (D-01..D-03).
    # CONTEXT D-01 is the authority; do not use the ROADMAP "FCAT-Research-Desk" variant.
    "revenium_organization_name":  "Revenium-Research-Desk",   # D-01
    "revenium_product_name":       "trading-signal",           # D-03
    "revenium_subscriber_id":      "john.demic+trading@revenium.io",  # D-02
    # Task-type taxonomy (D-11) — maps internal LangGraph node names to
    # Revenium pipeline-stage labels used for cost attribution by phase.
    "revenium_task_type_map": {
        "market_analyst":        "analysis",
        "sentiment_analyst":     "analysis",
        "news_analyst":          "analysis",
        "fundamentals_analyst":  "analysis",
        "bull_researcher":       "research_debate",
        "bear_researcher":       "research_debate",
        "research_manager":      "planning",
        "trader":                "trade",
        "aggressive_debator":    "risk_debate",
        "conservative_debator":  "risk_debate",
        "neutral_debator":       "risk_debate",
        "portfolio_manager":     "decision",
    },
    "revenium_trace_type":         os.getenv("REVENIUM_TRACE_TYPE", "trading-run"),
    # Billing / monetize pillar (Phase 4, BIL-01, D-07)
    # revenium_signal_price MUST be a float literal (not a string) so that
    # _coerce's isinstance(reference, float) branch fires correctly when
    # TRADINGAGENTS_SIGNAL_PRICE is set via env (Pitfall 5).
    "revenium_signal_price":        2.00,
    # rev_sk_* write-scope key — primary billing key (GAP-04-LINK).
    # Used for Jobs/Outcomes writes (create_job/report_outcome) AND enforcement reads.
    # The same key provisioned by scripts/setup_revenium.py.
    # When empty the billing emitter is a silent no-op (DMO-04).
    "revenium_sk_api_key":          os.getenv("REVENIUM_SK_API_KEY", ""),
    # Legacy alias kept for backwards compatibility; from_config prefers revenium_sk_api_key.
    "revenium_billing_api_key":     os.getenv("REVENIUM_BILLING_API_KEY", ""),
    # Jobs/Outcomes profitstream host — must be HOST-ONLY (no path suffix).
    # The AgenticOutcomeClient appends /profitstream/v2/api itself; supplying the full
    # path doubles it and produces a 404.  The default api.revenium.io 403s on jobs
    # writes; set REVENIUM_PROFITSTREAM_BASE_URL=https://api.prod.ai.hcapp.io for live runs.
    "revenium_profitstream_url":    os.getenv("REVENIUM_PROFITSTREAM_BASE_URL", "https://api.revenium.io"),
    # Team id for jobs/outcomes attribution — empty default lets the SDK auto-resolve
    # teams[0], which is the WRONG personal team for the demo tenant.  Set
    # REVENIUM_TEAM_ID in .env (e.g. the "Trading Agents" demo team) to target the
    # correct team so meter→trace→control→monetize data lands under the demo tenant.
    "revenium_team_id":             os.getenv("REVENIUM_TEAM_ID", ""),
    # ── Jentic tool metering / monetization (Phase 6, JEN-01) ──────────────────
    # jentic_tool_enabled: master switch for the Jentic-backed news tool. Must be
    # a bool literal so _coerce converts JENTIC_TOOL_ENABLED="true"/"1" correctly.
    "jentic_tool_enabled":          False,
    # API key for Jentic's managed-auth gateway (JENTIC_AGENT_API_KEY env var).
    # Default is empty string — when empty, the tool returns NO_DATA_AVAILABLE
    # (fail-soft) and never crashes the run. Never log this value (T-06-01).
    "jentic_agent_api_key":         os.getenv("JENTIC_AGENT_API_KEY", ""),
    # Pinned operation-id for newsapi.org/main getEverything in the Jentic catalog.
    # Account-specific — keep in config, not hardcoded in tool code (CLAUDE.md
    # no-provider-hardcoding rule). Empty string falls back to search-by-query.
    "jentic_op_id":                 os.getenv("JENTIC_OP_ID", "op_ba86fdce1bade1b7"),
    # Fallback search query when jentic_op_id is unset (search→load→execute path).
    "jentic_search_query":          os.getenv("JENTIC_SEARCH_QUERY", "get news headlines for a stock ticker"),
    # Stable toolId emitted in Revenium tool events AND used as the ToolResource
    # registration key for per-call pricing. Must exactly match the toolId in the
    # Revenium price model (see 06-CONTEXT.md pricing mechanism). Single source
    # of truth — never hardcode this in tool code; always read from config (L6).
    # NOTE: must NOT contain ':' — Revenium's Tools UI validation rejects colons
    # in the tool name (API accepts it, UI does not; FE ticket open). Use '_'.
    "jentic_tool_id":               os.getenv("JENTIC_TOOL_ID", "jentic_news"),
    # ── Edgehound decision-intelligence tool (Phase 7, PIL-01) ─────────────────
    # edgehound_tool_enabled: master switch for the Edgehound mock tool. Must be
    # a bool literal so _coerce converts EDGEHOUND_TOOL_ENABLED="true"/"1" correctly.
    # When False, the LLM is not offered the tool (gated in market_analyst).
    # The tool itself is a fully local mock — no network, no API key required.
    "edgehound_tool_enabled":        False,
    # Stable toolId for the Edgehound decision-intelligence tool event. Must NOT
    # contain ':' (Revenium UI rejects colons). Single source of truth (L6) —
    # never hardcode in tool code; @meter_tool reads it from here.
    "edgehound_tool_id":             os.getenv("EDGEHOUND_TOOL_ID", "edgehound_decision"),
})
