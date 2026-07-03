"""Unit tests for the Jentic-backed news tool (JEN-01, JEN-02, JEN-03).

All tests are @pytest.mark.unit and pass without a live JENTIC_AGENT_API_KEY
or network access.  Jentic SDK calls are mocked via patch("jentic.Jentic", ...)
targeting the SOURCE module attribute — the implementation lazy-imports
`from jentic import Jentic` INSIDE _do_jentic_news so patching the source
module namespace is correct (the lazy `from` import resolves jentic.Jentic
at call time, not at module load time).

Coverage:
- JEN-01: fail-soft sentinel when disabled; sentinel when keyless.
- JEN-01: async→sync bridge (_run_async) returns the coroutine result.
- JEN-02: @meter_tool fires exactly one Revenium tool event per execute()
  with the correct tool_id ("jentic_news") when op_id is pinned.
- JEN-01/JEN-02: fail-soft — Jentic execute() exception → NO_DATA_AVAILABLE,
  never propagates.

TDD RED: all five tests MUST fail before tradingagents/agents/utils/jentic_news_tools.py
is created (ImportError / ModuleNotFoundError on collection).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_exec_resp(success: bool = True, output=None, error=None, status_code: int = 200):
    """Build a synthetic ExecuteResponse mock."""
    r = MagicMock()
    r.success = success
    r.status_code = status_code
    r.output = output
    r.error = error
    return r


def _mock_jentic_client(exec_resp=None, exec_side_effect=None):
    """Return a MagicMock Jentic client with AsyncMock search/load/execute."""
    client = MagicMock()
    if exec_side_effect is not None:
        client.execute = AsyncMock(side_effect=exec_side_effect)
    else:
        client.execute = AsyncMock(return_value=exec_resp)
    client.search = AsyncMock()  # should not be called when op_id is pinned
    client.load = AsyncMock()    # should not be called for pinned flow
    return client


# ---------------------------------------------------------------------------
# Test 1: disabled config → sentinel, never touches SDK
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_jentic_tool_disabled_returns_sentinel():
    """jentic_tool_enabled=False → NO_DATA_AVAILABLE; Jentic is never constructed."""
    from tradingagents.agents.utils.jentic_news_tools import _jentic_news_impl
    from tradingagents.dataflows.config import get_config, set_config

    orig = get_config()
    set_config({"jentic_tool_enabled": False})
    try:
        with patch("jentic.Jentic") as mock_jentic_cls:
            result = _jentic_news_impl("NVDA news")
        assert result.startswith("NO_DATA_AVAILABLE"), (
            f"Expected NO_DATA_AVAILABLE sentinel, got: {result!r}"
        )
        mock_jentic_cls.assert_not_called()
    finally:
        set_config(orig)


# ---------------------------------------------------------------------------
# Test 2: enabled but keyless → sentinel, never touches SDK
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_jentic_tool_keyless_returns_sentinel():
    """jentic_tool_enabled=True but jentic_agent_api_key='' → NO_DATA_AVAILABLE; Jentic never constructed."""
    from tradingagents.agents.utils.jentic_news_tools import _jentic_news_impl
    from tradingagents.dataflows.config import get_config, set_config

    orig = get_config()
    set_config({"jentic_tool_enabled": True, "jentic_agent_api_key": ""})
    try:
        with patch("jentic.Jentic") as mock_jentic_cls:
            result = _jentic_news_impl("NVDA news")
        assert result.startswith("NO_DATA_AVAILABLE"), (
            f"Expected NO_DATA_AVAILABLE sentinel, got: {result!r}"
        )
        mock_jentic_cls.assert_not_called()
    finally:
        set_config(orig)


# ---------------------------------------------------------------------------
# Test 3: async→sync bridge works
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_jentic_async_bridge_returns_output():
    """_run_async() returns the coroutine result (bridge_ok) without error."""
    from tradingagents.agents.utils.jentic_news_tools import _run_async

    async def _coro():
        return "bridge_ok"

    assert _run_async(_coro()) == "bridge_ok"


# ---------------------------------------------------------------------------
# Test 4: meter event fires with correct tool_id
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_jentic_tool_fires_meter_event():
    """@meter_tool fires exactly one tool event per execute() call with tool_id=DEFAULT_CONFIG['jentic_tool_id'] (default 'jentic_news').

    Patches:
    - jentic.Jentic (source module) → mock client with execute returning success
    - revenium_metering.decorator._send_tool_event → captures the event call

    search must NOT be called (op_id is pinned in config).
    """
    from tradingagents.agents.utils.jentic_news_tools import get_jentic_news
    from tradingagents.dataflows.config import get_config, set_config

    exec_resp = _make_exec_resp(success=True, output="headline: NVDA surges")
    mock_client = _mock_jentic_client(exec_resp=exec_resp)

    orig = get_config()
    set_config({
        "jentic_tool_enabled": True,
        "jentic_agent_api_key": "ak_test",
        "jentic_op_id": "op_test123",
        "revenium_api_key": "rev_mk_test",
        "revenium_api_url": "https://api.revenium.ai",
        "revenium_organization_name": "Revenium-Research-Desk",
        "revenium_product_name": "trading-signal",
        "revenium_subscriber_id": "test@example.com",
    })
    try:
        with (
            patch("jentic.Jentic", return_value=mock_client),
            patch("revenium_metering.decorator._send_tool_event") as mock_send,
        ):
            result = get_jentic_news.func("NVDA latest news")

        # Exactly one tool event per call
        assert mock_send.call_count == 1, (
            f"Expected 1 Revenium tool event, got {mock_send.call_count}"
        )
        # tool_id must match the config value (single source of truth, L6) and
        # must NOT contain ':' — Revenium's Tools UI rejects colons.
        from tradingagents.default_config import DEFAULT_CONFIG
        expected_tool_id = DEFAULT_CONFIG["jentic_tool_id"]
        assert ":" not in expected_tool_id, (
            f"jentic_tool_id must not contain ':' (Revenium UI rejects it), got {expected_tool_id!r}"
        )
        assert mock_send.call_args.kwargs["tool_id"] == expected_tool_id, (
            f"Expected tool_id={expected_tool_id!r}, got {mock_send.call_args.kwargs.get('tool_id')!r}"
        )
        # Result must be a string (stringified output)
        assert isinstance(result, str), f"Expected str result, got {type(result)}"
        # search must NOT have been called (op_id is pinned)
        mock_client.search.assert_not_called()
    finally:
        set_config(orig)


# ---------------------------------------------------------------------------
# Test 5: execute() exception → fail-soft sentinel
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_jentic_tool_fail_soft_on_execute_error():
    """Jentic execute() raises → _jentic_news_impl returns NO_DATA_AVAILABLE, never raises."""
    from tradingagents.agents.utils.jentic_news_tools import _jentic_news_impl
    from tradingagents.dataflows.config import get_config, set_config

    mock_client = _mock_jentic_client(exec_side_effect=Exception("network timeout"))

    orig = get_config()
    set_config({
        "jentic_tool_enabled": True,
        "jentic_agent_api_key": "ak_test",
        "jentic_op_id": "op_test123",
    })
    try:
        with patch("jentic.Jentic", return_value=mock_client):
            result = _jentic_news_impl("NVDA news")
        assert result.startswith("NO_DATA_AVAILABLE"), (
            f"Expected NO_DATA_AVAILABLE sentinel after execute error, got: {result!r}"
        )
    finally:
        set_config(orig)
