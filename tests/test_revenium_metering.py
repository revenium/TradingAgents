"""Tests for the Revenium metering slice — context, client, and callback handler.

All tests are unit-level (marker: unit) and pass without any live
REVENIUM_METERING_API_KEY.  All Revenium HTTP calls are mocked.

Design:
- Tests for context.py and client.py are in their own classes (added during
  Task 1 of plan 01-02).
- Tests for callback.py are in their own class (added during Task 2).
- The comprehensive one-event invariant and attribution tests (Task 4) combine
  all three modules and assert the 1:1 event-per-call invariant, attribution
  field presence, and keyless no-op behaviour.

Key invariants validated:
- Exactly ONE meter_ai_completion call per on_llm_end (no double-counting).
- Every payload carries organizationName, productName, subscriber.id.
- The handler is a silent no-op when REVENIUM_METERING_API_KEY is absent.
- A client exception inside on_llm_end is swallowed and never propagates.
"""

from __future__ import annotations

import threading
import uuid
from datetime import datetime
from typing import Any
from unittest.mock import MagicMock, patch

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


def _flush_handler_threads(handler: Any, timeout: float = 2.0) -> None:
    """Join all background threads the handler launched (for test synchronisation)."""
    for t in list(handler._threads):
        t.join(timeout=timeout)


# ---------------------------------------------------------------------------
# Task 1 tests: tradingagents/revenium/context.py
# ---------------------------------------------------------------------------

class TestReveniumRunContext:
    """Verify the contextvar machinery set/reset lifecycle."""

    @pytest.mark.unit
    def test_trace_id_is_set_and_reset(self):
        """revenium_run_context sets a non-empty trace_id and resets it on exit."""
        from tradingagents.revenium.context import current_trace_id, revenium_run_context

        assert current_trace_id.get() == "", "trace_id should be empty before context"
        with revenium_run_context("NVDA", "2026-06-27") as tid:
            assert len(tid) == 36, "trace_id should be a uuid4 string (36 chars)"
            assert current_trace_id.get() == tid
        assert current_trace_id.get() == "", "trace_id should be reset to '' after context"

    @pytest.mark.unit
    def test_run_meta_is_set_and_reset(self):
        """revenium_run_context sets run_meta with ticker+trade_date and resets on exit."""
        from tradingagents.revenium.context import current_run_meta, revenium_run_context

        assert current_run_meta.get() == {}
        with revenium_run_context("AAPL", "2026-06-27") as _:
            meta = current_run_meta.get()
            assert meta["ticker"] == "AAPL"
            assert meta["trade_date"] == "2026-06-27"
        assert current_run_meta.get() == {}

    @pytest.mark.unit
    def test_extra_kwargs_forwarded_to_meta(self):
        """Keyword arguments to revenium_run_context appear in current_run_meta."""
        from tradingagents.revenium.context import current_run_meta, revenium_run_context

        with revenium_run_context("TSLA", "2026-06-27", extra_key="extra_value") as _:
            meta = current_run_meta.get()
            assert meta.get("extra_key") == "extra_value"

    @pytest.mark.unit
    def test_agent_name_defaults_to_unknown(self):
        """current_agent_name defaults to 'unknown' without an explicit set."""
        from tradingagents.revenium.context import current_agent_name

        assert current_agent_name.get() == "unknown"

    @pytest.mark.unit
    def test_trace_id_reset_even_on_exception(self):
        """trace_id is reset even when an exception is raised inside the context."""
        from tradingagents.revenium.context import current_trace_id, revenium_run_context

        with pytest.raises(ValueError):
            with revenium_run_context("NVDA", "2026-06-27"):
                raise ValueError("deliberate error")
        assert current_trace_id.get() == ""


# ---------------------------------------------------------------------------
# Task 1 tests: tradingagents/revenium/client.py
# ---------------------------------------------------------------------------

