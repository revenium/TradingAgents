---
phase: 07-pilot-partner-integrations
plan: "01"
subsystem: edgehound-partner-tool
tags: [pilot-partner, edgehound, meter-tool, decision-intelligence, mock, PIL-01]
dependency_graph:
  requires: [phase-06-jentic-tool-pattern]
  provides: [edgehound-metered-tool, partner-tool-registry, edgehound-market-analyst-gating]
  affects: [tradingagents/agents/analysts/market_analyst.py, scripts/setup_revenium.py]
tech_stack:
  added: [hashlib-based deterministic mock output, _PARTNER_TOOLS registry pattern]
  patterns: [meter_tool-outermost-inner decorator pattern, call-time cfg-gating in analyst]
key_files:
  created:
    - tradingagents/agents/utils/edgehound_tools.py
    - tests/test_edgehound_tool.py
  modified:
    - tradingagents/default_config.py
    - tradingagents/agents/utils/agent_utils.py
    - tradingagents/agents/analysts/market_analyst.py
    - scripts/setup_revenium.py
decisions:
  - "edgehound_tool_id sourced exclusively from DEFAULT_CONFIG (single source of truth L6); never hardcoded"
  - "No sentinel branch — edgehound is a local mock so it always returns data; gating is at analyst level (T-07-02)"
  - "_PARTNER_TOOLS registry added to setup_revenium.py for extensible partner ToolResource registration"
  - "Dry-run allows missing sk_key — no network needed; keyless live-mode exits 0 gracefully (DMO-04)"
metrics:
  duration_minutes: 35
  completed_date: "2026-07-03"
  tasks_completed: 2
  files_changed: 6
---

# Phase 07 Plan 01: Edgehound Pilot Partner Tool (PIL-01) Summary

Delivered Edgehound as a mocked, Revenium-metered AND priced decision-intelligence tool using the Phase 6 `@meter_tool` + per-call `ToolResource` pattern, with zero live partner dependency and a keyless test suite.

## What Was Built

- **`tradingagents/agents/utils/edgehound_tools.py`**: `get_edgehound_decision` LangChain `@tool` using `@tool` outermost / `@meter_tool(DEFAULT_CONFIG["edgehound_tool_id"])` innermost. Deterministic local mock — derives thesis/entry_level/exit_level/conviction_score from a `hashlib.sha256` of the query string. No network, no API key.
- **`tradingagents/default_config.py`**: Added `edgehound_tool_enabled` (bool `False`) + `edgehound_tool_id` (`"edgehound_decision"`) config keys and `EDGEHOUND_TOOL_ENABLED` / `EDGEHOUND_TOOL_ID` `_ENV_OVERRIDES` entries.
- **`tradingagents/agents/utils/agent_utils.py`**: Re-exported `get_edgehound_decision` from `__all__` (single import surface for analysts).
- **`tradingagents/agents/analysts/market_analyst.py`**: Built tool list at call time; appends `get_edgehound_decision` only when `cfg.get("edgehound_tool_enabled")` — mirrors news analyst Jentic gating (T-07-02).
- **`scripts/setup_revenium.py`**: Added `_PARTNER_TOOLS` list registry, `register_partner_tool` generic upsert function, and `--partner-tools` flag. Dry-run works keyless.
- **`tests/test_edgehound_tool.py`**: 7 unit tests — colon-free toolId, plausible JSON output (thesis/entry/exit/conviction), exactly-one meter event, import-never-raises, agent_utils re-export, market analyst enabled/disabled gating.

## Verification Results

- `pytest tests/test_edgehound_tool.py -v`: 7/7 passed (keyless, no network)
- `pytest tests/ -q`: 563 passed, 2 skipped, 2 pre-existing failures (xai/deepseek key tests, unrelated)
- `REVENIUM_SK_API_KEY= python scripts/setup_revenium.py --partner-tools --dry-run`: exits 0, output contains `edgehound_decision` and `COUNT`
- `python -c "from tradingagents.default_config import DEFAULT_CONFIG as c; assert c['edgehound_tool_id']=='edgehound_decision' and ':' not in c['edgehound_tool_id']"`: exits 0

## TDD Gate Compliance

- RED: `test_edgehound_tool.py` written before `edgehound_tools.py` existed — all 5 tests failed on collection (`ModuleNotFoundError` / `KeyError`)
- GREEN: Implementation written; all 5 original tests pass
- Task 2 RED: market analyst gating tests written before wiring — `test_market_analyst_includes_edgehound_when_enabled` failed (tool absent from list)
- Task 2 GREEN: `market_analyst.py` wired; both gating tests pass

## Commits

- `f08e4c9` — `feat(07-01)`: Edgehound config keys + local mock @meter_tool + agent_utils re-export (Task 1)
- `a273f0b` — `feat(07-01)`: wire get_edgehound_decision into market analyst + register ToolResource (Task 2)

## Deviations from Plan

### Auto-fixed Issues

None — plan executed as written.

### Notes

- Two pre-existing test failures (`test_ollama_base_url::test_resolver_does_not_affect_other_providers`, `test_temperature_config::test_temperature_reaches_client_when_set[deepseek-deepseek-chat]`) are unrelated to this plan — they require XAI_API_KEY / DEEPSEEK_API_KEY which the CI environment does not have. Not caused by this plan's changes.
- Dry-run `--partner-tools` with missing sk_key now proceeds to print intended actions (not a hard early exit) so the output satisfies the acceptance criteria (`edgehound_decision` + `COUNT` visible in dry-run output).

## Known Stubs

None. Edgehound mock output is deterministic local data — not a placeholder. The `source: "edgehound (mock)"` field explicitly identifies mock provenance.

## Threat Surface Scan

No new network endpoints. `register_partner_tool` only executes on explicit `--partner-tools` invocation with a `rev_sk_` key; no runtime egress. No new auth paths or schema changes at trust boundaries.

## Self-Check: PASSED

- `tradingagents/agents/utils/edgehound_tools.py` — FOUND
- `tests/test_edgehound_tool.py` — FOUND
- `.planning/phases/07-pilot-partner-integrations/07-01-SUMMARY.md` — FOUND
- Commit `f08e4c9` — FOUND
- Commit `a273f0b` — FOUND
