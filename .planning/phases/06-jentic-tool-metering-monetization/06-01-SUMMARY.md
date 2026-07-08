---
phase: 06-jentic-tool-metering-monetization
plan: "01"
subsystem: dependency-management, config
tags: [jentic, dependency, config, keyless-isolation, pyproject]
dependency_graph:
  requires: []
  provides: [jentic-declared-dependency, jentic-config-surface]
  affects: [tradingagents/default_config.py, tests/conftest.py, pyproject.toml, uv.lock, .env.example]
tech_stack:
  added: [jentic>=0.10.0,<1.0]
  patterns: [DEFAULT_CONFIG + _ENV_OVERRIDES pattern, autouse keyless fixture]
key_files:
  created: []
  modified:
    - pyproject.toml
    - uv.lock
    - tradingagents/default_config.py
    - tests/conftest.py
    - .env.example
decisions:
  - "Tightened requires-python from >=3.10 to >=3.11 because jentic==0.10.0 requires Python>=3.11; active runtime was already 3.11 per .venv/pyvenv.cfg"
  - "jentic_agent_api_key defaults to empty string (not placeholder) so the config gate in the Jentic tool returns NO_DATA_AVAILABLE immediately without network calls"
  - "conftest _isolate_jentic_key fixture forces JENTIC_AGENT_API_KEY='' per-test (not 'placeholder') to honour the config-gate fail-soft convention (Pitfall 5)"
metrics:
  duration: "~12 minutes"
  completed: "2026-07-03"
  tasks_completed: 3
  files_modified: 5
requirements: [JEN-01]
---

# Phase 06 Plan 01: Jentic Foundation (Dependency + Config) Summary

**One-liner:** Declared `jentic>=0.10.0,<1.0` in pyproject.toml with uv.lock regenerated, added five `jentic_*` config keys with env overrides to DEFAULT_CONFIG, and hardened keyless test isolation for JENTIC_AGENT_API_KEY.

## What Was Built

The Phase 6 foundation: made jentic a first-class declared, locked dependency (closing CI blocker L1), registered the five `jentic_*` config keys that all later Phase 6 plans read, and added a conftest fixture that forces `JENTIC_AGENT_API_KEY=""` under every test so a live key cannot leak into the keyless suite.

No Jentic code runs yet — this plan makes the dependency real and the config surface exist.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Confirm jentic package legitimacy (human-verify) | (approved by user) | — |
| 2 | Declare jentic dependency + regenerate lockfile | 26663e0 | pyproject.toml, uv.lock |
| 3 | Add five jentic_* config keys + env overrides + conftest guard + .env.example | 62bd83a | tradingagents/default_config.py, tests/conftest.py, .env.example |

## Verification Results

- `import jentic` succeeds from venv after declaration
- `grep -c 'name = "jentic"' uv.lock` = 3 (package + extras + lock entry)
- All five keys resolve from DEFAULT_CONFIG with correct defaults
- `JENTIC_TOOL_ENABLED=true` coerces to `bool True` via `_coerce`
- `jentic_op_id` defaults to `op_ba86fdce1bade1b7` (the newsapi.org getEverything op-id)
- Keyless suite: **551 pass, 2 pre-existing known failures** (test_ollama_base_url, test_temperature_config[deepseek]) — no new failures
- `ruff check` clean on all modified Python files

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Updated requires-python from >=3.10 to >=3.11**
- **Found during:** Task 2, `uv lock` execution
- **Issue:** `jentic==0.10.0` declares `requires-python = ">=3.11"`. The `uv lock` resolution failed for the Python 3.10 split even though the active runtime is 3.11. The `>=3.10` floor in pyproject.toml was stale (CLAUDE.md documents "Python 3.11 in active use per `.venv/pyvenv.cfg`").
- **Fix:** Changed `requires-python = ">=3.10"` to `requires-python = ">=3.11"` in pyproject.toml to match the actual pinned runtime and satisfy jentic's Python constraint.
- **Files modified:** pyproject.toml
- **Commit:** 26663e0

## Threat Surface Scan

No new network endpoints, auth paths, or file access patterns were introduced. The `JENTIC_AGENT_API_KEY` config key stores a secret at the operator env/.env → process config trust boundary (T-06-01). Mitigations applied: key defaults to empty string; never logged; `.env.example` ships an empty placeholder; conftest forces empty under test.

## Known Stubs

None — this plan contains no UI rendering, no data wiring, and no placeholder text. All five config keys have functional defaults. No stub patterns apply.

## Self-Check: PASSED

- pyproject.toml exists and contains `jentic`: confirmed
- uv.lock exists and contains `name = "jentic"`: confirmed
- tradingagents/default_config.py contains `jentic_tool_enabled`: confirmed
- tests/conftest.py contains `JENTIC_AGENT_API_KEY`: confirmed
- .env.example contains `JENTIC_AGENT_API_KEY=`: confirmed
- Commit 26663e0 exists: confirmed
- Commit 62bd83a exists: confirmed
