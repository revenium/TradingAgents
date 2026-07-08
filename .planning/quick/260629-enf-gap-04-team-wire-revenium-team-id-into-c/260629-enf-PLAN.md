---
phase: quick-260629-enf
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - tradingagents/default_config.py
  - scripts/validate_billing.py
  - tests/test_billing_emitter.py
autonomous: true
requirements: [GAP-04-TEAM]
must_haves:
  truths:
    - "Setting env REVENIUM_TEAM_ID=vQgNV5 causes DEFAULT_CONFIG['revenium_team_id'] to equal 'vQgNV5'."
    - "When unset, DEFAULT_CONFIG['revenium_team_id'] is the empty string '' (no hardcoded real team id)."
    - "validate_billing.py constructs AgenticOutcomeSettings with team_id sourced from config, so live jobs/outcomes post to the configured demo team rather than the SDK's auto-resolved personal team."
    - "from_config({...,'revenium_billing_api_key':'x','revenium_team_id':'TEAM123'}) results in AgenticOutcomeSettings receiving team_id='TEAM123'."
    - "Keyless test suite stays green; ruff lint clean; no real team id committed."
  artifacts:
    - path: tradingagents/default_config.py
      provides: "revenium_team_id config key + REVENIUM_TEAM_ID env override mapping"
      contains: "revenium_team_id"
    - path: scripts/validate_billing.py
      provides: "team_id forwarded into AgenticOutcomeSettings for live validation"
      contains: "team_id"
    - path: tests/test_billing_emitter.py
      provides: "keyless unit test asserting team_id reaches AgenticOutcomeSettings"
      contains: "revenium_team_id"
  key_links:
    - from: "tradingagents/default_config.py"
      to: "tradingagents/revenium/billing.py from_config"
      via: "config['revenium_team_id'] read by from_config (already wired)"
      pattern: "revenium_team_id"
    - from: "scripts/validate_billing.py"
      to: "AgenticOutcomeSettings"
      via: "team_id kwarg"
      pattern: "team_id="
---

<objective>
Close GAP-04-TEAM: wire `REVENIUM_TEAM_ID` end-to-end so Revenium billing jobs/outcomes
are recorded under the configured demo team ("Trading Agents", vQgNV5) instead of the
SDK's auto-resolved personal team (teams[0] = 5oWd65).

Root cause: `billing.py from_config` already reads `config.get("revenium_team_id")` and
forwards it to `AgenticOutcomeSettings(team_id=...)`, BUT `revenium_team_id` is missing from
`DEFAULT_CONFIG` and has no `_ENV_OVERRIDES` mapping, so it is always `""` → the SDK's
`_get_team_id()` falls back to `teams[0]` (the wrong team). The live validation script also
omits `team_id` from its direct `AgenticOutcomeSettings(...)` construction.

Purpose: A live demo run must attribute spend and revenue to the correct Revenium team where
the cost rule and metering live, or the meter→trace→control→monetize story breaks for FCAT.

Output: Three edits — config key + env override (CONFIG), validation script wiring (CODE),
keyless regression test (TEST). No change to `billing.py` (already correct).
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@CLAUDE.md
@tradingagents/default_config.py
@tradingagents/revenium/billing.py
@scripts/validate_billing.py
@tests/test_billing_emitter.py
</context>

<tasks>

