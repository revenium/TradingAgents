"""Combined 3-partner integration test: 3 distinct tool events in one run (PIL-04).

Proves Success Criterion 1: a single enabled run emits exactly 3 distinct
Revenium tool events whose tool_ids are {edgehound_decision, trinigence_strategy,
saif_assurance}, covering all three pilot-partner slices (PIL-01..PIL-03).

All tests are @pytest.mark.unit and pass without any API keys or network access.

Coverage:
- PIL-04: with all three partner flags enabled and _send_tool_event patched, calling
  the three metered units (get_edgehound_decision.func, get_trinigence_strategy.func,
  run_saif_assurance) captures exactly 3 tool events with distinct tool_ids.
- PIL-04: the set of captured tool_ids equals {edgehound_decision, trinigence_strategy,
  saif_assurance} — 3 DISTINCT partner tool events (Success Criterion 1).
- PIL-04: all three toolIds are colon-free.
- PIL-04: all three toolIds are sourced from their DEFAULT_CONFIG keys (L6 invariant).

Design notes
------------
- Edgehound and Trinigence are LangChain @tools; call via .func(...) to bypass
  the @tool wrapper and pass directly through @meter_tool.
- SAIF is a gate (NOT a @tool); call run_saif_assurance(...) directly (no .func).
- Config is restored in a finally block so this test is side-effect-free.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Sample PM decision markdown for the SAIF gate call
# ---------------------------------------------------------------------------

_SAMPLE_PM_HOLD = """\
**Rating**: Hold

**Executive Summary**: Maintain Hold on NVDA — balanced risk/reward.

