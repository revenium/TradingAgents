"""Tests for the Revenium enforcement gate — check_enforcement wiring in the callback handler.

All tests are unit-level (marker: unit) and pass without any live
REVENIUM_METERING_API_KEY or REVENIUM_CIRCUIT_BREAKER_ENABLED.
All Revenium enforcement checks are mocked via _seed_rules().

Key invariants validated:
- check_enforcement() raises BudgetExceededError for a breached enforce-mode rule.
- check_enforcement() is a no-op when REVENIUM_BYPASS=true.
- shadowMode:true rules never block, even when breached.
- BudgetExceededError from check_enforcement() propagates OUT of on_chat_model_start
  (is NOT caught by the fail-open except block) — D-03.
- REVENIUM_CIRCUIT_BREAKER_ENABLED unset → check_enforcement() is a no-op.
"""

from __future__ import annotations

import importlib
from unittest.mock import MagicMock

import pytest
from revenium_middleware._core import enforcement
from revenium_middleware._core.exceptions import BudgetExceededError


# ---------------------------------------------------------------------------
# Autouse fixture — enforcement module isolation
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_enforcement(monkeypatch):
    """Isolate enforcement module state across tests.

    Delenvs all circuit-breaker env vars, reloads the enforcement module to
    reset its module-global cache state, then calls stop_polling() on cleanup
    to shut down any daemon poll threads started during the test.
    """
    for var in (
        "REVENIUM_CIRCUIT_BREAKER_ENABLED",
        "REVENIUM_BYPASS",
        "REVENIUM_CB_FAIL_MODE",
        "REVENIUM_TEAM_ID",
        "REVENIUM_METERING_API_KEY",
        "REVENIUM_CACHE_DIR",  # prevents _load_cache_from_disk from reading a stale file
    ):
        monkeypatch.delenv(var, raising=False)
    importlib.reload(enforcement)
    yield
    enforcement.stop_polling()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _seed_rules(monkeypatch, rules: list, *, initialized: bool = True) -> None:
    """Inject rules into the enforcement cache, bypassing the network poller.

    Monkeypatches the enforcement module's cache fields directly — no live
    Revenium keys required (D-10 keyless discipline).
    """
    monkeypatch.setattr(enforcement, "_cached_rules", list(rules))
    monkeypatch.setattr(enforcement, "_cache_timestamp", float("inf"))
    monkeypatch.setattr(enforcement, "_cache_initialized", initialized)
    monkeypatch.setattr(enforcement, "_ensure_poller_running", lambda: None)
    monkeypatch.setattr(enforcement, "_fetch_rules", lambda: None)


def _make_serialized(model: str = "gpt-4.1-mini", provider: str = "openai") -> dict:
    """Build a synthetic serialized LLM dict as LangChain passes to on_chat_model_start."""
    return {
        "id": [f"langchain_{provider}", "chat_models", f"Chat{provider.capitalize()}"],
        "kwargs": {"model_name": model},
    }


# ---------------------------------------------------------------------------
# Tests: enforcement engine behavior
# ---------------------------------------------------------------------------

