"""The market analyst is bound (and prompt-instructed) to call
get_verified_market_snapshot; if the executor ToolNode doesn't register it, the
call fails and the model reports the tool "unavailable" and skips verification.

Regression guard for that wiring gap (snapshot bound to the LLM but missing from
the market ToolNode).
"""
from types import SimpleNamespace

import pytest

from tradingagents.graph.trading_graph import TradingAgentsGraph


@pytest.mark.unit
def test_market_toolnode_can_execute_verified_snapshot():
    # _create_tool_nodes only reads self.config -> a lightweight stub avoids
    # building LLMs. The market entry is an attribution-wrapped node (Phase 7
    # WR-03); introspect its executable set via the exposed inner ToolNode.
    nodes = TradingAgentsGraph._create_tool_nodes(SimpleNamespace(config={}))
    market_tools = set(nodes["market"].tool_node.tools_by_name)
    assert "get_verified_market_snapshot" in market_tools, (
        "get_verified_market_snapshot is bound to the market analyst but not "
        "registered in the market ToolNode, so the model's call fails."
    )
    # the other core market tools must remain too
    assert {"get_stock_data", "get_indicators"} <= market_tools
