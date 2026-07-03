"""Combined 3-partner integration test: 3 distinct tool events in one run (PIL-04).

Proves Success Criterion 1: a single enabled run emits exactly 3 distinct
Revenium tool events whose tool_ids are {edgehound_decision, trinigence_strategy,
saif_assurance}, covering all three pilot-partner slices (PIL-01..PIL-03).

All tests are @pytest.mark.unit and pass without any API keys or network access.

Coverage:
- PIL-04: with all three partner flags enabled and _send_tool_event patched, calling
  the three metered units (get_edgehound_decision.func, get_trinigence_strategy.func,
  run_saif_assurance) captures exactly 3 tool events with distinct tool_ids.
- PIL-04: the set of captured tool_ids equals {edgehound_decision, trinigence_strategy,
  saif_assurance} — 3 DISTINCT partner tool events (Success Criterion 1).
- PIL-04: all three toolIds are colon-free.
- PIL-04: all three toolIds are sourced from their DEFAULT_CONFIG keys (L6 invariant).

Design notes
------------
- Edgehound and Trinigence are LangChain @tools; call via .func(...) to bypass
  the @tool wrapper and pass directly through @meter_tool.
- SAIF is a gate (NOT a @tool); call run_saif_assurance(...) directly (no .func).
- Config is restored in a finally block so this test is side-effect-free.
"""

from __future__ import annotations

from unittest.mock import call, patch

import pytest


# ---------------------------------------------------------------------------
# Sample PM decision markdown for the SAIF gate call
# ---------------------------------------------------------------------------

_SAMPLE_PM_HOLD = """\
**Rating**: Hold

**Executive Summary**: Maintain Hold on NVDA — balanced risk/reward.

**Investment Thesis**: GPU demand offset by near-term supply constraints."""


# ---------------------------------------------------------------------------
# Test 1: 3 distinct partner tool events in one combined run (PIL-04 Success Criterion 1)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_three_partner_tool_events_distinct():
    """3 distinct partner tool events fire in one enabled run (PIL-04 Success Criterion 1).

    With all three partner flags enabled and _send_tool_event patched, calling:
      - get_edgehound_decision.func(query)       → edgehound_decision event
      - get_trinigence_strategy.func(description)→ trinigence_strategy event
      - run_saif_assurance(pm_decision_text)     → saif_assurance event

    captures exactly 3 tool events with distinct tool_ids matching the three
    DEFAULT_CONFIG keys.
    """
    from tradingagents.agents.utils.agent_utils import (
        get_edgehound_decision,
        get_trinigence_strategy,
    )
    from tradingagents.agents.utils.saif_gate import run_saif_assurance
    from tradingagents.dataflows.config import get_config, set_config
    from tradingagents.default_config import DEFAULT_CONFIG

    orig = get_config()
    set_config({
        # Enable all three partner tools
        "edgehound_tool_enabled": True,
        "trinigence_tool_enabled": True,
        "saif_tool_enabled": True,
        # Provide a metering key so @meter_tool fires (not a no-op)
        "revenium_api_key": "rev_mk_test",
        "revenium_api_url": "https://api.revenium.ai",
        "revenium_organization_name": "Revenium-Research-Desk",
        "revenium_product_name": "trading-signal",
        "revenium_subscriber_id": "test@example.com",
    })

    try:
        with patch("revenium_metering.decorator._send_tool_event") as mock_send:
            # Edgehound: LangChain @tool — call via .func to hit the @meter_tool layer
            get_edgehound_decision.func("NVDA momentum breakout entry signal")

            # Trinigence: LangChain @tool — call via .func to hit the @meter_tool layer
            get_trinigence_strategy.func("momentum breakout strategy for NVDA in tech sector")

            # SAIF: gate (NOT a @tool) — call directly (no .func wrapper)
            run_saif_assurance(_SAMPLE_PM_HOLD)

        # --- Assertion 1: exactly 3 tool events captured ---
        assert mock_send.call_count == 3, (
            f"Expected exactly 3 partner tool events, got {mock_send.call_count}. "
            f"Calls: {[c.kwargs.get('tool_id') for c in mock_send.call_args_list]}"
        )

        # --- Assertion 2: 3 DISTINCT tool_ids equal the expected set ---
        captured_tool_ids = {
            c.kwargs["tool_id"]
            for c in mock_send.call_args_list
        }
        expected_tool_ids = {
            DEFAULT_CONFIG["edgehound_tool_id"],
            DEFAULT_CONFIG["trinigence_tool_id"],
            DEFAULT_CONFIG["saif_tool_id"],
        }
        assert captured_tool_ids == expected_tool_ids, (
            f"Expected tool_ids {expected_tool_ids!r}, "
            f"got {captured_tool_ids!r}"
        )

    finally:
        set_config(orig)


# ---------------------------------------------------------------------------
# Test 2: all three toolIds are colon-free and sourced from DEFAULT_CONFIG (L6)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_all_partner_tool_ids_colon_free_from_config():
    """All three partner toolIds are colon-free and sourced from DEFAULT_CONFIG (L6, T-07-10).

    Ensures that SAIF's toolId follows the same single-source-of-truth invariant
    as Edgehound (PIL-01) and Trinigence (PIL-02): the value in DEFAULT_CONFIG is
    the authoritative string used both by @meter_tool at decoration time and by
    the ToolResource registration in setup_revenium.py.
    """
    from tradingagents.default_config import DEFAULT_CONFIG

    partner_keys = [
        "edgehound_tool_id",
        "trinigence_tool_id",
        "saif_tool_id",
    ]
    expected_values = {
        "edgehound_tool_id": "edgehound_decision",
        "trinigence_tool_id": "trinigence_strategy",
        "saif_tool_id": "saif_assurance",
    }

    for key in partner_keys:
        tool_id = DEFAULT_CONFIG[key]

        # Must be the expected stable default (no env override in CI)
        assert tool_id == expected_values[key], (
            f"DEFAULT_CONFIG[{key!r}] == {tool_id!r}; expected {expected_values[key]!r}"
        )

        # Must NOT contain ':' — Revenium UI rejects colons in toolIds
        assert ":" not in tool_id, (
            f"DEFAULT_CONFIG[{key!r}] must not contain ':'; got {tool_id!r} "
            f"(Revenium UI validation rejects colons)"
        )
