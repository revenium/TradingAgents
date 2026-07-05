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
def test_emit_billing_event_block_waits_for_outcome():
    em, client = _enabled_emitter_with_mock_client()

    em.emit_billing_event(trace_id="t1", signal_price=2.00, block=True)

    # With block=True the POST must have completed by the time emit returns.
    assert client.completed.is_set(), "block=True must wait for the outcome POST"
    assert len(client.calls) == 1
    trace_id, payload = client.calls[0]
    assert trace_id == "t1"
    assert payload["executionStatus"] == "SUCCESS"
    assert payload["outcomeType"] == "CONVERTED"
    assert payload["outcomeValue"] == 2.00


@pytest.mark.unit
def test_emit_billing_event_nonblock_returns_before_outcome():
    em, client = _enabled_emitter_with_mock_client()

    em.emit_billing_event(trace_id="t2", signal_price=2.00)  # block=False (default)

    # Fire-and-forget: emit returns before the slow POST finishes.
    assert not client.completed.is_set()
    # The daemon thread still lands the outcome eventually.
    assert client.completed.wait(timeout=2.0)
    assert len(client.calls) == 1


@pytest.mark.unit
def test_emit_billing_event_disabled_is_noop():
    em = TradingSignalBillingEmitter(api_key="")  # disabled (no key)
    assert not em.enabled
    # Must not raise and must make no client call (there is no client).
    em.emit_billing_event(trace_id="t3", signal_price=2.00, block=True)
