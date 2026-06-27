"""Tests for Revenium tool metering (@meter_tool) and agent attribution.

All tests are unit-level (marker: unit) and pass without any live
REVENIUM_METERING_API_KEY.  All Revenium HTTP calls are mocked.

Coverage:
- Tool-event fires exactly once per decorated-tool call when a metering key
  is present, carrying the tool name, active trace_id, and agent context.
- Keyless (no api_key) variant: zero tool events, identical return value.
- Fail-open: a metering exception does not block the data fetch.
- Agent attribution: two distinct agent names produce events with the correct
  agent field and matching task_type from revenium_task_type_map.

NOTE (TDD RED phase intent): Tests in TestMeterToolEventFires and
TestMeterToolKeylessNoop are written before tradingagents/revenium/meter_tool.py
exists or @meter_tool is applied to tools.  They MUST fail in RED:
- Metered tests fail because _send_tool_event is never called (no decorator).
- Keyless tests also fail because _send_tool_event is never called but the
  assertion on call_count == 0 would pass -- however some variants will fail
  because result comparison will work once the correct mock path is used.
The agent-attribution tests (TestAgentAttribution) test the already-complete
callback handler from Plan 01-02; they pass in both RED and GREEN.
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult


# ---------------------------------------------------------------------------
# Contextvar isolation — reset per-agent and per-trace contextvars before
# every test so ContextVar.set() calls in one test do not bleed into the next.
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_contextvars():
    """Isolate Revenium ContextVars across every test in this module."""
    from tradingagents.revenium.context import (
        current_agent_name,
        current_trace_id,
        current_run_meta,
    )
    tok_agent = current_agent_name.set("unknown")
    tok_trace = current_trace_id.set("")
    tok_meta = current_run_meta.set({})
    yield
    current_agent_name.reset(tok_agent)
    current_trace_id.reset(tok_trace)
    current_run_meta.reset(tok_meta)


# ---------------------------------------------------------------------------
# Helpers shared with test_revenium_metering.py (duplicated for independence)
# ---------------------------------------------------------------------------

def _make_llm_result(input_tokens: int = 100, output_tokens: int = 50) -> LLMResult:
    """Build a synthetic LLMResult with usage_metadata."""
    msg = AIMessage(content="Test response")
    msg.usage_metadata = {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
    }
    gen = ChatGeneration(message=msg)
    return LLMResult(generations=[[gen]])


def _make_serialized(model: str = "gpt-4.1-mini", provider: str = "openai") -> dict:
    """Build a synthetic serialized LLM dict."""
    return {
        "id": [f"langchain_{provider}", "chat_models", f"Chat{provider.capitalize()}"],
        "kwargs": {"model_name": model},
    }


def _flush_handler_threads(handler: Any, timeout: float = 2.0) -> None:
    """Join all background threads the handler launched (for test synchronisation)."""
    for t in list(handler._threads):
        t.join(timeout=timeout)


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def _set_metering_config(api_key: str = "rev_mk_test"):
    """Return a test config dict with metering fields set."""
    return {
        "revenium_api_key": api_key,
        "revenium_api_url": "https://api.revenium.ai",
        "revenium_organization_name": "Revenium-Research-Desk",
        "revenium_product_name": "trading-signal",
        "revenium_subscriber_id": "test@example.com",
    }


# ---------------------------------------------------------------------------
# (a) Tool-event test: one event per decorated tool call
# ---------------------------------------------------------------------------

class TestMeterToolEventFires:
    """@meter_tool fires exactly one tool event per call when a key is present."""

    @pytest.mark.unit
    def test_one_tool_event_per_call(self):
        """Decorated tool inside revenium_run_context fires exactly one tool event.

        RED: fails because no @meter_tool applied yet → _send_tool_event count = 0.
        GREEN: passes once @meter_tool("get_stock_data") is applied to core_stock_tools.py.
        """
        from tradingagents.revenium.context import (
            current_agent_name,
            revenium_run_context,
        )
        from tradingagents.dataflows.config import get_config, set_config

        config_orig = get_config()
        set_config(_set_metering_config())
        try:
            from tradingagents.agents.utils.core_stock_tools import get_stock_data

            with patch("revenium_metering.decorator._send_tool_event") as mock_send, \
                 patch(
                     "tradingagents.agents.utils.core_stock_tools.route_to_vendor"
                 ) as mock_route:
                mock_route.return_value = "mock OHLCV data"

                with revenium_run_context("NVDA", "2026-06-27") as trace_id:
                    current_agent_name.set("market_analyst")
                    result = get_stock_data.func("NVDA", "2026-01-01", "2026-06-27")

            assert mock_send.call_count == 1, (
                f"Expected exactly 1 tool event, got {mock_send.call_count}"
            )
            call_kwargs = mock_send.call_args.kwargs
            assert call_kwargs.get("tool_id") == "get_stock_data"
            assert result == "mock OHLCV data"
        finally:
            set_config(config_orig)

    @pytest.mark.unit
    def test_tool_event_carries_trace_id_and_agent(self):
        """Tool event context carries the active trace_id and agent from contextvars.

        RED: fails because no @meter_tool → mock_send never called.
        GREEN: passes once decorator applied.
        """
        from tradingagents.revenium.context import (
            current_agent_name,
            revenium_run_context,
        )
        from tradingagents.dataflows.config import get_config, set_config

        config_orig = get_config()
        set_config(_set_metering_config())
        try:
            from tradingagents.agents.utils.core_stock_tools import get_stock_data

            with patch("revenium_metering.decorator._send_tool_event") as mock_send, \
                 patch(
                     "tradingagents.agents.utils.core_stock_tools.route_to_vendor"
                 ) as mock_route:
                mock_route.return_value = "data"

                with revenium_run_context("AAPL", "2026-06-27") as trace_id:
                    current_agent_name.set("market_analyst")
                    get_stock_data.func("AAPL", "2026-01-01", "2026-06-27")

            assert mock_send.call_count == 1
            ctx = mock_send.call_args.kwargs.get("context")
            assert ctx is not None, "context must be passed to _send_tool_event"
            assert ctx.trace_id == trace_id, (
                f"trace_id mismatch: expected {trace_id!r}, got {ctx.trace_id!r}"
            )
            assert ctx.agent == "market_analyst", (
                f"agent mismatch: expected 'market_analyst', got {ctx.agent!r}"
            )
        finally:
            set_config(config_orig)


# ---------------------------------------------------------------------------
# (a-keyless) Keyless variant: zero events, identical return
# ---------------------------------------------------------------------------

class TestMeterToolKeylessNoop:
    """With no REVENIUM_METERING_API_KEY, the decorator is a transparent no-op."""

    @pytest.mark.unit
    def test_zero_tool_events_when_keyless(self):
        """No tool events are fired when api_key is empty.

        RED: should pass (no decorator → no events). Fails only if route_to_vendor mock wrong.
        GREEN: passes with correct mock path.
        """
        from tradingagents.revenium.context import revenium_run_context
        from tradingagents.dataflows.config import get_config, set_config

        config_orig = get_config()
        set_config({"revenium_api_key": ""})
        try:
            from tradingagents.agents.utils.core_stock_tools import get_stock_data

            with patch("revenium_metering.decorator._send_tool_event") as mock_send, \
                 patch(
                     "tradingagents.agents.utils.core_stock_tools.route_to_vendor"
                 ) as mock_route:
                mock_route.return_value = "real data"

                with revenium_run_context("NVDA", "2026-06-27"):
                    result = get_stock_data.func("NVDA", "2026-01-01", "2026-06-27")

            assert mock_send.call_count == 0, (
                f"Expected 0 tool events when keyless, got {mock_send.call_count}"
            )
            assert result == "real data", "Return value must be identical to undecorated"
        finally:
            set_config(config_orig)

    @pytest.mark.unit
    def test_keyless_tool_import_and_call_no_raise(self):
        """Decorated tool imports and executes without raising when key is absent."""
        from tradingagents.dataflows.config import get_config, set_config

        config_orig = get_config()
        set_config({"revenium_api_key": ""})
        try:
            from tradingagents.agents.utils.news_data_tools import get_news

            with patch(
                "tradingagents.agents.utils.news_data_tools.route_to_vendor"
            ) as mock_route:
                mock_route.return_value = "news data"
                result = get_news.func("NVDA", "2026-01-01", "2026-06-27")

            assert result == "news data"
        finally:
            set_config(config_orig)


# ---------------------------------------------------------------------------
# (b) Fail-open: metering failure does not block data fetch
# ---------------------------------------------------------------------------

class TestMeterToolFailOpen:
    """A metering failure inside @meter_tool must not block the data fetch."""

    @pytest.mark.unit
    def test_data_fetch_succeeds_when_metering_raises(self):
        """Data fetch returns its value even when _send_tool_event raises.

        RED: passes (no decorator → _send_tool_event never called → route_to_vendor mock returns).
        GREEN: passes (decorator applied; SDK raises but we catch and run func directly).
        """
        from tradingagents.revenium.context import revenium_run_context
        from tradingagents.dataflows.config import get_config, set_config

        config_orig = get_config()
        set_config(_set_metering_config())
        try:
            from tradingagents.agents.utils.core_stock_tools import get_stock_data

            with patch(
                "revenium_metering.decorator._send_tool_event",
                side_effect=RuntimeError("Revenium down"),
            ), patch(
                "tradingagents.agents.utils.core_stock_tools.route_to_vendor"
            ) as mock_route:
                mock_route.return_value = "stock data despite metering failure"

                with revenium_run_context("NVDA", "2026-06-27"):
                    result = get_stock_data.func("NVDA", "2026-01-01", "2026-06-27")

            assert result == "stock data despite metering failure", (
                "Tool must return data even when metering raises"
            )
        finally:
            set_config(config_orig)


# ---------------------------------------------------------------------------
# (d) Agent attribution: distinct agents → distinct event fields
# ---------------------------------------------------------------------------

class TestAgentAttribution:
    """Distinct current_agent_name values produce distinct agent+task_type in events.

    These tests drive the already-implemented callback handler from Plan 01-02.
    They pass in both RED and GREEN phases since no @meter_tool is involved.
    """

    @pytest.fixture
    def handler_with_mock_client(self):
        """Return a handler with captured payloads and full task_type_map."""
        from tradingagents.revenium.callback import ReveniumCallbackHandler

        captured: list[dict] = []
        mock_client = MagicMock()
        mock_client.meter_ai_completion.side_effect = lambda p: captured.append(p)

        handler = ReveniumCallbackHandler.from_config({
            "revenium_api_key": "rev_mk_test",
            "revenium_api_url": "https://api.revenium.ai",
            "revenium_organization_name": "Revenium-Research-Desk",
            "revenium_product_name": "trading-signal",
            "revenium_subscriber_id": "john.demic+trading@revenium.io",
            "revenium_task_type_map": {
                "market_analyst": "analysis",
                "sentiment_analyst": "analysis",
                "news_analyst": "analysis",
                "fundamentals_analyst": "analysis",
                "bull_researcher": "research_debate",
                "bear_researcher": "research_debate",
                "research_manager": "planning",
                "trader": "trade",
                "aggressive_debator": "risk_debate",
                "conservative_debator": "risk_debate",
                "neutral_debator": "risk_debate",
                "portfolio_manager": "decision",
            },
        })
        handler._client = mock_client
        return handler, captured

    @pytest.mark.unit
    def test_market_analyst_attribution(self, handler_with_mock_client):
        """market_analyst agent → agent='market_analyst', task_type='analysis'."""
        from tradingagents.revenium.context import current_agent_name, revenium_run_context

        handler, captured = handler_with_mock_client
        run_id = uuid.uuid4()

        with revenium_run_context("NVDA", "2026-06-27"):
            current_agent_name.set("market_analyst")
            handler.on_chat_model_start(_make_serialized(), [[]], run_id=run_id)
            handler.on_llm_end(_make_llm_result(), run_id=run_id)

        _flush_handler_threads(handler)
        assert len(captured) == 1
        p = captured[0]
        assert p.get("agent") == "market_analyst"
        assert p.get("task_type") == "analysis"

    @pytest.mark.unit
    def test_bull_researcher_attribution(self, handler_with_mock_client):
        """bull_researcher agent → agent='bull_researcher', task_type='research_debate'."""
        from tradingagents.revenium.context import current_agent_name, revenium_run_context

        handler, captured = handler_with_mock_client
        run_id = uuid.uuid4()

        with revenium_run_context("NVDA", "2026-06-27"):
            current_agent_name.set("bull_researcher")
            handler.on_chat_model_start(_make_serialized(), [[]], run_id=run_id)
            handler.on_llm_end(_make_llm_result(), run_id=run_id)

        _flush_handler_threads(handler)
        assert len(captured) == 1
        p = captured[0]
        assert p.get("agent") == "bull_researcher"
        assert p.get("task_type") == "research_debate"

    @pytest.mark.unit
    def test_two_distinct_agents_produce_distinct_events(self, handler_with_mock_client):
        """market_analyst and bull_researcher produce events with distinct agent+task_type."""
        from tradingagents.revenium.context import current_agent_name, revenium_run_context

        handler, captured = handler_with_mock_client

        with revenium_run_context("NVDA", "2026-06-27"):
            for agent in ("market_analyst", "bull_researcher"):
                run_id = uuid.uuid4()
                current_agent_name.set(agent)
                handler.on_chat_model_start(_make_serialized(), [[]], run_id=run_id)
                handler.on_llm_end(_make_llm_result(), run_id=run_id)

        _flush_handler_threads(handler)
        assert len(captured) == 2, f"Expected 2 events, got {len(captured)}"

        agents_seen = {p["agent"] for p in captured}
        task_types_seen = {p["task_type"] for p in captured}
        assert agents_seen == {"market_analyst", "bull_researcher"}
        assert task_types_seen == {"analysis", "research_debate"}

    @pytest.mark.unit
    def test_all_twelve_task_types_map_correctly(self, handler_with_mock_client):
        """All 12 node names resolve to the correct pipeline-stage task_type bucket."""
        from tradingagents.revenium.context import current_agent_name, revenium_run_context

        handler, captured = handler_with_mock_client

        expected = {
            "market_analyst": "analysis",
            "sentiment_analyst": "analysis",
            "news_analyst": "analysis",
            "fundamentals_analyst": "analysis",
            "bull_researcher": "research_debate",
            "bear_researcher": "research_debate",
            "research_manager": "planning",
            "trader": "trade",
            "aggressive_debator": "risk_debate",
            "conservative_debator": "risk_debate",
            "neutral_debator": "risk_debate",
            "portfolio_manager": "decision",
        }

        with revenium_run_context("NVDA", "2026-06-27"):
            for agent_name in expected:
                run_id = uuid.uuid4()
                current_agent_name.set(agent_name)
                handler.on_chat_model_start(_make_serialized(), [[]], run_id=run_id)
                handler.on_llm_end(_make_llm_result(), run_id=run_id)

        _flush_handler_threads(handler)
        assert len(captured) == 12

        actual_map = {p["agent"]: p["task_type"] for p in captured}
        for agent_name, expected_task_type in expected.items():
            assert actual_map.get(agent_name) == expected_task_type, (
                f"{agent_name}: expected task_type={expected_task_type!r}, "
                f"got {actual_map.get(agent_name)!r}"
            )
