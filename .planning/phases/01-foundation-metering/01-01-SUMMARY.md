---
phase: 01-foundation-metering
plan: "01"
subsystem: infra
tags: [revenium, langchain, anthropic, openai, multi-provider, sdk, provisioning, config]

# Dependency graph
requires: []
provides:
  - Valid demo model IDs (claude-sonnet-4-6 deep-think, gpt-4.1-mini quick-think) replacing invalid gpt-5.5/gpt-5.4-mini
  - deep_think_provider / quick_think_provider config keys enabling cross-provider split
  - revenium-python-sdk[langchain]>=0.1.9 and revenium-metering>=6.8.2 pinned in pyproject.toml
  - tradingagents/revenium/ package scaffold (__init__.py, config.py) with attribution helper
  - All revenium_* config keys + _ENV_OVERRIDES entries in DEFAULT_CONFIG
  - .env.example placeholders for all Revenium env vars (no secrets committed)
  - scripts/setup_revenium.py - idempotent attribution-hierarchy provisioning script
  - Live Revenium entities: Org DyGMJl, Subscriber l3Pwo5, Product DEnNNv, Subscription lR2kQl
affects:
  - 01-02-PLAN.md (metering slice depends on SDK + config + attribution hierarchy)
  - 01-03-PLAN.md (per-agent contextvars depend on revenium_task_type_map)
  - Phase 4 (monetize pillar — product pricing deferred here)

# Tech tracking
tech-stack:
  added:
    - revenium-python-sdk[langchain]>=0.1.9
    - revenium-metering>=6.8.2
  patterns:
    - Attribution constants live in tradingagents/revenium/config.py (single source of truth, not duplicated)
    - Provider split via deep_think_provider / quick_think_provider config keys; no hardcoded provider strings in trading_graph.py
    - Platform API (management/provisioning) is separate from metering hot-path API; different host, auth, and scoping model
    - revenium_task_type_map in DEFAULT_CONFIG maps all 12 LangGraph node names to pipeline-stage taxonomy

key-files:
  created:
    - tradingagents/revenium/__init__.py
    - tradingagents/revenium/config.py
    - scripts/setup_revenium.py
  modified:
    - tradingagents/default_config.py
    - tradingagents/graph/trading_graph.py
    - pyproject.toml
    - .env.example
    - tests/test_env_overrides.py

key-decisions:
  - "Use claude-sonnet-4-6 for deep-think (Anthropic) and gpt-4.1-mini for quick-think (OpenAI) — valid demo model IDs replacing speculative gpt-5.5/gpt-5.4-mini"
  - "Provider split via config keys (deep_think_provider/quick_think_provider), not hardcoded strings in trading_graph.py"
  - "Revenium Platform API host is https://api.prod.ai.hcapp.io/profitstream/v2/api (not api.revenium.ai); auth is x-api-key header; scoping is tenantId (org/subscriber) vs teamId (product/subscription)"
  - "Product pricing deferred to Phase 4 — product created with minimal valid plan (SUBSCRIPTION/MONTH) rather than $2.00/signal metered pricing"
  - "REVENIUM_TENANT_ID and REVENIUM_TEAM_ID are distinct env vars; passing teamId where tenantId is expected yields 404"
  - "Linear ticket FRONT-1385 filed to document management API host, auth, and scoping gaps in public reference"

patterns-established:
  - "Attribution source of truth: tradingagents/revenium/config.py:attribution_from_config() — all setup/callback code reads here, no duplicate literals"
  - "Setup scripts follow smoke_structured_output.py shape: argparse, def main() -> int, sys.exit(main()), PASS/FAIL summary"
  - "Platform API (provisioning) vs metering API (hot path) are separate concerns with different hosts and auth"

requirements-completed: [FND-01, FND-02, FND-03]

# Metrics
duration: 90min
completed: 2026-06-27
---

# Phase 01 Plan 01: Foundation — SDK, Config, and Revenium Attribution Hierarchy Summary

**Replaced invalid speculative model names, installed and pinned Revenium SDK, registered all revenium_* config keys, and provisioned the live Org/Subscriber/Product/Subscription hierarchy via an idempotent setup script — after discovering and correcting undocumented Platform API host, auth, and scoping schemas through live 400 validation.**

## Performance

- **Duration:** ~90 min
- **Started:** 2026-06-27T18:00:00Z (approx)
- **Completed:** 2026-06-27T20:30:00Z (approx)
- **Tasks:** 5/5 (including 2 checkpoint tasks — package legitimacy gate + live provisioning verification)
- **Files modified:** 8

