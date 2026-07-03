"""Unit tests for the Edgehound decision-intelligence mock tool (PIL-01).

All tests are @pytest.mark.unit and pass without any API keys or network
access.  Unlike Jentic, Edgehound is a fully local mock — no external
dependency means no sentinel branch is needed when the tool is called directly.
The LLM-level gating (only offering the tool when edgehound_tool_enabled=True)
is tested in Task 2 (market_analyst wiring tests below).

Coverage:
- PIL-01: edgehound_tool_id is colon-free; sourced from DEFAULT_CONFIG single source.
- PIL-01: @meter_tool fires exactly one Revenium tool event per call with the
  correct tool_id when a revenium_api_key is present.
- PIL-01: returned output contains decision-intelligence fields (thesis,
  entry_level, exit_level, conviction_score).
- PIL-01: importing the module with NO keys never raises.

TDD RED: all tests MUST fail before tradingagents/agents/utils/edgehound_tools.py
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
def test_edgehound_tool_id_is_colon_free():
    """DEFAULT_CONFIG['edgehound_tool_id'] == 'edgehound_decision' and contains no ':'."""
    from tradingagents.default_config import DEFAULT_CONFIG

    tool_id = DEFAULT_CONFIG["edgehound_tool_id"]
    assert tool_id == "edgehound_decision", (
        f"Expected 'edgehound_decision', got {tool_id!r}"
    )
    assert ":" not in tool_id, (
        f"edgehound_tool_id must not contain ':' (Revenium UI rejects it), got {tool_id!r}"
    )


# ---------------------------------------------------------------------------
# Test 2: tool returns plausible decision-intelligence output
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_edgehound_tool_returns_plausible_output():
    """get_edgehound_decision.func(...) returns JSON with decision-intelligence fields."""
    from tradingagents.agents.utils.edgehound_tools import get_edgehound_decision

    result = get_edgehound_decision.func("NVDA momentum breakout")
    assert isinstance(result, str), f"Expected str result, got {type(result)}"

    # Must be valid JSON
    parsed = json.loads(result)

    # Required decision-intelligence keys
    assert "thesis" in parsed, f"Missing 'thesis' key in output: {parsed}"
    assert "entry_level" in parsed, f"Missing 'entry_level' key in output: {parsed}"
    assert "exit_level" in parsed, f"Missing 'exit_level' key in output: {parsed}"
    assert "conviction_score" in parsed, f"Missing 'conviction_score' key in output: {parsed}"

    # conviction_score must be 0-100
    score = parsed["conviction_score"]
    assert isinstance(score, (int, float)), f"conviction_score must be numeric, got {type(score)}"
    assert 0 <= score <= 100, f"conviction_score must be 0-100, got {score}"


# ---------------------------------------------------------------------------
# Test 3: meter event fires exactly once with correct tool_id
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_edgehound_tool_fires_meter_event():
    """@meter_tool fires exactly one tool event per call with tool_id=DEFAULT_CONFIG['edgehound_tool_id'].

    Patches:
    - revenium_metering.decorator._send_tool_event → captures the event call

    The tool is a local mock — no external SDK to patch.
    """
    from tradingagents.agents.utils.edgehound_tools import get_edgehound_decision
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
            result = get_edgehound_decision.func("NVDA entry signal")

        # Exactly one tool event per call
        assert mock_send.call_count == 1, (
            f"Expected 1 Revenium tool event, got {mock_send.call_count}"
        )

        # tool_id must match config value (single source of truth, L6) and
        # must NOT contain ':' — Revenium's Tools UI rejects colons.
        expected_tool_id = DEFAULT_CONFIG["edgehound_tool_id"]
        assert ":" not in expected_tool_id, (
            f"edgehound_tool_id must not contain ':', got {expected_tool_id!r}"
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
def test_edgehound_import_never_raises():
    """Importing tradingagents.agents.utils.edgehound_tools with NO keys never raises."""
    # If import itself fails, the test fails — which is correct behavior on collection.
    import importlib

    # Re-import to confirm (already done at top of test session if tests above ran)
    importlib.import_module("tradingagents.agents.utils.edgehound_tools")


# ---------------------------------------------------------------------------
# Test 5: agent_utils re-export is importable
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_edgehound_reexport_from_agent_utils():
    """get_edgehound_decision is importable from tradingagents.agents.utils.agent_utils."""
    from tradingagents.agents.utils.agent_utils import get_edgehound_decision  # noqa: F401

    assert get_edgehound_decision is not None


# ---------------------------------------------------------------------------
# Task 2: Market analyst wiring tests (PIL-01 T-07-02 gate)
# ---------------------------------------------------------------------------


def _get_market_analyst_tools(edgehound_enabled: bool) -> list:
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
    set_config({"edgehound_tool_enabled": edgehound_enabled})
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
def test_market_analyst_excludes_edgehound_when_disabled():
    """edgehound_tool_enabled=False → get_edgehound_decision NOT in market analyst tools (T-07-02)."""
    from tradingagents.agents.utils.agent_utils import get_edgehound_decision

    tools = _get_market_analyst_tools(edgehound_enabled=False)
    tool_names = [getattr(t, "name", str(t)) for t in tools]
    assert get_edgehound_decision.name not in tool_names, (
        f"get_edgehound_decision must not be in tools when disabled; got tools: {tool_names}"
    )


@pytest.mark.unit
def test_market_analyst_includes_edgehound_when_enabled():
    """edgehound_tool_enabled=True → get_edgehound_decision IS in market analyst tools (T-07-02)."""
    from tradingagents.agents.utils.agent_utils import get_edgehound_decision

    tools = _get_market_analyst_tools(edgehound_enabled=True)
    tool_names = [getattr(t, "name", str(t)) for t in tools]
    assert get_edgehound_decision.name in tool_names, (
        f"get_edgehound_decision must be in tools when enabled; got tools: {tool_names}"
    )
