"""Every tool node is attribution-wrapped so its @meter_tool events land on the
triggering analyst, not the "unknown" default (WR-03).

LangGraph runs each node in its own copy_context().run(), so the current_agent_name
an analyst sets does not reach its sibling ToolNode. TradingAgentsGraph._create_tool_nodes
wraps EACH tool node with _attributed_tool_node(<analyst name>) so tool cost is
attributed per agent in Revenium. This also guards the CR-01-style gap where a bound
tool (jentic) is missing from the executable ToolNode.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from tradingagents.graph.trading_graph import TradingAgentsGraph

# tool-node key -> current_agent_name each analyst sets in its node
_EXPECTED_AGENT = {
    "market": "market_analyst",
    "social": "sentiment_analyst",
    "news": "news_analyst",
    "fundamentals": "fundamentals_analyst",
}


@pytest.mark.unit
def test_all_tool_nodes_are_attribution_wrapped_with_correct_agent():
    nodes = TradingAgentsGraph._create_tool_nodes(SimpleNamespace(config={}))
    for key, expected_agent in _EXPECTED_AGENT.items():
        node = nodes[key]
        # Wrapped nodes expose tool_node + agent_name; a bare ToolNode would not.
        assert getattr(node, "tool_node", None) is not None, (
            f"tool node {key!r} is not attribution-wrapped — its tool events would "
            f"attribute to 'unknown' (WR-03)"
        )
        assert node.agent_name == expected_agent, (
            f"tool node {key!r} attributes to {node.agent_name!r}, expected {expected_agent!r}"
        )


@pytest.mark.unit
def test_jentic_tool_executable_in_news_node_only_when_enabled():
    # Disabled (default): jentic tool must NOT be in the news executable set.
    off = TradingAgentsGraph._create_tool_nodes(SimpleNamespace(config={}))
    assert "get_jentic_news" not in off["news"].tool_node.tools_by_name

    # Enabled: jentic must be dispatchable through the news ToolNode (CR-01-style),
    # or a real graph run cannot fire its metered event.
    on = TradingAgentsGraph._create_tool_nodes(
        SimpleNamespace(config={"jentic_tool_enabled": True})
    )
    assert "get_jentic_news" in on["news"].tool_node.tools_by_name
