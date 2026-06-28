"""Tests for the Revenium tracing slice — parent-chain, enrichment fields, and per-run reset.

All tests are unit-level (marker: unit) and pass without any live
REVENIUM_METERING_API_KEY.  All Revenium HTTP calls are mocked.

Key invariants validated:
- The first metered call in a run omits parent_transaction_id entirely.
- Each subsequent call carries parent_transaction_id equal to the prior call's transaction_id.
- Every payload carries transaction_name (== agent), trace_name (== "{ticker}-{date}"),
  and trace_type (== "trading-run") when emitted inside revenium_run_context.
- current_parent_transaction_id resets to "" on revenium_run_context exit (normal and exception).
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import AIMessage
from langchain_core.outputs import (
    ChatGeneration,
    LLMResult,
)

# ---------------------------------------------------------------------------
# ContextVar isolation — reset per-agent and per-trace contextvars before
# every test so ContextVar.set() calls in one test do not bleed into the next.
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_contextvars():
    """Isolate Revenium ContextVars across every test in this module."""
    from tradingagents.revenium.context import (
        current_agent_name,
        current_parent_transaction_id,
        current_run_meta,
        current_trace_id,
    )
    tok_agent = current_agent_name.set("unknown")
    tok_trace = current_trace_id.set("")
    tok_meta = current_run_meta.set({})
    tok_parent = current_parent_transaction_id.set("")
    yield
    current_agent_name.reset(tok_agent)
    current_trace_id.reset(tok_trace)
    current_run_meta.reset(tok_meta)
    current_parent_transaction_id.reset(tok_parent)


# ---------------------------------------------------------------------------
# Helpers (verbatim from test_revenium_metering.py for independence)
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
# Shared fixture — handler with mock client that captures payloads
# ---------------------------------------------------------------------------

@pytest.fixture
def handler_with_mock_client():
    """Return (handler, captured) where captured accumulates metered payloads."""
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
            "bull_researcher": "research_debate",
        },
        "revenium_trace_type": "trading-run",
    })
    handler._client = mock_client
    return handler, captured


# ---------------------------------------------------------------------------
# Tests: parent chain invariants
# ---------------------------------------------------------------------------

class TestParentTransactionChain:
    """Assert the parent_transaction_id chain is correct across sequential calls."""

    @pytest.mark.unit
    def test_first_call_has_no_parent_transaction_id(self, handler_with_mock_client):
        """The very first metered call of a run omits parent_transaction_id entirely."""
        from tradingagents.revenium.context import revenium_run_context

        handler, captured = handler_with_mock_client
        run_id = uuid.uuid4()

        with revenium_run_context("NVDA", "2026-06-27"):
            handler.on_chat_model_start(_make_serialized(), [[]], run_id=run_id)
            handler.on_llm_end(_make_llm_result(), run_id=run_id)

        _flush_handler_threads(handler)

        assert len(captured) == 1, "Expected exactly 1 payload"
        assert "parent_transaction_id" not in captured[0], (
            f"First call must not have parent_transaction_id; got: {captured[0].get('parent_transaction_id')}"
        )

    @pytest.mark.unit
    def test_sequential_chain_links_transaction_ids(self, handler_with_mock_client):
        """Each call's parent_transaction_id equals the prior call's transaction_id."""
        from tradingagents.revenium.context import revenium_run_context

        handler, captured = handler_with_mock_client
        serialized = _make_serialized()

        with revenium_run_context("NVDA", "2026-06-27"):
            for _ in range(3):
                run_id = uuid.uuid4()
                handler.on_chat_model_start(serialized, [[]], run_id=run_id)
                handler.on_llm_end(_make_llm_result(), run_id=run_id)

        _flush_handler_threads(handler)

        assert len(captured) == 3, f"Expected 3 payloads, got {len(captured)}"

        # First call: no parent
        assert "parent_transaction_id" not in captured[0], (
            "First call must not have parent_transaction_id"
        )
        # Second call: parent == first call's transaction_id
        assert captured[1]["parent_transaction_id"] == captured[0]["transaction_id"], (
            f"captured[1].parent_transaction_id={captured[1].get('parent_transaction_id')!r} "
            f"!= captured[0].transaction_id={captured[0].get('transaction_id')!r}"
        )
        # Third call: parent == second call's transaction_id
        assert captured[2]["parent_transaction_id"] == captured[1]["transaction_id"], (
            f"captured[2].parent_transaction_id={captured[2].get('parent_transaction_id')!r} "
            f"!= captured[1].transaction_id={captured[1].get('transaction_id')!r}"
        )


# ---------------------------------------------------------------------------
# Tests: enrichment fields
# ---------------------------------------------------------------------------

class TestTraceEnrichmentFields:
    """Assert trace_name, trace_type, and transaction_name are present on payloads."""

    @pytest.mark.unit
    def test_transaction_name_equals_agent(self, handler_with_mock_client):
        """Every payload carries transaction_name equal to the agent field."""
        from tradingagents.revenium.context import current_agent_name, revenium_run_context

        handler, captured = handler_with_mock_client

        agents = ["market_analyst", "bull_researcher"]
        with revenium_run_context("NVDA", "2026-06-27"):
            for agent_name in agents:
                run_id = uuid.uuid4()
                current_agent_name.set(agent_name)
                handler.on_chat_model_start(_make_serialized(), [[]], run_id=run_id)
                handler.on_llm_end(_make_llm_result(), run_id=run_id)

        _flush_handler_threads(handler)

        assert len(captured) == 2
        for i, agent_name in enumerate(agents):
            assert captured[i]["transaction_name"] == agent_name, (
                f"captured[{i}].transaction_name={captured[i].get('transaction_name')!r} "
                f"!= {agent_name!r}"
            )
            # Also confirm it matches the agent field
            assert captured[i]["transaction_name"] == captured[i]["agent"]

    @pytest.mark.unit
    def test_trace_name_and_trace_type_in_payload(self, handler_with_mock_client):
        """Payloads carry trace_name == '{ticker}-{date}' and trace_type == 'trading-run'."""
        from tradingagents.revenium.context import revenium_run_context

        handler, captured = handler_with_mock_client
        run_id = uuid.uuid4()
        ticker = "NVDA"
        trade_date = "2026-06-27"

        with revenium_run_context(ticker, trade_date):
            handler.on_chat_model_start(_make_serialized(), [[]], run_id=run_id)
            handler.on_llm_end(_make_llm_result(), run_id=run_id)

        _flush_handler_threads(handler)

        assert len(captured) == 1
        payload = captured[0]
        assert payload.get("trace_name") == f"{ticker}-{trade_date}", (
            f"trace_name={payload.get('trace_name')!r} != {ticker!r}-{trade_date!r}"
        )
        assert payload.get("trace_type") == "trading-run", (
            f"trace_type={payload.get('trace_type')!r} != 'trading-run'"
        )

    @pytest.mark.unit
    def test_trace_name_absent_outside_run_context(self, handler_with_mock_client):
        """trace_name is absent (not sent) when there is no active revenium_run_context."""
        handler, captured = handler_with_mock_client
        run_id = uuid.uuid4()

        # Call outside any revenium_run_context — no ticker available
        handler.on_chat_model_start(_make_serialized(), [[]], run_id=run_id)
        handler.on_llm_end(_make_llm_result(), run_id=run_id)

        _flush_handler_threads(handler)

        assert len(captured) == 1
        assert "trace_name" not in captured[0], (
            "trace_name must be absent when ticker is empty"
        )


# ---------------------------------------------------------------------------
# Tests: per-run reset of current_parent_transaction_id
# ---------------------------------------------------------------------------

class TestParentTransactionIdReset:
    """Assert current_parent_transaction_id resets correctly across run boundaries."""

    @pytest.mark.unit
    def test_parent_tid_is_empty_before_context(self):
        """current_parent_transaction_id is '' before any revenium_run_context."""
        from tradingagents.revenium.context import current_parent_transaction_id

        assert current_parent_transaction_id.get() == "", (
            "parent_transaction_id must be '' outside any run context"
        )

    @pytest.mark.unit
    def test_parent_tid_resets_to_empty_after_context(self, handler_with_mock_client):
        """current_parent_transaction_id is '' after revenium_run_context exits normally."""
        from tradingagents.revenium.context import (
            current_parent_transaction_id,
            revenium_run_context,
        )

        handler, captured = handler_with_mock_client
        run_id = uuid.uuid4()

        assert current_parent_transaction_id.get() == "", "'' before context"

        with revenium_run_context("NVDA", "2026-06-27"):
            handler.on_chat_model_start(_make_serialized(), [[]], run_id=run_id)
            handler.on_llm_end(_make_llm_result(), run_id=run_id)
            _flush_handler_threads(handler)
            # After first on_llm_end, the contextvar is non-empty
            assert current_parent_transaction_id.get() != "", (
                "parent_transaction_id must be non-empty after first on_llm_end"
            )

        # After context exit it must be reset to ""
        assert current_parent_transaction_id.get() == "", (
            "parent_transaction_id must be '' after revenium_run_context exits"
        )

    @pytest.mark.unit
    def test_parent_tid_resets_to_empty_after_exception(self):
        """current_parent_transaction_id is '' even when an exception propagates through the context."""
        from tradingagents.revenium.context import (
            current_parent_transaction_id,
            revenium_run_context,
        )

        with pytest.raises(ValueError), revenium_run_context("NVDA", "2026-06-27"):
            raise ValueError("deliberate error")

        assert current_parent_transaction_id.get() == "", (
            "parent_transaction_id must be '' after exception in revenium_run_context"
        )