class TestReveniumClient:
    """Verify fail-open semantics and disabled-state behaviour of ReveniumClient."""

    @pytest.mark.unit
    def test_disabled_when_api_key_empty(self):
        """ReveniumClient.enabled is False when api_key is an empty string."""
        from tradingagents.revenium.client import ReveniumClient

        c = ReveniumClient(api_key="", api_url="https://api.revenium.ai")
        assert c.enabled is False

    @pytest.mark.unit
    def test_meter_ai_completion_noop_when_disabled(self):
        """meter_ai_completion returns None without raising when disabled."""
        from tradingagents.revenium.client import ReveniumClient

        c = ReveniumClient(api_key="", api_url="https://api.revenium.ai")
        result = c.meter_ai_completion({"agent": "test_agent"})
        assert result is None

    @pytest.mark.unit
    def test_imports_cleanly_without_key(self):
        """Module imports without crashing when REVENIUM_METERING_API_KEY is absent."""
        import tradingagents.revenium.client  # noqa: F401
        import tradingagents.revenium.context  # noqa: F401

    @pytest.mark.unit
    def test_sdk_exception_is_swallowed(self):
        """meter_ai_completion does NOT raise when the underlying SDK raises."""
        from tradingagents.revenium.client import ReveniumClient

        c = ReveniumClient(api_key="fake_key", api_url="https://api.revenium.ai")
        # Force _sdk_client to a mock that raises on create_completion
        mock_sdk = MagicMock()
        mock_sdk.ai.create_completion.side_effect = RuntimeError("network error")
        c._sdk_client = mock_sdk

        # Should not raise — fail-open
        result = c.meter_ai_completion({"agent": "test_agent"})
        assert result is None


# ---------------------------------------------------------------------------
# Task 2 tests: tradingagents/revenium/callback.py
# ---------------------------------------------------------------------------

class TestReveniumCallbackHandlerBasic:
    """Basic construction, enabled/disabled, and import tests."""

    @pytest.mark.unit
    def test_disabled_when_no_key(self):
        """from_config with empty api_key gives enabled=False."""
        from tradingagents.revenium.callback import ReveniumCallbackHandler

        handler = ReveniumCallbackHandler.from_config({"revenium_api_key": ""})
        assert handler.enabled is False

    @pytest.mark.unit
    def test_importable_from_package(self):
        """ReveniumCallbackHandler is re-exported from tradingagents.revenium."""
        from tradingagents.revenium import ReveniumCallbackHandler  # noqa: F401

    @pytest.mark.unit
    def test_on_llm_end_disabled_does_not_raise(self):
        """on_llm_end on a disabled handler makes zero client calls and does not raise."""
        from tradingagents.revenium.callback import ReveniumCallbackHandler

        handler = ReveniumCallbackHandler.from_config({"revenium_api_key": ""})
        result = handler.on_llm_end(_make_llm_result(), run_id=uuid.uuid4())
        assert result is None  # must not raise


# ---------------------------------------------------------------------------
# Task 4 tests: comprehensive invariants
# ---------------------------------------------------------------------------

class TestOneEventPerCallInvariant:
    """Assert exactly ONE meter_ai_completion call per on_llm_end (no double-counting)."""

    @pytest.mark.unit
    def test_one_event_per_llm_end(self):
        """N on_chat_model_start/on_llm_end pairs produce exactly N meter calls."""
        from tradingagents.revenium.callback import ReveniumCallbackHandler
        from tradingagents.revenium.context import revenium_run_context

        mock_client = MagicMock()

        handler = ReveniumCallbackHandler.from_config({
            "revenium_api_key": "rev_mk_test",
            "revenium_api_url": "https://api.revenium.ai",
            "revenium_organization_name": "Test-Org",
            "revenium_product_name": "test-product",
            "revenium_subscriber_id": "test@example.com",
        })
        handler._client = mock_client

        n_calls = 5
        serialized = _make_serialized()

        with revenium_run_context("NVDA", "2026-06-27"):
            for _ in range(n_calls):
                run_id = uuid.uuid4()
                handler.on_chat_model_start(serialized, [[]], run_id=run_id)
                handler.on_llm_end(_make_llm_result(), run_id=run_id)

        _flush_handler_threads(handler)

        assert mock_client.meter_ai_completion.call_count == n_calls, (
            f"Expected {n_calls} calls, got {mock_client.meter_ai_completion.call_count}"
        )

    @pytest.mark.unit
    def test_no_double_counting_across_calls(self):
        """Two sequential LLM calls produce exactly 2 events, not 4 (dedup guard)."""
        from tradingagents.revenium.callback import ReveniumCallbackHandler
        from tradingagents.revenium.context import revenium_run_context

        mock_client = MagicMock()
        handler = ReveniumCallbackHandler.from_config({
            "revenium_api_key": "rev_mk_test",
            "revenium_api_url": "https://api.revenium.ai",
            "revenium_organization_name": "Test-Org",
            "revenium_product_name": "test-product",
            "revenium_subscriber_id": "test@example.com",
        })
        handler._client = mock_client

        with revenium_run_context("AAPL", "2026-06-27"):
            for _ in range(2):
                run_id = uuid.uuid4()
                handler.on_chat_model_start(_make_serialized(), [[]], run_id=run_id)
                handler.on_llm_end(_make_llm_result(), run_id=run_id)

        _flush_handler_threads(handler)
        assert mock_client.meter_ai_completion.call_count == 2