<task type="auto">
  <name>Task 1: Add revenium_team_id config key and REVENIUM_TEAM_ID env override</name>
  <files>tradingagents/default_config.py</files>
  <read_first>
    - tradingagents/default_config.py lines 30-34: the billing-pillar block of `_ENV_OVERRIDES`
      (REVENIUM_BILLING_API_KEY, REVENIUM_PROFITSTREAM_BASE_URL). Add the new mapping in this block.
    - tradingagents/default_config.py lines 183-196: the billing-pillar DEFAULT_CONFIG block
      (revenium_signal_price, revenium_billing_api_key, revenium_profitstream_url). Add the new
      key adjacent to these revenium_* keys.
  </read_first>
  <action>
    In `_ENV_OVERRIDES`, add a row mapping env var `REVENIUM_TEAM_ID` to config key
    `revenium_team_id`, placed in the "Revenium billing / monetize pillar" comment block
    (after REVENIUM_PROFITSTREAM_BASE_URL), matching the existing alignment/style of that block.
    In the DEFAULT_CONFIG dict, add a `revenium_team_id` entry near the other billing
    `revenium_*` keys (after `revenium_profitstream_url`), defaulting to
    `os.getenv("REVENIUM_TEAM_ID", "")` consistent with the sibling keys that read directly
    from os.getenv. Add a brief comment explaining that an empty value lets the SDK auto-resolve
    `teams[0]` (which is the WRONG personal team for the demo tenant) and that the real demo team
    id must come from `.env`. Do NOT hardcode the real team id (vQgNV5) anywhere — default stays "".
    Coercion is automatic: `_coerce` keeps it a string since the reference default is a string.
  </action>
  <verify>
    <automated>cd /Users/johndemic/Development/projects/revenium/TradingAgents && .venv/bin/python -c "import importlib, os; os.environ.pop('REVENIUM_TEAM_ID', None); import tradingagents.default_config as d; importlib.reload(d); assert d.DEFAULT_CONFIG['revenium_team_id']=='' , d.DEFAULT_CONFIG['revenium_team_id']; os.environ['REVENIUM_TEAM_ID']='TEAM123'; importlib.reload(d); assert d.DEFAULT_CONFIG['revenium_team_id']=='TEAM123', d.DEFAULT_CONFIG['revenium_team_id']; print('OK')"</automated>
    <automated>cd /Users/johndemic/Development/projects/revenium/TradingAgents && .venv/bin/ruff check tradingagents/default_config.py</automated>
  </verify>
  <done>
    DEFAULT_CONFIG contains `revenium_team_id` defaulting to "" when env unset and to the env
    value when `REVENIUM_TEAM_ID` is set; `_ENV_OVERRIDES` has the `REVENIUM_TEAM_ID → revenium_team_id`
    row; no real team id literal appears in the file; ruff clean.
  </done>
</task>

<task type="auto">
  <name>Task 2: Forward team_id into AgenticOutcomeSettings in validate_billing.py</name>
  <files>scripts/validate_billing.py</files>
  <read_first>
    - scripts/validate_billing.py lines 110-130: where `profitstream_host`, `subscriber_id` are
      read from config and `AgenticOutcomeSettings(...)` is constructed (currently omits team_id).
    - scripts/validate_billing.py lines 113-120: the operator print block (Profitstream host etc.).
  </read_first>
  <action>
    Read `team_id` from config alongside the existing host/subscriber reads, using
    `config.get("revenium_team_id", "")`. Pass `team_id=team_id` into the
    `AgenticOutcomeSettings(...)` construction (~line 125) so the live validation posts to the
    configured demo team rather than the SDK's auto-resolved teams[0]. Add a print line in the
    operator-info block showing the resolved team id (label it e.g. "Team id (configured)") —
    the Revenium platform team id is NOT a secret, so printing it is allowed and helps operators
    confirm the demo team. When `team_id` is empty, print a short hint that the SDK will
    auto-resolve teams[0] (likely the wrong team). Keep the billing key hidden as it already is.
  </action>
  <verify>
    <automated>cd /Users/johndemic/Development/projects/revenium/TradingAgents && .venv/bin/python -c "import ast,inspect; src=open('scripts/validate_billing.py').read(); assert 'revenium_team_id' in src and 'team_id=' in src, 'team_id not wired'; print('OK')"</automated>
    <automated>cd /Users/johndemic/Development/projects/revenium/TradingAgents && .venv/bin/ruff check scripts/validate_billing.py</automated>
    <automated>cd /Users/johndemic/Development/projects/revenium/TradingAgents && .venv/bin/python -m pytest tests/test_billing_emitter.py::test_validate_billing_keyless_exits_zero -q</automated>
  </verify>
  <done>
    `AgenticOutcomeSettings(...)` in validate_billing.py receives `team_id` from config; the
    keyless-skip path still exits 0 with the keyless message; resolved team id is printed in the
    operator info block; ruff clean.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: Keyless test — team_id reaches AgenticOutcomeSettings via from_config</name>
  <files>tests/test_billing_emitter.py</files>
  <behavior>
    - Given config {"revenium_billing_api_key":"rev_sk_test_fake", "revenium_team_id":"TEAM123"},
      TradingSignalBillingEmitter.from_config(config) constructs AgenticOutcomeSettings with
      kwarg team_id == "TEAM123".
    - The test is keyless (SDK mocked via sys.modules patch, as existing tests do) and spawns no
      network I/O.
    - Edge: when revenium_team_id is absent from config, AgenticOutcomeSettings receives team_id == ""
      (the from_config default), proving no accidental hardcoded fallback.
  </behavior>
  <read_first>
    - tests/test_billing_emitter.py lines 34-61: `_make_emitter_with_mock_client` shows the
      `patch.dict("sys.modules", {...})` pattern with `AgenticOutcomeClient` and
      `AgenticOutcomeSettings` MagicMocks. Reuse this patching approach.
    - tradingagents/revenium/billing.py lines 87-92: `AgenticOutcomeSettings(api_key=..., profitstream_base_url=..., outcome_api_key=..., team_id=team_id)` — the kwarg under test.
    - tradingagents/revenium/billing.py lines 106-133: `from_config` reads `config.get("revenium_team_id", "")` and forwards it (already wired — do NOT modify billing.py).
  </read_first>
  <action>
    Add a `@pytest.mark.unit` test (e.g. `test_from_config_forwards_team_id_to_settings`) that
    patches `sys.modules["revenium_middleware.agentic_outcomes"]` with a MagicMock exposing
    `AgenticOutcomeClient` and a capturing `AgenticOutcomeSettings` mock (mirror
    `_make_emitter_with_mock_client`). Within the patch, call
    `TradingSignalBillingEmitter.from_config({"revenium_billing_api_key": "rev_sk_test_fake",
    "revenium_profitstream_url": "https://api.revenium.io", "revenium_team_id": "TEAM123"})`.
    Assert the `AgenticOutcomeSettings` mock was called once and its call kwargs include
    `team_id == "TEAM123"` (use `.call_args.kwargs["team_id"]`). Add a second assertion (same test
    or a sibling) that calling from_config with the team key omitted yields
    `team_id == ""`. Keep mocks pure in-memory; no real key, no network. Follow the file's existing
    docstring/style conventions.
  </action>
  <verify>
    <automated>cd /Users/johndemic/Development/projects/revenium/TradingAgents && .venv/bin/python -m pytest tests/test_billing_emitter.py -q</automated>
    <automated>cd /Users/johndemic/Development/projects/revenium/TradingAgents && .venv/bin/ruff check tests/test_billing_emitter.py</automated>
  </verify>
  <done>
    New keyless test passes asserting AgenticOutcomeSettings receives team_id="TEAM123" via
    from_config, plus the empty-default case; full test_billing_emitter.py suite green; ruff clean.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| .env → process config | REVENIUM_TEAM_ID read from operator-controlled .env into DEFAULT_CONFIG |
