"""Unit tests for the Trinigence NL→strategy-generation mock tool (PIL-02).

All tests are @pytest.mark.unit and pass without any API keys or network
access.  Trinigence is a fully local mock — no external dependency means no
sentinel branch is needed when the tool is called directly.
The LLM-level gating (only offering the tool when trinigence_tool_enabled=True)
is tested in Task 2 (market_analyst wiring tests below).

Coverage:
- PIL-02: trinigence_tool_id is colon-free; sourced from DEFAULT_CONFIG single source.
- PIL-02: @meter_tool fires exactly one Revenium tool event per call with the
  correct tool_id when a revenium_api_key is present.
- PIL-02: returned output contains strategy-generation fields (strategy_name,
  entry_rules, exit_rules, indicators).
- PIL-02: importing the module with NO keys never raises.

TDD RED: all tests MUST fail before tradingagents/agents/utils/trinigence_tools.py
is created (ImportError / ModuleNotFoundError on collection).
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Test 1: colon-free toolId from DEFAULT_CONFIG
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_trinigence_tool_id_is_colon_free():
    """DEFAULT_CONFIG['trinigence_tool_id'] == 'trinigence_strategy' and contains no ':'."""
    from tradingagents.default_config import DEFAULT_CONFIG

    tool_id = DEFAULT_CONFIG["trinigence_tool_id"]
    assert tool_id == "trinigence_strategy", (
        f"Expected 'trinigence_strategy', got {tool_id!r}"
    )
    assert ":" not in tool_id, (
        f"trinigence_tool_id must not contain ':' (Revenium UI rejects it), got {tool_id!r}"
    )


# ---------------------------------------------------------------------------
# Test 2: tool returns plausible strategy-generation output
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_trinigence_tool_returns_plausible_output():
    """get_trinigence_strategy.func(...) returns JSON with strategy-generation fields."""
    from tradingagents.agents.utils.trinigence_tools import get_trinigence_strategy

    result = get_trinigence_strategy.func("momentum breakout strategy for NVDA")
    assert isinstance(result, str), f"Expected str result, got {type(result)}"

    # Must be valid JSON
    parsed = json.loads(result)

    # Required strategy-generation keys
    assert "strategy_name" in parsed, f"Missing 'strategy_name' key in output: {parsed}"
    assert "entry_rules" in parsed, f"Missing 'entry_rules' key in output: {parsed}"
    assert "exit_rules" in parsed, f"Missing 'exit_rules' key in output: {parsed}"
    assert "indicators" in parsed, f"Missing 'indicators' key in output: {parsed}"

    # entry_rules and exit_rules must be lists
    assert isinstance(parsed["entry_rules"], list), (
        f"entry_rules must be a list, got {type(parsed['entry_rules'])}"
    )
    assert isinstance(parsed["exit_rules"], list), (
        f"exit_rules must be a list, got {type(parsed['exit_rules'])}"
    )
    assert isinstance(parsed["indicators"], list), (
        f"indicators must be a list, got {type(parsed['indicators'])}"
    )


# ---------------------------------------------------------------------------
# Test 3: meter event fires exactly once with correct tool_id
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_trinigence_tool_fires_meter_event():
    """@meter_tool fires exactly one tool event per call with tool_id=DEFAULT_CONFIG['trinigence_tool_id'].

    Patches:
    - revenium_metering.decorator._send_tool_event → captures the event call

    The tool is a local mock — no external SDK to patch.
    """
    from tradingagents.agents.utils.trinigence_tools import get_trinigence_strategy
    from tradingagents.dataflows.config import get_config, set_config
    from tradingagents.default_config import DEFAULT_CONFIG

    orig = get_config()
    set_config({
        "revenium_api_key": "rev_mk_test",
        "revenium_api_url": "https://api.revenium.ai",
        "revenium_organization_name": "Revenium-Research-Desk",
        "revenium_product_name": "trading-signal",
        "revenium_subscriber_id": "test@example.com",
    })
    try:
        with patch("revenium_metering.decorator._send_tool_event") as mock_send:
            result = get_trinigence_strategy.func("momentum breakout strategy for NVDA")

        # Exactly one tool event per call
        assert mock_send.call_count == 1, (
            f"Expected 1 Revenium tool event, got {mock_send.call_count}"
        )

        # tool_id must match config value (single source of truth, L6) and
        # must NOT contain ':' — Revenium's Tools UI rejects colons.
        expected_tool_id = DEFAULT_CONFIG["trinigence_tool_id"]
        assert ":" not in expected_tool_id, (
            f"trinigence_tool_id must not contain ':', got {expected_tool_id!r}"
        )
        assert mock_send.call_args.kwargs["tool_id"] == expected_tool_id, (
            f"Expected tool_id={expected_tool_id!r}, got "
            f"{mock_send.call_args.kwargs.get('tool_id')!r}"
        )

        # Result must be a valid JSON string
        assert isinstance(result, str)
        json.loads(result)  # must not raise
    finally:
        set_config(orig)


# ---------------------------------------------------------------------------
# Test 4: importing with no keys never raises
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_trinigence_import_never_raises():
    """Importing tradingagents.agents.utils.trinigence_tools with NO keys never raises."""
    import importlib

    # Re-import to confirm (already done at top of test session if tests above ran)
    importlib.import_module("tradingagents.agents.utils.trinigence_tools")


# ---------------------------------------------------------------------------
# Test 5: agent_utils re-export is importable
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_trinigence_reexport_from_agent_utils():
    """get_trinigence_strategy is importable from tradingagents.agents.utils.agent_utils."""
    from tradingagents.agents.utils.agent_utils import get_trinigence_strategy  # noqa: F401

    assert get_trinigence_strategy is not None


# ---------------------------------------------------------------------------
# Task 2: Market analyst wiring tests (PIL-02 T-07-05 gate)
# ---------------------------------------------------------------------------


def _get_market_analyst_tools(trinigence_enabled: bool) -> list:
    """Helper: create a market analyst node and extract its tool list.

    Uses a fake LLM that captures the tools passed to bind_tools so we can
    inspect them without making any API calls.
    """
    from tradingagents.agents.analysts.market_analyst import create_market_analyst
    from tradingagents.dataflows.config import get_config, set_config

    captured_tools: list = []

    class _FakeLLM:
        """Minimal LLM stand-in: captures bind_tools invocation."""

        def bind_tools(self, tools):
            captured_tools.extend(tools)
            return self

        def __or__(self, other):
            return self

        def __ror__(self, other):
            return self

    orig = get_config()
    set_config({"trinigence_tool_enabled": trinigence_enabled})
    try:
        fake_llm = _FakeLLM()
        analyst_node = create_market_analyst(fake_llm)

        # Build a minimal state that lets the node proceed far enough to
        # call llm.bind_tools — we don't need the full invoke to complete.
        from unittest.mock import MagicMock, patch

        # Patch prompt.partial and chain.invoke so we don't need a real LLM
        with patch("langchain_core.prompts.ChatPromptTemplate.from_messages") as mock_pt:
            mock_prompt = MagicMock()
            mock_prompt.partial.return_value = mock_prompt
            mock_chain = MagicMock()
            mock_chain.invoke.return_value = MagicMock(tool_calls=[], content="report")
            mock_prompt.__or__ = lambda s, o: mock_chain
            mock_pt.return_value = mock_prompt

            analyst_node({
                "trade_date": "2025-01-01",
                "messages": [],
                "company_of_interest": "NVDA",
                "asset_type": "stock",
            })
    finally:
        set_config(orig)

    return captured_tools


@pytest.mark.unit
def test_market_analyst_excludes_trinigence_when_disabled():
    """trinigence_tool_enabled=False → get_trinigence_strategy NOT in market analyst tools (T-07-05)."""
    from tradingagents.agents.utils.agent_utils import get_trinigence_strategy

    tools = _get_market_analyst_tools(trinigence_enabled=False)
    tool_names = [getattr(t, "name", str(t)) for t in tools]
    assert get_trinigence_strategy.name not in tool_names, (
        f"get_trinigence_strategy must not be in tools when disabled; got tools: {tool_names}"
    )


@pytest.mark.unit
def test_market_analyst_includes_trinigence_when_enabled():
    """trinigence_tool_enabled=True → get_trinigence_strategy IS in market analyst tools (T-07-05)."""
    from tradingagents.agents.utils.agent_utils import get_trinigence_strategy

    tools = _get_market_analyst_tools(trinigence_enabled=True)
    tool_names = [getattr(t, "name", str(t)) for t in tools]
    assert get_trinigence_strategy.name in tool_names, (
        f"get_trinigence_strategy must be in tools when enabled; got tools: {tool_names}"
    )
