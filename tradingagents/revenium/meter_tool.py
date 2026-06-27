"""Fail-open @meter_tool adapter for TradingAgents analyst data-fetch tools.

Bridges our per-agent ContextVars (current_agent_name, current_trace_id)
with the revenium-metering SDK's tool-event pipeline.  Every analyst
data-fetch tool is decorated with @meter_tool so Revenium can show the
"cost iceberg" — the hidden data-fetch spend beneath each LLM call.

Design invariants
-----------------
- Decorator MUST be innermost (beneath @tool) so LangChain sees the correct
  StructuredTool wrapper:

    @tool                          # LangChain tool contract (outermost)
    @meter_tool("get_stock_data")  # metering (innermost)
    def get_stock_data(...): ...

  As a result, StructuredTool.func IS the meter_tool wrapper; .func() calls
  also pass through metering when a key is present.

- Fail-open: any metering exception is caught and logged at DEBUG level so
  the data fetch is never blocked.  The SDK's _send_tool_event has its own
  HTTP-level error handling; we add an outer catch for unexpected SDK errors.

- Keyless no-op: when revenium_api_key is empty in config, the wrapper
  calls the underlying function directly and returns its result without any
  SDK interaction.  Imports of the SDK modules are deferred to call time.

- All SDK imports happen lazily inside the wrapper to avoid pulling in
  heavy httpx / SDK code at process start (or in tests that do not set a key).

- Duration measurement: the elapsed time of func(*args, **kwargs) is included
  in the tool event's duration_ms field for latency-attribution in Revenium.
"""

from __future__ import annotations

import functools
import logging
import time
from typing import Any, Callable

logger = logging.getLogger(__name__)


def meter_tool(tool_id: str) -> Callable:
    """Decorator factory: wrap a data-fetch function with Revenium tool metering.

    Parameters
    ----------
    tool_id:
        The tool identifier sent to the Revenium platform (e.g. "get_stock_data").
        This appears as the tool label in the Revenium usage dashboard.

    Returns
    -------
    A decorator that wraps the target function with fail-open metering.
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            # ----------------------------------------------------------------
            # Step 1: Run the underlying function regardless of metering status.
            # Capture both the result and elapsed duration for the tool event.
            # ----------------------------------------------------------------
            t0 = time.monotonic()
            success = True
            error_message: str | None = None
            result: Any = None
            try:
                result = func(*args, **kwargs)
            except Exception as exc:
                success = False
                error_message = type(exc).__name__
                raise
            finally:
                duration_ms = int((time.monotonic() - t0) * 1000)

            # ----------------------------------------------------------------
            # Step 2: Emit a tool event to Revenium — fail-open.
            # Only attempted when an API key is configured; never blocks return.
            # ----------------------------------------------------------------
            try:
                from tradingagents.dataflows.config import get_config  # noqa: PLC0415

                cfg = get_config()
                api_key: str = cfg.get("revenium_api_key", "") or ""
                if not api_key:
                    return result  # keyless no-op

                # Lazy SDK imports — avoid heavy pull at process start.
                from revenium_metering.context import ReveniumContext  # noqa: PLC0415
                from revenium_metering.decorator import _send_tool_event  # noqa: PLC0415
                from tradingagents.revenium.context import (  # noqa: PLC0415
                    current_agent_name,
                    current_trace_id,
                )

                ctx = ReveniumContext(
                    trace_id=current_trace_id.get("") or None,
                    agent=current_agent_name.get("unknown") or None,
                    organization_name=cfg.get("revenium_organization_name") or None,
                    product_name=cfg.get("revenium_product_name") or None,
                    subscriber_credential=cfg.get("revenium_subscriber_id") or None,
                )

                _send_tool_event(
                    tool_id=tool_id,
                    operation=None,
                    duration_ms=duration_ms,
                    success=success,
                    error_message=error_message,
                    usage_metadata=None,
                    context=ctx,
                )

            except Exception:  # noqa: BLE001 — fail open, never block the run
                logger.debug(
                    "Revenium tool metering suppressed for tool_id=%r", tool_id
                )

            return result

        return wrapper

    return decorator
