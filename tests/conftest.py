"""Shared pytest fixtures that prevent CI hangs when API keys are absent."""

import os
from unittest.mock import MagicMock, patch

import pytest


def pytest_configure(config):
    for marker in ("unit", "integration", "smoke"):
        config.addinivalue_line("markers", f"{marker}: {marker}-level tests")


_API_KEY_ENV_VARS = (
    "OPENAI_API_KEY",
    "GOOGLE_API_KEY",
    "ANTHROPIC_API_KEY",
    "XAI_API_KEY",
    "DEEPSEEK_API_KEY",
    "DASHSCOPE_API_KEY",
    "DASHSCOPE_CN_API_KEY",
    "ZHIPU_API_KEY",
    "ZHIPU_CN_API_KEY",
    "MINIMAX_API_KEY",
    "MINIMAX_CN_API_KEY",
    "OPENROUTER_API_KEY",
    "AZURE_OPENAI_API_KEY",
    "ALPHA_VANTAGE_API_KEY",
)


@pytest.fixture(autouse=True)
def _dummy_api_keys(monkeypatch):
    for env_var in _API_KEY_ENV_VARS:
        monkeypatch.setenv(env_var, os.environ.get(env_var, "placeholder"))


@pytest.fixture(autouse=True)
def _isolate_config():
    """Reset the global dataflows config before and after each test.

    ``set_config`` merges (it never clears keys absent from the override), so a
    test that sets e.g. ``tool_vendors`` would otherwise leak into later tests
    and make routing behavior order-dependent. Replace the global outright so
    every test starts from a clean DEFAULT_CONFIG.
    """
    import copy

    import tradingagents.dataflows.config as config_module
    import tradingagents.default_config as default_config

    config_module._config = copy.deepcopy(default_config.DEFAULT_CONFIG)
    yield
    config_module._config = copy.deepcopy(default_config.DEFAULT_CONFIG)


@pytest.fixture(autouse=True)
def _reset_revenium_contextvars():
    """Reset Revenium ContextVars to their defaults before and after each test.

    Agent node functions now call current_agent_name.set(...) at their entry
    point (D-12).  Without resetting, a test that executes an agent node leaks
    its agent-name value into subsequent tests (e.g. test_memory_log.py runs
    portfolio_manager_node which sets current_agent_name="portfolio_manager";
    this contaminates test_agent_name_defaults_to_unknown in the next file).

    The reset must be session-global (conftest.py) rather than module-local so
    that any test in the suite that exercises an agent node is covered.
    """
    try:
        from tradingagents.revenium.context import (
            current_agent_name,
            current_run_meta,
            current_trace_id,
        )
    except ImportError:
        # Revenium package not present; nothing to reset.
        yield
        return

    tok_agent = current_agent_name.set("unknown")
    tok_trace = current_trace_id.set("")
    tok_meta = current_run_meta.set({})
    yield
    current_agent_name.reset(tok_agent)
    current_trace_id.reset(tok_trace)
    current_run_meta.reset(tok_meta)


@pytest.fixture()
def mock_llm_client():
    client = MagicMock()
    client.get_llm.return_value = MagicMock()
    with patch(
        "tradingagents.llm_clients.factory.create_llm_client",
        return_value=client,
    ):
        yield client