class TestMeteringEventAttribution:
    """Assert every payload carries the required attribution and identity fields."""

    @pytest.fixture
    def handler_with_mock_client(self):
        """Return a handler with a mock client that captures payloads."""
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
                "bull_researcher": "research_debate",
                "market_analyst": "analysis",
            },
        })
        handler._client = mock_client
        return handler, captured

    @pytest.mark.unit
    def test_attribution_fields_in_payload(self, handler_with_mock_client):
        """Payload carries non-empty organizationName, productName, subscriber.id."""
        from tradingagents.revenium.context import current_agent_name, revenium_run_context

        handler, captured = handler_with_mock_client
        run_id = uuid.uuid4()

        with revenium_run_context("NVDA", "2026-06-27"):
            current_agent_name.set("bull_researcher")
            handler.on_chat_model_start(_make_serialized(), [[]], run_id=run_id)
            handler.on_llm_end(_make_llm_result(100, 50), run_id=run_id)

        _flush_handler_threads(handler)
        assert len(captured) == 1, "Expected exactly 1 captured payload"
        payload = captured[0]

        assert payload.get("organization_name") == "Revenium-Research-Desk"
        assert payload.get("product_name") == "trading-signal"
        sub = payload.get("subscriber", {})
        assert sub.get("id") == "john.demic+trading@revenium.io" or \
               sub.get("email") == "john.demic+trading@revenium.io", \
               f"subscriber must carry the subscriber_id; got: {sub}"

    @pytest.mark.unit
    def test_agent_and_trace_id_in_payload(self, handler_with_mock_client):
        """Payload carries agent name and trace_id from contextvar."""
        from tradingagents.revenium.context import current_agent_name, revenium_run_context

        handler, captured = handler_with_mock_client
        run_id = uuid.uuid4()

        with revenium_run_context("NVDA", "2026-06-27") as expected_trace:
            current_agent_name.set("market_analyst")
            handler.on_chat_model_start(_make_serialized(), [[]], run_id=run_id)
            handler.on_llm_end(_make_llm_result(), run_id=run_id)

        _flush_handler_threads(handler)
        assert len(captured) == 1
        payload = captured[0]

        assert payload.get("agent") == "market_analyst"
        assert payload.get("trace_id") == expected_trace

    @pytest.mark.unit
    def test_task_type_mapped_from_agent_name(self, handler_with_mock_client):
        """task_type is derived from agent name via revenium_task_type_map."""
        from tradingagents.revenium.context import current_agent_name, revenium_run_context

        handler, captured = handler_with_mock_client
        run_id = uuid.uuid4()

        with revenium_run_context("NVDA", "2026-06-27"):
            current_agent_name.set("bull_researcher")
            handler.on_chat_model_start(_make_serialized(), [[]], run_id=run_id)
            handler.on_llm_end(_make_llm_result(), run_id=run_id)

        _flush_handler_threads(handler)
        payload = captured[0]
        assert payload.get("task_type") == "research_debate"

    @pytest.mark.unit
    def test_non_zero_token_counts(self, handler_with_mock_client):
        """Payload carries non-zero input/output token counts when usage_metadata present."""
        from tradingagents.revenium.context import revenium_run_context

        handler, captured = handler_with_mock_client
        run_id = uuid.uuid4()

        with revenium_run_context("NVDA", "2026-06-27"):
            handler.on_chat_model_start(_make_serialized(), [[]], run_id=run_id)
            handler.on_llm_end(_make_llm_result(input_tokens=123, output_tokens=77), run_id=run_id)

        _flush_handler_threads(handler)
        payload = captured[0]
        assert payload.get("input_token_count", 0) == 123
        assert payload.get("output_token_count", 0) == 77
        assert payload.get("total_token_count", 0) == 200

    @pytest.mark.unit
    def test_sdk_exception_in_on_llm_end_does_not_propagate(self, handler_with_mock_client):
        """A client exception inside on_llm_end is swallowed — handler never raises."""
        from tradingagents.revenium.context import revenium_run_context

        handler, _ = handler_with_mock_client
        # Override mock to raise on every call
        handler._client.meter_ai_completion.side_effect = RuntimeError("backend down")
        run_id = uuid.uuid4()

        with revenium_run_context("NVDA", "2026-06-27"):
            handler.on_chat_model_start(_make_serialized(), [[]], run_id=run_id)
            # Must not raise even though the client will fail
            handler.on_llm_end(_make_llm_result(), run_id=run_id)

        _flush_handler_threads(handler)  # threads may log warnings but not raise
