"""Keyless unit tests for TradingSignalBillingEmitter (BIL-01, DMO-04).

All tests pass without any live REVENIUM_BILLING_API_KEY.  Revenium SDK calls
are mocked via MagicMock injection; no network I/O occurs.

Key invariants validated:
- ``DEFAULT_CONFIG["revenium_signal_price"]`` is a float (Pitfall 5).
- ``TRADINGAGENTS_SIGNAL_PRICE`` env override coerces to the correct float.
- Emitter with empty api_key has ``enabled is False``; both public methods are
  no-ops (no thread spawned, no exception raised).
- Emitter with a fake key and a mocked AgenticOutcomeClient calls
  ``create_job`` with ``agentic_job_id == trace_id`` and ``report_outcome``
  with a payload whose ``outcomeValue`` equals the configured price,
  ``executionStatus == "SUCCESS"`` (not ``result``), and ``metadata`` is a
  JSON string that round-trips to a dict with ``ticker`` and ``trade_date``.
- When the mock client raises, both public methods still return ``None`` and
  do not propagate the exception.
"""

from __future__ import annotations

import importlib
import json
import threading
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helper: build an emitter with an injected mock client
# ---------------------------------------------------------------------------

def _make_emitter_with_mock_client(
    api_key: str = "rev_sk_test_fake",
    profitstream_base_url: str = "https://api.revenium.io",
    subscriber_id: str = "test@example.com",
) -> tuple[Any, MagicMock]:
    """Return (emitter, mock_client) with the AgenticOutcomeClient patched."""
    from tradingagents.revenium.billing import TradingSignalBillingEmitter

    mock_client = MagicMock()
    mock_settings_cls = MagicMock()
    mock_client_cls = MagicMock(return_value=mock_client)

    with patch.dict(
        "sys.modules",
        {
            "revenium_middleware.agentic_outcomes": MagicMock(
                AgenticOutcomeClient=mock_client_cls,
                AgenticOutcomeSettings=mock_settings_cls,
            )
        },
    ):
        emitter = TradingSignalBillingEmitter(
            api_key=api_key,
            profitstream_base_url=profitstream_base_url,
            subscriber_id=subscriber_id,
        )

    return emitter, mock_client


# ---------------------------------------------------------------------------
# Helpers for deterministic background-thread assertions
# ---------------------------------------------------------------------------

def _collect_threads_for(emitter: Any, fn, *args, **kwargs) -> None:
    """Call ``fn(*args, **kwargs)`` and join all daemon threads spawned by it."""
    before = {t.name for t in threading.enumerate()}
    fn(*args, **kwargs)
    after = threading.enumerate()
    # Join any threads whose names start with "rev-billing-" spawned by fn
    for t in after:
        if t.name.startswith("rev-billing-") and t.name not in before:
            t.join(timeout=5.0)


# ---------------------------------------------------------------------------
# (a) revenium_signal_price is a float; env override coerces correctly
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_signal_price_default_is_float(monkeypatch):
    """DEFAULT_CONFIG['revenium_signal_price'] is a float equal to 2.00 (Pitfall 5)."""
    import tradingagents.default_config as dc_mod

    # Clear all _ENV_OVERRIDES env vars to avoid cross-test contamination.
    for var in dc_mod._ENV_OVERRIDES:
        monkeypatch.delenv(var, raising=False)

    dc = importlib.reload(dc_mod)
    price = dc.DEFAULT_CONFIG["revenium_signal_price"]
    assert isinstance(price, float), f"expected float, got {type(price)}"
    assert price == 2.00


@pytest.mark.unit
def test_signal_price_env_override_coerces_to_float(monkeypatch):
    """TRADINGAGENTS_SIGNAL_PRICE=3.5 overrides and coerces to float 3.5."""
    import tradingagents.default_config as dc_mod

    for var in dc_mod._ENV_OVERRIDES:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("TRADINGAGENTS_SIGNAL_PRICE", "3.5")

    dc = importlib.reload(dc_mod)
    price = dc.DEFAULT_CONFIG["revenium_signal_price"]
    assert isinstance(price, float), f"expected float, got {type(price)}"
    assert price == 3.5


# ---------------------------------------------------------------------------
# (b) Emitter with empty api_key is disabled and both methods are no-ops
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_emitter_disabled_when_no_api_key():
    """Emitter with empty api_key has enabled==False and both methods are no-ops."""
    from tradingagents.revenium.billing import TradingSignalBillingEmitter

    emitter = TradingSignalBillingEmitter(api_key="")
    assert emitter.enabled is False

    threads_before = {t.ident for t in threading.enumerate()}

    # Both methods must return None without spawning any threads or raising.
    result_create = emitter.create_trading_signal_job("trace-abc", "NVDA", "2026-06-28")
    result_emit = emitter.emit_billing_event("trace-abc", 2.00)

    threads_after = {t.ident for t in threading.enumerate()}

    assert result_create is None
    assert result_emit is None
    assert threads_after == threads_before, "no new threads should have been spawned"


