---
phase: quick-260701-d0h
plan: "01"
subsystem: revenium/pricing
tags: [pricing, cost-panel, cli, demo, testing]
dependency_graph:
  requires: []
  provides: [QUICK-260701-d0h]
  affects: [tradingagents/revenium/pricing.py, tradingagents/revenium/callback.py]
tech_stack:
  added: []
  patterns: [longest-substring-match, declarative-lookup-table, keyless-unit-tests]
key_files:
  modified:
    - tradingagents/revenium/pricing.py
  created:
    - tests/test_pricing_coverage.py
decisions:
  - "Longest-substring-match (option b): collect all matching substrings per provider, select max len — order-independent and future-proof"
  - "gpt-4o rate updated from assumed 5.00/15.00 to plan-specified 2.50/10.00 per 1M tokens"
  - "ruff SIM102 applied inline (combined nested-if into single and condition)"
metrics:
  duration: "~8 minutes"
  completed: "2026-07-01"
  tasks_completed: 2
  files_modified: 2
---

# Phase quick-260701-d0h Plan 01: Broaden Pricing Table + Longest-Match Lookup Summary

**One-liner:** Expanded `_PER_MILLION` from 4 to 16 demo-family entries with order-independent longest-substring-match so no demo model renders $0.00 in the CLI cost panel.

## Tasks Completed

| # | Name | Commit | Files |
|---|------|--------|-------|
| 1 | Broaden pricing table + longest-match refactor | ae5fde5 | tradingagents/revenium/pricing.py |
| 2 | Keyless pricing coverage test module | 09b773f | tests/test_pricing_coverage.py, tradingagents/revenium/pricing.py (ruff fix) |

## What Was Built

### Task 1 — pricing.py

- Added 12 new `_PER_MILLION` entries covering all demo model families: `gpt-4.1-nano`, `gpt-4.1` (base), `gpt-4o` (updated rate), `gpt-5`/`gpt-5-mini`/`gpt-5-nano`, `gpt-5.4`/`gpt-5.4-mini`, `o3`, `o4-mini`, `o1`, `claude-opus-4`, `claude-haiku-4`.
- Refactored `compute_cost` from first-match-wins to longest-substring-match: iterates all entries, collects those where `table_provider == provider_lower` and `model_substring in model_lower`, picks the entry with `max(len(model_substring))`. Order in the dict no longer affects correctness.
- Updated module docstring to reflect the new invariant.
- Signature `compute_cost(provider, model, input_tokens, output_tokens) -> float` and `callback.py` call site are unchanged.

### Task 2 — tests/test_pricing_coverage.py

Three test groups (27 tests total, all keyless):
1. **Coverage** — 18-model parametrize over all demo families (including version-suffixed variants like `gpt-5-mini-20250601`) asserting `> 0.0`.
2. **Ordering** — 5 exact-value assertions proving `gpt-5-mini` (0.25) != `gpt-5` (1.25), `gpt-5.4-mini` (0.25) != base, `gpt-4.1-nano` (0.10) != base (2.00) or mini (0.40).
3. **Fail-open** — 4 regression tests confirming unknown model/provider returns `0.0` and never raises.

## Test Results

```
41 passed in 0.61s  (27 new + 14 existing test_cost_panel.py)
```

Run command: `env -u OPENAI_API_KEY -u ANTHROPIC_API_KEY .venv/bin/python -m pytest tests/test_pricing_coverage.py tests/test_cost_panel.py -v`

Ruff: `.venv/bin/ruff check tradingagents/revenium/pricing.py tests/test_pricing_coverage.py` — **All checks passed**.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Lint] ruff SIM102 on pricing.py**
- **Found during:** Task 2 ruff check
- **Issue:** Nested `if table_provider == ... and model_substring in model_lower: if len(...) > best_len:` triggered SIM102 (combine nested ifs).
- **Fix:** Combined into single `if ... and ... and len(...) > best_len:` with multi-line parenthesized form.
- **Files modified:** tradingagents/revenium/pricing.py
- **Commit:** 09b773f

**2. [Rule 1 - Lint] ruff I001 import sort on test file**
- **Found during:** Task 2 ruff check
- **Issue:** Import block un-sorted (isort).
- **Fix:** `ruff check --fix tests/test_pricing_coverage.py` auto-applied the sort.
- **Files modified:** tests/test_pricing_coverage.py
- **Commit:** 09b773f

## Known Stubs

None — `compute_cost` now returns real [ASSUMED] rates for all demo families; no placeholder values flow to the CLI panel.

## Threat Flags

None — pricing.py is a pure local function (no network, no auth, no new surface).

## Self-Check: PASSED

- `tradingagents/revenium/pricing.py` — found, contains `gpt-5.4-mini`
- `tests/test_pricing_coverage.py` — found, contains `def test_`
- Commits ae5fde5, 09b773f — verified in git log
- 41 tests pass without API keys
- ruff clean on both files
