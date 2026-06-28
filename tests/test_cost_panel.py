"""Tests for the Phase 4 live cost panel — pricing math, call_count aggregation,
end_run reset, and the _build_cost_panel smoke test.

All tests are unit-level (marker: unit) and pass without any live
REVENIUM_METERING_API_KEY.  All Revenium HTTP calls are mocked.

Key invariants validated:
- compute_cost returns correct per-provider dollar amounts for known models.
- compute_cost returns 0.0 for unknown provider/model without raising.
- on_llm_end accumulates call_count and cost additively across repeated calls.
- end_run clears agent_costs and resets run_total_tokens.
- _build_cost_panel returns a rich.panel.Panel for both empty and populated handlers.
- A populated panel applies ×N only to agents with call_count > 1.
- The max-cost agent row is highlighted (no assertion on Rich internals, smoke only).
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_llm_result(input_tokens: int = 100, output_tokens: int = 50) -> LLMResult:
    """Build a synthetic LLMResult with usage_metadata that mimics a real provider."""
    msg = AIMessage(content="Test response")
    msg.usage_metadata = {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
    }
    gen = ChatGeneration(message=msg)
    return LLMResult(generations=[[gen]])


def _make_serialized(model: str = "gpt-4.1-mini", provider: str = "openai") -> dict:
    """Build a synthetic serialized LLM dict as LangChain passes to on_chat_model_start."""
    return {
        "id": [f"langchain_{provider}", "chat_models", f"Chat{provider.capitalize()}"],
        "kwargs": {"model_name": model},
    }


def _make_handler():
    """Return a ReveniumCallbackHandler with a mock client (no live keys needed)."""
    from tradingagents.revenium.callback import ReveniumCallbackHandler

    mock_client = MagicMock()
    # MagicMock().enabled evaluates to truthy by default, so the handler is "enabled"
    handler = ReveniumCallbackHandler.from_config({
        "revenium_api_key": "rev_mk_test",
        "revenium_api_url": "https://api.revenium.ai",
        "revenium_organization_name": "Revenium-Research-Desk",
        "revenium_product_name": "trading-signal",
        "revenium_subscriber_id": "test@revenium.io",
        "revenium_task_type_map": {},
        "revenium_trace_type": "trading-run",
    })
    handler._client = mock_client
    return handler


def _fire_llm_call(
    handler,
    agent_name: str,
    model: str = "gpt-4.1-mini",
    provider: str = "openai",
    input_tokens: int = 100,
    output_tokens: int = 50,
) -> None:
    """Simulate one complete LLM call through the handler (start + end)."""
    from tradingagents.revenium.context import current_agent_name

    run_id = uuid.uuid4()
    tok = current_agent_name.set(agent_name)
    try:
        handler.on_chat_model_start(
            _make_serialized(model=model, provider=provider),
            [],
            run_id=run_id,
        )
        handler.on_llm_end(
            _make_llm_result(input_tokens=input_tokens, output_tokens=output_tokens),
            run_id=run_id,
        )
    finally:
        current_agent_name.reset(tok)


def _flush_threads(handler, timeout: float = 2.0) -> None:
    """Join all background threads the handler launched (for test sync)."""
    for t in list(handler._threads):
        t.join(timeout=timeout)


# ---------------------------------------------------------------------------
# Task 1 — pricing module
# ---------------------------------------------------------------------------

class TestComputeCost:
    """Verify the local pricing math for known and unknown models."""

    @pytest.mark.unit
    def test_anthropic_claude_sonnet_input_rate(self):
        """compute_cost('anthropic', 'claude-sonnet-4-6', 1_000_000, 0) == 3.00."""
        from tradingagents.revenium.pricing import compute_cost

        result = compute_cost("anthropic", "claude-sonnet-4-6", 1_000_000, 0)
        assert abs(result - 3.00) < 1e-6, f"Expected 3.00, got {result}"

    @pytest.mark.unit
    def test_openai_gpt_4_1_mini_output_rate(self):
        """compute_cost('openai', 'gpt-4.1-mini', 0, 1_000_000) == 1.60."""
        from tradingagents.revenium.pricing import compute_cost

        result = compute_cost("openai", "gpt-4.1-mini", 0, 1_000_000)
        assert abs(result - 1.60) < 1e-6, f"Expected 1.60, got {result}"

    @pytest.mark.unit
    def test_unknown_model_returns_zero_and_does_not_raise(self):
        """compute_cost for an unknown provider/model returns 0.0 without raising."""
        from tradingagents.revenium.pricing import compute_cost

        result = compute_cost("unknown", "mystery-model", 1000, 1000)
        assert result == 0.0, f"Expected 0.0, got {result}"

    @pytest.mark.unit
    def test_unknown_provider_known_model_substring_returns_zero(self):
        """An unknown provider returns 0.0 even if model substring matches another provider."""
        from tradingagents.revenium.pricing import compute_cost

        # "google" provider is not in the table — should return 0.0, not raise
        result = compute_cost("google", "claude-sonnet-4", 500_000, 500_000)
        assert result == 0.0, f"Expected 0.0 for unknown provider, got {result}"

    @pytest.mark.unit
    def test_cost_combines_input_and_output(self):
        """compute_cost correctly combines input and output token costs."""
        from tradingagents.revenium.pricing import compute_cost

        # anthropic claude-sonnet-4: input=$3/M, output=$15/M
        # 500k input + 500k output = (500k*3 + 500k*15)/1M = (1.5 + 7.5) = 9.0
        result = compute_cost("anthropic", "claude-sonnet-4", 500_000, 500_000)
        assert abs(result - 9.00) < 1e-6, f"Expected 9.00, got {result}"


# ---------------------------------------------------------------------------
# Task 1 — agent_costs schema extension (call_count + cost fields)
# ---------------------------------------------------------------------------

class TestAgentCostsSchema:
    """Verify the extended agent_costs dict accumulates call_count and cost."""

    @pytest.mark.unit
    def test_two_calls_accumulate_call_count(self):
        """Calling on_llm_end twice for the same agent yields call_count == 2."""
        handler = _make_handler()

        _fire_llm_call(
            handler,
            agent_name="market_analyst",
            model="gpt-4.1-mini",
            provider="openai",
            input_tokens=100,
            output_tokens=50,
        )
        _fire_llm_call(
            handler,
            agent_name="market_analyst",
            model="gpt-4.1-mini",
            provider="openai",
            input_tokens=200,
            output_tokens=80,
        )
        _flush_threads(handler)

        entry = handler.agent_costs["market_analyst"]
        assert entry["call_count"] == 2, f"Expected call_count=2, got {entry['call_count']}"

    @pytest.mark.unit
    def test_two_calls_accumulate_cost(self):
        """Calling on_llm_end twice for the same agent yields cost == sum of both calls."""
        from tradingagents.revenium.pricing import compute_cost

        handler = _make_handler()

        in1, out1 = 1_000_000, 0
        in2, out2 = 0, 1_000_000

        _fire_llm_call(
            handler,
            agent_name="portfolio_manager",
            model="claude-sonnet-4-6",
            provider="anthropic",
            input_tokens=in1,
            output_tokens=out1,
        )
        _fire_llm_call(
            handler,
            agent_name="portfolio_manager",
            model="claude-sonnet-4-6",
            provider="anthropic",
            input_tokens=in2,
            output_tokens=out2,
        )
        _flush_threads(handler)

        expected = compute_cost("anthropic", "claude-sonnet-4-6", in1, out1) + \
                   compute_cost("anthropic", "claude-sonnet-4-6", in2, out2)
        actual = handler.agent_costs["portfolio_manager"]["cost"]
        assert abs(actual - expected) < 1e-6, f"Expected cost={expected:.6f}, got {actual:.6f}"

    @pytest.mark.unit
    def test_new_entry_has_zero_call_count_before_first_call(self):
        """After a single call, call_count == 1 (not 0, not 2)."""
        handler = _make_handler()

        _fire_llm_call(handler, "trader", model="gpt-4.1-mini", provider="openai")
        _flush_threads(handler)

        assert handler.agent_costs["trader"]["call_count"] == 1


# ---------------------------------------------------------------------------
# Task 1 — end_run reset
# ---------------------------------------------------------------------------

class TestEndRunReset:
    """Verify end_run() clears agent_costs and run_total_tokens."""

    @pytest.mark.unit
    def test_end_run_clears_agent_costs(self):
        """end_run() resets agent_costs to an empty dict."""
        handler = _make_handler()

        _fire_llm_call(handler, "market_analyst")
        _flush_threads(handler)

        # Precondition: agent_costs is non-empty after a call
        assert handler.agent_costs, "agent_costs should be non-empty before end_run"

        handler.end_run()

        assert handler.agent_costs == {}, \
            f"agent_costs should be empty after end_run, got {handler.agent_costs}"

    @pytest.mark.unit
    def test_end_run_resets_run_total_tokens(self):
        """end_run() resets run_total_tokens to 0."""
        handler = _make_handler()

        _fire_llm_call(handler, "market_analyst", input_tokens=500, output_tokens=200)
        _flush_threads(handler)

        assert handler.run_total_tokens > 0, "run_total_tokens should be > 0 after a call"

        handler.end_run()

        assert handler.run_total_tokens == 0, \
            f"run_total_tokens should be 0 after end_run, got {handler.run_total_tokens}"

    @pytest.mark.unit
    def test_costs_do_not_bleed_across_runs(self):
        """Per-agent costs from run 1 are not visible in run 2 after end_run()."""
        handler = _make_handler()

        # Run 1
        _fire_llm_call(handler, "market_analyst")
        _flush_threads(handler)
        handler.end_run()

        # Run 2 — different agent
        _fire_llm_call(handler, "trader")
        _flush_threads(handler)

        assert "market_analyst" not in handler.agent_costs, \
            "market_analyst costs from run 1 should not appear in run 2"
        assert "trader" in handler.agent_costs


# ---------------------------------------------------------------------------
# Task 2 — _build_cost_panel smoke tests (added here per plan structure)
# ---------------------------------------------------------------------------

class TestBuildCostPanelSmoke:
    """Smoke tests: _build_cost_panel returns a Panel for empty and populated handlers."""

    @pytest.mark.unit
    def test_returns_panel_for_empty_handler(self):
        """_build_cost_panel returns a rich.panel.Panel when agent_costs is empty."""
        from rich.panel import Panel

        from cli.main import _build_cost_panel

        handler = _make_handler()
        # agent_costs is empty by default
        result = _build_cost_panel(handler)
        assert isinstance(result, Panel), \
            f"Expected Panel for empty handler, got {type(result)}"

    @pytest.mark.unit
    def test_returns_panel_for_populated_handler(self):
        """_build_cost_panel returns a rich.panel.Panel when agent_costs is populated."""
        from rich.panel import Panel

        from cli.main import _build_cost_panel

        handler = _make_handler()
        # Populate with one single-call agent and one multi-call agent
        handler.agent_costs = {
            "market_analyst": {
                "input_tokens": 1_000_000,
                "output_tokens": 0,
                "cost": 3.00,
                "call_count": 1,
            },
            "bull_researcher": {
                "input_tokens": 500_000,
                "output_tokens": 500_000,
                "cost": 9.00,
                "call_count": 3,
            },
        }
        result = _build_cost_panel(handler)
        assert isinstance(result, Panel), \
            f"Expected Panel for populated handler, got {type(result)}"

    @pytest.mark.unit
    def test_multi_call_agent_annotated_with_xn(self):
        """An agent with call_count > 1 appears with ×N annotation; single-call does not."""
        from rich.panel import Panel
        from rich.console import Console
        import io

        from cli.main import _build_cost_panel

        handler = _make_handler()
        handler.agent_costs = {
            "market_analyst": {
                "input_tokens": 100,
                "output_tokens": 50,
                "cost": 0.001,
                "call_count": 1,  # single call — should NOT have ×N
            },
            "bull_researcher": {
                "input_tokens": 200,
                "output_tokens": 100,
                "cost": 0.003,
                "call_count": 3,  # multi-call — SHOULD have ×3
            },
        }

        panel = _build_cost_panel(handler)
        assert isinstance(panel, Panel)

        # Render to a string buffer to check for ×N annotation
        console = Console(file=io.StringIO(), width=120, highlight=False)
        console.print(panel)
        rendered = console.file.getvalue()

        assert "×3" in rendered, f"Expected '×3' in panel output; rendered:\n{rendered}"
        # market_analyst has call_count=1, must NOT have ×1
        assert "×1" not in rendered, f"Unexpected '×1' in panel output; rendered:\n{rendered}"