class TestEnforcementEngine:
    """Direct tests for check_enforcement() — the enforcement engine's core behavior.

    These tests exercise the SDK enforcement engine directly, without the callback
    handler layer.  All four PASS in the RED phase because the engine is already
    functional; only the handler wiring (TestCallbackHandlerEnforcementGate) has a
    RED test.
    """

    @pytest.mark.unit
    def test_check_enforcement_raises_when_rule_breached(self, monkeypatch):
        """check_enforcement raises BudgetExceededError for a breached enforce-mode rule."""
        monkeypatch.setenv("REVENIUM_CIRCUIT_BREAKER_ENABLED", "true")
        _seed_rules(monkeypatch, [{
            "ruleId": 1,
            "name": "demo-budget",
            "breached": True,
            "shadowMode": False,
            "threshold": 1.0,
            "currentValue": 1.5,
            "resetsAt": "2026-06-29T00:00:00Z",
        }])
        with pytest.raises(BudgetExceededError) as exc_info:
            enforcement.check_enforcement({})
        err = exc_info.value
        assert err.rule_name == "demo-budget"
        assert err.threshold == 1.0
        assert err.current_value == 1.5

    @pytest.mark.unit
    def test_bypass_env_disables_enforcement(self, monkeypatch):
        """REVENIUM_BYPASS=true short-circuits even when a breached rule is cached."""
        monkeypatch.setenv("REVENIUM_CIRCUIT_BREAKER_ENABLED", "true")
        monkeypatch.setenv("REVENIUM_BYPASS", "true")
        _seed_rules(monkeypatch, [{"name": "would-block", "breached": True, "shadowMode": False}])
        enforcement.check_enforcement({})  # must not raise

    @pytest.mark.unit
    def test_shadow_mode_rule_does_not_block(self, monkeypatch):
        """shadowMode:true rules are observe-only and must never block the run (D-07)."""
        monkeypatch.setenv("REVENIUM_CIRCUIT_BREAKER_ENABLED", "true")
        _seed_rules(monkeypatch, [{"name": "shadow", "breached": True, "shadowMode": True}])
        enforcement.check_enforcement({})  # must not raise

    @pytest.mark.unit
    def test_cb_disabled_env_is_noop(self, monkeypatch):
        """check_enforcement is a no-op when REVENIUM_CIRCUIT_BREAKER_ENABLED is unset (D-10)."""
        # Do NOT set REVENIUM_CIRCUIT_BREAKER_ENABLED — CB disabled by default
        _seed_rules(monkeypatch, [{"name": "would-block", "breached": True, "shadowMode": False}])
        enforcement.check_enforcement({})  # must not raise


# ---------------------------------------------------------------------------
# Tests: BudgetExceededError propagation through the callback handler
# ---------------------------------------------------------------------------

class TestCallbackHandlerEnforcementGate:
    """BudgetExceededError propagation from on_chat_model_start (D-03 gate).

    The propagation test is the RED test for Task 1: it FAILS until Task 2 wires
    check_enforcement() into on_chat_model_start outside the fail-open except block.
    """

    @pytest.mark.unit
    def test_budget_exceeded_propagates_from_on_chat_model_start(self, monkeypatch):
        """BudgetExceededError from check_enforcement escapes the callback handler.

        RED: fails until the enforcement gate is wired in callback.py (Task 2).
        The gate must sit BEFORE the fail-open try/except so BudgetExceededError
        propagates to _run_graph / CLI (D-03).
        """
        from tradingagents.revenium.callback import ReveniumCallbackHandler

        monkeypatch.setenv("REVENIUM_CIRCUIT_BREAKER_ENABLED", "true")
        _seed_rules(monkeypatch, [{
            "name": "demo-budget",
            "breached": True,
            "shadowMode": False,
            "threshold": 1.0,
            "currentValue": 1.5,
        }])

        mock_client = MagicMock()
        mock_client.enabled = True
        handler = ReveniumCallbackHandler(
            client=mock_client,
            attribution={
                "subscriber_id": "john.demic+trading@revenium.io",
                "organizationName": "Revenium-Research-Desk",
                "productName": "trading-signal",
                "api_key": "rev_mk_test",
            },
            task_type_map={},
        )
        serialized = _make_serialized()

        with pytest.raises(BudgetExceededError):
            handler.on_chat_model_start(serialized, [], run_id="test-run-id")

    @pytest.mark.unit
    def test_normal_call_proceeds_when_no_rule_breached(self, monkeypatch):
        """When no rule is breached, on_chat_model_start proceeds without raising."""
        from tradingagents.revenium.callback import ReveniumCallbackHandler

        monkeypatch.setenv("REVENIUM_CIRCUIT_BREAKER_ENABLED", "true")
        _seed_rules(monkeypatch, [])  # empty rules → no breach

        mock_client = MagicMock()
        mock_client.enabled = True
        handler = ReveniumCallbackHandler(
            client=mock_client,
            attribution={
                "subscriber_id": "john.demic+trading@revenium.io",
                "organizationName": "Revenium-Research-Desk",
                "productName": "trading-signal",
                "api_key": "rev_mk_test",
            },
            task_type_map={},
        )
        serialized = _make_serialized()

        # Must not raise — run proceeds normally with no breached rules
        handler.on_chat_model_start(serialized, [], run_id="test-run-id")

    @pytest.mark.unit
    def test_bypass_disables_gate_in_callback(self, monkeypatch):
        """REVENIUM_BYPASS=true disables the enforcement gate within the callback (D-10)."""
        from tradingagents.revenium.callback import ReveniumCallbackHandler

        monkeypatch.setenv("REVENIUM_CIRCUIT_BREAKER_ENABLED", "true")
        monkeypatch.setenv("REVENIUM_BYPASS", "true")
        _seed_rules(monkeypatch, [{"name": "would-block", "breached": True, "shadowMode": False}])

        mock_client = MagicMock()
        mock_client.enabled = True
        handler = ReveniumCallbackHandler(
            client=mock_client,
            attribution={
                "subscriber_id": "john.demic+trading@revenium.io",
                "organizationName": "Revenium-Research-Desk",
                "productName": "trading-signal",
                "api_key": "rev_mk_test",
            },
            task_type_map={},
        )
        serialized = _make_serialized()

        # Must not raise — bypass is set (keeps keyless test suite green — DMO-04)
        handler.on_chat_model_start(serialized, [], run_id="test-run-id")


