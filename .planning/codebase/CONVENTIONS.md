# Coding Conventions

**Analysis Date:** 2026-06-26

## Naming Patterns

**Files:**
- `snake_case.py` throughout (`agent_utils.py`, `symbol_utils.py`, `trading_graph.py`)
- Test files: `test_<feature>.py` (e.g., `test_vendor_routing.py`, `test_signal_processing.py`)
- Config/default file: `default_config.py` (singular, top-level module)

**Functions:**
- `snake_case` for all functions: `get_stock_data`, `normalize_symbol`, `parse_rating`
- Agent factory functions always prefixed `create_`: `create_market_analyst(llm)`, `create_trader(llm)`, `create_portfolio_manager(llm)`
- Data tool functions: `get_<data_type>` pattern: `get_stock_data`, `get_indicators`, `get_fundamentals`
- Render helpers: `render_<schema>`: `render_pm_decision`, `render_research_plan`, `render_trader_proposal`

**Variables:**
- `snake_case` for all locals and module-level: `structured_llm`, `instrument_context`, `trade_date`
- Private module-level constants: `_RATING_LABEL_RE`, `_BY_ID`, `_ENV_OVERRIDES` (leading underscore)
- Public module-level constants: `RATINGS_5_TIER`, `VENDOR_METHODS`, `DEFAULT_CONFIG`, `TOOLS_CATEGORIES` (ALL_CAPS)

**Types / Classes:**
- `PascalCase` for all classes: `VendorError`, `NoMarketDataError`, `TradingMemoryLog`, `ModelCapabilities`
- Pydantic schemas: PascalCase with descriptive noun phrase: `ResearchPlan`, `TraderProposal`, `PortfolioDecision`, `SentimentReport`
- Enums: PascalCase class name, ALL_CAPS members: `PortfolioRating.BUY`, `TraderAction.HOLD`, `SentimentBand.MILDLY_BULLISH`

**Logging:**
- Logger always named at module level: `logger = logging.getLogger(__name__)`

## Code Style

**Formatting:**
- Ruff lint only — `ruff format` is intentionally NOT applied repo-wide (see `pyproject.toml` comment)
- `line-length = 100` (configured but E501 is ignored in lint, so formatter ownership is deferred)
- Match surrounding style; never run a mass reformat

**Linting (ruff):**
- Config: `pyproject.toml` `[tool.ruff.lint]`
- `select = ["E", "W", "F", "I", "B", "UP", "C4", "SIM"]` — pyflakes + pycodestyle + isort + bugbear + pyupgrade + comprehensions
- `ignore = ["E501"]` — line length is formatter-owned, not linted
- `**/__init__.py` ignores `F401` (intentional re-exports are expected there)
- `noqa` comments include an explanation: `# noqa: BLE001 — fail open, never block the run`

**`from __future__ import annotations`:**
- Used in all newer modules where type annotations contain forward references or `X | Y` union syntax on Python 3.10 target
- Files: `errors.py`, `structured.py`, `schemas.py`, `capabilities.py`, `rating.py`, `symbol_utils.py`, `research_manager.py`, `trader.py`, `portfolio_manager.py`

## Import Organization

**Order (ruff isort enforced):**
1. `from __future__ import annotations` (when needed)
2. Standard library (`os`, `re`, `logging`, `copy`, `dataclasses`, etc.)
3. Third-party (`pydantic`, `langchain_core`, `langgraph`, `yfinance`, etc.)
4. Local project (`tradingagents.*`, `cli.*`)

**Path Aliases:**
- No path aliases; all internal imports use the full `tradingagents.*` package path
- `combine-as-imports = true` in isort config — vendor re-exports in `interface.py` group combined imports in a single block

**Barrel files:**
- `tradingagents/agents/__init__.py` — re-exports all agent factory functions
- `tradingagents/agents/utils/agent_utils.py` — public surface for all tool functions (declared via `__all__`); agents import tools from here, not from the individual tool files
- `tradingagents/agents/utils/__init__.py` style: `F401` suppressed on `__init__.py` by ruff rule

**Lazy imports in factory:**
- `tradingagents/llm_clients/factory.py` imports provider modules inside `if` branches to avoid pulling in heavy SDKs at import time

## Error Handling

**Vendor error hierarchy (`tradingagents/dataflows/errors.py`):**
```python
VendorError
├── NoMarketDataError        # empty/stale result → sentinel string
├── VendorRateLimitError     # transient throttle → skip to next vendor
└── VendorNotConfiguredError # missing key → vendor unavailable (also ValueError)
```
- Router catches by base type (behavior-based), not vendor-specific type
- New vendors raise these or a thin named subclass (e.g., `AlphaVantageRateLimitError(VendorRateLimitError)`)
- `VendorNotConfiguredError` also extends `ValueError` for backwards-compat with existing `except ValueError` callers

**Fail-open pattern (agent utils):**
```python
try:
    info = yf.Ticker(normalize_symbol(ticker)).info or {}
except Exception as exc:  # noqa: BLE001 — fail open, never block the run
    logger.debug("Could not resolve instrument identity for %s: %s", ticker, exc)
    return {}
```
Used when a failure should not block analysis; always accompanied by a `noqa` explanation.

