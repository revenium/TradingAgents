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

    @pytest.mark.unit
    def test_non_budget_exception_from_check_enforcement_fails_open(self, monkeypatch):
        """A non-BudgetExceededError from check_enforcement must NOT abort the run (CR-01).

        ONLY BudgetExceededError is the deliberate exception to the fail-open
        convention (D-03).  Every other error from the enforcement engine — a
        network blip, a malformed compiled-rules payload, an SDK error — must be
        swallowed so a single Revenium hiccup never crashes the live trading run.
        The gate must continue into the normal capture path afterwards.
        """
        import tradingagents.revenium.callback as cb

        monkeypatch.setenv("REVENIUM_CIRCUIT_BREAKER_ENABLED", "true")

        def _boom(_payload):
            raise RuntimeError("revenium enforcement network blip")

        monkeypatch.setattr(cb, "check_enforcement", _boom)

        mock_client = MagicMock()
        mock_client.enabled = True
        handler = cb.ReveniumCallbackHandler(
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

        # Must NOT raise — the non-budget error fails open and the run continues.
        handler.on_chat_model_start(serialized, [], run_id="test-run-id")

        # Fail-open means the normal capture path still ran after the swallowed error.
        assert "test-run-id" in handler._call_state


# ---------------------------------------------------------------------------
# Tests: _get_enforcement_base_url() config resolution (GAP-CTL03-01)
# ---------------------------------------------------------------------------

class TestEnforcementBaseUrlResolution:
    """Config-resolution tests for enforcement._get_enforcement_base_url() (GAP-CTL03-01).

    These tests are keyless (no live credentials, no network — D-10 discipline).
    They prove:
    1. When REVENIUM_ENFORCEMENT_BASE_URL is set, the function returns it verbatim
       (trailing slash stripped), so the compiled-rules feed path is correct.
    2. When REVENIUM_ENFORCEMENT_BASE_URL is unset, the function falls back to the
       bare metering origin (scheme://netloc with no context path) — documenting
       the 404 cause that GAP-CTL03-01 closes via .env.example documentation.
    """

    @pytest.mark.unit
    def test_explicit_enforcement_base_url_returned_verbatim(self, monkeypatch):
        """_get_enforcement_base_url() returns REVENIUM_ENFORCEMENT_BASE_URL verbatim (trailing slash stripped).

        Satisfies GAP-CTL03-01 constraint (c): when the operator sets
        REVENIUM_ENFORCEMENT_BASE_URL=https://api.revenium.ai/profitstream the
        SDK uses that exact value as the base for the compiled-rules fetch.
        """
        monkeypatch.setenv("REVENIUM_ENFORCEMENT_BASE_URL", "https://api.revenium.ai/profitstream")
        assert enforcement._get_enforcement_base_url() == "https://api.revenium.ai/profitstream"

    @pytest.mark.unit
    def test_fallback_to_bare_metering_origin_when_enforcement_url_unset(self, monkeypatch):
        """Without REVENIUM_ENFORCEMENT_BASE_URL the function falls back to the bare metering origin.

        Documents the 404 cause identified in the GAP-CTL03-01 spike: the bare origin
        (https://api.revenium.ai) lacks the /profitstream context path required by the
        compiled-rules feed, so the enforcement gate can never arm without the explicit var.
        """
        monkeypatch.delenv("REVENIUM_ENFORCEMENT_BASE_URL", raising=False)
        # Set the metering base URL deterministically to avoid ambient env dependency.
        monkeypatch.setenv("REVENIUM_METERING_BASE_URL", "https://api.revenium.ai/meter/")
        result = enforcement._get_enforcement_base_url()
        assert result == "https://api.revenium.ai"
        assert "/profitstream" not in result


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


# ---------------------------------------------------------------------------
# Tests: agenticJobId injected into metering payload when trace_id is set
# ---------------------------------------------------------------------------

class TestAgenticJobIdInMeteringPayload:
    """on_llm_end attaches extra_body={"agenticJobId": trace_id} when trace_id is non-empty (GAP-04-LINK).

    This links each per-agent metering completion to the billing job whose
    agenticJobId IS the run trace_id.  Fail-open: no extra_body when trace_id is "".
    """

    def _make_llm_result(self, input_tokens: int = 50, output_tokens: int = 20):
        from langchain_core.messages import AIMessage
        from langchain_core.outputs import ChatGeneration, LLMResult

        msg = AIMessage(content="ok")
        msg.usage_metadata = {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
        }
        return LLMResult(generations=[[ChatGeneration(message=msg)]])

    def _make_serialized(self, model: str = "gpt-4.1-mini", provider: str = "openai") -> dict:
        return {
            "id": [f"langchain_{provider}", "chat_models", f"Chat{provider.capitalize()}"],
            "kwargs": {"model_name": model},
        }

    def _flush(self, handler, timeout: float = 2.0) -> None:
        for t in list(handler._threads):
            t.join(timeout=timeout)

    @pytest.mark.unit
    def test_agentic_job_id_present_when_trace_id_set(self, monkeypatch):
        """Metering payload includes extra_body={"agenticJobId": trace_id} when trace_id is non-empty."""
        import uuid

        from tradingagents.revenium.callback import ReveniumCallbackHandler

        captured_payloads: list[dict] = []

        mock_client = MagicMock()
        mock_client.enabled = True
        mock_client.meter_ai_completion.side_effect = lambda p: captured_payloads.append(dict(p))

        handler = ReveniumCallbackHandler(
            client=mock_client,
            attribution={
                "subscriber_id": "test@example.com",
                "organizationName": "TestOrg",
                "productName": "test-product",
                "api_key": "rev_mk_test",
            },
            task_type_map={},
        )

        trace_id = uuid.uuid4().hex
        handler.begin_run(trace_id, "NVDA", "2026-06-29")

        run_id = "test-run-agentic-job-id"
        serialized = self._make_serialized()
        handler.on_chat_model_start(serialized, [], run_id=run_id)
        handler.on_llm_end(self._make_llm_result(), run_id=run_id)
        self._flush(handler)

        assert len(captured_payloads) == 1, f"Expected 1 metering call, got {len(captured_payloads)}"
        payload = captured_payloads[0]
        assert "extra_body" in payload, "payload must contain extra_body when trace_id is set"
        assert payload["extra_body"] == {"agenticJobId": trace_id}, (
            f"extra_body must be {{agenticJobId: {trace_id!r}}}, got {payload.get('extra_body')!r}"
        )

    @pytest.mark.unit
    def test_no_extra_body_when_trace_id_empty(self, monkeypatch):
        """Metering payload has no extra_body when no trace_id is set (keyless / no begin_run)."""
        from tradingagents.revenium.callback import ReveniumCallbackHandler

        captured_payloads: list[dict] = []

        mock_client = MagicMock()
        mock_client.enabled = True
        mock_client.meter_ai_completion.side_effect = lambda p: captured_payloads.append(dict(p))

        handler = ReveniumCallbackHandler(
            client=mock_client,
            attribution={
                "subscriber_id": "test@example.com",
                "organizationName": "TestOrg",
                "productName": "test-product",
                "api_key": "rev_mk_test",
            },
            task_type_map={},
        )
        # No begin_run — trace_id will be empty string

        run_id = "test-run-no-trace"
        serialized = self._make_serialized()
        handler.on_chat_model_start(serialized, [], run_id=run_id)
        handler.on_llm_end(self._make_llm_result(), run_id=run_id)
        self._flush(handler)

        assert len(captured_payloads) == 1, f"Expected 1 metering call, got {len(captured_payloads)}"
        payload = captured_payloads[0]
        assert "extra_body" not in payload, (
            f"extra_body must be absent when trace_id is empty, got {payload.get('extra_body')!r}"
        )
