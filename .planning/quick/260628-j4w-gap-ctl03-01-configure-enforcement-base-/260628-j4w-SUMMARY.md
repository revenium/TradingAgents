---
phase: quick
plan: 260628-j4w
subsystem: revenium-enforcement
tags: [gap-closure, config, docs, testing, circuit-breaker, enforcement]
dependency_graph:
  requires: []
  provides: [GAP-CTL03-01]
  affects: [CTL-01, CTL-02, D-05, D-08, D-09, D-10]
tech_stack:
  added: []
  patterns: [keyless-unit-test, env-var-documentation, docstring-requirements]
key_files:
  created: []
  modified:
    - .env.example
    - scripts/validate_controls.py
    - tests/test_revenium_enforcement.py
decisions:
  - "No SDK edits: REVENIUM_ENFORCEMENT_BASE_URL gap closed via documentation only — the vendored SDK already honors the env var verbatim in _get_enforcement_base_url()"
  - "Keyless unit test proves both the set-case (profitstream path returned) and the fallback (bare origin, documenting the 404 cause)"
metrics:
  duration: "~10 minutes"
  completed: "2026-06-28"
  tasks: 3
  files: 3
---

# Phase quick Plan 260628-j4w: Configure Enforcement Base URL (GAP-CTL03-01) Summary

## One-liner

Closed GAP-CTL03-01 via config+docs only: documented REVENIUM_ENFORCEMENT_BASE_URL=https://api.revenium.ai/profitstream and enforcement-READ key-scope requirement so the in-process circuit breaker can reach the compiled-rules feed without any SDK changes.

## What Was Built

Three targeted changes to arm the Revenium in-process enforcement gate correctly:

1. **`.env.example`** — Added `#REVENIUM_ENFORCEMENT_BASE_URL=https://api.revenium.ai/profitstream` in the circuit-breaker block (adjacent to existing CB knobs), with comments explaining the /profitstream context path requirement and the key-scope requirement (rev_sk_ required; rev_mk_ rejected 403 by the enforcement feed).

2. **`scripts/validate_controls.py`** — Updated the module docstring Requirements section to list `REVENIUM_ENFORCEMENT_BASE_URL`, the enforcement-READ key-scope requirement (rev_sk_ vs rev_mk_), the ~30s recompile cadence / ~30-60s pre-warm lead-time note (D-08), and updated the Usage example to include the new var.

3. **`tests/test_revenium_enforcement.py`** — Added `TestEnforcementBaseUrlResolution` class with two keyless unit tests: (a) when env var is set, `_get_enforcement_base_url()` returns `https://api.revenium.ai/profitstream`; (b) when unset, falls back to bare origin `https://api.revenium.ai` (no /profitstream — the 404 cause).

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Document REVENIUM_ENFORCEMENT_BASE_URL in .env.example | 3d326cb | .env.example |
| 2 | Update validate_controls.py docstring Requirements | 39481f5 | scripts/validate_controls.py |
| 3 | Add keyless config-resolution unit test | b4e1815 | tests/test_revenium_enforcement.py |

## Verification

- All 12 tests in `tests/test_revenium_enforcement.py` pass keyless (no live credentials).
- Ruff lint clean on both .py files touched.
- `REVENIUM_ENFORCEMENT_BASE_URL` documented in all three target files.
- No real API key value committed (pre-existing `rev_mk_secretkey123` in `TestBudgetHaltPanel._make_handler_with_costs` is a synthetic test fixture, not a real key; unchanged by this task).
- Zero SDK edits, zero monkeypatches, zero new wrappers.

## Deviations from Plan

None - plan executed exactly as written. The TDD task (Task 3) was treated as write-once-passing because `_get_enforcement_base_url()` is already implemented in the vendored SDK — the tests validated existing behavior rather than driving new implementation.

## Known Stubs

None.

## Threat Flags

None — changes are documentation and config-only; no new network endpoints, auth paths, or schema changes introduced.

## Self-Check: PASSED

- `.env.example` contains `#REVENIUM_ENFORCEMENT_BASE_URL=https://api.revenium.ai/profitstream`: FOUND
- `scripts/validate_controls.py` docstring contains `REVENIUM_ENFORCEMENT_BASE_URL` and `read scope` and `30s`: FOUND
- `tests/test_revenium_enforcement.py` contains `TestEnforcementBaseUrlResolution`: FOUND
- Commits 3d326cb, 39481f5, b4e1815: FOUND (via git log)
- All 12 enforcement tests pass keyless: CONFIRMED