@pytest.mark.unit
def test_from_config_disabled_when_no_billing_key():
    """from_config with empty keys (both revenium_sk_api_key and legacy alias) yields disabled emitter."""
    from tradingagents.revenium.billing import TradingSignalBillingEmitter

    config = {
        "revenium_sk_api_key": "",
        "revenium_billing_api_key": "",
        "revenium_profitstream_url": "https://api.revenium.io",
    }
    emitter = TradingSignalBillingEmitter.from_config(config)
    assert emitter.enabled is False


@pytest.mark.unit
def test_from_config_enabled_with_sk_api_key():
    """from_config with revenium_sk_api_key set yields enabled emitter (GAP-04-LINK)."""
    from tradingagents.revenium.billing import TradingSignalBillingEmitter

    mock_settings_cls = MagicMock()
    mock_client_cls = MagicMock(return_value=MagicMock())

    config = {
        "revenium_sk_api_key": "rev_sk_x",
        "revenium_profitstream_url": "https://api.prod.ai.hcapp.io",
        "revenium_team_id": "T1",
    }

    with patch.dict(
        "sys.modules",
        {
            "revenium_middleware.agentic_outcomes": MagicMock(
                AgenticOutcomeClient=mock_client_cls,
                AgenticOutcomeSettings=mock_settings_cls,
            )
        },
    ):
        emitter = TradingSignalBillingEmitter.from_config(config)

    assert emitter.enabled is True, (
        "from_config with revenium_sk_api_key='rev_sk_x' must yield enabled=True"
    )


# ---------------------------------------------------------------------------
# (c) Mocked client: create_job called with agentic_job_id==trace_id;
#     report_outcome called with outcomeValue==price and result=="SUCCESS"
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_create_job_called_with_trace_id():
    """create_trading_signal_job dispatches create_job(trace_id, ...) on background thread."""
    emitter, mock_client = _make_emitter_with_mock_client()
    assert emitter.enabled is True

    trace_id = "test-trace-001"
    _collect_threads_for(
        emitter,
        emitter.create_trading_signal_job,
        trace_id,
        "NVDA",
        "2026-06-28",
    )

    mock_client.create_job.assert_called_once()
    call_args = mock_client.create_job.call_args
    # create_job(agentic_job_id, name=..., type=..., environment=...)
    # agentic_job_id is the positional first arg
    assert call_args[0][0] == trace_id, (
        f"expected agentic_job_id=={trace_id!r}, got {call_args[0][0]!r}"
    )


@pytest.mark.unit
def test_emit_billing_event_payload_shape():
    """emit_billing_event dispatches report_outcome with outcomeValue==price, result=='SUCCESS'."""
    emitter, mock_client = _make_emitter_with_mock_client(subscriber_id="test@example.com")
    assert emitter.enabled is True

    trace_id = "test-trace-002"
    signal_price = 2.00

    # Create job first so metadata is populated.
    _collect_threads_for(
        emitter,
        emitter.create_trading_signal_job,
        trace_id,
        "NVDA",
        "2026-06-28",
    )
    _collect_threads_for(
        emitter,
        emitter.emit_billing_event,
        trace_id,
        signal_price,
    )

    mock_client.report_outcome.assert_called_once()
    call_args = mock_client.report_outcome.call_args
    called_trace_id = call_args[0][0]
    payload = call_args[0][1]

    assert called_trace_id == trace_id
    assert payload["outcomeValue"] == signal_price
    assert payload["executionStatus"] == "SUCCESS"
    assert payload["executionStatus"] in {"SUCCESS", "FAILED", "CANCELLED"}
    assert "result" not in payload
    assert payload["outcomeType"] == "CONVERTED"
    assert payload["outcomeCurrency"] == "USD"
    assert payload["reportedBy"] == "test@example.com"
    # Metadata must be a JSON string that round-trips to a dict with ticker/trade_date.
    assert isinstance(payload["metadata"], str), (
        f"metadata must be a JSON string, got {type(payload['metadata'])}"
    )
    meta = json.loads(payload["metadata"])
    assert meta["ticker"] == "NVDA"
    assert meta["trade_date"] == "2026-06-28"


# ---------------------------------------------------------------------------
# (d) When mock client raises, public methods still return None and don't raise
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_create_job_fail_open_when_client_raises():
    """create_trading_signal_job returns None and does not propagate when create_job raises."""
    emitter, mock_client = _make_emitter_with_mock_client()
    mock_client.create_job.side_effect = RuntimeError("simulated network failure")

    trace_id = "test-trace-003"
    # Must not raise; joins the daemon thread to confirm the exception was swallowed.
    _collect_threads_for(
        emitter,
        emitter.create_trading_signal_job,
        trace_id,
        "AAPL",
        "2026-06-28",
    )
    # No exception means pass; create_job was called and the error was swallowed.
    mock_client.create_job.assert_called_once()