## Accomplishments

- FND-01: Replaced invalid default model IDs (`gpt-5.5`, `gpt-5.4-mini`) with `claude-sonnet-4-6` (deep-think, Anthropic) and `gpt-4.1-mini` (quick-think, OpenAI); added `deep_think_provider` / `quick_think_provider` config keys and env-var overrides so the provider split is config-driven with no hardcoding.
- FND-02: Installed and pinned `revenium-python-sdk[langchain]>=0.1.9` and `revenium-metering>=6.8.2`; excluded archived `revenium-middleware-langchain`; created `tradingagents/revenium/` package with `attribution_from_config()` helper and full `revenium_task_type_map` for all 12 LangGraph node names; documented env var placeholders in `.env.example`.
- FND-03: Delivered `scripts/setup_revenium.py` — idempotent, committed, re-runnable; live run provisioned all four Revenium entities (Org, Subscriber, Product, Subscription) and re-run confirmed idempotency. Script corrected through multiple live-validation iterations due to undocumented Platform API.

## Task Commits

Each task was committed atomically:

1. **Task 1: Fix invalid model names and add two-provider split (FND-01)** - `6d7f42a` (feat)
2. **Task 2: Package legitimacy gate** - checkpoint (human-approved, no code commit)
3. **Task 3: Install/pin Revenium SDK, add config keys, create revenium package (FND-02)** - `1f91896` (feat)
4. **Task 4: Idempotent attribution-hierarchy setup script (FND-03)** - `0694de1` (feat)
5. **Task 5: Live provisioning verification** - checkpoint (human-approved); multiple fix commits during live validation:
   - `7034002` fix(revenium): correct Platform API host/path/auth
   - `80a67c6` fix(revenium): use authoritative profitstream API schemas (tenant/team scoping)
   - `2ca5f14` fix(revenium): set required plan period on product create
   - `8eadfd1` fix(revenium): add required name to subscription create
   - `b556bf1` fix(revenium): add ownerId/clientEmailAddress/teamId to subscription create

**Rule 1 fix (post-execution):** `6974bec` fix(01-01): update test to reflect FND-01 model defaults

**Plan metadata:** (docs commit — see Final Commit below)

## Files Created/Modified

- `tradingagents/default_config.py` - Valid demo model IDs, deep/quick provider split keys, all revenium_* config keys, _ENV_OVERRIDES entries
- `tradingagents/graph/trading_graph.py` - Two create_llm_client calls now read deep_think_provider / quick_think_provider from config
- `pyproject.toml` - Pinned revenium-python-sdk[langchain]>=0.1.9 and revenium-metering>=6.8.2
- `.env.example` - Revenium env var placeholder block (no secrets)
- `tradingagents/revenium/__init__.py` - Package scaffold; ReveniumCallbackHandler import deferred to Plan 02
- `tradingagents/revenium/config.py` - attribution_from_config() helper, revenium_task_type_map passthrough
- `scripts/setup_revenium.py` - Idempotent Revenium provisioning script; argparse + --dry-run; reads attribution from config
- `tests/test_env_overrides.py` - Updated to assert new valid model defaults (Rule 1 fix)

## Decisions Made

