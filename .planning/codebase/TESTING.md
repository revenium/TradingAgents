# Testing Patterns

**Analysis Date:** 2026-06-26

## Test Framework

**Runner:**
- pytest >= 8.0
- Config: `pyproject.toml` `[tool.pytest.ini_options]`

**Assertion Library:**
- pytest built-in `assert` (used in pytest-style classes)
- `unittest.TestCase` assert methods (`assertEqual`, `assertIn`, `assertRaises`, `assertLogs`) in unittest-style classes
- Both styles coexist in the suite; `unittest.TestCase` subclasses are recognized by pytest

**Run Commands:**
```bash
pytest                                                        # full suite
pytest tests/test_signal_processing.py                        # single file
pytest tests/test_signal_processing.py::TestParseRating       # single class
pytest tests/test_signal_processing.py::TestParseRating::test_explicit_label_buy  # single test
pytest -m unit                                                # by marker: unit | integration | smoke
pytest -ra                                                    # show short test summary (default addopts)
```

## Test File Organization

**Location:**
- All tests in `tests/` at repo root — never co-located with source
- `test.py` at repo root is a legacy scratch file, NOT part of the suite (not in `testpaths`)

**Naming:**
- Files: `test_<feature_or_module>.py`
- Classes: `Test<Subject>` (pytest-style) or `<Subject>Tests` / `<Subject>UnitTests` (unittest.TestCase-style)
- Functions: `test_<what_is_being_verified>` — descriptive, behavior-focused names

**Structure:**
```
tests/
├── conftest.py                       # autouse fixtures; marker registration
├── test_signal_processing.py         # unit tests for rating heuristic + SignalProcessor
├── test_vendor_routing.py            # unit tests for vendor dispatch logic
├── test_vendor_errors.py             # unit tests for error hierarchy
├── test_structured_agents.py         # unit tests for schemas + render + agent fallback
├── test_memory_log.py                # unit + integration tests for TradingMemoryLog
├── test_capabilities.py              # unit tests for LLM capability table
├── test_symbol_utils.py              # unit tests for symbol normalization
├── test_i18n_coverage.py             # source-scan test for language instruction coverage
├── test_checkpoint_resume.py         # integration test for LangGraph checkpoint/resume
└── test_<other_feature>.py           # ...one file per feature/subsystem
```

## Test Structure

**pytest-style class (preferred for new tests):**
```python
@pytest.mark.unit
class TestParseRating:
    def test_explicit_label_buy(self):
        assert parse_rating("Rating: Buy\nReasoning here.") == "Buy"

    def test_no_rating_returns_default(self):
        assert parse_rating("No clear directional signal at this time.") == "Hold"

    def test_no_rating_custom_default(self):
        assert parse_rating("Plain prose.", default="Underweight") == "Underweight"
```

**unittest.TestCase class (used when setUp/tearDown are needed):**
```python
@pytest.mark.unit
class VendorRoutingTests(unittest.TestCase):
    def setUp(self):
        _reset_config()

    def tearDown(self):
        _reset_config()

    def test_explicit_single_vendor_does_not_fall_back(self):
        set_config({"data_vendors": {"core_stock_apis": "yfinance"}})
        ...
        self.assertIn("NO_DATA_AVAILABLE", result)
        av.assert_not_called()
```

**Patterns:**
- `setUp`/`tearDown` in `unittest.TestCase` subclasses for config state reset when `_isolate_config` autouse fixture is insufficient
- `tmp_path` pytest fixture for filesystem tests (write/read memory log, cache, SQLite)
- `monkeypatch` for env-var injection and `set_config` calls within pytest-style tests
- Test classes carry the `@pytest.mark.unit` decorator at class level, not on each method

## Mocking

**Framework:**
- `unittest.mock.MagicMock` and `unittest.mock.patch` (both `from unittest.mock import ...` and `from unittest import mock`)
- `mock.patch.dict` for patching dict registries (e.g., `interface.VENDOR_METHODS`)
- `monkeypatch.setenv` for environment variable injection in pytest-style tests

