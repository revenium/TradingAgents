"""Keyless unit tests for per-role base_url gating in TradingAgentsGraph.__init__.

Verifies the fix for the cross-provider base_url leak (quick-260629-qwz): the CLI
resolves backend_url for the PRIMARY provider only, so a role whose provider differs
from the primary must receive base_url=None — not the primary provider's URL — to
prevent routing requests to the wrong host (live HTTP 404 at Research Manager node).

All tests pass without any API keys set and without network access.  All heavy
collaborators (Revenium handlers, LangGraph compilation, filesystem I/O) are mocked.
"""

from __future__ import annotations

import copy
from unittest.mock import MagicMock

import pytest

from tradingagents.default_config import DEFAULT_CONFIG

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_config(tmp_path, overrides: dict) -> dict:
    """Copy DEFAULT_CONFIG, point I/O dirs at tmp_path, apply overrides."""
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    cfg["data_cache_dir"] = str(tmp_path / "cache")
    cfg["results_dir"] = str(tmp_path / "results")
    cfg["checkpoint_enabled"] = False
    cfg.update(overrides)
    return cfg


def _patch_trading_graph(monkeypatch) -> list[dict]:
    """Patch all heavy collaborators in tradingagents.graph.trading_graph.

    Returns a call-recording list; each create_llm_client call appends a dict
    with keys ``provider``, ``model``, and ``base_url`` so tests can assert
    per-role gating without depending on call order.
    """
    import tradingagents.graph.trading_graph as tg_mod

    calls: list[dict] = []

    def fake_create_llm_client(provider, model, base_url=None, **kwargs):
        calls.append({"provider": provider, "model": model, "base_url": base_url})
        stub = MagicMock()
        stub.get_llm.return_value = MagicMock()
        return stub

    monkeypatch.setattr(tg_mod, "create_llm_client", fake_create_llm_client)

    # Revenium handlers — stub so no key or network is required at construction.
    # Set enabled=False on the handler instance so the dedup guard does not append
    # it to self.callbacks (keeps llm_kwargs callback-free and test-portable).
    rev_handler_stub = MagicMock()
    rev_handler_stub.enabled = False
    rev_handler_cls_stub = MagicMock()
    rev_handler_cls_stub.from_config.return_value = rev_handler_stub
    monkeypatch.setattr(tg_mod, "ReveniumCallbackHandler", rev_handler_cls_stub)
    monkeypatch.setattr(tg_mod, "TradingSignalBillingEmitter", MagicMock())

    # Heavy graph collaborators — stub to avoid LangGraph compilation and I/O.
    monkeypatch.setattr(tg_mod, "TradingMemoryLog", MagicMock())
    monkeypatch.setattr(tg_mod, "GraphSetup", MagicMock())
    monkeypatch.setattr(tg_mod, "Propagator", MagicMock())
    monkeypatch.setattr(tg_mod, "Reflector", MagicMock())
    monkeypatch.setattr(tg_mod, "SignalProcessor", MagicMock())
    monkeypatch.setattr(tg_mod, "get_checkpointer", MagicMock())

    return calls


# ---------------------------------------------------------------------------
# Test A: Cross-provider — non-primary role receives base_url=None
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_cross_provider_deep_base_url_is_none(monkeypatch, tmp_path):
    """Non-primary provider role receives base_url=None; primary role gets backend_url.

    Config: llm_provider=openai (primary), deep_think_provider=anthropic (non-primary),
    quick_think_provider=openai (primary).  With backend_url set to the OpenAI endpoint,
    the deep (Anthropic) client must receive None — forwarding the OpenAI URL to
    Anthropic's SDK client would route the request to the wrong host and produce a 404.
    """
    calls = _patch_trading_graph(monkeypatch)

    from tradingagents.graph.trading_graph import TradingAgentsGraph

    backend_url = "https://api.openai.com/v1"
    cfg = _make_config(tmp_path, {
        "llm_provider": "openai",
        "deep_think_provider": "anthropic",
        "quick_think_provider": "openai",
        "deep_think_llm": "claude-sonnet-4-6",
        "quick_think_llm": "gpt-4.1-mini",
        "backend_url": backend_url,
    })

    TradingAgentsGraph(config=cfg)

    assert len(calls) == 2, (
        f"Expected exactly 2 create_llm_client calls (deep + quick), got {len(calls)}: {calls}"
    )

    deep_call = next(c for c in calls if c["model"] == cfg["deep_think_llm"])
    quick_call = next(c for c in calls if c["model"] == cfg["quick_think_llm"])

    assert deep_call["base_url"] is None, (
        f"Non-primary (anthropic) deep client must receive base_url=None to avoid "
        f"routing to the wrong host; got {deep_call['base_url']!r}"
    )
    assert quick_call["base_url"] == backend_url, (
        f"Primary-matching (openai) quick client must receive backend_url={backend_url!r}; "
        f"got {quick_call['base_url']!r}"
    )


# ---------------------------------------------------------------------------
# Test B: Single-provider — both clients receive backend_url (regression guard)
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_single_provider_both_clients_receive_backend_url(monkeypatch, tmp_path):
    """When all roles share the primary provider, both clients receive backend_url.

    Guards against a regression where per-role gating would incorrectly deny
    backend_url to a client whose provider does equal the primary.
    """
    calls = _patch_trading_graph(monkeypatch)

    from tradingagents.graph.trading_graph import TradingAgentsGraph

    backend_url = "https://gw.example.com/v1"
    cfg = _make_config(tmp_path, {
        "llm_provider": "openai",
        "deep_think_provider": "openai",
        "quick_think_provider": "openai",
        "deep_think_llm": "gpt-4o",
        "quick_think_llm": "gpt-4o-mini",
        "backend_url": backend_url,
    })

    TradingAgentsGraph(config=cfg)

    assert len(calls) == 2, (
        f"Expected exactly 2 create_llm_client calls (deep + quick), got {len(calls)}: {calls}"
    )

    deep_call = next(c for c in calls if c["model"] == cfg["deep_think_llm"])
    quick_call = next(c for c in calls if c["model"] == cfg["quick_think_llm"])

    assert deep_call["base_url"] == backend_url, (
        f"Primary-matching deep client must receive backend_url={backend_url!r}; "
        f"got {deep_call['base_url']!r}"
    )
    assert quick_call["base_url"] == backend_url, (
        f"Primary-matching quick client must receive backend_url={backend_url!r}; "
        f"got {quick_call['base_url']!r}"
    )
