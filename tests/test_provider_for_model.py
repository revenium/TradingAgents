"""Regression tests for provider_for_model (per-role provider resolution).

Guards the crash where a CLI run selected a gpt-* deep-think model but the stale
DEFAULT_CONFIG per-role provider default ('anthropic') survived, routing the gpt
model to Anthropic's /v1/messages endpoint and 404-ing with "model: gpt-5.5".

provider_for_model resolves each role's provider from its model so:
- a model the selected provider offers keeps that provider (authoritative choice,
  handles shared 'custom' ids and regional twins),
- a model that drifted from the selection routes to its unique owner,
- an unknown/ambiguous model falls back to the selected provider.
"""

from __future__ import annotations

import pytest

from tradingagents.llm_clients.model_catalog import provider_for_model


@pytest.mark.unit
def test_selected_provider_offering_model_is_honored():
    assert provider_for_model("gpt-5.5", "openai") == "openai"
    assert provider_for_model("claude-sonnet-4-6", "anthropic") == "anthropic"
    assert provider_for_model("gemini-2.5-flash", "google") == "google"


@pytest.mark.unit
def test_model_drifted_from_selection_routes_to_unique_owner():
    # The crash: gpt-* deep model with a non-openai selected provider must route
    # to openai, NOT the mismatched selection (which would 404 on the wrong host).
    assert provider_for_model("gpt-5.5", "anthropic") == "openai"
    assert provider_for_model("gpt-5.4", "anthropic") == "openai"
    # And the inverse — a claude model under an openai selection routes to anthropic.
    assert provider_for_model("claude-sonnet-4-6", "openai") == "anthropic"


@pytest.mark.unit
def test_multi_provider_default_is_preserved():
    # DEFAULT_CONFIG demo: llm_provider=openai, deep=claude (anthropic),
    # quick=gpt-4.1-mini (openai). Resolving each role from its model keeps the
    # cross-provider split intact.
    assert provider_for_model("claude-sonnet-4-6", "openai") == "anthropic"
    assert provider_for_model("gpt-4.1-mini", "openai") == "openai"


@pytest.mark.unit
def test_ambiguous_or_unknown_models_fall_back_to_selection():
    # Shared 'custom' id (offered by many providers) -> trust the selected provider.
    assert provider_for_model("custom", "openai_compatible") == "openai_compatible"
    # Regional twins share a model list -> trust the selection.
    assert provider_for_model("qwen3.7-max", "qwen-cn") == "qwen-cn"
    # Completely unknown id -> selected provider owns its endpoint.
    assert provider_for_model("some-unlisted-model", "openai") == "openai"


@pytest.mark.unit
def test_fallback_is_lowercased_and_none_safe():
    assert provider_for_model("gpt-5.5", "OpenAI") == "openai"
    # Unknown model with empty fallback returns the (empty) fallback, never crashes.
    assert provider_for_model("some-unlisted-model", "") == ""
