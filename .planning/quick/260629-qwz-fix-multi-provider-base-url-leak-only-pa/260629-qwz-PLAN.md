---
phase: quick-260629-qwz
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - tradingagents/graph/trading_graph.py
  - tests/test_multi_provider_base_url.py
autonomous: true
requirements: []
must_haves:
  truths:
    - "A deep/quick client whose provider != primary llm_provider is built with base_url=None"
    - "A role whose provider == primary llm_provider still receives config['backend_url']"
    - "The single-provider case (deep==quick==primary) passes backend_url to both clients"
    - "Fix uses no hardcoded provider string literals (provider-agnostic)"
    - "New test passes with no API keys set and no network access"
  artifacts:
    - path: "tradingagents/graph/trading_graph.py"
      provides: "Per-role base_url gating in TradingAgentsGraph.__init__"
      contains: "primary_provider"
    - path: "tests/test_multi_provider_base_url.py"
      provides: "Keyless unit tests for per-role base_url gating"
      contains: "base_url"
  key_links:
    - from: "tradingagents/graph/trading_graph.py"
      to: "create_llm_client"
      via: "base_url=deep_base / base_url=quick_base"
      pattern: "base_url=(deep_base|quick_base)"
---

<objective>
Fix the multi-provider `base_url` leak in `TradingAgentsGraph.__init__`. The CLI resolves a single `backend_url` for the PRIMARY selected provider (`config["llm_provider"]`), but the deep-think and quick-think clients are both constructed with that same `backend_url`. When a role's provider differs from the primary (e.g. deep=anthropic while primary=openai), the Anthropic client is handed OpenAI's host and POSTs the Anthropic request to the wrong endpoint, producing a mid-run HTTP 404 at the Research Manager node (confirmed live 2026-06-29).

Purpose: A cross-provider run is core to the Revenium cross-provider cost view (MTR-04) and must not 404. The fix must stay provider-agnostic (no hardcoded provider literals — hard CLAUDE.md convention) and the test must run keyless (hard CLAUDE.md test-discipline constraint).

Output: A gated `base_url` selection in `__init__` plus a keyless unit test covering the cross-provider and single-provider cases.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@CLAUDE.md
@tradingagents/graph/trading_graph.py
@tradingagents/llm_clients/factory.py
@tests/test_billing_graph_hook.py

# Reference for keyless construction/mocking style (monkeypatch fixture bypassing heavy I/O):
# tests/test_billing_graph_hook.py — _fake_init fixture pattern
# create_llm_client(provider, model, base_url=None, **kwargs) -> BaseLLMClient; client.get_llm() returns the LLM.
# DEFAULT_CONFIG already ships llm_provider="openai", deep_think_provider="anthropic",
# quick_think_provider="openai", backend_url=None — the bug scenario is defaults + a non-None backend_url.
</context>

<tasks>

<task type="auto">
  <name>Task 1: Gate backend_url per role in TradingAgentsGraph.__init__</name>
  <files>tradingagents/graph/trading_graph.py</files>
  <action>
In `TradingAgentsGraph.__init__`, where `deep_client` and `quick_client` are created (currently ~lines 109-123), replace the two unconditional `base_url=self.config.get("backend_url")` arguments with per-role gating.

After computing `deep_provider` and `quick_provider`, add:
  - `primary_provider = self.config["llm_provider"]`
  - `backend_url = self.config.get("backend_url")`
  - `deep_base = backend_url if deep_provider == primary_provider else None`
  - `quick_base = backend_url if quick_provider == primary_provider else None`

Then pass `base_url=deep_base` to the deep `create_llm_client(...)` call and `base_url=quick_base` to the quick call.

Add a concise design comment above the gating explaining WHY: `backend_url` is resolved by the CLI (`cli/main.py` + `cli/utils.resolve_backend_url`) for the PRIMARY provider only; passing it to a role whose provider differs would route that request to the wrong host (the live 404). A non-primary role must use `base_url=None` so its client falls back to its own provider-default endpoint.