| process → Revenium Jobs/Outcomes API | team_id scopes which Revenium team is billed |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-ENF-01 | Information Disclosure | logging/printing team_id | accept | Revenium platform team id is a non-secret identifier; printing it in validate_billing operator output is intentional for demo-team confirmation. Billing API key stays hidden (existing). |
| T-ENF-02 | Tampering | hardcoded team id in source | mitigate | Default stays `""`; real team id (vQgNV5) comes only from .env. Task verify greps confirm no literal real id committed. |
| T-ENF-03 | Repudiation | wrong-team attribution | mitigate | Wiring team_id from config to AgenticOutcomeSettings ensures jobs/outcomes attribute to the configured demo team, not auto-resolved teams[0]. |
</threat_model>

<verification>
- `ruff check tradingagents/default_config.py scripts/validate_billing.py tests/test_billing_emitter.py` clean.
- `pytest tests/test_billing_emitter.py -q` green (including new team_id test and existing keyless-skip test).
- Env round-trip: REVENIUM_TEAM_ID unset → "", set → forwarded (Task 1 automated check).
- No real team id literal (vQgNV5) in any committed file.
- Pre-existing unrelated failures (test_ollama_base_url, test_temperature_config deepseek) NOT touched.
</verification>

<success_criteria>
- DEFAULT_CONFIG exposes `revenium_team_id` (default "") with a `REVENIUM_TEAM_ID` env override.
- validate_billing.py forwards config team_id into AgenticOutcomeSettings and prints the resolved team id.
- A keyless unit test proves team_id propagates from from_config into AgenticOutcomeSettings.
- billing.py unchanged (already wired); keyless suite green; ruff clean; no secret/real-id leakage.
</success_criteria>

<output>
Create `.planning/quick/260629-enf-gap-04-team-wire-revenium-team-id-into-c/260629-enf-SUMMARY.md` when done.
</output>