# ---------------------------------------------------------------------------
# Tests: _render_budget_halt_panel (CTL-02, D-05, T-03-01)
# ---------------------------------------------------------------------------

class TestBudgetHaltPanel:
    """Tests for _render_budget_halt_panel in cli/main.py (CTL-02, D-05).

    Verifies that the halt panel renders correctly and never leaks API key
    values (T-03-01 — Information Disclosure mitigation).
    """

    def _make_handler_with_costs(self):
        """Return a ReveniumCallbackHandler stub with populated agent_costs."""
        from tradingagents.revenium.callback import ReveniumCallbackHandler

        handler = ReveniumCallbackHandler(
            client=MagicMock(),
            attribution={
                "subscriber_id": "john.demic+trading@revenium.io",
                "organizationName": "Revenium-Research-Desk",
                "productName": "trading-signal",
                "api_key": "rev_mk_secretkey123",
            },
            task_type_map={},
        )
        # Inject synthetic per-agent cost data
        handler.agent_costs["Market Analyst"] = {"input_tokens": 500, "output_tokens": 200}
        handler.agent_costs["Bull Researcher"] = {"input_tokens": 800, "output_tokens": 350}
        return handler

    @pytest.mark.unit
    def test_render_budget_halt_panel_renders_without_raising(self):
        """_render_budget_halt_panel renders without raising given a BudgetExceededError."""
        from rich.console import Console
        from cli.main import _render_budget_halt_panel

        err = BudgetExceededError(
            "Budget exceeded",
            rule_name="TradingAgents Demo Budget",
            current_value=1.25,
            threshold=1.00,
            resets_at="2026-06-29T00:00:00Z",
            rule_id=42,
        )
        rec_console = Console(record=True)
        handler = self._make_handler_with_costs()

        # Must not raise
        _render_budget_halt_panel(rec_console, err, handler)

    @pytest.mark.unit
    def test_render_budget_halt_panel_content_and_no_key_leakage(self):
        """Rendered output contains rule name, spent, limit, per-agent rows, no raw key values (T-03-01)."""
        from rich.console import Console
        from cli.main import _render_budget_halt_panel

        err = BudgetExceededError(
            "Budget exceeded",
            rule_name="TradingAgents Demo Budget",
            current_value=1.25,
            threshold=1.00,
            resets_at="2026-06-29T00:00:00Z",
            rule_id=42,
        )
        rec_console = Console(record=True)
        handler = self._make_handler_with_costs()

        _render_budget_halt_panel(rec_console, err, handler)
        output = rec_console.export_text()

        # Required content
        assert "TradingAgents Demo Budget" in output, "rule_name must appear in panel"
        assert "1.2500" in output, "spent (current_value) must appear in panel"
        assert "1.0000" in output, "limit (threshold) must appear in panel"
        assert "Market Analyst" in output, "per-agent row must appear"
        assert "Bull Researcher" in output, "per-agent row must appear"

        # T-03-01: no raw key leakage
        assert "rev_mk_" not in output, "raw rev_mk_* key must never appear in panel output"
        assert "rev_sk_" not in output, "raw rev_sk_* key must never appear in panel output"