@pytest.mark.unit
def test_emit_billing_event_fail_open_when_client_raises():
    """emit_billing_event returns None and does not propagate when report_outcome raises."""
    emitter, mock_client = _make_emitter_with_mock_client()
    mock_client.report_outcome.side_effect = RuntimeError("simulated billing failure")

    trace_id = "test-trace-004"
    _collect_threads_for(
        emitter,
        emitter.emit_billing_event,
        trace_id,
        2.00,
    )
    # No exception means pass; report_outcome was called and the error was swallowed.
    mock_client.report_outcome.assert_called_once()


# ---------------------------------------------------------------------------
# (e2) from_config forwards team_id to AgenticOutcomeSettings (GAP-04-TEAM)
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_from_config_forwards_team_id_to_settings():
    """from_config with revenium_team_id='TEAM123' passes team_id='TEAM123' to AgenticOutcomeSettings."""
    from tradingagents.revenium.billing import TradingSignalBillingEmitter

    mock_settings_cls = MagicMock()
    mock_client_cls = MagicMock(return_value=MagicMock())

    config = {
        "revenium_billing_api_key": "rev_sk_test_fake",
        "revenium_profitstream_url": "https://api.revenium.io",
        "revenium_team_id": "TEAM123",
    }

    with patch.dict(
        "sys.modules",
        {
            "revenium_middleware.agentic_outcomes": MagicMock(
                AgenticOutcomeClient=mock_client_cls,
                AgenticOutcomeSettings=mock_settings_cls,
            )
        },
    ):
        TradingSignalBillingEmitter.from_config(config)

    mock_settings_cls.assert_called_once()
    assert mock_settings_cls.call_args.kwargs["team_id"] == "TEAM123", (
        f"Expected team_id='TEAM123', got {mock_settings_cls.call_args.kwargs.get('team_id')!r}"
    )


@pytest.mark.unit
def test_from_config_team_id_defaults_to_empty_string():
    """from_config without revenium_team_id in config passes team_id='' to AgenticOutcomeSettings."""
    from tradingagents.revenium.billing import TradingSignalBillingEmitter

    mock_settings_cls = MagicMock()
    mock_client_cls = MagicMock(return_value=MagicMock())

    # Omit revenium_team_id entirely — from_config must default to "".
    config = {
        "revenium_billing_api_key": "rev_sk_test_fake",
        "revenium_profitstream_url": "https://api.revenium.io",
    }

    with patch.dict(
        "sys.modules",
        {
            "revenium_middleware.agentic_outcomes": MagicMock(
                AgenticOutcomeClient=mock_client_cls,
                AgenticOutcomeSettings=mock_settings_cls,
            )
        },
    ):
        TradingSignalBillingEmitter.from_config(config)

    mock_settings_cls.assert_called_once()
    assert mock_settings_cls.call_args.kwargs["team_id"] == "", (
        f"Expected team_id='', got {mock_settings_cls.call_args.kwargs.get('team_id')!r}"
    )


# ---------------------------------------------------------------------------
# (e) validate_billing.main() returns 0 and prints keyless-skip message
#     when REVENIUM_BILLING_API_KEY is unset (DMO-04 CI safety check)
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_validate_billing_keyless_exits_zero(monkeypatch, capsys):
    """validate_billing.main() returns 0 and prints keyless-skip when billing key is absent."""
    # Ensure billing key is absent in both the env and DEFAULT_CONFIG.
    monkeypatch.delenv("REVENIUM_BILLING_API_KEY", raising=False)

    # Insert the worktree root onto sys.path so the script's path-insert does nothing
    # unexpected when executed in a test context.
    import os
    import sys
    worktree_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if worktree_root not in sys.path:
        sys.path.insert(0, worktree_root)

    import importlib

    import tradingagents.default_config as dc_mod

    # Remove all _ENV_OVERRIDES so DEFAULT_CONFIG is rebuilt keyless.
    for var in dc_mod._ENV_OVERRIDES:
        monkeypatch.delenv(var, raising=False)
    importlib.reload(dc_mod)

    # Patch argparse to avoid consuming pytest argv.
    with patch("argparse.ArgumentParser.parse_args", return_value=type(
        "A", (), {"ticker": "NVDA", "date": "2026-06-27"}
    )()):
        # Import the script from the worktree scripts directory.
        import importlib.util

        script_path = os.path.join(worktree_root, "scripts", "validate_billing.py")
        spec = importlib.util.spec_from_file_location("validate_billing", script_path)
        assert spec is not None
        validate_billing = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(validate_billing)  # type: ignore[union-attr]

        ret = validate_billing.main()

    captured = capsys.readouterr()
    assert ret == 0, f"Expected exit 0 in keyless mode, got {ret}"
    assert "keyless mode" in captured.out.lower(), (
        f"Expected keyless-skip message in stdout, got:\n{captured.out}"
    )
