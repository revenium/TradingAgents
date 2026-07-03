---
phase: 07-pilot-partner-integrations
plan: "03"
subsystem: saif-partner-gate
tags: [pilot-partner, saif, meter-tool, governance-gate, graph-node, PIL-03, PIL-04]
dependency_graph:
  requires: [phase-07-02-trinigence-tool, phase-07-01-edgehound-tool]
  provides: [saif-metered-gate, saif-graph-node, combined-3-partner-test, saif-assurance-toolresource]
  affects: [tradingagents/graph/setup.py, tradingagents/agents/utils/agent_states.py, tradingagents/graph/propagation.py, tradingagents/graph/trading_graph.py, scripts/setup_revenium.py]
tech_stack:
  added: [re-based PM decision parser for PASS/FLAG verdict, fail-open saif_gate_node factory]
  patterns: [meter_tool-decorator-only (no @tool), build-time config-gate in setup.py, three-site AgentState field (CLAUDE.md invariant)]
key_files:
  created:
    - tradingagents/agents/utils/saif_gate.py
    - tests/test_saif_gate.py
    - tests/test_partner_integrations.py
  modified:
    - tradingagents/default_config.py
    - tradingagents/agents/utils/agent_states.py
    - tradingagents/graph/propagation.py
    - tradingagents/graph/trading_graph.py
    - tradingagents/graph/setup.py
    - scripts/setup_revenium.py
decisions:
  - "SAIF modelled as a gate (not a data tool): run_saif_assurance has @meter_tool only, no @tool; not in agent_utils"
  - "saif_tool_id sourced exclusively from DEFAULT_CONFIG (single source of truth L6, T-07-10); never hardcoded"
  - "build-time flag in setup.py: saif_tool_enabled=True wires PM->SAIF->END; default=False keeps PM->END (T-07-08)"
  - "three-site AgentState update (CLAUDE.md): agent_states.py + propagation.py + trading_graph.py"
  - "SAIF appended to _PARTNER_TOOLS registry — no other setup_revenium.py code changes needed"
  - "fail-open gate node: any exception returns FAIL_OPEN_VERDICT; never raises out of the node (T-07-09)"
metrics:
  duration_minutes: 30
  completed_date: "2026-07-03"
  tasks_completed: 3
  files_changed: 9
---

# Phase 07 Plan 03: SAIF Pilot Partner Gate (PIL-03) and 3-Partner Integration Test (PIL-04) Summary

Delivered SAIF as a mocked, Revenium-metered AND priced safety/assurance GATE on the Portfolio Manager decision, completing the three-partner FinOps story. A single enabled run now emits 3 distinct partner tool events (edgehound_decision, trinigence_strategy, saif_assurance) under one neutral Revenium cost view — Success Criterion 1.

## What Was Built

- **`tradingagents/agents/utils/saif_gate.py`**: Two public objects:
  - `run_saif_assurance(decision_text: str) -> str` — decorated `@meter_tool(DEFAULT_CONFIG["saif_tool_id"])` only (NOT a LangChain `@tool`; not in agent_utils). Deterministic local mock: parses `**Rating**:` from the rendered PM decision via regex; returns FLAG on Sell/Underweight, PASS otherwise. Output JSON has `verdict`, `checks` (list of named checks), `notes`, `source: "saif (mock)"`.
  - `create_saif_gate_node()` — factory returning a LangGraph node `saif_gate_node(state) -> {"saif_verdict": verdict_json}`. Reads `state["final_trade_decision"]`, calls `run_saif_assurance`, sets `current_agent_name` for Revenium attribution (D-12). Fail-open: never raises.
- **`tradingagents/default_config.py`**: Added `saif_tool_enabled` (bool `False`) + `saif_tool_id` (`"saif_assurance"`) config keys and `SAIF_TOOL_ENABLED` / `SAIF_TOOL_ID` `_ENV_OVERRIDES` entries.
- **`tradingagents/agents/utils/agent_states.py`**: Added `saif_verdict: Annotated[str, "SAIF safety/assurance gate verdict on the PM decision"]` to `AgentState` (site 1/3 per CLAUDE.md three-site rule).
- **`tradingagents/graph/propagation.py`**: Added `"saif_verdict": ""` to `create_initial_state` (site 2/3).
- **`tradingagents/graph/trading_graph.py`**: Added `"saif_verdict": final_state.get("saif_verdict", "")` to `_log_state` (site 3/3).
- **`tradingagents/graph/setup.py`**: Build-time `get_config()` gate: if `saif_tool_enabled=True`, adds "SAIF Assurance" node, replaces `Portfolio Manager → END` with `Portfolio Manager → SAIF Assurance → END`. Default=False leaves topology unchanged.
- **`scripts/setup_revenium.py`**: Appended SAIF third entry to `_PARTNER_TOOLS` registry (`saif_tool_id`, $0.15/call COUNT pricing). `--partner-tools --dry-run` now prints all three toolIds.
- **`tests/test_saif_gate.py`**: 12 unit tests — colon-free toolId, PASS verdict for Hold, FLAG verdict for Sell/Underweight, exactly-one meter event, import-never-raises, graph disabled topology, graph enabled node, node delta, node meter event, three-site plumbing check.
- **`tests/test_partner_integrations.py`**: 2 unit tests — combined 3-distinct-tool-event assertion (Success Criterion 1); all three toolIds colon-free from DEFAULT_CONFIG.

