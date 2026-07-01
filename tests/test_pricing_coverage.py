"""Keyless coverage and correctness tests for tradingagents.revenium.pricing.

Validates three properties of compute_cost:
1. Every demo model family resolves to a NON-ZERO estimate (coverage).
2. More-specific variants (mini/nano/versioned) win over broader base keys,
   proving the longest-substring-match is order-independent (ordering).
3. Unknown provider/model combinations return 0.0 and never raise (fail-open).

No API keys or network connections required — compute_cost is a pure function.
"""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# 1. Coverage — every demo family must resolve to a non-zero cost
# ---------------------------------------------------------------------------

_COVERED_MODELS = [
    # (provider, model_name)
    # OpenAI: GPT-4.1 family
    ("openai", "gpt-4.1"),
    ("openai", "gpt-4.1-mini"),
    ("openai", "gpt-4.1-nano"),
    # OpenAI: GPT-4o family
    ("openai", "gpt-4o"),
    ("openai", "gpt-4o-mini"),
    # OpenAI: GPT-5 family (with version-suffixed variants to confirm substring match)
    ("openai", "gpt-5"),
    ("openai", "gpt-5-mini"),
    ("openai", "gpt-5-nano"),
    ("openai", "gpt-5-20250601"),          # version-suffixed base
    ("openai", "gpt-5-mini-20250601"),     # version-suffixed mini
    # OpenAI: GPT-5.4 family
    ("openai", "gpt-5.4"),
    ("openai", "gpt-5.4-mini"),
    # OpenAI: reasoning models
    ("openai", "o3"),
    ("openai", "o4-mini"),
    ("openai", "o1"),
    # Anthropic
    ("anthropic", "claude-sonnet-4-6"),
    ("anthropic", "claude-opus-4-8"),
    ("anthropic", "claude-haiku-4-5"),
]


@pytest.mark.unit
@pytest.mark.parametrize("provider,model", _COVERED_MODELS)
def test_covered_model_returns_nonzero(provider: str, model: str) -> None:
    """Every demo model family resolves to a positive cost for 1000 in + 1000 out tokens."""
    from tradingagents.revenium.pricing import compute_cost

    result = compute_cost(provider, model, 1000, 1000)
    assert result > 0.0, (
        f"compute_cost({provider!r}, {model!r}, 1000, 1000) returned {result!r}; "
        f"expected non-zero — entry missing from _PER_MILLION?"
    )


# ---------------------------------------------------------------------------
# 2. Ordering / longest-match correctness
# ---------------------------------------------------------------------------

class TestLongestMatchOrdering:
    """Assert exact rates that prove specific variants did NOT fall through to a broader base."""

    @pytest.mark.unit
    def test_gpt5_mini_gets_mini_rate_not_base(self) -> None:
        """gpt-5-mini input rate must be 0.25/M (mini), not 1.25/M (base gpt-5)."""
        from tradingagents.revenium.pricing import compute_cost

        result = compute_cost("openai", "gpt-5-mini", 1_000_000, 0)
        assert abs(result - 0.25) < 1e-6, (
            f"gpt-5-mini: expected 0.25, got {result} "
            f"(longest-match may have selected the base gpt-5 rate of 1.25)"
        )

    @pytest.mark.unit
    def test_gpt5_4_mini_gets_mini_rate_not_base(self) -> None:
        """gpt-5.4-mini input rate must be 0.25/M (mini), not 1.25/M (base gpt-5.4 or gpt-5)."""
        from tradingagents.revenium.pricing import compute_cost

        result = compute_cost("openai", "gpt-5.4-mini", 1_000_000, 0)
        assert abs(result - 0.25) < 1e-6, (
            f"gpt-5.4-mini: expected 0.25, got {result} "
            f"(longest-match may have selected the base gpt-5 or gpt-5.4 rate)"
        )

    @pytest.mark.unit
    def test_gpt4_1_nano_gets_nano_rate_not_base_or_mini(self) -> None:
        """gpt-4.1-nano input rate must be 0.10/M, not 2.00 (base) or 0.40 (mini)."""
        from tradingagents.revenium.pricing import compute_cost

        result = compute_cost("openai", "gpt-4.1-nano", 1_000_000, 0)
        assert abs(result - 0.10) < 1e-6, (
            f"gpt-4.1-nano: expected 0.10, got {result} "
            f"(longest-match may have selected gpt-4.1 base=2.00 or mini=0.40)"
        )

    @pytest.mark.unit
    def test_gpt5_base_resolves_correctly_when_no_variant_matches(self) -> None:
        """gpt-5 (bare base name) input rate must be 1.25/M."""
        from tradingagents.revenium.pricing import compute_cost

        result = compute_cost("openai", "gpt-5", 1_000_000, 0)
        assert abs(result - 1.25) < 1e-6, (
            f"gpt-5 base: expected 1.25, got {result}"
        )

    @pytest.mark.unit
    def test_gpt4_1_mini_gets_mini_rate_not_base(self) -> None:
        """gpt-4.1-mini output rate must be 1.60/M (mini), not 8.00/M (base gpt-4.1)."""
        from tradingagents.revenium.pricing import compute_cost

        result = compute_cost("openai", "gpt-4.1-mini", 0, 1_000_000)
        assert abs(result - 1.60) < 1e-6, (
            f"gpt-4.1-mini output: expected 1.60, got {result}"
        )


# ---------------------------------------------------------------------------
# 3. Fail-open regression
# ---------------------------------------------------------------------------

class TestFailOpen:
    """Unknown models and providers must return 0.0 without raising."""

    @pytest.mark.unit
    def test_unknown_model_returns_zero(self) -> None:
        """An entirely unrecognized model returns 0.0 and does not raise."""
        from tradingagents.revenium.pricing import compute_cost

        result = compute_cost("openai", "totally-made-up-model", 1000, 1000)
        assert result == 0.0, f"Expected 0.0, got {result}"

    @pytest.mark.unit
    def test_unknown_provider_returns_zero(self) -> None:
        """An unrecognized provider returns 0.0 even if model substring would match another."""
        from tradingagents.revenium.pricing import compute_cost

        result = compute_cost("unknown", "mystery", 1000, 1000)
        assert result == 0.0, f"Expected 0.0, got {result}"

    @pytest.mark.unit
    def test_provider_mismatch_returns_zero(self) -> None:
        """Correct model substring under wrong provider returns 0.0 (no cross-provider leak)."""
        from tradingagents.revenium.pricing import compute_cost

        # "google" is not in the table; claude-sonnet-4 is anthropic only
        result = compute_cost("google", "claude-sonnet-4", 500_000, 500_000)
        assert result == 0.0, f"Expected 0.0 for wrong provider, got {result}"

    @pytest.mark.unit
    def test_unknown_model_does_not_raise(self) -> None:
        """compute_cost never raises for unknown inputs."""
        from tradingagents.revenium.pricing import compute_cost

        try:
            compute_cost("openai", "totally-made-up-model", 1000, 1000)
        except Exception as exc:  # noqa: BLE001 — fail open, never block the run
            pytest.fail(f"compute_cost raised unexpectedly: {exc!r}")
