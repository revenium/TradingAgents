---
phase: 06-jentic-tool-metering-monetization
plan: "02"
subsystem: agent-tools, revenium-metering
tags: [jentic, meter_tool, news-analyst, async-bridge, fail-soft, unit-tests, JEN-01, JEN-02, JEN-03]
dependency_graph:
  requires:
    - phase: 06-01
      provides: jentic-declared-dependency, jentic-config-surface (jentic_tool_enabled, jentic_agent_api_key, jentic_op_id, jentic_tool_id)
  provides:
    - get_jentic_news tool: @tool/@meter_tool("jentic:news") sync wrapper over Jentic async SDK
    - _run_async bridge: asyncio.run + ThreadPoolExecutor fallback
    - jentic_news_tools.py: full fail-soft implementation with lazy SDK import
    - JEN-01/02/03 unit tests (5 tests, fully keyless-mockable)
    - Conditional news analyst wiring (jentic_tool_enabled gate)
  affects: [tradingagents/agents/analysts/news_analyst.py, tradingagents/agents/utils/agent_utils.py]
tech-stack:
  added: []
  patterns:
    - "Lazy SDK import inside async body: from jentic import Jentic inside _do_jentic_news — never at module level"
    - "Config-gate before SDK init: if not enabled or not api_key return NO_DATA_AVAILABLE before constructing Jentic"
    - "@tool outermost / @meter_tool innermost — StructuredTool.func IS the metered wrapper"
    - "Force-set os.environ['JENTIC_AGENT_API_KEY'] from config before AgentConfig.from_env() — allows test config key to override conftest monkeypatch"
    - "patch('jentic.Jentic', ...) targets source module attribute (correct for lazy from-imports resolved at call time)"
key-files:
  created:
    - tests/test_jentic_tool.py
    - tradingagents/agents/utils/jentic_news_tools.py
  modified:
    - tradingagents/agents/utils/agent_utils.py
    - tradingagents/agents/analysts/news_analyst.py
key-decisions:
  - "Force-set os.environ['JENTIC_AGENT_API_KEY'] = api_key (not setdefault) inside _do_jentic_news so tests that provide a config key override the autouse conftest monkeypatch that forces the var to ''"
  - "patch('jentic.Jentic') targets the jentic module namespace (not jentic_news_tools.Jentic which doesn't exist as a module attribute) because _do_jentic_news lazy-imports with 'from jentic import Jentic' inside the function"
  - "inputs={'q': query} hardcoded for the pinned NewsAPI getEverything op (op_ba86fdce1bade1b7); load step skipped since input schema is known from CONTEXT.md LIVE TARGET"
  - "Conditional append of get_jentic_news at node call time (not factory build time) so config changes between runs take effect without re-creating the analyst"

patterns-established:
  - "Jentic async tool pattern: @tool/@meter_tool + _run_async + lazy import + config-gate + fail-soft NO_DATA_AVAILABLE"
  - "TDD gate compliance: RED commit (test) before GREEN commit (feat) verified in git log"

requirements-completed: [JEN-01, JEN-02, JEN-03]

duration: "~7 minutes"
completed: "2026-07-03"
---

# Phase 06 Plan 02: Metered Jentic News Tool Summary

**Sync wrapper `get_jentic_news` with `@tool`/`@meter_tool("jentic:news")` decorator order, async bridge, config-gate fail-soft, and conditional news analyst wiring delivering JEN-01/02/03**

## Performance

- **Duration:** ~7 minutes
- **Started:** 2026-07-03T00:13:05Z
- **Completed:** 2026-07-03T00:20:05Z
- **Tasks:** 3
- **Files modified:** 4 (2 created, 2 modified)

## Accomplishments

- Built `jentic_news_tools.py` with the full JEN-01 vertical slice: `_run_async` async bridge, `_do_jentic_news` async body with lazy SDK imports and `inputs={"q": query}` for the pinned NewsAPI `getEverything` op, `_jentic_news_impl` with config-gate fail-soft, and `get_jentic_news` public tool with correct `@tool`/`@meter_tool` decorator order
- Delivered JEN-02 (code half): `@meter_tool("jentic:news")` fires exactly one Revenium tool event per execute call with `tool_id="jentic:news"` verified in tests — unit-confirmed without a live key
- Delivered JEN-03: 5 `@pytest.mark.unit` tests (TDD RED→GREEN) cover disabled-returns-sentinel, keyless-returns-sentinel, async-bridge-output, meter-event fires, and fail-soft-on-execute-error — full unit suite passes with no `JENTIC_AGENT_API_KEY` and no network (392 pass, 1 pre-existing deepseek failure)
- Wired `get_jentic_news` conditionally into `news_analyst_node` at call time when `jentic_tool_enabled=True`; disabled by default so LLM never sees a tool that always returns `NO_DATA_AVAILABLE`

## Task Commits

| Task | Name | Commit | Type |
|------|------|--------|------|
| 1 | Failing unit suite for Jentic news tool (RED) | 4e2aaa6 | test |
| 2 | Implement jentic_news_tools.py + agent_utils re-export (GREEN) | fb26d4a | feat |
| 3 | Wire get_jentic_news conditionally into news analyst | b69a0a5 | feat |