## Verification Results

- `pytest tests/test_saif_gate.py -q`: 12/12 passed (keyless, no network)
- `pytest tests/test_partner_integrations.py -q`: 2/2 passed (keyless, no network)
- `pytest tests/ -q`: 584 passed, 2 skipped, 2 pre-existing failures (xai/deepseek key tests, unrelated)
- `REVENIUM_SK_API_KEY= python scripts/setup_revenium.py --partner-tools --dry-run`: exits 0, output contains `edgehound_decision`, `trinigence_strategy`, AND `saif_assurance`, each with `COUNT`
- `python -c "from tradingagents.default_config import DEFAULT_CONFIG as c; assert c['saif_tool_id']=='saif_assurance' and ':' not in c['saif_tool_id']"`: exits 0
- `grep -q 'saif_verdict' tradingagents/agents/utils/agent_states.py tradingagents/graph/propagation.py tradingagents/graph/trading_graph.py`: exits 0

## TDD Gate Compliance

- RED: `test_saif_gate.py` written before implementation — 11 of 12 tests failed (`KeyError: 'saif_tool_id'` / `ModuleNotFoundError: saif_gate`); `test_saif_gate_no_node_when_disabled` passed vacuously (correct: absence check)
- GREEN Task 1: `default_config.py` + `saif_gate.py` + `setup_revenium.py` written; all 7 Task 1 tests pass
- GREEN Task 2: `agent_states.py` + `propagation.py` + `trading_graph.py` + `setup.py` updated; all 12 tests pass
- Task 3: `test_partner_integrations.py` written; 2 tests pass immediately (dependent implementations from Tasks 1-2 already complete)

## Commits

- `bc6726a` — `test(07-03)`: add failing tests for SAIF gate + graph wiring (TDD RED)
- `fbb24b6` — `feat(07-03)`: SAIF config keys + local mock @meter_tool gate + saif_assurance ToolResource
- `ee3e220` — `feat(07-03)`: wire SAIF gate node after Portfolio Manager (build-time flag-gated)
- `b040808` — `feat(07-03)`: combined 3-partner integration test — 3 distinct tool events (PIL-04)

## Deviations from Plan

### Auto-fixed Issues

None — plan executed exactly as written.

### Notes

- Same two pre-existing test failures as 07-01 and 07-02 (`test_ollama_base_url`, `test_temperature_config[deepseek-deepseek-chat]`) require XAI_API_KEY / DEEPSEEK_API_KEY not present in CI. Not caused by this plan's changes.
- `create_saif_gate_node` was placed in `saif_gate.py` (same module as `run_saif_assurance`) per the plan's Task 1 `<files>` and Task 2 scope — consistent with the single-file pattern for the gate module.
- `saif_verdict` uses `.get("saif_verdict", "")` in `_log_state` for backward compatibility (in case a graph run completes without the SAIF node ever having set the field).

## Known Stubs

None. SAIF mock output is deterministic local governance data — not a placeholder. The `source: "saif (mock)"` field explicitly identifies mock provenance. The PASS/FLAG verdict is derived from the parsed PM decision rating, which is a plausible governance logic representation for the demo.

## Threat Surface Scan

No new network endpoints introduced at runtime. `run_saif_assurance` is a fully local mock — no network, no external API. `register_partner_tool` for SAIF only executes on explicit `--partner-tools` invocation with a `rev_sk_` key. The `saif_tool_enabled=False` default ensures the gate node is never wired into the graph unless explicitly configured (T-07-08). No new auth paths or schema changes at trust boundaries beyond the `saif_verdict` state field (internal, in-process only).

## Self-Check: PASSED

- `tradingagents/agents/utils/saif_gate.py` — FOUND
- `tests/test_saif_gate.py` — FOUND
- `tests/test_partner_integrations.py` — FOUND
- `.planning/phases/07-pilot-partner-integrations/07-03-SUMMARY.md` — FOUND
- Commit `bc6726a` — FOUND (TDD RED)
- Commit `fbb24b6` — FOUND (Task 1 GREEN)
- Commit `ee3e220` — FOUND (Task 2 GREEN)
- Commit `b040808` — FOUND (Task 3)
