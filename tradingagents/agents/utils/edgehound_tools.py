"""Edgehound decision-intelligence mock tool: Revenium tool metering (PIL-01).

Purpose
-------
Provides ``get_edgehound_decision``, a LangChain ``@tool`` that returns a
fully local, deterministic mock of Edgehound's decision-intelligence output
(thesis / entry-exit levels / conviction score) and meters each call through
Revenium's tool-event pipeline (``@meter_tool(DEFAULT_CONFIG["edgehound_tool_id"])``,
default ``edgehound_decision`` — no colon: Revenium's Tools UI rejects ':').

This follows the Phase 6 ``@meter_tool`` + per-call ``ToolResource`` pattern
(see ``jentic_news_tools.py``), extended to a partner with zero live dependency.

Design invariants
-----------------
- **Fully local mock** — no network calls, no API key, no external dependency.
  The output is derived from a stable hash of the query so tests can assert
  exact structure without worrying about non-determinism.
- **No sentinel branch** — unlike Jentic, there is no external API to fail.
  The tool always returns plausible output when called directly. LLM-level
  gating (only offering the tool when ``edgehound_tool_enabled=True``) is
  enforced in ``market_analyst.py``, not here (T-07-02).
- **Decorator order** — ``@tool`` is outermost (so LangChain sees a
  ``StructuredTool``), ``@meter_tool`` is innermost (so
  ``StructuredTool.func`` IS the metered wrapper — direct ``.func()`` calls
  in tests also pass through metering when a key is present).
- **Single source of truth for toolId** — ``DEFAULT_CONFIG["edgehound_tool_id"]``
  is the ONLY place the toolId is defined; ``@meter_tool`` reads it at decoration
  time (T-07-01). Never hardcode the string elsewhere.
- **No key logging** — implementation takes no secret; never log query contents
  in a way that could contain sensitive info (T-07-03).
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Annotated

from langchain_core.tools import tool

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.revenium.meter_tool import meter_tool

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Local mock implementation (separated for testability)
# ---------------------------------------------------------------------------


def _edgehound_decision_impl(query: str) -> str:
    """Deterministic local mock of Edgehound's decision-intelligence API.

    Derives plausible entry/exit/conviction values from a stable hash of the
    query string so test assertions can rely on exact structure (not exact
    values).  Output is a JSON string containing the required fields for the
    demo narrative: thesis, entry_level, exit_level, conviction_score, source.

    No network, no API key, no external dependency.
    """
    # Derive stable numeric seeds from the query hash (not random — deterministic
    # across runs for a given query, which lets tests assert structure without
    # re-implementing the hash).
    digest = hashlib.sha256(query.encode()).digest()
    # Use first four bytes for base price (range 100-999) and next byte for
    # conviction (range 40-95) — arbitrary but reproducible.
    base_price = 100 + (int.from_bytes(digest[0:2], "big") % 900)
    spread_pct = 0.05 + (digest[2] % 10) * 0.005   # 5–9.5%
    entry_level = round(base_price * (1 - spread_pct * 0.5), 2)
    exit_level = round(base_price * (1 + spread_pct), 2)
    conviction_score = 40 + (digest[3] % 56)        # 40–95

    tickers = query.split()[:2]
    ticker_hint = " ".join(tickers) if tickers else "the asset"

    thesis = (
        f"Edgehound signals a potential momentum setup for {ticker_hint}. "
        f"Key support at ${entry_level:.2f}; target resistance at ${exit_level:.2f}. "
        "Pattern analysis indicates elevated institutional flow."
    )

    output = {
        "thesis": thesis,
        "entry_level": entry_level,
        "exit_level": exit_level,
        "conviction_score": conviction_score,
        "source": "edgehound (mock)",
    }
    return json.dumps(output, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Public tool: @tool outermost, @meter_tool innermost
# ---------------------------------------------------------------------------


@tool
@meter_tool(DEFAULT_CONFIG["edgehound_tool_id"])  # single source of truth (L6); no colon (Revenium UI)
def get_edgehound_decision(
    query: Annotated[str, "Decision query, e.g. 'NVDA momentum breakout entry signal'"],
) -> str:
    """Retrieve decision intelligence from Edgehound (mocked, Revenium-metered).

    Returns a JSON string with decision-intelligence fields:
    - ``thesis``: narrative rationale
    - ``entry_level``: suggested entry price
    - ``exit_level``: suggested exit (target) price
    - ``conviction_score``: 0–100 confidence score
    - ``source``: always ``"edgehound (mock)"``

    This is a fully local mock — no network, no API key required.
    Metered per-call via Revenium's ``@meter_tool`` pipeline so every
    call emits an ``edgehound_decision`` tool event.

    Requirements:
    - ``edgehound_tool_enabled=True`` in config (controls whether the market
      analyst offers this tool to the LLM — not enforced by the tool itself).
    """
    return _edgehound_decision_impl(query)