**Structured output fallback (`tradingagents/agents/utils/structured.py`):**
```python
def bind_structured(llm, schema, agent_name):
    try:
        return llm.with_structured_output(schema)
    except (NotImplementedError, AttributeError) as exc:
        logger.warning("%s: provider does not support ...", agent_name, exc)
        return None

def invoke_structured_or_freetext(structured_llm, plain_llm, prompt, render, agent_name):
    if structured_llm is not None:
        try:
            result = structured_llm.invoke(prompt)
            return render(result)
        except Exception as exc:
            logger.warning("%s: structured-output invocation failed (%s); retrying ...", ...)
    response = plain_llm.invoke(prompt)
    return response.content
```
Pattern used in: `create_research_manager`, `create_trader`, `create_portfolio_manager`, `create_sentiment_analyst`.

**Raising errors:**
- Use `ValueError` for invalid configuration or parameter values: `raise ValueError(f"unknown analyst key: {analyst_key}")`
- Use domain-specific errors from `errors.py` for data-layer conditions
- Never raise bare `Exception`

**No-data sentinel string:**
- When all vendors exhaust, `route_to_vendor` returns a string `"NO_DATA_AVAILABLE: ..."` rather than raising; agents treat this as a "no data" signal and must not fabricate numbers

## Logging

**Framework:** `logging` (stdlib), module-level logger via `logging.getLogger(__name__)`

**Patterns:**
- `logger.debug(...)` — for non-blocking retries and identity-resolution failures
- `logger.warning(...)` — for structured-output fallbacks and broken-primary-vendor events
- Never log secrets or API keys; log only symbolic model names / vendor names
- Log both the cause and the vendor name when a primary fails: `logger.warning("...", exc, vendor_name)`

## Comments

**Module docstrings:**
- Every module-level file has a triple-quoted docstring explaining purpose, design rationale, and key invariants
- Example (`errors.py`): explains the hierarchy shape and the behavioral router-reaction model
- Example (`capabilities.py`): explains the declarative table rationale vs. `if` ladders

**Inline comments:**
- Explain *why*, not *what*: `# noqa: BLE001 — fail open, never block the run`
- Issue number references common for regression fixes: `# #988: with yfinance pinned...`
- Private constants documented inline: `_BY_ID: dict[str, ModelCapabilities] = {...}  # Exact-ID matches take precedence`

**Type annotations:**
- All public functions and methods use return-type annotations and parameter annotations
- Pydantic `Field(description=...)` strings serve as both runtime docs and LLM output instructions

## Function Design

**Agent factories (key pattern):**
```python
def create_research_manager(llm):
    structured_llm = bind_structured(llm, ResearchPlan, "Research Manager")  # setup once

    def research_manager_node(state) -> dict:   # inner node function
        ...
        return {"investment_plan": investment_plan, ...}

    return research_manager_node   # return the node function, not a class
```
- Outer function does expensive setup (binding structured output)
- Inner function is the LangGraph node: `(state) -> state-delta dict`
- No classes for agents; factories always return callables

**Pydantic schema + render pairing:**
- Every structured output schema has a paired `render_<schema>` function that converts it back to markdown
- Schemas: `ResearchPlan`/`render_research_plan`, `TraderProposal`/`render_trader_proposal`, `PortfolioDecision`/`render_pm_decision`, `SentimentReport`/`render_sentiment_report`
- Schema field `description=` strings are the model's output instructions — keep them precise and schema-consistent

**Declarative config tables over if-ladders:**
- Model capability quirks → `llm_clients/capabilities.py` `_BY_ID` and `_BY_PATTERN` dicts
- Provider API key mappings → `llm_clients/api_key_env.py`
- Env-var → config-key overrides → `default_config.py` `_ENV_OVERRIDES`
- Vendor method dispatch → `dataflows/interface.py` `VENDOR_METHODS`

## Module Design

**Exports:**
- Public API declared via `__all__` where needed: `agents/utils/agent_utils.py` lists all tool names
- `__init__.py` files re-export agents and clients so callers use one import path
- `F401` suppressed on `__init__.py` to allow intentional re-export without lint noise

**Config access:**
- `from tradingagents.dataflows.config import get_config` for runtime reads inside any module
- `set_config(dict)` merges one level deep (dict values merge; scalar values replace)
- Always call `get_config()` at call time, not at import time — config may change between calls

**Multi-provider constraint:**
- Never hardcode model names or provider behavior in agent code
- Model quirks belong in `llm_clients/capabilities.py`, not in client code or agent prompts
- New providers added to the factory's provider registry; not as new `if` branches in agent files

**i18n invariant:**
- Every report-producing agent must call `get_language_instruction()` and append it to the system message
- `test_i18n_coverage.py` parametrizes over `REPORT_AGENTS` and asserts the call is present in source
- Internal agent debate stays in English regardless of `output_language` config

---

*Convention analysis: 2026-06-26*
