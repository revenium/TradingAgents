"""Keyless tests for the --core-tools registration in setup_revenium.py.

The core analyst data-fetch tools (@meter_tool-decorated) auto-create Revenium
ToolResources with a NULL provider and no pricing. The `_CORE_TOOLS` registry
attributes each to a provider ("jentic") AND gives it a per-call COUNT price,
registered via the shared `register_partner_tool` path. These tests run with NO
API keys and NO network (DMO-04):

- `_CORE_TOOLS` excludes the three pilot partners and jentic_news (which carry
  their own registrations) and every entry has a colon-free toolId + a price.
- `register_partner_tool` (the shared registration path) is a keyless no-op and
  makes no network call in dry-run.

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
def test_core_tools_registry_excludes_partners_and_jentic():
    """Core registry must not include the tools that are registered elsewhere."""
    mod = _load_setup_module()

    core_ids = {e["tool_id"] for e in mod._CORE_TOOLS}
    assert mod._CORE_TOOL_PROVIDER == "jentic"

    excluded = {
        "edgehound_decision",
        "trinigence_strategy",
        "saif_assurance",
        "jentic_news",
    }
    assert core_ids.isdisjoint(excluded), (
        f"_CORE_TOOLS must not overlap partner/jentic toolIds: {core_ids & excluded}"
    )
    assert {"get_stock_data", "get_indicators", "get_news"} <= core_ids


@pytest.mark.unit
def test_core_tools_all_have_colon_free_id_and_price():
    """Every core tool must carry a colon-free toolId and a parseable price (all priced)."""
    mod = _load_setup_module()

    for entry in mod._CORE_TOOLS:
        tool_id = entry["tool_id"]
        assert tool_id and ":" not in tool_id
        assert entry.get("name")
        price = entry["default_price"]
        assert float(price) > 0, f"{tool_id} must have a positive per-call price, got {price!r}"


@pytest.mark.unit
def test_register_partner_tool_keyless_is_noop():
    """Empty sk_key → skip and return True, with no network call (DMO-04).

    The core tools register through register_partner_tool, so its keyless
    contract covers the --core-tools path too.
    """
    mod = _load_setup_module()

    def _boom(*_a, **_k):
        raise AssertionError("no HTTP call must be made in keyless mode")

    mod.requests.get = _boom
    mod.requests.post = _boom
    mod.requests.put = _boom

    ok = mod.register_partner_tool(
        profitstream_host="https://api.prod.ai.hcapp.io",
        sk_key="",
        team_id="team123",
        tool_id="get_stock_data",
        name="Stock Data",
        description="Core analyst data-fetch tool.",
        provider="jentic",
        unit_price="0.01",
        dry_run=False,
    )
    assert ok is True


@pytest.mark.unit
def test_register_partner_tool_dry_run_makes_no_network_call():
    """dry_run=True returns True and issues no HTTP even with a key present."""
    mod = _load_setup_module()

    def _boom(*_a, **_k):
        raise AssertionError("dry-run must not make any HTTP call")

    mod.requests.get = _boom
    mod.requests.post = _boom
    mod.requests.put = _boom

    ok = mod.register_partner_tool(
        profitstream_host="https://api.prod.ai.hcapp.io",
        sk_key="rev_sk_fake",
        team_id="team123",
        tool_id="get_stock_data",
        name="Stock Data",
        description="Core analyst data-fetch tool.",
        provider="jentic",
        unit_price="0.01",
        dry_run=True,
    )
    assert ok is True