**LLM mocking — structured path:**
```python
def _structured_trader_llm(captured: dict, proposal: TraderProposal | None = None):
    if proposal is None:
        proposal = TraderProposal(action=TraderAction.BUY, reasoning="Strong setup.")
    structured = MagicMock()
    structured.invoke.side_effect = lambda prompt: (
        captured.__setitem__("prompt", prompt) or proposal
    )
    llm = MagicMock()
    llm.with_structured_output.return_value = structured
    return llm
```
Pattern captures the prompt passed to the LLM (for assertion) and returns a real Pydantic instance so `render_*` functions work against it.

**LLM mocking — free-text fallback path:**
```python
plain_response = "**Action**: Sell\n\nGuidance cut.\n\nFINAL TRANSACTION PROPOSAL: **SELL**"
llm = MagicMock()
llm.with_structured_output.side_effect = NotImplementedError("provider unsupported")
llm.invoke.return_value = MagicMock(content=plain_response)
trader = create_trader(llm)
result = trader(_make_trader_state())
assert result["trader_investment_plan"] == plain_response
```

**Vendor method mocking:**
```python
with mock.patch.dict(
    interface.VENDOR_METHODS,
    {"get_stock_data": {"yfinance": _no_data, "alpha_vantage": av}},
    clear=False,
):
    result = interface.route_to_vendor("get_stock_data", "AAPL", "2026-01-01", "2026-01-10")
```

**`mock_llm_client` fixture (from `conftest.py`):**
```python
@pytest.fixture()
def mock_llm_client():
    client = MagicMock()
    client.get_llm.return_value = MagicMock()
    with patch("tradingagents.llm_clients.factory.create_llm_client", return_value=client):
        yield client
```
Used in tests that need to exercise the graph or CLI without real providers.

**What to mock:**
- LLM clients (always — real API calls are not permitted in unit/smoke tests)
- `yfinance.Ticker` when testing return calculation or instrument identity logic
- Vendor method implementations (`interface.VENDOR_METHODS` entries) for routing tests
- `os.environ` / env vars via `monkeypatch.setenv` (never mutate `os.environ` directly)

**What NOT to mock:**
- The vendor error hierarchy or config module — tests depend on real behavior
- `parse_rating`, `normalize_symbol`, and other pure functions — test them directly
- Pydantic schema validation — let `ValidationError` propagate to test it

## Fixtures and Factories

**Autouse fixtures (apply to every test, defined in `tests/conftest.py`):**

```python
@pytest.fixture(autouse=True)
def _dummy_api_keys(monkeypatch):
    for env_var in _API_KEY_ENV_VARS:
        monkeypatch.setenv(env_var, os.environ.get(env_var, "placeholder"))

@pytest.fixture(autouse=True)
def _isolate_config():
    import copy
    import tradingagents.dataflows.config as config_module
    import tradingagents.default_config as default_config
    config_module._config = copy.deepcopy(default_config.DEFAULT_CONFIG)
    yield
    config_module._config = copy.deepcopy(default_config.DEFAULT_CONFIG)
```

**Helper functions in test files (not fixtures):**
Test files use module-level helper functions for building test state dicts:
```python
def _make_trader_state():
    return {
        "company_of_interest": "NVDA",
        "investment_plan": "**Recommendation**: Buy\n**Rationale**: ...",
    }

def make_log(tmp_path, filename="trading_memory.md"):
    config = {"memory_log_path": str(tmp_path / filename)}
    return TradingMemoryLog(config)
```

**Seeding helpers for file-based tests:**
```python
def _seed_completed(tmp_path, ticker, date, decision_text, reflection_text, ...):
    """Write a completed entry directly to file, bypassing the API."""
    entry = (
        f"[{date} | {ticker} | Buy | +1.0% | +0.5% | 5d]\n\n"
        f"DECISION:\n{decision_text}\n\nREFLECTION:\n{reflection_text}"
        + _SEP
    )
    with open(tmp_path / filename, "a", encoding="utf-8") as f:
        f.write(entry)
```

**Test data — inline strings, not fixtures:**
Constant decision/response strings declared at module scope:
```python
DECISION_BUY = "Rating: Buy\nEnter at $189-192, 6% portfolio cap."
DECISION_SELL = "Rating: Sell\nExit position immediately."
DECISION_NO_RATING = "Executive Summary: Complex situation..."
```