1. **Demo model IDs:** `claude-sonnet-4-6` (deep-think) and `gpt-4.1-mini` (quick-think) — avoids speculative names, provides the two-provider story needed for Revenium's cross-provider cost view.
2. **Provider split via config:** `deep_think_provider` defaults to `anthropic`, `quick_think_provider` defaults to `openai`; both readable/overridable via env vars — no hardcoded strings in trading_graph.py (repo anti-pattern).
3. **Attribution single source of truth:** `tradingagents/revenium/config.py:attribution_from_config()` — setup script and (future) callback handler both import from here; D-01/D-02/D-03 values are not duplicated.
4. **Product pricing deferred:** Product created with minimal valid plan (SUBSCRIPTION/MONTH) — the $2.00/signal metered pricing is intentionally deferred to Phase 4 (monetize pillar). See Open Items.
5. **Linear docs-gap ticket filed:** FRONT-1385 — Platform/management API host, path prefix, auth header, and teamId scoping are not published in the public API reference; create-subscription reference doc 404s.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Platform API host, auth, and scoping were wrong in 01-PATTERNS.md**
- **Found during:** Task 5 (live provisioning run)
- **Issue:** The plan's PATTERNS section assumed the Revenium management API was at `https://api.revenium.ai/api/v2/` with `Authorization: Bearer` auth. This yielded 404s immediately. The correct Platform API is at a completely different host with different auth and two-level scoping.
- **Fix (5 commits over live validation):**
  - Correct host: `https://api.prod.ai.hcapp.io/profitstream/v2/api` (env: `REVENIUM_PLATFORM_BASE_URL`)
  - Correct auth: `x-api-key` header (not `Authorization: Bearer`)
  - Org/subscriber endpoints are TENANT-scoped via `tenantId` (`REVENIUM_TENANT_ID`)
  - Product/subscription endpoints are TEAM-scoped via `teamId` (`REVENIUM_TEAM_ID`)
  - `tenantId != teamId` — passing teamId where tenantId expected yields 404
  - Subscriber lookup: `GET /subscribers/lookup-by-email?email=`
  - Subscriber create: body needs `organizationIds:[orgId]`
  - Product create: body needs `teamId + ownerId` plus a plan object with `period` (e.g. `MONTH`) for `SUBSCRIPTION` type
  - Subscription create: body needs `{name, subscriberId, productId, ownerId, clientEmailAddress, teamId}`
- **New env vars introduced:** `REVENIUM_TENANT_ID`, `REVENIUM_TEAM_ID`, `REVENIUM_OWNER_ID`, `REVENIUM_PLATFORM_BASE_URL`
  - Placeholders added to `.env.example`; real values in gitignored `.env`
  - Note: `revenium_api_url = https://api.revenium.ai` (the metering hot-path host) is unchanged and separate from Platform API
- **Files modified:** `scripts/setup_revenium.py`, `.env.example`
- **Committed in:** 7034002, 80a67c6, 2ca5f14, 8eadfd1, b556bf1

**2. [Rule 1 - Bug] test_no_env_uses_built_in_defaults hardcoded old invalid model names**
- **Found during:** Post-execution test run
- **Issue:** Test asserted `deep_think_llm == "gpt-5.5"` and `quick_think_llm == "gpt-5.4-mini"`, which are the exact invalid defaults we replaced in Task 1.
- **Fix:** Updated assertions to `claude-sonnet-4-6` and `gpt-4.1-mini` with a comment noting the FND-01 change.
- **Files modified:** `tests/test_env_overrides.py`
- **Committed in:** 6974bec

---

**Total deviations:** 2 auto-fixed (both Rule 1 - Bug)

**Impact on plan:** Both auto-fixes necessary for correctness. The Platform API discovery is the most significant — it required 5 iterative fix commits driven entirely by live 400 validation, since the correct API details are not published in the Revenium public reference. No scope creep; the plan's goal (idempotent hierarchy) was fully achieved.

## Issues Encountered

- **Platform API undocumented:** The Revenium management/Platform API host, auth header, and two-level scoping (tenantId vs teamId) are not published in the public API reference at revenium.readme.io. The create-subscription reference doc 404s entirely. Correct parameters were discovered exclusively through live 400 validation against the Platform API. Linear ticket FRONT-1385 filed to close the documentation gap.
- **Product pricing blocked:** The plan intended `$2.00/signal` metered pricing (D-03) on the Product. The Platform API schema for priced billing events was not discoverable without access to the docs (which 404d for subscription creation). Product created with minimal valid plan (SUBSCRIPTION/MONTH); pricing wiring is deferred to Phase 4.

## Known Stubs

- `tradingagents/revenium/__init__.py` — `ReveniumCallbackHandler` import is commented out / deferred. Plan 02 will implement the callback handler and uncomment it.
- Product `trading-signal` (id=DEnNNv) — created with a minimal SUBSCRIPTION/MONTH plan, not the `$2.00/signal` metered pricing from D-03. Phase 4 (monetize pillar) must wire real per-signal pricing. This is intentional and documented.

## Open Items for Later Phases

| Item | Deferred To | Notes |
|------|-------------|-------|
| $2.00/signal metered pricing on the trading-signal Product | Phase 4 | Product provisioned with minimal SUBSCRIPTION/MONTH plan; pricing wiring requires Phase 4 monetize pillar work |
| FRONT-1385 docs gap | Revenium frontend team | Platform API host, auth, scoping, and create-subscription reference are undocumented; ticket filed |

## Live Provisioned Entities

