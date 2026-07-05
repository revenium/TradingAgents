"""Fail-open billing emitter for completed trading signals (BIL-01/02, D-07, D-09, D-10).

Wraps ``AgenticOutcomeClient`` from ``revenium_middleware.agentic_outcomes`` so any
Jobs/Outcomes API failure is logged as a warning and never blocks or corrupts a trading
run.  The emitter is disabled (silent no-op) when the billing key
(``revenium_sk_api_key``, the same ``rev_sk_*`` write key used for setup and enforcement)
is absent, so keyless CI suites remain green (DMO-04).

Design rationale:
- Mirrors ``tradingagents/revenium/client.py``: lazy SDK import in ``__init__``, the
  ``enabled`` property, ``from_config`` factory, and fail-open ``except Exception`` guards.
- Both public methods (``create_trading_signal_job``, ``emit_billing_event``) dispatch the
  actual network I/O on a daemon thread so the caller (``_run_graph``) is never blocked
  waiting for a Jobs/Outcomes HTTP round-trip (Anti-Pattern 3).
- ``emit_billing_event`` is called only from the SUCCESS path of ``_run_graph``
  (inside ``try``, after ``graph.invoke()`` returns) so circuit-breaker-halted runs never
  emit a billing event (D-10).

Key invariants:
- Only symbolic values (trace_id, ticker, signal_price, result codes) appear in log
  messages.  The billing API key, subscriber email, and raw HTTP response body are NEVER
  logged (T-04-03 mitigation).
- ``enabled`` is ``False`` when the billing key is empty or the SDK failed to initialise.
  All public methods are no-ops in that case and never raise.
- The ``_job_meta`` dict stores per-trace_id metadata (ticker, trade_date) so
  ``emit_billing_event`` can populate the outcome payload ``metadata`` field without
  requiring the caller to pass it again.
"""

from __future__ import annotations

import json
import logging
import threading
from typing import Any

logger = logging.getLogger(__name__)


