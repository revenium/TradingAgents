---
phase: 03-cost-controls
plan: "02"
subsystem: scripts/setup_revenium.py + .env.example
tags: [cost-controls, provisioning, circuit-breaker, configuration]
dependency_graph:
  requires: []
  provides: [cost-rule-provisioning, cb-env-docs]
  affects: [scripts/setup_revenium.py, .env.example]
tech_stack:
  added: []
  patterns: [idempotent-create-or-verify, management-api-patch]
key_files:
  modified:
    - scripts/setup_revenium.py
    - .env.example
decisions:
  - shadowMode:false forced in both POST and PATCH paths — critical for dashboard ENFORCEMENT_VIOLATION event (D-07)
  - teamId in POST body per Pitfall #6 — management API requires it for correct rule scoping
  - _patch() added alongside _post() following the same shape (requests.patch, _headers, timeout=15, raise_for_status)
  - CB env vars all commented-out in .env.example — keyless suite stays green by default (DMO-04)
  - CTL-01 REQUIREMENTS.md wording was already correct (no change needed; confirmed per D-08 reword)
metrics:
  duration_minutes: 15
  completed: "2026-06-28"
  tasks: 2
  files: 2
---

# Phase 3 Plan 2: Enforce-Mode Cost Rule Provisioning Summary

**One-liner:** Idempotent `_setup_cost_rule()` + `_patch()` wired into `setup_revenium.py` provisions the TOTAL_COST DAILY $1.00 BLOCK rule with `shadowMode:false`; circuit-breaker env vars documented in `.env.example`.

## Tasks Completed

| Task | Description | Commit | Files |
|------|-------------|--------|-------|
| 1 | Add _setup_cost_rule() + _patch() + DEMO_RULE_* constants | decb447 | scripts/setup_revenium.py |
| 2 | Document CB env vars in .env.example + confirm CTL-01 wording | c24b190 | .env.example |

## What Was Built

### Task 1: _setup_cost_rule() + _patch()

Extended `scripts/setup_revenium.py` with:
- Three module-level constants: `DEMO_RULE_NAME = "TradingAgents Demo Budget"`, `DEMO_RULE_HARD_LIMIT = 1.00`, `DEMO_RULE_WARN_THRESHOLD = 0.50`
- `_patch()` helper alongside `_post()` — same shape (requests.patch, _headers, raise_for_status, return json)
- `_setup_cost_rule(base_url, sk_key, team_id, dry_run)` with full idempotency:
  - GET `/ai/cost-controls?teamId={team_id}` then match by `name` or `label` client-side
  - If found in enforce mode (`shadowMode=False, enabled=True`): prints "exists in enforce mode — OK"
  - If found in wrong state: PATCH `/ai/cost-controls/{rule_id}` with `{"shadowMode": False, "enabled": True}`
  - If not found: POST `/ai/cost-controls` with the verified body (ORGANIZATION filter, teamId in body)
  - dry-run branch prints GET/POST/PATCH intent lines and returns True
- Wired as step 5 in `main()` after `_setup_subscription` with `failures += 1` guard

### Task 2: .env.example CB block + CTL-01 confirmation

- Appended a documented circuit-breaker config block to `.env.example` after the existing Revenium section
- Four vars documented with one-line explanations, all commented-out:
  - `REVENIUM_CIRCUIT_BREAKER_ENABLED` — arms the enforcement gate
  - `REVENIUM_CB_POLL_INTERVAL_SECONDS` — 60s default too slow; set to 5 for demo timing (D-09)
  - `REVENIUM_CB_FAIL_MODE` — default "open" keeps CI green when cache uninitialized
  - `REVENIUM_BYPASS` — disables all enforcement; keeps keyless test suite green (D-10/DMO-04)
- Noted that threshold lives in the Revenium rule (not .env) and REVENIUM_TEAM_ID doubles as polling scope
- CTL-01 in REQUIREMENTS.md was already correct per D-08 reword — no text change needed

## Verification Results

- `scripts/setup_revenium.py --dry-run` prints "Cost rule: 'TradingAgents Demo Budget' (TOTAL_COST DAILY $1.0)" and the GET/POST/PATCH dry-run lines, exits 0
- `grep -n "shadowMode"` confirms `shadowMode: False` in POST body and `{"shadowMode": False, "enabled": True}` in PATCH path
- `grep -n '"teamId"'` confirms teamId in cost-rule POST body (Pitfall #6)
- `grep -n "/ai/cost-controls"` shows management-host relative path (no api.revenium.ai literal)
- `ruff check scripts/setup_revenium.py` — All checks passed
- `.env.example` contains all 4 CB env vars (`grep -c` returns 4)
- REQUIREMENTS.md CTL-01 contains "circuit breaker gates the run" — confirmed
- Keyless test suite: 480 passed, 2 pre-existing failures (Ollama/DeepSeek tests unrelated to these changes)

## Deviations from Plan

None — plan executed exactly as written.

## Threat Surface Scan

No new network endpoints, auth paths, file access patterns, or schema changes beyond those documented in the plan's threat model:
- `_handle_http_error` reused for all HTTP error paths in `_setup_cost_rule` — never logs the `rev_sk_*` key (T-03-01)
- `.env.example` adds only key NAMES with blank values; no real secrets committed (T-03-05)
- POST and PATCH both force `shadowMode:false` — the shadow-mode misconfiguration threat is mitigated (T-03-06)

## Self-Check: PASSED

- `scripts/setup_revenium.py` — file exists and contains `_setup_cost_rule`, `_patch`, `DEMO_RULE_NAME`
- `.env.example` — file exists and contains `REVENIUM_CIRCUIT_BREAKER_ENABLED`
- Commits decb447 and c24b190 verified in git log
