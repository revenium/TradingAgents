"""Unit tests for the SAIF safety/assurance gate (PIL-03).

All tests are @pytest.mark.unit and pass without any API keys or network
access.  SAIF is modelled as a safety/assurance GATE on the Portfolio Manager
decision, NOT an analyst data tool.  run_saif_assurance is NOT a LangChain
@tool and is NOT re-exported through agent_utils.

Coverage (Task 1 — config, gate, meter event, import):
- PIL-03: saif_tool_id is colon-free; sourced from DEFAULT_CONFIG single source.
- PIL-03: run_saif_assurance returns a PASS/FLAG verdict for a sample rendered PM decision.
- PIL-03: @meter_tool fires exactly one Revenium tool event per call with the
  correct tool_id when a revenium_api_key is present.
- PIL-03: importing the module with NO keys never raises.

Coverage (Task 2 — graph topology + node behaviour):
- PIL-03: when saif_tool_enabled=False, graph has no 'SAIF Assurance' node
  and Portfolio Manager topology is unchanged.
- PIL-03: when saif_tool_enabled=True, graph has 'SAIF Assurance' node.
- PIL-03: SAIF gate node returns {"saif_verdict": ...} state delta and
  (with a key + patched _send_tool_event) fires exactly one saif_assurance event.
- PIL-03: saif_verdict is plumbed at all three AgentState sites (CLAUDE.md invariant).

TDD RED (Task 1): all Task 1 tests MUST fail before default_config.py has
saif_tool_id (KeyError) and before tradingagents/agents/utils/saif_gate.py
exists (ImportError / ModuleNotFoundError on collection).

TDD RED (Task 2): Task 2 graph-topology and node-behaviour tests MUST fail
before create_saif_gate_node is implemented and before setup.py is updated.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Sample rendered PM decision markdown (matches render_pm_decision output)
# ---------------------------------------------------------------------------

_SAMPLE_PM_HOLD = """\
**Rating**: Hold

**Executive Summary**: We maintain a Hold position on NVDA given balanced risk/reward.
Consider re-evaluation in 3-6 months.

**Investment Thesis**: Strong GPU demand offset by valuation concerns and near-term
supply constraints. The current risk/reward is neutral."""

_SAMPLE_PM_SELL = """\
**Rating**: Sell

**Executive Summary**: We recommend exiting NVDA positions given deteriorating fundamentals.

**Investment Thesis**: Revenue growth decelerating, valuation stretched, competition intensifying."""

_SAMPLE_PM_UNDERWEIGHT = """\
**Rating**: Underweight

**Executive Summary**: Reduce NVDA exposure — near-term headwinds dominate.