## Coverage

**Requirements:** None enforced (no `--cov` in `addopts`); no minimum threshold configured

**View Coverage (ad-hoc):**
```bash
pytest --cov=tradingagents --cov-report=term-missing
```

## Test Types

**Unit Tests (`@pytest.mark.unit`):**
- 99 of 372 tests explicitly marked `unit` (unmarked tests also run by default)
- Scope: single function, class, or agent node — no network, no filesystem (except `tmp_path`)
- Examples: `TestParseRating`, `TestNormalizeSymbol`, `TestExactIdMatches`, `TestRenderTraderProposal`

**Integration Tests (`@pytest.mark.integration`):**
- 1 test marked `integration` (rare — almost everything is mocked or uses `tmp_path`)
- Scope: tests requiring external services or real API keys
- Must not require live keys unless marked `integration` (enforced by convention, not automation)

**Smoke Tests (`@pytest.mark.smoke`):**
- Quick sanity-check tests
- Run with `pytest -m smoke`

**Source-scan tests (special category):**
- `tests/test_i18n_coverage.py` reads agent source files as text and asserts that `get_language_instruction()` appears in each report-producing agent
- This pattern enforces structural invariants that unit tests cannot easily verify
- Adding a new report-producing agent requires adding it to `REPORT_AGENTS` in `test_i18n_coverage.py`

**LangGraph integration tests:**
- `tests/test_checkpoint_resume.py` builds a minimal `StateGraph`, triggers a simulated crash, and verifies resume from checkpoint
- Uses `tempfile.mkdtemp()` directly (not `tmp_path`) for SQLite checkpointer file isolation

## Common Patterns

**Parametrize for exhaustive coverage of enums/tables:**
```python
@pytest.mark.unit
@pytest.mark.parametrize("rel", REPORT_AGENTS)
def test_report_agent_applies_language_instruction(rel):
    path = _AGENTS_DIR / rel
    assert path.exists()
    src = path.read_text(encoding="utf-8")
    assert "get_language_instruction()" in src

@pytest.mark.unit
class TestAllFiveTiersRecognised:
    def test_all_five_tiers_recognised(self):
        for r in RATINGS_5_TIER:
            assert parse_rating(f"Rating: {r}") == r
```

**Log assertion for warning/error surfacing:**
```python
with self.assertLogs("tradingagents.dataflows.interface", level="WARNING") as cm:
    result = interface.route_to_vendor(...)
joined = "\n".join(cm.output)
self.assertIn("boom", joined)
self.assertIn("yfinance", joined)
```

**Verifying LLM is NOT called:**
```python
def test_makes_no_llm_calls(self):
    from unittest.mock import MagicMock
    llm = MagicMock()
    sp = SignalProcessor(llm)
    sp.process_signal("Rating: Buy\nDetails.")
    llm.invoke.assert_not_called()
    llm.with_structured_output.assert_not_called()
```

**Testing ValidationError on invalid schema data:**
```python
def test_score_out_of_range_rejected(self):
    with pytest.raises(ValidationError):
        SentimentReport(
            overall_band=SentimentBand.BULLISH, overall_score=11.0,
            confidence="high", narrative="n",
        )
```

**Config isolation in unittest.TestCase (when autouse fixture is insufficient):**
```python
def setUp(self):
    config_module._config = copy.deepcopy(default_config.DEFAULT_CONFIG)

def tearDown(self):
    config_module._config = copy.deepcopy(default_config.DEFAULT_CONFIG)
```
This direct `_config` replacement is used because `set_config` merges (never clears missing keys), so a partial `set_config({})` would not restore the original state.

**yfinance patching for return calculations:**
```python
with patch("yfinance.Ticker") as mock_ticker_cls:
    def _make_ticker(sym):
        m = MagicMock()
        m.history.return_value = _price_df(spy_prices if sym == "SPY" else stock_prices)
        return m
    mock_ticker_cls.side_effect = _make_ticker
    raw, alpha, days = TradingAgentsGraph._fetch_returns(mock_graph, "NVDA", "2026-01-05")
```

---

*Testing analysis: 2026-06-26*
