---
quick_id: 260629-qwz
description: Fix multi-provider base_url leak in trading_graph.py
status: complete
date: 2026-06-29
commits:
  - f797b2d  # fix: gate backend_url per role
  - 2925157  # test: keyless assertions
---

# Quick Task 260629-qwz — Summary

## Problem

`TradingAgentsGraph.__init__` constructed both the deep-think and quick-think LLM
clients with the **same** shared `base_url=self.config.get("backend_url")`. The CLI
(`cli/main.py` + `cli/utils.resolve_backend_url`) resolves a single `backend_url` for
the **primary** selected provider only (`config["llm_provider"]`). When
`deep_think_provider != quick_think_provider` (the multi-provider demo: Anthropic
deep-think + OpenAI quick-think, primary = OpenAI), the Anthropic deep client wrongly
received OpenAI's `backend_url` and POSTed the Anthropic request to the OpenAI host →
**HTTP 404 `NotFoundError` mid-run at the Research Manager node**.

Confirmed live 2026-06-29: a `curl` to `api.anthropic.com` with `claude-sonnet-4-6`
returns `200`, but the app 404'd because it sent the Anthropic request to the wrong host.

## Fix (Task 1 — commit f797b2d)

`tradingagents/graph/trading_graph.py`: gate `backend_url` per role.

```python
primary_provider = self.config["llm_provider"]
backend_url = self.config.get("backend_url")
deep_base = backend_url if deep_provider == primary_provider else None
quick_base = backend_url if quick_provider == primary_provider else None
```

A role whose provider differs from the primary receives `base_url=None`, so its SDK
client falls back to its own provider-default endpoint. Provider-agnostic — the
comparison is `role_provider == primary_provider`; no hardcoded `"anthropic"`/`"openai"`
literals (CLAUDE.md convention). Includes a design comment explaining the leak.

## Test (Task 2 — commit 2925157)

`tests/test_multi_provider_base_url.py` — keyless, patches `create_llm_client` to
capture the `base_url` kwarg per call and stubs heavy collaborators so `__init__` runs
without API keys or network:
- `test_cross_provider_deep_base_url_is_none`: deep=anthropic, quick=openai, primary=openai,
  backend_url set → Anthropic deep client gets `base_url=None`; OpenAI quick client gets `backend_url`.
- `test_single_provider_both_clients_receive_backend_url`: regression guard — when both
  roles match the primary, both clients receive `backend_url`.

## Verification

- New tests: 2 passed keyless (`env -u OPENAI_API_KEY -u ANTHROPIC_API_KEY pytest`).
- Ruff: clean on both changed files (import-sort auto-fixed).
- Full keyless suite: **524 passed**, 2 skipped, 2 failed — the 2 failures are the
  pre-existing unrelated `test_ollama_base_url` + `test_temperature_config[deepseek]`
  (no regression; +2 passes vs prior 522 are this task's new tests).

## Impact

Unblocks the genuine **two-provider demo path** (Anthropic deep-think + OpenAI
quick-think) → real cross-provider cost view in Revenium. Also a strong **Phase 5
pre-flight candidate**: "deep≠quick provider but a single backend_url is set → warn".
