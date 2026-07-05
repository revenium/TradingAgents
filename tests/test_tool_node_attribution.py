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


@pytest.mark.unit
def test_tool_event_attributed_through_real_graph_execution():
    """End-to-end proof: a tool dispatched through a compiled LangGraph attributes
    its @meter_tool event to the analyst, NOT "unknown".

    This exercises the REAL execution path — a compiled StateGraph whose ToolNode
    runs the tool in a ContextThreadPoolExecutor worker thread — rather than a
    unit-level wrapper call. It guards the exact symptom the platform reported:
    tool-metering events arriving with agent="unknown". The context deliberately
    starts at the "unknown" default so a passing assertion proves the wrapper set
    the agent that Revenium ultimately receives (meter_tool.py reads
    current_agent_name at emit time).
    """
    from unittest.mock import patch

    from langchain_core.messages import AIMessage
    from langgraph.graph import END, START, MessagesState, StateGraph

    from tradingagents.dataflows.config import get_config, set_config
    from tradingagents.revenium.context import current_agent_name

    orig = get_config()
    set_config({
        "trinigence_tool_enabled": True,
        "revenium_api_key": "rev_mk_test",
        "revenium_api_url": "https://api.revenium.ai",
        "revenium_organization_name": "org",
        "revenium_product_name": "p",
        "revenium_subscriber_id": "s",
    })

    market_node = TradingAgentsGraph._create_tool_nodes(
        SimpleNamespace(config=get_config())
    )["market"]

    def emit(_state):
        return {"messages": [AIMessage(
            content="",
            tool_calls=[{
                "name": "get_trinigence_strategy",
                "args": {"description": "momentum"},
                "id": "c1",
                "type": "tool_call",
            }],
        )]}

    sg = StateGraph(MessagesState)
    sg.add_node("emit", emit)
    sg.add_node("tools", market_node)
    sg.add_edge(START, "emit")
    sg.add_edge("emit", "tools")
    sg.add_edge("tools", END)
    app = sg.compile()

    token = current_agent_name.set("unknown")  # the default that produced the bug
    try:
        with patch("revenium_metering.decorator._send_tool_event") as mock_send:
            app.invoke({"messages": []})

        assert mock_send.call_count == 1, (
            f"expected one tool event, got {mock_send.call_count}"
        )
        agent = mock_send.call_args.kwargs["context"].agent
        assert agent == "market_analyst", (
            f"tool event emitted with agent={agent!r}; expected 'market_analyst' "
            f"(the 'unknown' regression)"
        )
    finally:
        current_agent_name.reset(token)
        set_config(orig)
