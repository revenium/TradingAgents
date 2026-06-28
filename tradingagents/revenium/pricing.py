"""Local cost-estimate lookup for the Phase 4 CLI cost panel.

This module provides a provider-agnostic ``compute_cost`` function that returns
an estimated dollar amount for a given LLM call based on training-data price
values.  It is the single source of truth for the ``agent_costs["cost"]`` field
accumulated in ``ReveniumCallbackHandler.on_llm_end``.

Design rationale:
- Pattern mirrors ``tradingagents/llm_clients/capabilities.py``: a declarative
  dict-based lookup table keyed by ``(provider_lower, model_substring_lower)``
  rather than scattered ``if`` ladders.  Adding a new model is a single-line
  table entry.
- Prices are [ASSUMED] training-data estimates (verified against public pricing
  pages as of 2026-06; model providers change prices without notice).  The
  Revenium server-side cost computation is always authoritative; this local
  estimate drives only the in-app CLI panel and is never billed or logged to
  Revenium as a cost override.
- ``compute_cost`` returns ``0.0`` for any unknown provider/model combination
  (fail-open) — a missing price never raises and never crashes the ``Live``
  refresh loop it is called from (T-04-02 mitigation).
- The substring-match approach keeps the function provider-agnostic per
  CLAUDE.md conventions (no hardcoded single provider).  The OpenRouter
  migration (later phase) will add rows to the table rather than restructuring
  the lookup.

Key invariants:
- Every known ``(provider, model_substring)`` entry has exactly two rates:
  ``(input_$/1M_tokens, output_$/1M_tokens)``.
- Lookup iterates over the table in insertion order; the first ``provider``
  match whose ``model_substring`` appears in ``model.lower()`` wins.
- ``compute_cost`` never raises; ``0.0`` is the explicit fallback.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Pricing table
# [ASSUMED] prices from training data (as of 2026-06) — verify against official
# pricing pages before using for billing.  Revenium server-side cost is
# authoritative; these estimates drive the CLI cost panel only.
# ---------------------------------------------------------------------------

_PER_MILLION: dict[tuple[str, str], tuple[float, float]] = {
    # (provider_lower, model_substring_lower): (input_$/1M_tokens, output_$/1M_tokens)
    ("anthropic", "claude-sonnet-4"):  (3.00,  15.00),
    ("openai",    "gpt-4.1-mini"):     (0.40,   1.60),
    ("openai",    "gpt-4o-mini"):      (0.15,   0.60),
    ("openai",    "gpt-4o"):           (5.00,  15.00),
}


def compute_cost(
    provider: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
) -> float:
    """Return an estimated dollar cost for a single LLM completion.

    Looks up the ``(provider, model)`` pair in the local price table using a
    substring match on the model name.  Returns ``0.0`` for any combination
    not in the table — never raises.

    Args:
        provider:      Provider label as returned by ``_detect_provider``
                       (e.g. ``"anthropic"``, ``"openai"``, ``"google"``,
                       ``"unknown"``).  Case-insensitive.
        model:         Model name string as reported by the LangChain serialized
                       dict (e.g. ``"claude-sonnet-4-6"``).  Case-insensitive;
                       matched against table substrings.
        input_tokens:  Number of prompt/input tokens consumed.
        output_tokens: Number of completion/output tokens generated.

    Returns:
        Estimated cost in USD as a ``float``.  ``0.0`` when the provider/model
        pair is unknown or the table has no entry.
    """
    provider_lower = provider.lower()
    model_lower = model.lower()

    for (table_provider, model_substring), (inp_rate, out_rate) in _PER_MILLION.items():
        if table_provider == provider_lower and model_substring in model_lower:
            return (input_tokens * inp_rate + output_tokens * out_rate) / 1_000_000.0

    return 0.0
