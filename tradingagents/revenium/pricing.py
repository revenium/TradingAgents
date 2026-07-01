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
  pages as of 2026-06; broadened to cover all demo families 2026-07; model
  providers change prices without notice).  The Revenium server-side cost
  computation is always authoritative; this local estimate drives only the
  in-app CLI panel and is never billed or logged to Revenium as a cost
  override.
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
- Lookup collects ALL entries where the ``provider`` matches and the
  ``model_substring`` appears in ``model.lower()``, then selects the entry
  with the LONGEST ``model_substring`` (longest-substring-match, order-
  independent).  This ensures more-specific variants (e.g. ``gpt-5-mini``)
  never fall through to a broader base key (e.g. ``gpt-5``), regardless of
  insertion order in the table.
- ``compute_cost`` never raises; ``0.0`` is the explicit fallback.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Pricing table
# [ASSUMED] prices from training data (as of 2026-07) — verify against official
# pricing pages before using for billing.  Revenium server-side cost is
# authoritative; these estimates drive the CLI cost panel only.
# Entries are grouped most-specific-first within each family for human
# readability, but ordering does NOT affect correctness — longest-match wins.
# ---------------------------------------------------------------------------

_PER_MILLION: dict[tuple[str, str], tuple[float, float]] = {
    # (provider_lower, model_substring_lower): (input_$/1M_tokens, output_$/1M_tokens)

    # --- Anthropic ---
    ("anthropic", "claude-sonnet-4"):  (3.00,  15.00),
    ("anthropic", "claude-opus-4"):    (15.00, 75.00),
    ("anthropic", "claude-haiku-4"):   (1.00,   5.00),

    # --- OpenAI: GPT-4.1 family (most-specific variants first for readability) ---
    ("openai",    "gpt-4.1-mini"):     (0.40,   1.60),
    ("openai",    "gpt-4.1-nano"):     (0.10,   0.40),
    ("openai",    "gpt-4.1"):          (2.00,   8.00),

    # --- OpenAI: GPT-4o family ---
    ("openai",    "gpt-4o-mini"):      (0.15,   0.60),
    ("openai",    "gpt-4o"):           (2.50,  10.00),

    # --- OpenAI: GPT-5.4 family ---
    ("openai",    "gpt-5.4-mini"):     (0.25,   2.00),
    ("openai",    "gpt-5.4"):          (1.25,  10.00),

    # --- OpenAI: GPT-5 family ---
    ("openai",    "gpt-5-mini"):       (0.25,   2.00),
    ("openai",    "gpt-5-nano"):       (0.05,   0.40),
    ("openai",    "gpt-5"):            (1.25,  10.00),

    # --- OpenAI: reasoning models ---
    ("openai",    "o4-mini"):          (1.10,   4.40),
    ("openai",    "o3"):               (2.00,   8.00),
    ("openai",    "o1"):               (15.00, 60.00),
}


def compute_cost(
    provider: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
) -> float:
    """Return an estimated dollar cost for a single LLM completion.

    Looks up the ``(provider, model)`` pair in the local price table using a
    longest-substring match on the model name (order-independent).  All table
    entries matching the provider and whose ``model_substring`` appears in
    ``model.lower()`` are collected; the entry with the longest
    ``model_substring`` wins.  Returns ``0.0`` for any combination not in the
    table — never raises.

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

    # Collect all matching entries for this provider, then pick the longest
    # model_substring match (most-specific wins, order-independent).
    best_key: tuple[str, str] | None = None
    best_len = -1
    for (table_provider, model_substring) in _PER_MILLION:
        if table_provider == provider_lower and model_substring in model_lower:
            if len(model_substring) > best_len:
                best_len = len(model_substring)
                best_key = (table_provider, model_substring)

    if best_key is None:
        return 0.0

    inp_rate, out_rate = _PER_MILLION[best_key]
    return (input_tokens * inp_rate + output_tokens * out_rate) / 1_000_000.0
