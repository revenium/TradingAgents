---
phase: 04-cli-cost-panel-billing-monetization
plan: "01"
subsystem: cli-cost-panel
tags: [rich-layout, cost-panel, pricing, callback, tdd]
dependency_graph:
  requires:
    - 03-03  # CLI halt panel (agent_costs schema pre-existed)
  provides:
    - compute_cost  # tradingagents.revenium.pricing
    - agent_costs.cost/call_count  # extended schema in callback.py
    - _build_cost_panel  # live Rich panel for CLI layout
  affects:
    - cli/main.py layout  # adds third "costs" column
    - tradingagents/revenium/callback.py  # on_llm_end + end_run
tech_stack:
  added:
    - tradingagents/revenium/pricing.py  # new module: _PER_MILLION table + compute_cost()
  patterns:
    - TDD RED/GREEN for pricing math and schema extension
    - Declarative dict table (capability.py pattern) for pricing lookup
    - Provider-agnostic substring match on model name
    - Rich Panel/Table rendered inside Live refresh loop (never raises)
key_files:
  created:
    - tradingagents/revenium/pricing.py
    - tests/test_cost_panel.py
  modified:
    - tradingagents/revenium/callback.py
    - cli/main.py
decisions:
  - "Compute local_cost before acquiring the lock in on_llm_end — pure math, no I/O"
  - "Pricing table keyed by (provider_lower, model_substring_lower) tuple — first match wins, 0.0 fallback"
  - "revenium_handler is a keyword-only arg to update_display (prevents positional order ambiguity)"
  - "×N annotation uses ×{call_count} only when call_count > 1 (D-05/D-06)"
  - "Fixed pre-existing F401 (task_type_for_node unused import) in callback.py since ruff check must be clean on modified files"
metrics:
  duration: "~6 minutes"
  completed: "2026-06-28T20:24:20Z"
  tasks_completed: 2
  files_changed: 4
---

# Phase 04 Plan 01: CLI Live Cost Panel Summary

**One-liner:** Per-agent dollar cost panel with ×N debate annotation and bold-yellow hotspot wired into the Rich Live layout, fed from the callback handler's extended `agent_costs` schema.

## What Was Built

**Task 1 (TDD): Local pricing module + agent_costs schema extension**

Created `tradingagents/revenium/pricing.py` with:
- `_PER_MILLION` table: four entries `(provider_lower, model_substring_lower) → (inp_$/M, out_$/M)` for anthropic/claude-sonnet-4, openai/gpt-4.1-mini, openai/gpt-4o-mini, openai/gpt-4o.
- `compute_cost(provider, model, input_tokens, output_tokens) -> float`: substring match on provider + model, returns `0.0` for unknowns (fail-open). Prices tagged `[ASSUMED]` in docstring.

Extended `tradingagents/revenium/callback.py`:
- Added `from tradingagents.revenium.pricing import compute_cost`.
- `on_llm_end`: computes `local_cost` before the lock; `agent_costs.setdefault` default extended with `cost: 0.0` and `call_count: 0`; both accumulated additively inside the lock.
- `end_run()`: added `self.agent_costs.clear()` and `self.run_total_tokens = 0` after `_call_state.clear()` to prevent per-agent cost/×N bleed across runs (Pitfall 4).

**Task 2 (auto): Live cost panel wired into the Rich layout**

Modified `cli/main.py`:
- Added `COST_PANEL_DISPLAY_NAMES: dict[str, str]` — 12 raw agent keys → human-readable labels.
- `create_layout()`: added `Layout(name="costs", ratio=2)` as the third column in `upper.split_row` (ratios 2:2:3).
- `_build_cost_panel(handler) -> Panel`: sorts agents by cost descending, appends ` ×N` when `call_count > 1`, highlights the max-cost row in `bold yellow`, adds a dim separator and bold Total row. Never raises — all reads guarded with `.get()` defaults.
- `update_display()`: added `*, revenium_handler=None` kwarg; when `revenium_handler.enabled`, updates `layout["costs"]` via `_build_cost_panel`; otherwise renders a dim "not enabled" placeholder.
- All 6 `update_display` call sites in `run_analysis` updated with `revenium_handler=revenium_handler`.

**Tests:**

`tests/test_cost_panel.py` (14 tests, all keyless):
- `TestComputeCost` (5 tests): pricing math for anthropic/openai, fallback to 0.0 for unknowns.
- `TestAgentCostsSchema` (3 tests): call_count accumulation, cost accumulation, single-call count.
- `TestEndRunReset` (3 tests): agent_costs cleared, run_total_tokens reset, no cross-run bleed.
- `TestBuildCostPanelSmoke` (3 tests): Panel returned for empty/populated handlers, ×N annotation verified on rendered output.

## Deviations from Plan

**1. [Rule 1 - Bug] Fixed pre-existing F401 unused import in callback.py**
- **Found during:** Task 1 GREEN (ruff check step)
- **Issue:** `task_type_for_node` was imported from `tradingagents.revenium.config` but unused in `callback.py`. Pre-existing since at least Phase 2.
- **Fix:** Removed the unused import from the `from tradingagents.revenium.config import ...` line.
- **Files modified:** `tradingagents/revenium/callback.py`
- **Justification:** Plan acceptance criteria require `ruff check` to be clean on modified modules; fixing was necessary to meet the stated criteria.

## TDD Gate Compliance

- RED gate: `test(04-01): add failing cost panel tests (RED)` — commit `4487896` (14 tests, all failing with ModuleNotFoundError + missing schema fields)
- GREEN gate: `feat(04-01): add pricing module and extend agent_costs schema (GREEN)` — commit `1ad5a7d` (11 Task 1 tests passing)

## Known Stubs

None. Prices are tagged `[ASSUMED]` in the `pricing.py` docstring but the fallback to 0.0 is intentional (not a stub — it's the correct fail-open behavior for unknown models). The `billing.py` stub from Phase 1 is untouched by this plan.

## Threat Flags

No new threat surface introduced. `_build_cost_panel` renders only agent name, `$cost`, and token counts — no key material or prompt/completion content (T-04-01 mitigation). All dict reads use `.get()` defaults (T-04-02 mitigation).

## Self-Check: PASSED

| Item | Status |
|------|--------|
| `tradingagents/revenium/pricing.py` | FOUND |
| `tradingagents/revenium/callback.py` | FOUND |
| `cli/main.py` | FOUND |
| `tests/test_cost_panel.py` | FOUND |
| `04-01-SUMMARY.md` | FOUND |
| Commit `4487896` (RED test) | FOUND |
| Commit `1ad5a7d` (GREEN pricing + callback) | FOUND |
| Commit `af0e17d` (Task 2 cost panel) | FOUND |
