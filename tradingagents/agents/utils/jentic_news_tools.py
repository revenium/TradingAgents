"""Jentic-backed news tool: sync wrapper + Revenium tool metering.

Purpose
-------
Provides ``get_jentic_news``, a LangChain ``@tool`` that fetches external
news data via the Jentic SDK's async ``execute()`` call and meters each call
through Revenium's tool-event pipeline (``@meter_tool("jentic:news")``).

This extends Phase 3's MTR-03 from internal data-fetch tools to real
third-party API calls, completing the "cost iceberg" demo beat.

Design invariants
-----------------
- **Fail-soft** — any Jentic error (auth, network, no-data, timeout) is
  caught at the outermost level and returns a ``NO_DATA_AVAILABLE: ...``
  sentinel string.  The run is never crashed.  Matches ``route_to_vendor``
  convention so agents treat the result the same way they treat vendor
  exhaustion.
- **Keyless no-op** — when ``jentic_tool_enabled`` is False OR
  ``jentic_agent_api_key`` is empty in config, the function returns the
  sentinel immediately, BEFORE constructing a ``Jentic`` client.  This
  keeps the full test suite green without any ``JENTIC_AGENT_API_KEY`` set
  (JEN-03).
- **Lazy SDK import** — ``from jentic import Jentic`` and its companion
  models are imported INSIDE ``_do_jentic_news``, never at module load time.
  This means importing this module with no Jentic key installed or absent
  from the venv never raises.
- **Async→sync bridge** — Jentic is purely async; LangGraph and
  ``@meter_tool`` are sync.  ``_run_async`` wraps ``asyncio.run`` with a
  ``ThreadPoolExecutor`` fallback for the rare case of a running event loop
  (Jupyter, hypothetical async LangGraph).
- **Decorator order** — ``@tool`` is outermost (so LangChain sees a
  ``StructuredTool``), ``@meter_tool`` is innermost (so
  ``StructuredTool.func`` IS the metered wrapper — direct ``.func()`` calls
  in tests also pass through metering when a key is present).
- **No key logging** — ``jentic_agent_api_key`` must never appear in log
  output; log only symbolic reason strings (T-06-01).
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
import logging
import os
from typing import Annotated

from langchain_core.tools import tool

from tradingagents.revenium.meter_tool import meter_tool

logger = logging.getLogger(__name__)

# Sentinel template — starts with "NO_DATA_AVAILABLE:" matching the
# route_to_vendor convention so agents treat it as "no data" and must not
# fabricate news.
_NO_DATA = (
    "NO_DATA_AVAILABLE: Jentic news call failed — {reason}. "
    "Do not estimate or fabricate news data."
)


# ---------------------------------------------------------------------------
# Async→sync bridge
# ---------------------------------------------------------------------------


def _run_async(coro) -> object:
    """Run an async coroutine from sync context, thread-safely.

    Fast path: ``asyncio.run()`` creates a fresh event loop (correct for
    synchronous LangGraph nodes today).  Fallback: when a running loop is
    detected (Jupyter, hypothetical future async LangGraph), submit to a
    fresh thread that owns its own loop.
    """
    try:
        return asyncio.run(coro)
    except RuntimeError as exc:
        if "cannot be called from a running loop" not in str(exc):
            raise
        # Fallback — thread isolation keeps the running loop intact
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result()


# ---------------------------------------------------------------------------
# Async Jentic execution body
# ---------------------------------------------------------------------------


async def _do_jentic_news(query: str, cfg: dict) -> str:
    """Async body: config-driven search→(optional load)→execute via Jentic SDK.

    Imports are lazy (inside the function) to avoid pulling in the Jentic SDK
    at module load time.  ``inputs={"q": query}`` targets the pinned
    NewsAPI ``getEverything`` operation (op_ba86fdce1bade1b7) whose input
    parameter is ``q`` per the CONTEXT.md LIVE TARGET (2026-07-03).
    """
    # Lazy imports — never at module level (L2)
    from jentic import Jentic  # noqa: PLC0415
    from jentic.lib.cfg import AgentConfig  # noqa: PLC0415
    from jentic.lib.models import ExecutionRequest, SearchRequest  # noqa: PLC0415

    # Set key into env so AgentConfig.from_env() can read it.
    # Use direct assignment (not setdefault) so that a config-provided key
    # always takes effect — this handles the test scenario where conftest
    # force-sets JENTIC_AGENT_API_KEY="" before the test but the test
    # provides a mock key via set_config.
    os.environ["JENTIC_AGENT_API_KEY"] = cfg["jentic_agent_api_key"]
    client = Jentic(AgentConfig.from_env())

    op_id: str = cfg.get("jentic_op_id", "")
    if not op_id:
        # Discovery path — run once and pin the result in jentic_op_id config
        # for demo reliability (skips this round-trip on subsequent calls).
        search_query = cfg.get("jentic_search_query", query)
        search_resp = await client.search(
            SearchRequest(query=search_query, limit=5)
        )
        if not search_resp.results:
            return _NO_DATA.format(reason="no Jentic operations matched the search query")
        op_id = search_resp.results[0].id

    # Build inputs for the pinned op.  NewsAPI getEverything input key is `q`
    # (not `query`) per CONTEXT.md LIVE TARGET (L4/L5 guard).
    inputs: dict = {"q": query}

    exec_resp = await client.execute(ExecutionRequest(id=op_id, inputs=inputs))
    if not exec_resp.success or exec_resp.output is None:
        reason = exec_resp.error or f"status_code={exec_resp.status_code}"
        return _NO_DATA.format(reason=reason)

    output = exec_resp.output
    if isinstance(output, (dict, list)):
        return json.dumps(output, ensure_ascii=False)
    return str(output)


# ---------------------------------------------------------------------------
# Sync implementation (separated for testability)
# ---------------------------------------------------------------------------


def _jentic_news_impl(query: str) -> str:
    """Sync implementation called by the @tool wrapper.

    Reads config at call time (not import time) so the enable flag and key
    can be changed between calls without re-importing the module.
    """
    from tradingagents.dataflows.config import get_config  # noqa: PLC0415  # call-time

    cfg = get_config()

    # Config-gate BEFORE constructing Jentic — keyless no-op (L2)
    if not cfg.get("jentic_tool_enabled", False):
        return _NO_DATA.format(reason="jentic_tool_enabled is False")

    api_key: str = cfg.get("jentic_agent_api_key", "") or ""
    if not api_key:
        return _NO_DATA.format(reason="JENTIC_AGENT_API_KEY not configured")

    try:
        return _run_async(_do_jentic_news(query, cfg))
    except Exception as exc:  # noqa: BLE001 — fail open, never block the run
        # Log symbolic reason only — never include the key value (T-06-01)
        logger.warning("Jentic news call failed: %s", type(exc).__name__)
        return _NO_DATA.format(reason=str(exc)[:200])


# ---------------------------------------------------------------------------
# Public tool: @tool outermost, @meter_tool innermost (L8)
# ---------------------------------------------------------------------------


@tool
@meter_tool("jentic:news")
def get_jentic_news(
    query: Annotated[str, "News search query, e.g. 'NVDA latest earnings news'"],
) -> str:
    """Retrieve news via Jentic's managed-auth external API layer.

    Fetches news from a credentialed Jentic API operation (default: NewsAPI
    getEverything, op_ba86fdce1bade1b7) and returns the result as a JSON
    string or plain text.

    Requirements:
    - ``jentic_tool_enabled=True`` in config
    - ``JENTIC_AGENT_API_KEY`` set in config / env

    Returns ``NO_DATA_AVAILABLE: ...`` on any error (fail-soft — never
    crashes the run).  Do not fabricate news data if this sentinel is returned.
    """
    return _jentic_news_impl(query)