**Investment Thesis**: GPU demand offset by near-term supply constraints."""


# ---------------------------------------------------------------------------
# Test 1: 3 distinct partner tool events in one combined run (PIL-04 Success Criterion 1)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_three_partner_tool_events_distinct():
    """3 distinct partner tool events fire in one enabled run (PIL-04 Success Criterion 1).

    With all three partner flags enabled and _send_tool_event patched, calling:
      - get_edgehound_decision.func(query)       → edgehound_decision event
      - get_trinigence_strategy.func(description)→ trinigence_strategy event
      - run_saif_assurance(pm_decision_text)     → saif_assurance event

    captures exactly 3 tool events with distinct tool_ids matching the three
    DEFAULT_CONFIG keys.
    """
    from tradingagents.agents.utils.agent_utils import (
        get_edgehound_decision,
        get_trinigence_strategy,
    )
    from tradingagents.agents.utils.saif_gate import run_saif_assurance
    from tradingagents.dataflows.config import get_config, set_config
    from tradingagents.default_config import DEFAULT_CONFIG

    orig = get_config()
    set_config({
        # Enable all three partner tools
        "edgehound_tool_enabled": True,
        "trinigence_tool_enabled": True,
        "saif_tool_enabled": True,
        # Provide a metering key so @meter_tool fires (not a no-op)
        "revenium_api_key": "rev_mk_test",
        "revenium_api_url": "https://api.revenium.ai",
        "revenium_organization_name": "Revenium-Research-Desk",
        "revenium_product_name": "trading-signal",
        "revenium_subscriber_id": "test@example.com",
    })

    try:
        with patch("revenium_metering.decorator._send_tool_event") as mock_send:
            # Edgehound: LangChain @tool — call via .func to hit the @meter_tool layer
            get_edgehound_decision.func("NVDA momentum breakout entry signal")

            # Trinigence: LangChain @tool — call via .func to hit the @meter_tool layer
            get_trinigence_strategy.func("momentum breakout strategy for NVDA in tech sector")

            # SAIF: gate (NOT a @tool) — call directly (no .func wrapper)
            run_saif_assurance(_SAMPLE_PM_HOLD)

        # --- Assertion 1: exactly 3 tool events captured ---
        assert mock_send.call_count == 3, (
            f"Expected exactly 3 partner tool events, got {mock_send.call_count}. "
            f"Calls: {[c.kwargs.get('tool_id') for c in mock_send.call_args_list]}"
        )

        # --- Assertion 2: 3 DISTINCT tool_ids equal the expected set ---
        captured_tool_ids = {
            c.kwargs["tool_id"]
            for c in mock_send.call_args_list
        }
        expected_tool_ids = {
            DEFAULT_CONFIG["edgehound_tool_id"],
            DEFAULT_CONFIG["trinigence_tool_id"],
            DEFAULT_CONFIG["saif_tool_id"],
        }
        assert captured_tool_ids == expected_tool_ids, (
            f"Expected tool_ids {expected_tool_ids!r}, "
            f"got {captured_tool_ids!r}"
        )

    finally:
        set_config(orig)


# ---------------------------------------------------------------------------
# Test 2: all three toolIds are colon-free and sourced from DEFAULT_CONFIG (L6)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_all_partner_tool_ids_colon_free_from_config():
    """All three partner toolIds are colon-free and sourced from DEFAULT_CONFIG (L6, T-07-10).

    Ensures that SAIF's toolId follows the same single-source-of-truth invariant
    as Edgehound (PIL-01) and Trinigence (PIL-02): the value in DEFAULT_CONFIG is
    the authoritative string used both by @meter_tool at decoration time and by
    the ToolResource registration in setup_revenium.py.
    """
    from tradingagents.default_config import DEFAULT_CONFIG

    partner_keys = [
        "edgehound_tool_id",
        "trinigence_tool_id",
        "saif_tool_id",
    ]
    expected_values = {
        "edgehound_tool_id": "edgehound_decision",
        "trinigence_tool_id": "trinigence_strategy",
        "saif_tool_id": "saif_assurance",
    }

    for key in partner_keys:
        tool_id = DEFAULT_CONFIG[key]

        # Must be the expected stable default (no env override in CI)
        assert tool_id == expected_values[key], (
            f"DEFAULT_CONFIG[{key!r}] == {tool_id!r}; expected {expected_values[key]!r}"
        )

        # Must NOT contain ':' — Revenium UI rejects colons in toolIds
        assert ":" not in tool_id, (
            f"DEFAULT_CONFIG[{key!r}] must not contain ':'; got {tool_id!r} "
            f"(Revenium UI validation rejects colons)"
        )


# ---------------------------------------------------------------------------
# Test 3: partner tools are registered in the EXECUTABLE market ToolNode (CR-01)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_market_tool_node_executable_set_matches_bound_partner_tools():
    """The market ToolNode's executable tool set includes the partner tools when enabled.

    Guards against the CR-01 regression: create_market_analyst binds the partner
    tools to the LLM, but if TradingAgentsGraph._create_tool_nodes builds the market
    ToolNode without them, a real graph run cannot dispatch the LLM's tool call —
    LangGraph returns a ToolMessage error and @meter_tool never fires. The executable
    set (ToolNode.tools_by_name) MUST mirror the advertised (bound) set. This drives
    the ACTUAL _create_tool_nodes wiring (it only reads self.config) rather than a
    .func() shortcut.
    """
    from types import SimpleNamespace

    from tradingagents.graph.trading_graph import TradingAgentsGraph

    # Enabled: both partner tools must be executable through the market ToolNode.
    stub_on = SimpleNamespace(config={
        "edgehound_tool_enabled": True,
        "trinigence_tool_enabled": True,
    })
    market_on = TradingAgentsGraph._create_tool_nodes(stub_on)["market"]
    names_on = set(market_on.tool_node.tools_by_name)
    assert "get_edgehound_decision" in names_on, (
        "Edgehound bound to the LLM but NOT executable in the market ToolNode (CR-01)"
    )
    assert "get_trinigence_strategy" in names_on, (
        "Trinigence bound to the LLM but NOT executable in the market ToolNode (CR-01)"
    )

    # Disabled (default): partner tools must NOT be in the executable set — mirrors
    # the LLM binding gate so a disabled tool is neither advertised nor dispatchable.
    stub_off = SimpleNamespace(config={})
    market_off = TradingAgentsGraph._create_tool_nodes(stub_off)["market"]
    names_off = set(market_off.tool_node.tools_by_name)
    assert "get_edgehound_decision" not in names_off
    assert "get_trinigence_strategy" not in names_off


# ---------------------------------------------------------------------------
# Test 4: the market ToolNode re-sets per-agent attribution before dispatch (WR-03)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_attributed_tool_node_sets_agent_name_before_dispatch():
    """The attribution wrapper sets current_agent_name='market_analyst' before dispatch.

    Guards against the WR-03 regression: LangGraph runs each node in its own
    copy_context().run(), so current_agent_name set inside the analyst node does NOT
    reach the sibling market ToolNode — partner tool events would attribute to the
    "unknown" default. The wrapper must re-set the contextvar in the ToolNode's own
    context immediately before dispatch, so @meter_tool reads "market_analyst". A spy
    records the contextvar value at dispatch time.
    """
    from tradingagents.graph.trading_graph import _attributed_tool_node
    from tradingagents.revenium.context import current_agent_name

    seen = {}

    class _SpyToolNode:
        def invoke(self, state, config=None):
            seen["agent"] = current_agent_name.get()
            return {"messages": []}

    wrapped = _attributed_tool_node(_SpyToolNode(), "market_analyst")

    # Start from the "unknown" default so a passing assertion proves the wrapper set it.
    token = current_agent_name.set("unknown")
    try:
        wrapped({"messages": []})
    finally:
        current_agent_name.reset(token)

    assert seen["agent"] == "market_analyst", (
        f"ToolNode dispatched with agent={seen.get('agent')!r}; expected "
        f"'market_analyst' (WR-03 contextvar-isolation regression)"
    )
