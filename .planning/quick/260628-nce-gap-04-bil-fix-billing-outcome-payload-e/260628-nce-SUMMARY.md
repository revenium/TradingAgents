---
phase: quick-260628-nce
plan: 01
subsystem: billing
tags: [billing, outcome-payload, ruff, keyless-tests]
completed: "2026-06-28T20:56:33Z"
duration_minutes: 12
tasks_completed: 3
files_modified:
  - tradingagents/revenium/billing.py
  - scripts/validate_billing.py
  - .env.example
  - tests/test_billing_emitter.py
  - tradingagents/default_config.py
key_decisions:
  - "executionStatus replaces result key in outcome payload (server enum: SUCCESS/FAILED/CANCELLED)"
  - "metadata must be json.dumps(dict) not a raw dict (server expects String type)"
  - "REVENIUM_PROFITSTREAM_BASE_URL is HOST-ONLY; SDK appends /profitstream/v2/api itself"
  - "default_config.py comment corrected as out-of-plan addition (same wrong guidance present)"
---

# Quick Task 260628-nce: Fix Billing Outcome Payload (GAP-04-BIL)

**One-liner:** Corrected `report_outcome` payload to use `executionStatus` + `json.dumps(metadata)` and fixed profitstream HOST-ONLY URL guidance in three locations; keyless test suite updated and passing.

## Tasks Completed

| # | Task | Commit | Files |
|---|------|--------|-------|
| 1 | Fix outcome payload in billing.py and validate_billing.py | 18afa96 | billing.py, validate_billing.py |
| 2 | Correct profitstream host guidance in docstring, .env.example, default_config.py | 3ce95cb | validate_billing.py, .env.example, default_config.py |
| 3 | Update keyless billing tests to assert corrected payload shape | d6802b2 | tests/test_billing_emitter.py |

## What Was Fixed

### Defect 1: Wrong payload key (`result` → `executionStatus`)
- **File:** `tradingagents/revenium/billing.py` (`_report_outcome_safe` closure)
- **File:** `scripts/validate_billing.py` (`client.report_outcome` call)
- **Fix:** Replaced `"result": "SUCCESS"` with `"executionStatus": "SUCCESS"`.
  The server rejected `result` with "Missing required parameter executionStatus".
  Allowed values: `SUCCESS`, `FAILED`, `CANCELLED`.

### Defect 2: `metadata` must be a JSON string
- **File:** Both files above
- **Fix:** Added `import json` (ruff isort order) and changed `"metadata": meta` to
  `"metadata": json.dumps(meta)`. The server returned "Expected type String for field metadata"
  when given a raw dict.

### Defect 3: HOST-ONLY profitstream base URL (three locations)
- **File:** `scripts/validate_billing.py` — docstring + dashboard hint + usage example
- **File:** `.env.example` — new billing subsection added
- **File:** `tradingagents/default_config.py` — comment at `revenium_profitstream_url` (addition to plan)
- **Fix:** `REVENIUM_PROFITSTREAM_BASE_URL` must be `https://api.prod.ai.hcapp.io` (host only).
  The `AgenticOutcomeClient` appends `/profitstream/v2/api` itself. Supplying the full path
  doubles it → 404. The default `https://api.revenium.io` returns 403 on jobs write endpoints.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing critical functionality] Fixed wrong comment in default_config.py**
- **Found during:** Task 2
- **Issue:** `tradingagents/default_config.py` lines 191-193 contained the identical wrong full-path
  host guidance (`api.prod.ai.hcapp.io/profitstream/v2/api`) that was being fixed in other locations.
  This file was not in the plan's file list but carried the same incorrect guidance.
- **Fix:** Updated the comment to HOST-ONLY form and added explanation of SDK path-appending behavior.
- **Files modified:** `tradingagents/default_config.py`
- **Commit:** 3ce95cb (bundled with Task 2)

**2. [Rule 2 - Pre-existing ruff issues] Fixed pre-existing ruff lint violations in test file**
- **Found during:** Task 3
- **Issue:** `tests/test_billing_emitter.py` had 6 pre-existing ruff violations (I001 import ordering,
  C401 set comprehensions). Plan verification requires `ruff check` to be clean on all touched files.
- **Fix:** Applied ruff-recommended mechanical fixes: set comprehensions (`{x for x in ...}`),
  import block ordering (blank line between stdlib and first-party in function body), removed
  extra blank line after `import pytest`.
- **Files modified:** `tests/test_billing_emitter.py`
- **Commit:** d6802b2 (bundled with Task 3)

## Verification Results

```
$ python -m pytest tests/test_billing_emitter.py -x -q
.........
9 passed in 0.09s

$ ruff check tradingagents/revenium/billing.py scripts/validate_billing.py tests/test_billing_emitter.py
All checks passed!

$ grep -c 'executionStatus' tradingagents/revenium/billing.py scripts/validate_billing.py
tradingagents/revenium/billing.py:1
scripts/validate_billing.py:1

$ grep -q 'api.prod.ai.hcapp.io' .env.example && echo "host guidance corrected"
host guidance corrected
```

## Self-Check: PASSED

All files exist and commits are confirmed in git log:
- `tradingagents/revenium/billing.py` — FOUND (18afa96)
- `scripts/validate_billing.py` — FOUND (18afa96, 3ce95cb)
- `.env.example` — FOUND (3ce95cb)
- `tests/test_billing_emitter.py` — FOUND (d6802b2)
- `tradingagents/default_config.py` — FOUND (3ce95cb)