| Entity | Name | ID |
|--------|------|----|
| Organization | Revenium-Research-Desk | DyGMJl |
| Subscriber | john.demic+trading@revenium.io | l3Pwo5 |
| Product | trading-signal | DEnNNv |
| Subscription | (linked to above) | lR2kQl |

## New Environment Variables

| Variable | Purpose | Source |
|----------|---------|--------|
| `REVENIUM_METERING_API_KEY` | Metering hot-path auth (rev_mk_ key) | Revenium dashboard -> API Keys |
| `REVENIUM_METERING_BASE_URL` | Metering API host (default: https://api.revenium.ai) | Optional override |
| `REVENIUM_PLATFORM_BASE_URL` | Platform/management API host (https://api.prod.ai.hcapp.io/profitstream/v2/api) | Revenium env config |
| `REVENIUM_TENANT_ID` | Tenant scope for org/subscriber endpoints | Revenium account settings |
| `REVENIUM_TEAM_ID` | Team scope for product/subscription endpoints | Revenium account settings |
| `REVENIUM_OWNER_ID` | Owner ID for product/subscription create payloads | Revenium account settings |
| `REVENIUM_SK_API_KEY` | Write/management key for setup script (rev_sk_ key) | Revenium dashboard -> API Keys |
| `REVENIUM_ORGANIZATION_NAME` | Override for org name default (Revenium-Research-Desk) | Optional |
| `REVENIUM_PRODUCT_NAME` | Override for product name default (trading-signal) | Optional |
| `REVENIUM_SUBSCRIBER_ID` | Override for subscriber email default | Optional |

All placeholders are in `.env.example`; real values live in gitignored `.env`.

## Test Suite Results

Run: `.venv/bin/python -m pytest -q` (no live API keys in environment)

- **Result:** 440 passed, 3 failed, 2 skipped
- **Relevant passing:** All `tests/test_env_overrides.py` tests pass (including the fixed `test_no_env_uses_built_in_defaults`)
- **Pre-existing failures (not caused by this plan, confirmed by reverting our changes and re-running):**
  - `tests/test_ollama_base_url.py::test_resolver_does_not_affect_other_providers` — requires `DEEPSEEK_API_KEY`
  - `tests/test_temperature_config.py::TestTemperatureForwarding::test_temperature_reaches_client_when_set[deepseek-deepseek-chat]` — requires `DEEPSEEK_API_KEY`
- **Skipped:** `test_bedrock_provider.py` (langchain_aws not installed) and one deepseek live API test
- **Revenium calls:** Not exercised in unit tests — no live API keys required for the suite to pass (repo discipline maintained)

## Threat Surface Scan

No new network endpoints, auth paths, or schema changes at trust boundaries beyond what the plan's threat model already covers. All T-01-01 through T-01-SC mitigations were applied:

- `.env` remains gitignored; `.env.example` has placeholders only (verified: no rev_mk_/rev_sk_/hak_ literals in uncommitted lines)
- `setup_revenium.py` logs only symbolic entity names, never key material
- rev_sk_ write key is scoped to the setup utility only; rev_mk_ is the hot-path key (Phase 2+)
- Script validates key prefix on entry; exits 1 with human-readable message on mismatch

## Next Phase Readiness

**Plan 01-02 (thin metering slice) is unblocked:**
- Valid model names: providers will initialize without API errors
- SDK installed: `revenium-python-sdk[langchain]` importable, `ReveniumMetering` client available
- Config keys: all `revenium_*` keys registered in DEFAULT_CONFIG with env-var overrides
- Attribution hierarchy: live in Revenium (Org DyGMJl, Subscriber l3Pwo5, Product DEnNNv, Subscription lR2kQl) — events will not land in UNCLASSIFIED
- `attribution_from_config()` helper ready for callback handler to consume

**Concerns for Plan 01-02:**
- The `REVENIUM_PLATFORM_BASE_URL`, `REVENIUM_TENANT_ID`, `REVENIUM_TEAM_ID`, and `REVENIUM_OWNER_ID` env vars are required for `setup_revenium.py` to work but are NOT needed for the metering hot path (Plan 02). Keep these separate in env/config.
- Confirm non-streaming before relying on `on_llm_end` for token counts (grep for `.stream()` in `agents/` and `llm_clients/`).
- Validate exactly 1 Revenium event per LLM invocation (sentinel check) before wiring full graph — double-counting produces 2x wrong cost figures.

---
*Phase: 01-foundation-metering*
*Completed: 2026-06-27*
