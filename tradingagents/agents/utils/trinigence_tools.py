"""Trinigence NL→strategy-generation mock tool: Revenium tool metering (PIL-02).

Purpose
-------
Provides ``get_trinigence_strategy``, a LangChain ``@tool`` that accepts a
natural-language description of a desired trading strategy and returns a
fully local, deterministic mock of Trinigence's strategy-generation output
(strategy_name / entry_rules / exit_rules / indicators / backtest_summary)
and meters each call through Revenium's tool-event pipeline
(``@meter_tool(DEFAULT_CONFIG["trinigence_tool_id"])``, default
``trinigence_strategy`` — no colon: Revenium's Tools UI rejects ':').

This follows the Phase 6 ``@meter_tool`` + per-call ``ToolResource`` pattern
(see ``jentic_news_tools.py``), extended to a second pilot partner (Trinigence)
with zero live dependency.  It is the sibling of ``edgehound_tools.py``
(PIL-01) and mirrors its structure exactly, adapted for strategy-generation
output instead of decision-intelligence.

Design invariants
-----------------
- **Fully local mock** — no network calls, no API key, no external dependency.
  The output is derived from a stable hash of the description so tests can
  assert exact structure without worrying about non-determinism.
- **No sentinel branch** — unlike Jentic, there is no external API to fail.
  The tool always returns plausible output when called directly. LLM-level
  gating (only offering the tool when ``trinigence_tool_enabled=True``) is
  enforced in ``market_analyst.py``, not here (T-07-05).
- **Decorator order** — ``@tool`` is outermost (so LangChain sees a
  ``StructuredTool``), ``@meter_tool`` is innermost (so
  ``StructuredTool.func`` IS the metered wrapper — direct ``.func()`` calls
  in tests also pass through metering when a key is present).
- **Single source of truth for toolId** — ``DEFAULT_CONFIG["trinigence_tool_id"]``
  is the ONLY place the toolId is defined; ``@meter_tool`` reads it at decoration
  time (T-07-04). Never hardcode the string elsewhere.
- **No key logging** — implementation takes no secret; never log description
  contents in a way that could contain sensitive info (T-07-06).
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
# Strategy component tables (deterministic — derived from hash, not random)
# ---------------------------------------------------------------------------

_STRATEGY_NAMES = [
    "Momentum Breakout",
    "Mean Reversion Swing",
    "Trend Following Crossover",
    "Volatility Squeeze Expansion",
    "Volume-Weighted Accumulation",
    "Relative Strength Rotation",
    "Gap Fill Reversal",
    "Support/Resistance Bounce",
]

_ENTRY_RULE_TEMPLATES = [
    "Price closes above the {period}-day moving average with above-average volume",
    "RSI crosses above {threshold} from oversold territory",
    "MACD histogram turns positive after a negative divergence",
    "Price breaks above the upper Bollinger Band on rising volume",
    "Volume exceeds the 20-day average by {multiplier}x on a bullish candle",
    "ATR expands above its 14-day average following a consolidation phase",
]

_EXIT_RULE_TEMPLATES = [
    "Price closes below the {period}-day moving average",
    "RSI exceeds {threshold} (overbought) for two consecutive sessions",
    "Trailing stop triggered at {pct}% below the recent swing high",
    "MACD histogram turns negative after a peak",
    "Price reaches the pre-defined profit target of {pct}% from entry",
    "Volume dries up to below 50% of the 20-day average",
]

_INDICATOR_OPTIONS = [
    "RSI(14)",
    "MACD(12,26,9)",
    "Bollinger Bands(20,2)",
    "ATR(14)",
    "Volume SMA(20)",
    "EMA(50)",
    "SMA(200)",
    "VWMA(20)",
]


# ---------------------------------------------------------------------------
# Local mock implementation (separated for testability)
# ---------------------------------------------------------------------------


def _trinigence_strategy_impl(description: str) -> str:
    """Deterministic local mock of Trinigence's NL→strategy-generation API.

    Derives plausible strategy components from a stable hash of the description
    string so test assertions can rely on exact structure (not exact values).
    Output is a JSON string containing the required fields for the demo
    narrative: strategy_name, entry_rules, exit_rules, indicators,
    backtest_summary, source.

    No network, no API key, no external dependency.
    """
    digest = hashlib.sha256(description.encode()).digest()

    # Derive stable indexes and values from the hash (deterministic, not random).
    name_idx = digest[0] % len(_STRATEGY_NAMES)
    strategy_name = _STRATEGY_NAMES[name_idx]

    # Build two entry rules from hash-seeded template indexes and parameters.
    entry_period = 10 + (digest[1] % 40)   # 10–49 days
    entry_threshold = 30 + (digest[2] % 20)  # 30–49 (oversold range)
    entry_multiplier = 1 + (digest[3] % 3)   # 1–3x
    entry_rules = [
        _ENTRY_RULE_TEMPLATES[digest[4] % len(_ENTRY_RULE_TEMPLATES)].format(
            period=entry_period, threshold=entry_threshold, multiplier=entry_multiplier
        ),
        _ENTRY_RULE_TEMPLATES[(digest[5] + 1) % len(_ENTRY_RULE_TEMPLATES)].format(
            period=entry_period + 5, threshold=entry_threshold + 5, multiplier=entry_multiplier
        ),
    ]

    # Build two exit rules.
    exit_pct = 3 + (digest[6] % 12)         # 3–14% stop/target
    exit_threshold = 70 + (digest[7] % 15)  # 70–84 (overbought range)
    exit_rules = [
        _EXIT_RULE_TEMPLATES[digest[8] % len(_EXIT_RULE_TEMPLATES)].format(
            period=entry_period, threshold=exit_threshold, pct=exit_pct
        ),
        _EXIT_RULE_TEMPLATES[(digest[9] + 2) % len(_EXIT_RULE_TEMPLATES)].format(
            period=entry_period + 10, threshold=exit_threshold + 5, pct=exit_pct + 2
        ),
    ]

    # Pick three distinct indicators.
    num_indicators = 3
    indicator_idxs: list[int] = []
    for i in range(10, 10 + num_indicators + 2):
        idx = digest[i % 32] % len(_INDICATOR_OPTIONS)
        if idx not in indicator_idxs:
            indicator_idxs.append(idx)
        if len(indicator_idxs) == num_indicators:
            break
    indicators = [_INDICATOR_OPTIONS[i] for i in indicator_idxs[:num_indicators]]

    # Derive backtest summary metrics from hash.
    win_rate = 50 + (digest[12] % 30)      # 50–79%
    sharpe = round(0.8 + (digest[13] % 20) * 0.1, 2)   # 0.8–2.7
    max_drawdown = 5 + (digest[14] % 15)   # 5–19%

    backtest_summary = (
        f"Backtest over 3 years: win rate {win_rate}%, "
        f"Sharpe ratio {sharpe:.2f}, max drawdown {max_drawdown}%."
    )

    output = {
        "strategy_name": strategy_name,
        "entry_rules": entry_rules,
        "exit_rules": exit_rules,
        "indicators": indicators,
        "backtest_summary": backtest_summary,
        "source": "trinigence (mock)",
    }
    return json.dumps(output, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Public tool: @tool outermost, @meter_tool innermost
# ---------------------------------------------------------------------------


@tool
@meter_tool(DEFAULT_CONFIG["trinigence_tool_id"])  # single source of truth (L6); no colon (Revenium UI)
def get_trinigence_strategy(
    description: Annotated[str, "Natural-language description of the desired trading strategy"],
) -> str:
    """Generate a trading strategy from a natural-language description via Trinigence (mocked, Revenium-metered).

    Returns a JSON string with strategy-generation fields:
    - ``strategy_name``: descriptive strategy label
    - ``entry_rules``: list of entry conditions
    - ``exit_rules``: list of exit conditions
    - ``indicators``: list of technical indicators used
    - ``backtest_summary``: narrative summary of backtest performance
    - ``source``: always ``"trinigence (mock)"``

    This is a fully local mock — no network, no API key required.
    Metered per-call via Revenium's ``@meter_tool`` pipeline so every
    call emits a ``trinigence_strategy`` tool event.

    Requirements:
    - ``trinigence_tool_enabled=True`` in config (controls whether the market
      analyst offers this tool to the LLM — not enforced by the tool itself).
    """
    return _trinigence_strategy_impl(description)