**Investment Thesis**: Macro conditions and inventory build-up justify caution."""


# ---------------------------------------------------------------------------
# Task 1: SAIF config, gate verdict, meter event, import
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_saif_tool_id_is_colon_free():
    """DEFAULT_CONFIG['saif_tool_id'] == 'saif_assurance' and contains no ':'."""
    from tradingagents.default_config import DEFAULT_CONFIG

    tool_id = DEFAULT_CONFIG["saif_tool_id"]
    assert tool_id == "saif_assurance", (
        f"Expected 'saif_assurance', got {tool_id!r}"
    )
    assert ":" not in tool_id, (
        f"saif_tool_id must not contain ':' (Revenium UI rejects it), got {tool_id!r}"
    )


@pytest.mark.unit
def test_saif_gate_returns_verdict():
    """run_saif_assurance returns valid JSON with PASS/FLAG verdict, checks, notes, source."""
    from tradingagents.agents.utils.saif_gate import run_saif_assurance

    result = run_saif_assurance(_SAMPLE_PM_HOLD)
    assert isinstance(result, str), f"Expected str result, got {type(result)}"

    parsed = json.loads(result)

    assert "verdict" in parsed, f"Missing 'verdict' key in output: {parsed}"
    assert parsed["verdict"] in ("PASS", "FLAG"), (
        f"verdict must be 'PASS' or 'FLAG', got {parsed['verdict']!r}"
    )
    assert "checks" in parsed, f"Missing 'checks' key in output: {parsed}"
    assert isinstance(parsed["checks"], list), (
        f"'checks' must be a list, got {type(parsed['checks'])}"
    )
    assert len(parsed["checks"]) > 0, "checks list must not be empty"
    assert "notes" in parsed, f"Missing 'notes' key in output: {parsed}"
    assert "source" in parsed, f"Missing 'source' key in output: {parsed}"
    assert "saif" in parsed["source"].lower(), (
        f"source must identify SAIF, got {parsed['source']!r}"
    )


@pytest.mark.unit
def test_saif_gate_flags_sell_rating():
    """run_saif_assurance returns FLAG verdict for Sell-rated PM decisions (T-07-07)."""
    from tradingagents.agents.utils.saif_gate import run_saif_assurance

    result = run_saif_assurance(_SAMPLE_PM_SELL)
    parsed = json.loads(result)
    assert parsed["verdict"] == "FLAG", (
        f"Expected FLAG for Sell rating, got {parsed['verdict']!r}"
    )


@pytest.mark.unit
def test_saif_gate_flags_underweight_rating():
    """run_saif_assurance returns FLAG verdict for Underweight-rated PM decisions (T-07-07)."""
    from tradingagents.agents.utils.saif_gate import run_saif_assurance

    result = run_saif_assurance(_SAMPLE_PM_UNDERWEIGHT)
    parsed = json.loads(result)
    assert parsed["verdict"] == "FLAG", (
        f"Expected FLAG for Underweight rating, got {parsed['verdict']!r}"
    )


@pytest.mark.unit
def test_saif_gate_passes_hold_rating():
    """run_saif_assurance returns PASS verdict for Hold-rated PM decisions (T-07-07)."""
    from tradingagents.agents.utils.saif_gate import run_saif_assurance

    result = run_saif_assurance(_SAMPLE_PM_HOLD)
    parsed = json.loads(result)
    assert parsed["verdict"] == "PASS", (
        f"Expected PASS for Hold rating, got {parsed['verdict']!r}"
    )


@pytest.mark.unit
def test_saif_gate_fires_meter_event():
    """@meter_tool fires exactly one saif_assurance event with tool_id from DEFAULT_CONFIG.

    Patches:
    - revenium_metering.decorator._send_tool_event → captures the event call.

    SAIF is a local mock gate — run_saif_assurance is NOT a LangChain @tool;
    call it directly (no .func wrapper needed).
    """
    from tradingagents.agents.utils.saif_gate import run_saif_assurance
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
            result = run_saif_assurance(_SAMPLE_PM_HOLD)

        # Exactly one tool event per call
        assert mock_send.call_count == 1, (
            f"Expected 1 Revenium tool event, got {mock_send.call_count}"
        )

        # tool_id must match config value (single source of truth, L6; no colon)
        expected_tool_id = DEFAULT_CONFIG["saif_tool_id"]
        assert ":" not in expected_tool_id, (
            f"saif_tool_id must not contain ':', got {expected_tool_id!r}"
        )
        assert mock_send.call_args.kwargs["tool_id"] == expected_tool_id, (
            f"Expected tool_id={expected_tool_id!r}, got "
            f"{mock_send.call_args.kwargs.get('tool_id')!r}"
        )

        # Result is valid JSON
        assert isinstance(result, str)
        json.loads(result)  # must not raise
    finally:
        set_config(orig)


@pytest.mark.unit
def test_saif_import_never_raises():
    """Importing tradingagents.agents.utils.saif_gate with NO keys never raises."""
    import importlib

    # Re-import to confirm (already imported if earlier tests ran first)
    importlib.import_module("tradingagents.agents.utils.saif_gate")


# ---------------------------------------------------------------------------
# Task 2: graph topology (enabled/disabled) + node behaviour
# ---------------------------------------------------------------------------


def _build_graph_workflow(saif_enabled: bool):
    """Build a StateGraph workflow with saif_tool_enabled as specified.

    Returns the pre-compiled StateGraph for node-name inspection.
    Uses a single-analyst graph (market only) to minimise test overhead.
    """
    from tradingagents.dataflows.config import get_config, set_config
    from tradingagents.graph.conditional_logic import ConditionalLogic
    from tradingagents.graph.setup import GraphSetup

    fake_llm = MagicMock()
    # Ensure with_structured_output returns something callable
    fake_llm.with_structured_output.return_value = fake_llm
    fake_tool_node = MagicMock()

    tool_nodes = {
        "market": fake_tool_node,
        "social": fake_tool_node,
        "news": fake_tool_node,
        "fundamentals": fake_tool_node,
    }
    conditional_logic = ConditionalLogic(max_debate_rounds=1, max_risk_discuss_rounds=1)

    orig = get_config()
    set_config({"saif_tool_enabled": saif_enabled})
    try:
        setup = GraphSetup(
            quick_thinking_llm=fake_llm,
            deep_thinking_llm=fake_llm,
            tool_nodes=tool_nodes,
            conditional_logic=conditional_logic,
        )
        workflow = setup.setup_graph(selected_analysts=("market",))
    finally:
        set_config(orig)

    return workflow


def _workflow_node_names(workflow) -> list[str]:
    """Extract node names from a LangGraph StateGraph (pre-compile)."""
    # StateGraph.nodes returns a dict (or MappingProxy) of {name: node_fn}.
    # Fall back to the private _nodes dict for older LangGraph versions.
    if hasattr(workflow, "nodes") and isinstance(workflow.nodes, dict):
        return list(workflow.nodes.keys())
    return list(getattr(workflow, "_nodes", {}).keys())


@pytest.mark.unit
def test_saif_gate_no_node_when_disabled():
    """When saif_tool_enabled=False, graph has no 'SAIF Assurance' node (T-07-08)."""
    workflow = _build_graph_workflow(saif_enabled=False)
    node_names = _workflow_node_names(workflow)
    assert "SAIF Assurance" not in node_names, (
        f"SAIF Assurance node must not be present when disabled; found: {node_names}"
    )


@pytest.mark.unit
def test_saif_gate_node_when_enabled():
    """When saif_tool_enabled=True, graph has 'SAIF Assurance' node (T-07-08)."""
    workflow = _build_graph_workflow(saif_enabled=True)
    node_names = _workflow_node_names(workflow)
    assert "SAIF Assurance" in node_names, (
        f"SAIF Assurance node must be present when enabled; found: {node_names}"
    )


@pytest.mark.unit
def test_saif_node_returns_verdict_delta():
    """SAIF gate node returns a {'saif_verdict': ...} state delta (T-07-07)."""
    from tradingagents.agents.utils.saif_gate import create_saif_gate_node

    gate_node = create_saif_gate_node()

    state = {
        "final_trade_decision": _SAMPLE_PM_HOLD,
        "messages": [],
    }

    result = gate_node(state)
    assert isinstance(result, dict), f"Expected dict delta, got {type(result)}"
    assert "saif_verdict" in result, f"Missing 'saif_verdict' in delta: {result}"
    assert isinstance(result["saif_verdict"], str), (
        f"saif_verdict must be str, got {type(result['saif_verdict'])}"
    )
    # Verdict JSON should contain PASS or FLAG
    parsed_verdict = json.loads(result["saif_verdict"])
    assert parsed_verdict["verdict"] in ("PASS", "FLAG")


@pytest.mark.unit
def test_saif_node_fires_meter_event():
    """SAIF gate node fires exactly one saif_assurance meter event (T-07-09)."""
    from tradingagents.agents.utils.saif_gate import create_saif_gate_node
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
            gate_node = create_saif_gate_node()
            state = {
                "final_trade_decision": _SAMPLE_PM_HOLD,
                "messages": [],
            }
            delta = gate_node(state)

        assert mock_send.call_count == 1, (
            f"Expected 1 saif_assurance meter event, got {mock_send.call_count}"
        )
        assert mock_send.call_args.kwargs["tool_id"] == DEFAULT_CONFIG["saif_tool_id"], (
            f"Expected tool_id={DEFAULT_CONFIG['saif_tool_id']!r}, got "
            f"{mock_send.call_args.kwargs.get('tool_id')!r}"
        )
        assert "saif_verdict" in delta
    finally:
        set_config(orig)


@pytest.mark.unit
def test_saif_verdict_plumbed_all_three_sites():
    """saif_verdict is present in agent_states.py, propagation.py, trading_graph.py (CLAUDE.md)."""
    import pathlib

    base = pathlib.Path(__file__).parent.parent  # repo root (worktree root)

    files_to_check = [
        base / "tradingagents" / "agents" / "utils" / "agent_states.py",
        base / "tradingagents" / "graph" / "propagation.py",
        base / "tradingagents" / "graph" / "trading_graph.py",
    ]

    for path in files_to_check:
        content = path.read_text(encoding="utf-8")
        assert "saif_verdict" in content, (
            f"saif_verdict must be present in {path.name} "
            f"(all three AgentState sites, per CLAUDE.md)"
        )
