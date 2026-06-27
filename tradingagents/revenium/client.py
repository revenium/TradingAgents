"""Thin fail-open HTTP client wrapping the revenium-metering SDK.

This module is the single import gate for the Revenium metering SDK
(``revenium_metering``).  All other modules in the ``revenium/`` package
call ``meter_ai_completion()`` here instead of importing the SDK directly.
This isolation means tests can mock just this module without pulling in
``httpx`` or the full metering client library.

Design rationale:
- The SDK (``ReveniumMetering``) is imported lazily inside ``__init__`` so
  the *module* is importable even when the SDK is absent or
  ``REVENIUM_METERING_API_KEY`` is not set.  This upholds the test-suite
  discipline (DMO-04): ``pytest`` must run cleanly with no Revenium key.
- ``enabled`` is ``False`` when ``api_key`` is empty (D-05).  Callers check
  this before invoking ``meter_ai_completion`` to avoid unnecessary work,
  but calling it when disabled is also safe (early-return no-op).
- ``meter_ai_completion()`` is **fail-open**: any exception from the SDK
  (network error, timeout, bad payload, auth rejection) is caught,
  a warning is logged with the symbolic agent name *only* (never the API
  key or prompt bodies — D-06, T-02-01), and ``None`` is returned.
  This guarantees a Revenium outage can never halt or fail a trading run.

Key invariants:
- Only this file imports ``revenium_metering``.  No other file in the
  ``revenium/`` package should do so.
- Secrets (``api_key``) are never logged; only agent names and operation
  labels appear in warning messages.
- The SDK ``ReveniumMetering`` client is thread-safe for concurrent
  ``create_completion`` calls (per httpx sync-client design); the instance
  is shared across all callbacks for the life of the graph.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class ReveniumClient:
    """Fail-open wrapper around the revenium-metering SDK for AI completion events.

    Constructed once per ``TradingAgentsGraph.__init__`` and shared across all
    callback invocations for the lifetime of the graph instance.

    Thread-safety: ``meter_ai_completion`` is stateless (no mutable instance
    state is written during a call), so concurrent invocations from background
    threads (fire-and-forget in callback handler) are safe.
    """

    def __init__(self, *, api_key: str, api_url: str) -> None:
        """Construct the client, lazily importing the SDK only when a key is present.

        Args:
            api_key: Revenium metering API key (``rev_mk_*`` prefix).
                     Empty string disables metering (D-05).
            api_url: Metering API base URL.
                     Default is ``https://api.revenium.ai``; the SDK's
                     ``_normalize_base_url`` appends ``/meter`` automatically.
        """
        self._api_key = api_key
        self._api_url = api_url
        self._sdk_client: Any = None  # lazily initialised below if key present

        if api_key:
            try:
                from revenium_metering import ReveniumMetering  # lazy import (D-05)

                self._sdk_client = ReveniumMetering(api_key=api_key, base_url=api_url)
            except Exception:  # noqa: BLE001 — fail open, never block the run
                logger.warning(
                    "Revenium SDK initialisation failed — metering disabled",
                    exc_info=True,
                )
                self._sdk_client = None

    @property
    def enabled(self) -> bool:
        """``True`` when a non-empty API key was supplied and the SDK initialised."""
        return bool(self._api_key) and self._sdk_client is not None

    def meter_ai_completion(self, payload: dict) -> None:
        """Post one AI completion metering event to Revenium (fail-open).

        Translates the payload dict built by ``ReveniumCallbackHandler.on_llm_end``
        into a typed ``ReveniumMetering.ai.create_completion()`` call.  Any
        exception — network error, auth failure, bad payload — is caught,
        logged as a warning with the symbolic agent name only (never the key
        or prompt content), and dropped silently.

        The trading run is **never** affected by a metering failure.

        Args:
            payload: Metering fields as a dict.  Keys match the
                     ``create_completion`` parameter names exactly so the
                     dict can be unpacked via ``**payload``.
        """
        if not self.enabled:
            return
        try:
            self._sdk_client.ai.create_completion(**payload)
        except Exception:  # noqa: BLE001 — fail open, never block the run
            logger.warning(
                "Revenium metering failed for agent %r — event dropped",
                payload.get("agent", "unknown"),
                exc_info=True,
            )
