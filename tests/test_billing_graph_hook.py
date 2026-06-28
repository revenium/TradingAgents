"""Keyless placement tests for billing hooks in TradingAgentsGraph._run_graph (BIL-01, D-09, D-10).

All tests pass without any live REVENIUM_BILLING_API_KEY, REVENIUM_METERING_API_KEY,
or LLM provider API keys.  All Revenium and graph calls are mocked.

Key invariants validated:
- On a successful run (graph delivers a final_state), ``emit_billing_event`` is called
  exactly once with ``signal_price == config["revenium_signal_price"]`` (D-09).
- On a ``BudgetExceededError``-halted run, ``emit_billing_event`` is NOT called (D-10).
  ``BudgetExceededError`` propagates from ``graph.invoke()`` before the emit line is
  reached, so halted runs are structurally non-billable — no conditional needed.
- ``create_trading_signal_job`` is called once in both success and halt paths
  (the job is opened at run start, immediately after ``begin_run``).
- ``end_run`` always fires in the ``finally`` block regardless of graph outcome,
  preserving the fail-open posture.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from revenium_middleware._core.exceptions import BudgetExceededError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_fake_final_state() -> dict:
    """Build a minimal final_state that satisfies _run_graph's post-invoke field reads."""
    return {
        "final_trade_decision": "BUY - NVDA signals strong momentum.",
        "company_of_interest": "NVDA",
        "trade_date": "2026-06-28",
        "market_report": "",
        "sentiment_report": "",
        "news_report": "",
        "fundamentals_report": "",
        "investment_debate_state": {
            "bull_history": [],
            "bear_history": [],
            "history": [],
            "current_response": "",
            "judge_decision": "",
        },
        "risk_debate_state": {
            "aggressive_history": [],
            "conservative_history": [],
            "neutral_history": [],
            "history": [],
            "judge_decision": "",
        },
        "trader_investment_plan": "",
        "investment_plan": "",
    }


# ---------------------------------------------------------------------------
# Fixture: minimal TradingAgentsGraph with all I/O-heavy attributes mocked
# ---------------------------------------------------------------------------

@pytest.fixture
def graph(monkeypatch):
    """Return a TradingAgentsGraph with all I/O-heavy attributes replaced by MagicMocks.

    ``__init__`` is bypassed so no LLM client construction, no yfinance calls, no
    filesystem I/O, and no Revenium API keys are required.  The attributes set here
    are the minimal seam that ``_run_graph`` needs in order to execute its full
    try/finally control flow.

    ``_billing_emitter`` and ``_revenium_handler`` are plain MagicMocks by default;
    individual tests configure their return values / side_effects as needed.
    """
    from tradingagents.graph.trading_graph import TradingAgentsGraph
    from tradingagents.default_config import DEFAULT_CONFIG

    def _fake_init(self, *args, **kwargs):
        self.debug = False
        self.config = dict(DEFAULT_CONFIG)
        # Disable checkpoint to keep _run_graph simpler (no SqliteSaver setup).
        self.config["checkpoint_enabled"] = False
        self._revenium_handler = MagicMock()
        self._billing_emitter = MagicMock()
        self.memory_log = MagicMock()
        self.memory_log.get_past_context.return_value = ""
        self.propagator = MagicMock()
        self.propagator.create_initial_state.return_value = {}
        self.propagator.get_graph_args.return_value = {}
        self.graph = MagicMock()
        self.signal_processor = MagicMock()
        self.signal_processor.process_signal.return_value = "BUY"
        self.ticker = "NVDA"
        self.log_states_dict = {}

    monkeypatch.setattr(TradingAgentsGraph, "__init__", _fake_init)
    instance = TradingAgentsGraph()

    # Patch instance methods that perform filesystem / network I/O so _run_graph
    # exercises only the control-flow paths under test.
    instance.resolve_instrument_context = MagicMock(return_value="NVDA is a chip company.")
    instance._log_state = MagicMock()
    instance.process_signal = MagicMock(return_value="BUY")

    return instance


# ---------------------------------------------------------------------------
# Test A: success path — emit_billing_event called exactly once with signal_price
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_billing_emit_once_on_success(graph, monkeypatch):
    """On a successful graph run, emit_billing_event is called exactly once.

    Verifies D-09: the billing event is emitted after graph.invoke() returns
    (inside the ``try`` block, before ``return``) with ``signal_price`` sourced
    from ``config["revenium_signal_price"]``.

    Also confirms that ``create_trading_signal_job`` is called once at run start
    and ``end_run`` fires in the ``finally`` block.
    """
    monkeypatch.setattr(
        "tradingagents.graph.trading_graph.stop_polling",
        MagicMock(),
    )

    graph.graph.invoke.return_value = _make_fake_final_state()

    graph._run_graph("NVDA", "2026-06-28")

    # Job must be created once at run start (after begin_run, before graph.invoke).
    graph._billing_emitter.create_trading_signal_job.assert_called_once()

    # Billing event must be emitted exactly once on the success path.
    graph._billing_emitter.emit_billing_event.assert_called_once()

    emit_call = graph._billing_emitter.emit_billing_event.call_args
    expected_price = graph.config["revenium_signal_price"]
    actual_price = emit_call.kwargs["signal_price"]
    assert actual_price == expected_price, (
        f"signal_price mismatch: got {actual_price!r}, expected {expected_price!r}"
    )

    # end_run must always fire in the finally block.
    graph._revenium_handler.end_run.assert_called_once()


# ---------------------------------------------------------------------------
# Test B: BudgetExceededError halt path — NO emit_billing_event; end_run fires
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_no_billing_emit_on_budget_exceeded_error(graph, monkeypatch):
    """On BudgetExceededError from graph.invoke, emit_billing_event is NOT called.

    Verifies D-10: ``BudgetExceededError`` raised inside ``graph.invoke()`` propagates
    before the ``emit_billing_event`` call is reached.  The billing emit is therefore
    structurally unreachable on the halt path — no conditional guard is needed.

    ``create_trading_signal_job`` is still called (job was opened before graph.invoke)
    and ``end_run`` still fires unconditionally in the ``finally`` block.
    """
    monkeypatch.setattr(
        "tradingagents.graph.trading_graph.stop_polling",
        MagicMock(),
    )

    # Simulate a circuit-breaker halt inside graph.invoke().
    graph.graph.invoke.side_effect = BudgetExceededError("budget exceeded — halted")

    with pytest.raises(BudgetExceededError):
        graph._run_graph("NVDA", "2026-06-28")

    # Job was created at run start (before graph.invoke raised).
    graph._billing_emitter.create_trading_signal_job.assert_called_once()

    # Billing event MUST NOT be emitted on the halt path (D-10).
    graph._billing_emitter.emit_billing_event.assert_not_called()

    # end_run MUST always fire (finally block is unconditional).
    graph._revenium_handler.end_run.assert_called_once()
