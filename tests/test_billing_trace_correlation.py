"""Tool-metering events fire with the run's trace_id so tool cost correlates to
the Revenium Job (the CLI now opens revenium_run_context + create_trading_signal_job
around the stream, mirroring propagate()).

Before this, CLI runs produced tool events with a blank trace_id (no run context),
so tool cost could not be tied to any Job. This asserts that inside
revenium_run_context a metered tool event carries the same trace_id the Job is
created with. Uses a fully local @meter_tool mock — no network, no API keys beyond
a fake metering key so @meter_tool is not a no-op (DMO-04).
"""

from __future__ import annotations

from unittest.mock import patch

import pytest


@pytest.mark.unit
def test_tool_event_carries_run_trace_id_for_job_correlation():
    from tradingagents.agents.utils.agent_utils import get_edgehound_decision
    from tradingagents.dataflows.config import get_config, set_config
    from tradingagents.revenium.context import revenium_run_context

    orig = get_config()
    set_config({
        "revenium_api_key": "rev_mk_test",
        "revenium_api_url": "https://api.revenium.ai",
        "revenium_organization_name": "org",
        "revenium_product_name": "p",
        "revenium_subscriber_id": "s",
    })
    try:
        with (
            patch("revenium_metering.decorator._send_tool_event") as mock_send,
            revenium_run_context(ticker="NVDA", trade_date="2026-07-05") as trace_id,
        ):
            # Fully local metered tool — .func() passes through @meter_tool.
            get_edgehound_decision.func("test query")

        assert mock_send.call_count == 1
        ctx = mock_send.call_args.kwargs["context"]
        assert ctx.trace_id == trace_id, (
            f"tool event trace_id={ctx.trace_id!r} does not match the run trace_id "
            f"{trace_id!r} — tool cost would not correlate to the Job"
        )
        assert trace_id, "revenium_run_context must yield a non-empty trace_id"
    finally:
        set_config(orig)


@pytest.mark.unit
def test_run_context_resets_trace_id_after_exit():
    """The run trace_id must not bleed past the run (contextvar reset on exit)."""
    from tradingagents.revenium.context import current_trace_id, revenium_run_context

    assert current_trace_id.get() == ""  # default outside any run
    with revenium_run_context(ticker="NVDA", trade_date="2026-07-05") as trace_id:
        assert current_trace_id.get() == trace_id
    assert current_trace_id.get() == "", "trace_id must reset to default after the run"