class TradingSignalBillingEmitter:
    """Fail-open billing emitter for completed trading signals.

    Wraps ``AgenticOutcomeClient`` so Jobs/Outcomes API failures are logged and
    discarded rather than propagated to the caller.

    Disabled (all methods are silent no-ops) when no ``api_key`` is provided or
    when the SDK fails to initialise.  This is the same contract as
    ``ReveniumClient`` / ``ReveniumCallbackHandler``.
    """

    def __init__(
        self,
        *,
        api_key: str,
        profitstream_base_url: str = "https://api.revenium.io",
        team_id: str = "",
        subscriber_id: str = "",
    ) -> None:
        """Construct the emitter, lazily importing the AgenticOutcomeClient SDK.

        Args:
            api_key:                 Revenium billing API key (``rev_sk_*`` prefix).
                                     Empty string disables all billing calls (DMO-04).
            profitstream_base_url:   Jobs/Outcomes profitstream host.  Defaults to the
                                     SDK default (``https://api.revenium.io``); override
                                     via ``REVENIUM_PROFITSTREAM_BASE_URL`` when the live
                                     account uses a different host (Open Question 1).
            team_id:                 Optional Revenium team identifier; forwarded to
                                     ``AgenticOutcomeSettings`` for team-ID resolution.
            subscriber_id:           Revenium subscriber identifier (email/ID) used as the
                                     ``reportedBy`` field in the outcome payload.
        """
        self._api_key = api_key
        self._subscriber_id = subscriber_id
        self._client: Any = None  # lazily initialised below if key present
        # Per-trace-id metadata: {trace_id: {"ticker": str, "trade_date": str}}
        # Populated by create_trading_signal_job; consumed by emit_billing_event.
        self._job_meta: dict[str, dict[str, str]] = {}
        self._lock = threading.Lock()

        if api_key:
            try:
                from revenium_middleware.agentic_outcomes import (  # lazy import (D-05)
                    AgenticOutcomeClient,
                    AgenticOutcomeSettings,
                )

                settings = AgenticOutcomeSettings(
                    api_key=api_key,
                    profitstream_base_url=profitstream_base_url,
                    outcome_api_key=api_key,
                    team_id=team_id,
                )
                self._client = AgenticOutcomeClient(settings=settings)
            except Exception:  # noqa: BLE001 — fail open, never block the run
                logger.warning(
                    "TradingSignalBillingEmitter: AgenticOutcomeClient initialisation failed"
                    " — billing disabled",
                    exc_info=True,
                )
                self._client = None

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def from_config(cls, config: dict) -> TradingSignalBillingEmitter:
        """Build an emitter from a TradingAgents config dict.

        Reads the billing key from ``revenium_sk_api_key`` (primary; the same
        ``rev_sk_*`` write key used by setup_revenium.py and enforcement).
        Falls back to the legacy ``revenium_billing_api_key`` alias so existing
        .env files that set only the old name continue to work (GAP-04-LINK).
        Also reads ``revenium_profitstream_url``, ``revenium_subscriber_id``,
        and ``revenium_team_id`` from ``config``.  When the billing key is
        empty the returned emitter has ``enabled == False`` and is a silent
        no-op (DMO-04).

        Args:
            config: Process-global config dict (from ``get_config()`` or
                    ``DEFAULT_CONFIG``).

        Returns:
            A fully configured ``TradingSignalBillingEmitter``.
        """
        # Prefer revenium_sk_api_key; fall back to legacy alias (GAP-04-LINK).
        api_key: str = (
            config.get("revenium_sk_api_key", "")
            or config.get("revenium_billing_api_key", "")
        )
        profitstream_base_url: str = config.get(
            "revenium_profitstream_url", "https://api.revenium.io"
        )
        subscriber_id: str = config.get("revenium_subscriber_id", "")
        team_id: str = config.get("revenium_team_id", "")
        return cls(
            api_key=api_key,
            profitstream_base_url=profitstream_base_url,
            team_id=team_id,
            subscriber_id=subscriber_id,
        )

    # ------------------------------------------------------------------
    # Public properties
    # ------------------------------------------------------------------

    @property
    def enabled(self) -> bool:
        """``True`` when a non-empty billing key was supplied and the SDK initialised."""
        return bool(self._api_key) and self._client is not None

    # ------------------------------------------------------------------
    # Public methods — both are fail-open and dispatch on daemon threads
    # ------------------------------------------------------------------

    def create_trading_signal_job(
        self, trace_id: str, ticker: str, trade_date: str
    ) -> None:
        """Create a Job record in Revenium at the start of a trading run.

        Stores ``ticker`` / ``trade_date`` on the instance (keyed by ``trace_id``)
        so ``emit_billing_event`` can populate the outcome ``metadata`` field without
        requiring the caller to pass them again.

        Called from ``_run_graph`` immediately after ``begin_run``, before
        ``graph.invoke()``.  Fail-open: any exception is caught and logged; the
        trading run is never affected.  Silent no-op when ``enabled`` is ``False``.

        Args:
            trace_id:   Run's Revenium trace identifier (used as ``agentic_job_id``).
            ticker:     Ticker symbol (e.g. ``"NVDA"``).
            trade_date: ISO date string for the analysis date.
        """
        if not self.enabled:
            return

        # Store metadata immediately (synchronous) so emit_billing_event always
        # finds it regardless of daemon-thread scheduling.
        with self._lock:
            self._job_meta[trace_id] = {"ticker": ticker, "trade_date": str(trade_date)}

        def _create_job_safe() -> None:
            try:
                assert self._client is not None  # narrowing; already checked by enabled
                self._client.create_job(
                    trace_id,
                    name=f"trading-signal-{ticker}-{trade_date}",
                    type="trading-signal",
                    environment="production",
                )
                logger.debug(
                    "TradingSignalBillingEmitter.create_trading_signal_job: "
                    "trace_id=%r ticker=%r",
                    trace_id,
                    ticker,
                )
            except Exception:  # noqa: BLE001 — fail open, never block the run
                logger.warning(
                    "TradingSignalBillingEmitter: create_job failed for trace_id=%r"
                    " ticker=%r — billing event may be incomplete",
                    trace_id,
                    ticker,
                    exc_info=True,
                )

        t = threading.Thread(
            target=_create_job_safe,
            daemon=True,
            name=f"rev-billing-create-{trace_id[:8]}",
        )
        t.start()

    def emit_billing_event(
        self,
        trace_id: str,
        signal_price: float,
        reported_by: str = "",
        *,
        block: bool = False,
        block_timeout: float = 10.0,
    ) -> bool | None:
        """Emit a SUCCESS outcome for a completed trading signal run.

        Reports ``outcomeValue=signal_price`` to Revenium's Jobs/Outcomes API so
        the Costs & Revenue dashboard can display margin (Revenue - AI cost, D-08).

        Called from the SUCCESS path of ``_run_graph`` (inside ``try``, after
        ``graph.invoke()`` returns), never from ``finally``.  This guarantees that
        circuit-breaker-halted runs do NOT emit a billing event (D-10).

        Fail-open: any exception is caught and logged; the run is never affected.
        Silent no-op when ``enabled`` is ``False``.

        Args:
            trace_id:     Run's Revenium trace identifier; must match the
                          ``agentic_job_id`` passed to ``create_trading_signal_job``.
            signal_price: Configurable unit price for the trading signal in USD
                          (default $2.00, D-07).  Carried as ``outcomeValue``.
            reported_by:  Subscriber identifier for attribution.  Defaults to the
                          ``subscriber_id`` set at construction time.
            block:        When ``True``, wait (bounded by ``block_timeout``) for the
                          outcome POST to complete before returning.  Needed on the
                          CLI path, which emits at the very end of the run and then
                          tears down (``stop_polling`` / process exit) — without the
                          wait the daemon thread is killed mid-POST and the Job is
                          left ``PENDING`` (never converts).  ``_run_graph`` leaves
                          this ``False`` (fire-and-forget) since it does more work
                          after emitting.
            block_timeout: Max seconds to wait when ``block`` is ``True``; on timeout
                          the (daemon) thread continues best-effort and control
                          returns so the caller never hangs.

        Returns:
            When ``block`` is ``True``: ``True`` if the outcome POST was accepted,
            ``False`` if it was dropped (logged), or ``None`` if it was still in
            flight past ``block_timeout``. When ``block`` is ``False`` (or the
            emitter is disabled): always ``None`` (delivery not yet known). NOTE:
            this reflects POST *delivery* only — the Job's PENDING->SUCCESS flip is
            a separate async reconciliation on the Revenium backend.
        """
        if not self.enabled:
            return None

        attributed_to = reported_by or self._subscriber_id
        with self._lock:
            meta = dict(self._job_meta.get(trace_id, {}))

        # Captured by the worker thread; read after join() when block=True so the
        # caller can confirm the outcome POST was accepted (True) vs dropped (False)
        # vs still-in-flight/timed-out (None). The Job's PENDING->SUCCESS flip is a
        # separate async Revenium reconciliation — this only reports POST delivery.
        result: dict[str, bool] = {}

        def _report_outcome_safe() -> None:
            try:
                assert self._client is not None  # narrowing; already checked by enabled
                payload: dict[str, Any] = {
                    "executionStatus": "SUCCESS",
                    "outcomeType": "CONVERTED",
                    "outcomeValue": signal_price,
                    "outcomeCurrency": "USD",
                    "reportedBy": attributed_to,
                    "metadata": json.dumps(meta),
                }
                self._client.report_outcome(trace_id, payload)
                result["ok"] = True
                logger.debug(
                    "TradingSignalBillingEmitter.emit_billing_event: "
                    "trace_id=%r signal_price=%r result=SUCCESS",
                    trace_id,
                    signal_price,
                )
            except Exception:  # noqa: BLE001 — fail open, never block the run
                result["ok"] = False
                logger.warning(
                    "TradingSignalBillingEmitter: report_outcome failed for trace_id=%r"
                    " signal_price=%r — revenue event dropped",
                    trace_id,
                    signal_price,
                    exc_info=True,
                )

        t = threading.Thread(
            target=_report_outcome_safe,
            daemon=True,
            name=f"rev-billing-outcome-{trace_id[:8]}",
        )
        t.start()
        if block:
            # Wait (bounded) so the outcome POST lands before the caller tears down
            # its transport or exits the process. _report_outcome_safe is fail-open,
            # so on timeout the thread keeps running best-effort and we return.
            t.join(timeout=block_timeout)
            # True (accepted) / False (dropped) / None (still in flight past timeout).
            return result.get("ok")
        return None