Do NOT introduce any hardcoded provider string literals ("anthropic"/"openai"/etc.) in this logic — compare role provider against `primary_provider` only. Match the surrounding code style; do not reformat unrelated lines.
  </action>
  <verify>
    <automated>cd /Users/johndemic/Development/projects/revenium/TradingAgents && grep -Eq "deep_base = backend_url if deep_provider == primary_provider else None" tradingagents/graph/trading_graph.py && grep -Eq "base_url=deep_base" tradingagents/graph/trading_graph.py && grep -Eq "base_url=quick_base" tradingagents/graph/trading_graph.py && ! grep -nE "base_url[ ]*=[ ]*['\"](anthropic|openai|google|azure|bedrock)" tradingagents/graph/trading_graph.py && python -c "import ast; ast.parse(open('tradingagents/graph/trading_graph.py').read())" && echo OK</automated>
  </verify>
  <done>Deep and quick clients receive `base_url=deep_base` / `base_url=quick_base`; non-primary roles get None; no hardcoded provider literals appear in the gating; module parses.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Keyless unit test for per-role base_url gating</name>
  <files>tests/test_multi_provider_base_url.py</files>
  <behavior>
    - Cross-provider case: config with llm_provider="openai", deep_think_provider="anthropic", quick_think_provider="openai", backend_url="https://api.openai.com/v1" → captured base_url for the anthropic (deep) client is None; captured base_url for the openai (quick) client equals the backend_url.
    - Single-provider regression case: llm_provider="openai", deep_think_provider="openai", quick_think_provider="openai", backend_url="https://gw.example.com/v1" → both deep and quick clients receive the backend_url (not None).
    - No API keys and no network are required; create_llm_client is patched to capture the (provider, base_url) per call and return a stub whose get_llm() returns a MagicMock.
  </behavior>
  <action>
Create `tests/test_multi_provider_base_url.py`. Mark tests with `@pytest.mark.unit`.

Patch `tradingagents.graph.trading_graph.create_llm_client` (via `monkeypatch.setattr`) with a recorder that appends each call's `provider` and `base_url` kwargs to a list and returns a `MagicMock()` whose `.get_llm()` returns a `MagicMock()`. This avoids constructing real SDK clients and needs no API keys.

So that `TradingAgentsGraph.__init__` completes keyless and without I/O, also stub the heavy collaborators it constructs after the LLM clients — monkeypatch these names in the `tradingagents.graph.trading_graph` module to `MagicMock`: `TradingMemoryLog`, `GraphSetup`, `Propagator`, `Reflector`, `SignalProcessor`, and `get_checkpointer`. Use `tmp_path` for `data_cache_dir` and `results_dir` in the config so `os.makedirs` is harmless. Set `checkpoint_enabled=False` if needed. Mirror the monkeypatch/MagicMock style in `tests/test_billing_graph_hook.py`. If `_get_provider_kwargs` requires provider-specific env, keep providers to "openai"/"anthropic" which need none at construction since create_llm_client is mocked.

Build each test config by copying `DEFAULT_CONFIG` and overriding the four keys above plus the tmp dirs. Construct `TradingAgentsGraph(config=cfg)`, then assert against the recorded calls: find the deep call by `model == cfg["deep_think_llm"]` (or by recorded provider) and assert its captured `base_url`; likewise for the quick call. Assert exactly the two expected client constructions occurred.

Keep assertions keyed on provider/model identity, not call order, to stay robust.
  </action>
  <verify>
    <automated>cd /Users/johndemic/Development/projects/revenium/TradingAgents && .venv/bin/python -m pytest tests/test_multi_provider_base_url.py -m unit -q</automated>
  </verify>
  <done>Both tests pass with no API keys set and no network; cross-provider deep client base_url asserted None, primary-matching clients asserted to receive backend_url.</done>
</task>

</tasks>

<verification>
- `.venv/bin/python -m pytest tests/test_multi_provider_base_url.py -q` passes with no env keys.
- `.venv/bin/python -m pytest -m unit -q` shows no regressions in the existing suite.
- `grep` confirms no hardcoded provider literals in the new gating logic.
</verification>

<success_criteria>
- Non-primary role clients are constructed with `base_url=None`; primary-matching roles receive `config["backend_url"]`.
- Single-provider path still passes `backend_url` to both clients (no regression).
- Fix is provider-agnostic (no hardcoded provider strings).
- New unit test is keyless and green.
- ROADMAP.md is NOT modified.
</success_criteria>

<output>
Create `.planning/quick/260629-qwz-fix-multi-provider-base-url-leak-only-pa/260629-qwz-SUMMARY.md` when done.
</output>