## Files Created/Modified

- `tests/test_jentic_tool.py` — 5 `@pytest.mark.unit` tests covering JEN-01/02/03; patches `jentic.Jentic` at source module namespace; patches `revenium_metering.decorator._send_tool_event` for meter event assertion
- `tradingagents/agents/utils/jentic_news_tools.py` — `get_jentic_news` public tool, `_jentic_news_impl` sync impl, `_do_jentic_news` async body, `_run_async` bridge, `_NO_DATA` sentinel template; 155 lines
- `tradingagents/agents/utils/agent_utils.py` — added `get_jentic_news` import (isort-ordered) and `__all__` entry
- `tradingagents/agents/analysts/news_analyst.py` — import `get_jentic_news` + `get_config`; conditional append to tools list inside `news_analyst_node` at call time

## Decisions Made

- **Force-set env var:** `os.environ["JENTIC_AGENT_API_KEY"] = api_key` inside `_do_jentic_news` (not `setdefault`) so tests that provide a config key via `set_config` override the `autouse` conftest monkeypatch that forces the var to `""`. Without this, `AgentConfig.from_env()` raises `MissingAgentKeyError` even when the test passes a mock key in config.
- **Patch target `jentic.Jentic`:** The plan-checker correction is correct — the implementation does `from jentic import Jentic` INSIDE `_do_jentic_news`, so `Jentic` is never a module attribute of `jentic_news_tools`. Patching `jentic.Jentic` works because the lazy `from` import resolves `jentic.Jentic` at call time when the patch is active.
- **Skip `load` step for pinned op:** Since we know the input param is `q` for `op_ba86fdce1bade1b7` (NewsAPI getEverything), `load` is skipped even in the discovery path. Only `search` is called when no `jentic_op_id` is pinned.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed isort violation in agent_utils.py import block**
- **Found during:** Task 2 (`ruff check` after adding `get_jentic_news` import)
- **Issue:** Import added after `news_data_tools` block put `jentic_news_tools` out of alphabetical order within the `tradingagents.agents.utils.*` import group; ruff I001 flagged it
- **Fix:** Moved `from tradingagents.agents.utils.jentic_news_tools import get_jentic_news` to alphabetical position (after `fundamental_data_tools`, before `macro_data_tools`)
- **Files modified:** `tradingagents/agents/utils/agent_utils.py`
- **Verification:** `ruff check` clean after move; all 5 tests still pass
- **Committed in:** fb26d4a (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 — import ordering bug)
**Impact on plan:** Trivial isort correction. No scope creep.

## TDD Gate Compliance

RED gate: `test(06-02)` commit `4e2aaa6` — 5 tests fail with `ModuleNotFoundError` (module absent, confirmed RED)
GREEN gate: `feat(06-02)` commit `fb26d4a` — all 5 tests pass GREEN

Both TDD gates present in git log in correct order.

## Known Stubs

None — `get_jentic_news` is fully wired. The `jentic_tool_enabled=False` default is intentional (safe off-by-default per plan); it is not a stub. The tool returns a `NO_DATA_AVAILABLE` sentinel when disabled/keyless, which is the designed fail-soft behavior matching `route_to_vendor` convention.

## Threat Surface Scan

All new surfaces were in the plan's `<threat_model>`:

| Covered by | File | Description |
|-----------|------|-------------|
| T-06-01 | jentic_news_tools.py | `jentic_agent_api_key` never logged; symbolic error strings only in `logger.warning` |
| T-06-02 | jentic_news_tools.py | `except Exception` catch in `_jentic_news_impl` + `@meter_tool` fail-open both prevent run crashes |
| T-06-03 | jentic_news_tools.py | `ExecuteResponse.output` passed through LangChain tool-result channel unchanged; no eval |
| T-06-04 | jentic_news_tools.py | `@meter_tool("jentic:news")` hardcodes the string matching `jentic_tool_id` DEFAULT_CONFIG default |

No new threat surfaces beyond the plan's registered threats.

## Issues Encountered

None — plan executed smoothly. The one deviation (isort) was caught by `ruff check` immediately and fixed inline.

## Next Phase Readiness

- `get_jentic_news` is fully implemented, metered, fail-soft, and conditionally wired
- 06-03 can immediately proceed to: (1) server-side `ToolResource` pricing registration via `POST /v2/api/tools`, (2) live-verify script (`scripts/validate_jentic.py`) gated on credentialed news API
- Pre-condition for 06-03 live verify: operator must credential a news API in the Jentic dashboard; `jentic.list_apis()` currently shows only anthropic/openai/fred

## Self-Check: PASSED

- tests/test_jentic_tool.py exists: confirmed
- tradingagents/agents/utils/jentic_news_tools.py exists: confirmed
- 06-02-SUMMARY.md exists: confirmed
- Commit 4e2aaa6 exists (RED — test): confirmed
- Commit fb26d4a exists (GREEN — feat): confirmed
- Commit b69a0a5 exists (Task 3 — feat): confirmed
- 5 unit tests pass GREEN: confirmed
- ruff clean on all modified Python files: confirmed

---

*Phase: 06-jentic-tool-metering-monetization*
*Completed: 2026-07-03*
