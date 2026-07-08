---
status: partial
phase: 03-cost-controls
source: [03-VERIFICATION.md]
started: 2026-06-28T16:38:59Z
updated: 2026-06-28T17:03:00Z
---

## Current Test

[CTL-03 blocked by enforcement-feed integration gap — see Gaps]

## Tests

### 1. Enforce-mode rule confirmation (CTL-04)
expected: Running `scripts/setup_revenium.py` with live credentials provisions/updates the "TradingAgents Demo Budget" cost rule, and the Revenium dashboard shows it with `shadowMode:false`, `action:BLOCK`, `enabled:true` (TOTAL_COST, DAILY, $1.00, ORGANIZATION-scoped).
result: PASS — ran live 2026-06-28. Rule created in enforce mode (id `5Bzq85`): `shadowMode:false`, `enabled:true`, `action:BLOCK`, `metricType:TOTAL_COST`, `windowType:DAILY`, `hardLimit:1.0`, filter `ORGANIZATION IS Revenium-Research-Desk`. Idempotent re-run verified (lookup-by-name finds it; no duplicate). Org/Subscriber/Product/Subscription already existed.

### 2. Live halt + dashboard enforcement event (CTL-03)
expected: `validate_controls.py` (breaker on, poll 5s) raises `BudgetExceededError` mid-run, CLI shows the graceful halt panel + non-zero exit (no fabricated decision), and the dashboard shows an `ENFORCEMENT_VIOLATION` with `isShadow=false`.
result: ISSUE — server-side enforcement fires (metering host returns `429 "Budget limit exceeded: TradingAgents Demo Budget"` → dashboard events generated), BUT the in-process `check_enforcement()` gate never raises `BudgetExceededError`, so the run does NOT halt gracefully — it continues to completion with metering events dropped. Root cause: the middleware enforcement poller reads compiled rules from `https://api.revenium.ai/v2/api/ai/enforcement-rules/{team}` using the metering (`rev_mk_`) key → `404`/`403` on this environment, so its rule cache stays empty and the gate is a permanent no-op. The feed actually lives at `https://api.prod.ai.hcapp.io/profitstream/v2/api/ai/enforcement-rules/{team}` and only responds `200` to the management (`rev_sk_`) key. See Gaps.

## Summary

total: 2
passed: 1
issues: 1
pending: 0
skipped: 0
blocked: 0

## Gaps

### GAP-CTL03-01: in-process enforcement gate cannot read this environment's compiled-rules feed  — RESOLVED (quick 260628-j4w)
- **Resolution (2026-06-28):** Root cause was missing CONFIG, not an SDK bug. Fix = set `REVENIUM_ENFORCEMENT_BASE_URL=https://api.revenium.ai/profitstream` + use a Revenium key with enforcement-READ scope (`rev_sk_` write key works for both metering and the enforcement fetch). Proven live: unpatched SDK `check_enforcement()` raises `BudgetExceededError`. Documented in `.env.example` + `validate_controls.py`; keyless `_get_enforcement_base_url()` test added (commits 3d326cb, 39481f5, b4e1815). Operator must set both env vars in `.env` and pre-warm ~30-60s before the demo (compiled feed recompiles ~30s cadence).
- **Severity:** high (defeats the demo's headline graceful-halt moment; CTL-01/CTL-02/D-05)
- **Symptom:** budget breached → metering `429`s are caught and dropped (fail-open) → trading run continues to completion instead of halting.
- **Evidence (live, 2026-06-28):**
  - `check_enforcement()` cached-rule count = 0; never raises.
  - Gate polls `GET https://api.revenium.ai/v2/api/ai/enforcement-rules/vQgNV5` (x-api-key = rev_mk_) → **404**.
  - Same path on management host + `/profitstream` context with rev_mk_ → **403**; with **rev_sk_** → **200** `{"rules":[{"name":"TradingAgents Demo Budget","threshold":1.0,"currentValue":0.10,...}]}`.
- **Why no config-only fix:** `REVENIUM_ENFORCEMENT_BASE_URL` can correct the URL, but the poller authenticates with `ENV_REVENIUM_API_KEY = REVENIUM_METERING_API_KEY` (the rev_mk_ key), which is `403`-forbidden on the enforcement feed here. No separate enforcement-key env var exists, so the rev_mk_/rev_sk_ split requires an SDK change (or running metering under the rev_sk_ key, which has other implications).
- **FIX PROVEN (spike, 2026-06-28):** with `REVENIUM_ENFORCEMENT_BASE_URL=https://api.revenium.ai/profitstream` and the poller using the write (`rev_sk_`) key, the compiled feed reported `breached:true` and `check_enforcement()` raised `BudgetExceededError` (rule_id=3006). The CLI already catches that → graceful halt (unit-tested). Two-part fix: (1) enforcement base URL needs the `/profitstream` context path (config: `REVENIUM_ENFORCEMENT_BASE_URL`); (2) enforcement-rules fetch needs the write key, not the metering key — the SDK hardwires `ENV_REVENIUM_API_KEY=REVENIUM_METERING_API_KEY`, so this needs an SDK change OR a repo-level startup wrapper patching `enforcement._fetch_rules` (metering must stay on `rev_mk_`).
- **Compiled-feed latency:** the feed recompiles on a ~30s cadence; allow ~30-60s after pre-warming before the breach surfaces to the gate (D-08 demo lead-time).
- **Not a code defect in this phase's files:** `callback.py`/`cli/main.py` wiring is correct given the SDK contract; the gap is in the SDK↔environment integration the phase relies on.
- **Recommended remediation:** Phase 3 gap-closure plan — add a repo-level enforcement-poller wrapper (write key + `/profitstream` URL) + a live integration test, and file an upstream SDK issue for a first-class enforcement base-URL/key split.
