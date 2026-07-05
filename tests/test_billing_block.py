"""emit_billing_event(block=True) waits for the outcome POST to land.

The CLI emits the billing outcome at the very end of a run and then tears down
(stop_polling / process exit). With the default fire-and-forget daemon thread the
POST can be killed mid-flight, leaving the Job PENDING (never converts). block=True
waits (bounded) so the outcome lands first. These tests use a mocked outcome client
— no network, no API keys.
"""

from __future__ import annotations

import threading
import time

import pytest

from tradingagents.revenium.billing import TradingSignalBillingEmitter


def _enabled_emitter_with_mock_client():
    """Build an emitter whose outcome client is a controllable test double."""
    em = TradingSignalBillingEmitter(api_key="")  # empty key -> no real SDK client
    em._api_key = "rev_sk_test"  # flip `enabled` on without building a live client

    class _Client:
        def __init__(self):
            self.calls = []
            self.started = threading.Event()
            self.completed = threading.Event()

        def report_outcome(self, trace_id, payload):
            self.started.set()
            time.sleep(0.3)  # simulate a slow HTTP POST
            self.calls.append((trace_id, payload))
            self.completed.set()

    client = _Client()
    em._client = client
    assert em.enabled
    return em, client


@pytest.mark.unit
def test_emit_billing_event_block_waits_and_reports_accepted():
    em, client = _enabled_emitter_with_mock_client()

    ok = em.emit_billing_event(trace_id="t1", signal_price=2.00, block=True)

    # With block=True the POST must have completed by the time emit returns, and
    # emit reports delivery success for the CLI read-back.
    assert ok is True, "block=True must report the outcome POST was accepted"
    assert client.completed.is_set(), "block=True must wait for the outcome POST"
    assert len(client.calls) == 1
    trace_id, payload = client.calls[0]
    assert trace_id == "t1"
    assert payload["executionStatus"] == "SUCCESS"
    assert payload["outcomeType"] == "CONVERTED"
    assert payload["outcomeValue"] == 2.00


@pytest.mark.unit
def test_emit_billing_event_block_reports_false_on_failure():
    em, client = _enabled_emitter_with_mock_client()
    client.report_outcome = lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("boom"))

    ok = em.emit_billing_event(trace_id="tX", signal_price=2.00, block=True)

    # Fail-open: no raise, but the read-back reports the drop so the CLI can warn.
    assert ok is False


@pytest.mark.unit
def test_emit_billing_event_nonblock_returns_none_before_outcome():
    em, client = _enabled_emitter_with_mock_client()

    ok = em.emit_billing_event(trace_id="t2", signal_price=2.00)  # block=False (default)

    # Fire-and-forget: delivery not yet known, returns None; POST not done yet.
    assert ok is None
    assert not client.completed.is_set()
    # The daemon thread still lands the outcome eventually.
    assert client.completed.wait(timeout=2.0)
    assert len(client.calls) == 1


@pytest.mark.unit
def test_emit_billing_event_disabled_is_noop():
    em = TradingSignalBillingEmitter(api_key="")  # disabled (no key)
    assert not em.enabled
    # Must not raise, make no client call, and report None (nothing attempted).
    assert em.emit_billing_event(trace_id="t3", signal_price=2.00, block=True) is None
