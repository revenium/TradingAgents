---
phase: quick-260629-enf
plan: "01"
subsystem: revenium-billing
tags: [billing, config, team-id, env-override, keyless-test]
dependency_graph:
  requires: []
  provides: [revenium_team_id-config-key, REVENIUM_TEAM_ID-env-override, team_id-AgenticOutcomeSettings-wiring]
  affects: [tradingagents/default_config.py, scripts/validate_billing.py, tests/test_billing_emitter.py]
tech_stack:
  added: []
  patterns: [_ENV_OVERRIDES pattern, os.getenv default in DEFAULT_CONFIG, sys.modules patch for keyless tests]
key_files:
  created: []
  modified:
    - tradingagents/default_config.py
    - scripts/validate_billing.py
    - tests/test_billing_emitter.py
decisions:
  - "revenium_team_id default is '' (empty string) — .env supplies the real demo team id; no literal committed (T-ENF-02)"
  - "team_id is printed in validate_billing operator output (non-secret platform id); billing key stays hidden (T-ENF-01 accept)"
metrics:
  duration: "~4 minutes"
  completed: "2026-06-29"
  tasks: 3
  files_changed: 3
---

# Phase quick-260629-enf Plan 01: GAP-04-TEAM Wire revenium_team_id Summary

**One-liner:** End-to-end `REVENIUM_TEAM_ID` env-to-config wiring so Revenium billing jobs/outcomes attribute to the configured demo team rather than the SDK's auto-resolved personal teams[0].

## What Was Built

Closed GAP-04-TEAM by adding the missing config key, env override mapping, and live-validation script wiring that `billing.py from_config` already expected but couldn't receive.

**Root cause:** `billing.py from_config` reads `config.get("revenium_team_id", "")` and forwards it to `AgenticOutcomeSettings(team_id=...)` — this was already correct. The break was that `revenium_team_id` was absent from `DEFAULT_CONFIG` and `_ENV_OVERRIDES`, so the value was always `""` and the SDK auto-resolved to `teams[0]` (the personal team, not the "Trading Agents" demo tenant).

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Add revenium_team_id config key + REVENIUM_TEAM_ID env override | 36cfab7 | tradingagents/default_config.py |
| 2 | Forward team_id into AgenticOutcomeSettings in validate_billing.py | 497af0f | scripts/validate_billing.py |
| 3 | Keyless tests: team_id reaches AgenticOutcomeSettings via from_config | d6b8457 | tests/test_billing_emitter.py |

## Verification Results

- `ruff check tradingagents/default_config.py scripts/validate_billing.py tests/test_billing_emitter.py` — all clean
- `pytest tests/test_billing_emitter.py -q` — 11 passed (9 pre-existing + 2 new team_id tests)
- Env round-trip: `REVENIUM_TEAM_ID=ZZTEST` override confirmed forwarded; empty default confirmed when env unset (note: package `__init__.py` calls `load_dotenv()` on import, so `.env`'s `REVENIUM_TEAM_ID` is visible even without the shell env var — this is correct operator behavior)
- No real team id literal (vQgNV5) in any committed file

## Deviations from Plan

None - plan executed exactly as written.

Note on Task 1 verification command: the plan's automated verify used `os.environ.pop` + `importlib.reload`, but `tradingagents/__init__.py` calls `load_dotenv()` on import which re-injects `.env` values into `os.environ`. The round-trip was verified via `env -u REVENIUM_TEAM_ID` subprocess isolation combined with an explicit override test (`ZZTEST` forwarded correctly). The underlying mechanism is sound; the test approach was adapted to match the actual package behavior.

## Threat Surface Scan

No new network endpoints, auth paths, file access patterns, or schema changes introduced. All threat mitigations from plan's threat model satisfied:
- T-ENF-01 (team_id printing): accepted — platform team id is non-secret, printed for operator confirmation
- T-ENF-02 (hardcoded id): mitigated — default is `""`, no literal real id in any file
- T-ENF-03 (wrong-team attribution): mitigated — team_id now flows from config to AgenticOutcomeSettings in both billing.py (pre-existing) and validate_billing.py (this change)

## Self-Check

- [x] tradingagents/default_config.py modified with revenium_team_id key
- [x] scripts/validate_billing.py modified with team_id forwarding
- [x] tests/test_billing_emitter.py modified with 2 new tests
- [x] Commits 36cfab7, 497af0f, d6b8457 present in git log
- [x] All 11 tests pass
- [x] Ruff clean on all 3 files
- [x] No real team id (vQgNV5) in committed files

## Self-Check: PASSED
