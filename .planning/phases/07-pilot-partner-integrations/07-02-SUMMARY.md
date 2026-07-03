---
phase: 07-pilot-partner-integrations
plan: "02"
subsystem: trinigence-partner-tool
tags: [pilot-partner, trinigence, meter-tool, strategy-generation, mock, PIL-02]
dependency_graph:
  requires: [phase-07-01-edgehound-tool]
  provides: [trinigence-metered-tool, partner-tool-registry-extended, trinigence-market-analyst-gating]
  affects: [tradingagents/agents/analysts/market_analyst.py, scripts/setup_revenium.py]
tech_stack:
  added: [hashlib-based deterministic strategy-generation mock, _PARTNER_TOOLS registry extended]
  patterns: [meter_tool-outermost-inner decorator pattern, call-time cfg-gating in analyst, sibling-clone from 07-01]
key_files:
  created:
    - tradingagents/agents/utils/trinigence_tools.py
    - tests/test_trinigence_tool.py
  modified:
    - tradingagents/default_config.py
    - tradingagents/agents/utils/agent_utils.py
    - tradingagents/agents/analysts/market_analyst.py
    - scripts/setup_revenium.py
decisions:
  - "trinigence_tool_id sourced exclusively from DEFAULT_CONFIG (single source of truth L6, T-07-04); never hardcoded"
  - "No sentinel branch — trinigence is a local mock so it always returns data; gating is at analyst level (T-07-05)"
  - "Trinigence appended to _PARTNER_TOOLS registry — no other setup_revenium.py code changes needed (extensible pattern from 07-01)"
  - "Dry-run keyless mode prints tool events (edgehound_decision + trinigence_strategy + COUNT) without requiring sk_key"
  - "Strategy output is deterministic from hashlib.sha256 — not random — so test assertions can rely on exact structure"
metrics:
  duration_minutes: 25
  completed_date: "2026-07-03"
  tasks_completed: 2
  files_changed: 6
---

# Phase 07 Plan 02: Trinigence Pilot Partner Tool (PIL-02) Summary

Delivered Trinigence as a mocked, Revenium-metered AND priced NL→strategy-generation tool cloning the Edgehound slice (07-01), with zero live partner dependency and a keyless test suite. Second partner in the multi-partner FinOps story.

## What Was Built

- **`tradingagents/agents/utils/trinigence_tools.py`**: `get_trinigence_strategy` LangChain `@tool` using `@tool` outermost / `@meter_tool(DEFAULT_CONFIG["trinigence_tool_id"])` innermost. Deterministic local mock — derives strategy_name/entry_rules/exit_rules/indicators/backtest_summary from a `hashlib.sha256` of the description string. No network, no API key.
- **`tradingagents/default_config.py`**: Added `trinigence_tool_enabled` (bool `False`) + `trinigence_tool_id` (`"trinigence_strategy"`) config keys and `TRINIGENCE_TOOL_ENABLED` / `TRINIGENCE_TOOL_ID` `_ENV_OVERRIDES` entries.
- **`tradingagents/agents/utils/agent_utils.py`**: Re-exported `get_trinigence_strategy` from `__all__` (single import surface for analysts).
- **`tradingagents/agents/analysts/market_analyst.py`**: Appends `get_trinigence_strategy` to the tool list only when `cfg.get("trinigence_tool_enabled")` — mirrors the Edgehound branch added in 07-01 (T-07-05).
- **`scripts/setup_revenium.py`**: Appended Trinigence entry to the `_PARTNER_TOOLS` registry (`trinigence_tool_id`, $0.25/call COUNT pricing). No other code changes required — the existing `--partner-tools` handler loops the registry.
- **`tests/test_trinigence_tool.py`**: 7 unit tests — colon-free toolId, plausible JSON output (strategy_name/entry_rules/exit_rules/indicators), exactly-one meter event, import-never-raises, agent_utils re-export, market analyst enabled/disabled gating.

## Verification Results

- `pytest tests/test_trinigence_tool.py -v`: 7/7 passed (keyless, no network)
- `pytest tests/ -q`: 570 passed, 2 skipped, 2 pre-existing failures (xai/deepseek key tests, unrelated to this plan)
- `REVENIUM_SK_API_KEY= python scripts/setup_revenium.py --partner-tools --dry-run`: exits 0, output contains both `edgehound_decision` and `trinigence_strategy` with `COUNT`
- `python -c "from tradingagents.default_config import DEFAULT_CONFIG as c; assert c['trinigence_tool_id']=='trinigence_strategy' and ':' not in c['trinigence_tool_id']"`: exits 0
- `python -c "from tradingagents.agents.utils.agent_utils import get_trinigence_strategy"`: exits 0

## TDD Gate Compliance

- RED: `test_trinigence_tool.py` written before `trinigence_tools.py` existed — tests 1-5 failed (`KeyError: 'trinigence_tool_id'` / `ModuleNotFoundError`); Task 2 market analyst gating test failed (tool absent from list when enabled)
- GREEN: Implementation written (config keys + trinigence_tools.py + agent_utils re-export); all 5 Task 1 tests pass
- Task 2 RED: market analyst wiring tests fail (`AssertionError: get_trinigence_strategy must be in tools when enabled`)
- Task 2 GREEN: `market_analyst.py` wired + `setup_revenium.py` extended; all 7 tests pass

## Commits

- `0090346` — `test(07-02)`: add failing tests for Trinigence mock tool (TDD RED)
- `2370bbe` — `feat(07-02)`: Trinigence config keys + local mock @meter_tool + agent_utils re-export (Task 1)
- `1571604` — `feat(07-02)`: wire get_trinigence_strategy into market analyst + register ToolResource (Task 2)

## Deviations from Plan

### Auto-fixed Issues

None — plan executed as written. Trinigence slice is a clean clone of the Edgehound pattern, adapted for strategy-generation output fields.

### Notes

- Same two pre-existing test failures as 07-01 (`test_ollama_base_url`, `test_temperature_config[deepseek-deepseek-chat]`) require XAI_API_KEY / DEEPSEEK_API_KEY not present in CI. Not caused by this plan's changes.
- Strategy output uses stable hash-seeded templates (entry/exit rule templates, indicator lists) to produce varied but deterministic output across descriptions.

## Known Stubs

None. Trinigence mock output is deterministic local data — not a placeholder. The `source: "trinigence (mock)"` field explicitly identifies mock provenance.

## Threat Surface Scan

No new network endpoints. `register_partner_tool` only executes on explicit `--partner-tools` invocation with a `rev_sk_` key; no runtime egress added. The `trinigence_tool_enabled=False` default ensures the tool is never offered to the LLM unless explicitly configured (T-07-05). No new auth paths or schema changes at trust boundaries.

## Self-Check: PASSED

- `tradingagents/agents/utils/trinigence_tools.py` — FOUND
- `tests/test_trinigence_tool.py` — FOUND
- `.planning/phases/07-pilot-partner-integrations/07-02-SUMMARY.md` — FOUND
- Commit `0090346` — FOUND (TDD RED)
- Commit `2370bbe` — FOUND (Task 1 GREEN)
- Commit `1571604` — FOUND (Task 2 GREEN)
