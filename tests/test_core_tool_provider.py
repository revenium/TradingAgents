"""Keyless tests for the --core-tools provider registration in setup_revenium.py.

The core analyst data-fetch tools (@meter_tool-decorated) auto-create Revenium
ToolResources with a NULL provider. `register_core_tool_provider` (and the
`_CORE_TOOL_IDS` registry) attribute them to a single provider ("jentic") without
touching pricing. These tests run with NO API keys and NO network (DMO-04):

- `_CORE_TOOL_IDS` excludes the three pilot partners and jentic_news (which carry
  their own providers) and contains only colon-free, non-empty toolIds.
- `register_core_tool_provider` is a keyless no-op (empty sk_key → skip, no HTTP).
- dry-run makes no network call even when a key is present.

setup_revenium.py is a standalone script (scripts/ is not a package), so it is
loaded by file path via importlib.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "setup_revenium.py"


def _load_setup_module():
    spec = importlib.util.spec_from_file_location("setup_revenium_under_test", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.unit
def test_core_tool_ids_exclude_partners_and_jentic():
    """Core registry must not include the tools that carry their own provider."""
    mod = _load_setup_module()

    core = set(mod._CORE_TOOL_IDS)
    assert mod._CORE_TOOL_PROVIDER == "jentic"

    # Partners (edgehound/trinigence/saif) and jentic_news are provider-tagged
    # elsewhere — they must NOT be re-tagged as generic core tools.
    excluded = {
        "edgehound_decision",
        "trinigence_strategy",
        "saif_assurance",
        "jentic_news",
    }
    assert core.isdisjoint(excluded), (
        f"_CORE_TOOL_IDS must not overlap partner/jentic toolIds: {core & excluded}"
    )

    # Must include the well-known core data tools.
    assert {"get_stock_data", "get_indicators", "get_news"} <= core

    # All colon-free (Revenium UI rejects ':') and non-empty.
    for tool_id in core:
        assert tool_id and ":" not in tool_id


@pytest.mark.unit
def test_register_core_tool_provider_keyless_is_noop():
    """Empty sk_key → skip and return True, with no network call (DMO-04)."""
    mod = _load_setup_module()

    def _boom(*_a, **_k):
        raise AssertionError("no HTTP call must be made in keyless mode")

    # Any network use would raise; keyless path must not touch requests.
    mod.requests.get = _boom
    mod.requests.post = _boom
    mod.requests.put = _boom

    ok = mod.register_core_tool_provider(
        profitstream_host="https://api.prod.ai.hcapp.io",
        sk_key="",
        team_id="team123",
        tool_id="get_stock_data",
        provider="jentic",
        dry_run=False,
    )
    assert ok is True


@pytest.mark.unit
def test_register_core_tool_provider_dry_run_makes_no_network_call():
    """dry_run=True returns True and issues no HTTP even with a key present."""
    mod = _load_setup_module()

    def _boom(*_a, **_k):
        raise AssertionError("dry-run must not make any HTTP call")

    mod.requests.get = _boom
    mod.requests.post = _boom
    mod.requests.put = _boom

    ok = mod.register_core_tool_provider(
        profitstream_host="https://api.prod.ai.hcapp.io",
        sk_key="rev_sk_fake",
        team_id="team123",
        tool_id="get_stock_data",
        provider="jentic",
        dry_run=True,
    )
    assert ok is True
