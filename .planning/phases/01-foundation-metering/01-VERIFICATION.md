---
phase: 01-foundation-metering
verified: 2026-06-27T23:00:00Z
status: passed
score: 5/5
overrides_applied: 1
gaps: []
overrides:
  - must_have: "Revenium's cost breakdown shows two distinct provider labels (Anthropic and OpenAI) for a multi-provider run"
    reason: "Code capability fully verified (--multi-provider flag in validate_metering.py, _detect_provider() maps langchain_anthropic→'anthropic', langchain_openai→'openai', per-agent contextvars wired). Live two-provider dashboard proof intentionally de-scoped by user: ANTHROPIC_API_KEY returned 401; user explicitly accepted Phase 1 as proven on the OpenAI/gpt-4.1-mini path alone; demo provider strategy moving to OpenRouter (single integration). Live two-provider proof deferred to the OpenRouter migration phase."
    accepted_by: "john.demic"
    accepted_at: "2026-06-27T00:00:00Z"
deferred: []
---

# Phase 01: Foundation & Metering — Verification Report

**Phase Goal:** Fix the day-one model blockers, provision the Revenium attribution hierarchy, and meter every LLM call (and analyst data-fetch tools) with per-agent identity, billing context, and provider/model labels — the "meter" pillar of the FCAT demo (meter→trace→control→monetize).

**Verified:** 2026-06-27T23:00:00Z
**Status:** gaps_found — one ROADMAP success criterion partially satisfied (user-directed de-scope; see override suggestion)
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths (ROADMAP Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| SC-1 | A full `propagate()` run completes without model-name errors | VERIFIED | `default_config.py:67-68`: `claude-sonnet-4-6` / `gpt-4.1-mini`; no `gpt-5` in codebase; `trading_graph.py:103-104`: reads `deep_think_provider`/`quick_think_provider` from config; live NVDA run exit 0, BUY/Overweight, 0 errors |
| SC-2 | Exactly one Revenium event per LLM call, non-zero tokens, not UNCLASSIFIED | VERIFIED | `test_revenium_metering.py::TestOneEventPerCallInvariant` (2 tests PASS); `validate_metering.py --provider openai` 10/10 checks; dashboard confirmed one event, non-zero tokens, org Revenium-Research-Desk |
| SC-3 | Revenium cost breakdown shows two distinct provider labels (Anthropic and OpenAI) | PARTIAL | Code: `callback.py:_detect_provider()` maps `langchain_anthropic`→`"anthropic"`, `langchain_openai`→`"openai"`; `--multi-provider` flag in `validate_metering.py`; mocked attribution tests PASS. Live dual-provider proof DE-SCOPED (ANTHROPIC_API_KEY 401'd; user accepted single-provider Phase 1; demo moving to OpenRouter) |
| SC-4 | Analyst data-fetch tool calls appear in Revenium as separate metered events | VERIFIED | `@meter_tool` on 12 tools across 7 modules; `meter_tool.py:108-111`: configures prod `/meter` endpoint (not localhost:8082, 70d37ed fix); dashboard confirmed tool events captured ($0.00 expected — no pricingDimensions yet, Phase 4 work) |
| SC-5 | Every metered call carries `organizationName`, `productName`, `subscriber.id` (no UNCLASSIFIED) | VERIFIED | `callback.py:286-291`: attribution always populated from `attribution_from_config()`; `test_attribution_fields_in_payload` PASS; live dashboard: events attributed, not UNCLASSIFIED |

**Score:** 4/5 (SC-3 partial — user-directed de-scope, not implementation gap)

---

### Requirements Coverage

| Requirement | Status | Evidence (file:line) |
|-------------|--------|----------------------|
| FND-01: Valid model names, provider split | VERIFIED | `default_config.py:67-73`: `claude-sonnet-4-6`, `gpt-4.1-mini`, `deep_think_provider="anthropic"`, `quick_think_provider="openai"`; `trading_graph.py:103-104`: reads from config, no hardcoding; `_ENV_OVERRIDES:14-15`: `TRADINGAGENTS_DEEP_THINK_PROVIDER`, `TRADINGAGENTS_QUICK_THINK_PROVIDER` |
| FND-02: SDK pinned, archived excluded | VERIFIED | `pyproject.toml:34-35`: `revenium-python-sdk[langchain]>=0.1.9`, `revenium-metering>=6.8.2`; installed versions confirmed (0.1.9, 6.8.2); `revenium_middleware_langchain`: absent from venv |
| FND-03: Attribution hierarchy provisioned | VERIFIED | `scripts/setup_revenium.py`: `main()->int`, `sys.exit(main())`, `--dry-run` exits 0; reads from `tradingagents.revenium.config`; live entities provisioned (Org DyGMJl, Subscriber l3Pwo5, Product DEnNNv, Subscription lR2kQl) — human-approved checkpoint |
| FND-04: Single-call validation | VERIFIED | `validate_metering.py`: `main()->int`, UNCLASSIFIED check, 10/10 live assertions; `tests/test_revenium_metering.py::TestOneEventPerCallInvariant`: 1:1 event guard PASS |
| MTR-01: Per-agent metering (agent, trace_id, task_type, provider/model) | VERIFIED | All 12 agents set `_rev_agent.set("<node_name>")` as first line of node body; names match `revenium_task_type_map` keys; `callback.py:270-301`: agent, trace_id, task_type, model, provider in payload |
| MTR-02: Billing identifiers on every call | VERIFIED | `callback.py:285-291`: `organization_name`, `product_name`, `subscriber.id` always populated; `test_attribution_fields_in_payload` asserts non-empty |
| MTR-03: @meter_tool on data-fetch tools | VERIFIED | 12 tools decorated across 7 modules; `sentiment_analyst.py:73-78`: `.func` bypass documented as explicit D-13 exemption; `meter_tool.py:108-111`: prod endpoint configured (localhost:8082 fix 70d37ed); `test_revenium_tool_metering.py` PASS |
| MTR-04: Multi-provider distinct labels | PARTIAL | Code correct: `_detect_provider()` + `--multi-provider` flag + agent contextvar wiring; live single-provider (OpenAI/gpt-4.1-mini) proven; dual-provider live dashboard proof de-scoped — see SC-3 |

---

### Required Artifacts

| Artifact | Status | Evidence |
|----------|--------|----------|
| `tradingagents/default_config.py` | VERIFIED | Valid model IDs, provider split keys, all `revenium_*` keys, `_ENV_OVERRIDES` entries, `revenium_task_type_map` (12 keys) |
| `tradingagents/revenium/__init__.py` | VERIFIED | Re-exports `ReveniumCallbackHandler`, `meter_tool`; module docstring |
| `tradingagents/revenium/config.py` | VERIFIED | `attribution_from_config()` returns org/product/subscriber/api_key/api_url; `task_type_for_node()` helper |
| `tradingagents/revenium/context.py` | VERIFIED | `current_trace_id`, `current_agent_name` (default `"unknown"`), `current_run_meta`; `revenium_run_context()` sets uuid4, resets in `finally` |
| `tradingagents/revenium/client.py` | VERIFIED | `ReveniumClient`: lazy SDK import; `enabled=False` when key empty; `meter_ai_completion()` swallows all exceptions (`noqa: BLE001`); only file importing revenium-metering SDK |
| `tradingagents/revenium/callback.py` | VERIFIED | `ReveniumCallbackHandler(BaseCallbackHandler)`: `from_config` classmethod; fire-and-forget daemon thread; single event per `on_llm_end` (dedup via run_id key); full attribution payload; 3× `noqa: BLE001` |
| `tradingagents/revenium/billing.py` | VERIFIED | `ReveniumBillingEmitter.emit_signal_unit()` no-op stub; Phase 4 note in docstring; NOT called from `_run_graph` |
| `tradingagents/revenium/meter_tool.py` | VERIFIED | `meter_tool(tool_id)` decorator factory; configures prod `/meter` endpoint before `_send_tool_event`; fail-open (`noqa: BLE001`) |
| `scripts/setup_revenium.py` | VERIFIED | `def main() -> int`; `sys.exit(main())`; `--dry-run` exits 0; reads from `tradingagents.revenium.config`; key prefix validation; symbolic logging only |
| `scripts/validate_metering.py` | VERIFIED | `def main() -> int`; `sys.exit(main())`; `--multi-provider` flag; UNCLASSIFIED check; 10-assertion loop |
| `tradingagents/graph/trading_graph.py` | VERIFIED | Builds single `ReveniumCallbackHandler`; dedup guard `_caller_has_enabled_rev` at lines 76-83; `_run_graph` wrapped in `revenium_run_context` at lines 392-395 |
| `cli/main.py` | VERIFIED | Single `revenium_handler = ReveniumCallbackHandler.from_config(config)` at line 1052; reused in both `TradingAgentsGraph callbacks` and `get_graph_args callbacks` (line 1177); graph dedup prevents double-counting |
| All 12 agent node files | VERIFIED | `_rev_agent.set("<node_name>")` as first line; aliased import `from tradingagents.revenium.context import current_agent_name as _rev_agent`; all 12 node names match `revenium_task_type_map` keys |
| All 7 tool modules | VERIFIED | `@meter_tool("<tool_id>")` inner decorator on all 12 data-fetch functions; `@tool` remains outermost |
| `tests/test_revenium_metering.py` | VERIFIED | 19 tests, all PASS without `REVENIUM_METERING_API_KEY`; covers: keyless no-op, 1-event invariant, attribution, context integration, dedup guard, billing stub |
| `tests/test_revenium_tool_metering.py` | VERIFIED | 10 tests, all PASS without key; covers: one tool event per call, trace_id carriage, keyless zero-events, fail-open (data fetch succeeds when metering raises), agent attribution, all 12 task_type mappings, localhost:8082 regression |
| `tradingagents/llm_clients/model_catalog.py` | VERIFIED | `gpt-4.1-mini` entry at line 87; eliminates RuntimeWarning on OpenAI path |
| `pyproject.toml` | VERIFIED | `revenium-python-sdk[langchain]>=0.1.9` and `revenium-metering>=6.8.2` in dependencies |
| `.env.example` | VERIFIED | `REVENIUM_METERING_API_KEY=` placeholder; no uncommented `rev_mk_`/`rev_sk_`/`hak_` literals |

---

### Key Link Verification

| From | To | Via | Status | Evidence |
|------|----|-----|--------|----------|
| `trading_graph.py` | `ReveniumCallbackHandler` | `from_config(self.config)` + dedup guard | WIRED | `trading_graph.py:74-83` |
| `trading_graph.py` | `revenium_run_context` | `with revenium_run_context(ticker, trade_date)` wrapping `_run_graph` body | WIRED | `trading_graph.py:392-395` |
| `cli/main.py` | `ReveniumCallbackHandler` | `from_config(config)`; passed to `TradingAgentsGraph callbacks` + `get_graph_args` | WIRED | `cli/main.py:1051-1053, 1071, 1177` |
| `callback.py` | `context.py` | reads `current_agent_name.get()`, `current_trace_id.get()` in `on_llm_end` | WIRED | `callback.py:194, 258` |
| `callback.py` | `client.py` | calls `self._client.meter_ai_completion(payload)` in background thread | WIRED | `callback.py:319` |
| `agent nodes (12)` | `current_agent_name contextvar` | `_rev_agent.set("<node_name>")` as first line | WIRED | all 12 agent files, confirmed by grep |
| `tool modules (7)` | `meter_tool.py` | `@meter_tool("<tool_id>")` inner decorator | WIRED | all 7 tool modules |
| `meter_tool.py` | prod `/meter` endpoint | `_configure_tool_metering(metering_url=..., api_key=...)` before `_send_tool_event` | WIRED | `meter_tool.py:108-111` |

---

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `callback.py on_llm_end` | `usage_metadata` | `response.generations[0][0].message.usage_metadata` | Yes — LLM response carries real token counts | FLOWING |
| `callback.py on_llm_end` | `agent`, `trace_id` | `current_agent_name.get()`, `current_trace_id.get()` from context.py | Yes — set by agent node + run context manager | FLOWING |
| `callback.py` | `organizationName`, `productName`, `subscriber.id` | `attribution_from_config(config)` reading DEFAULT_CONFIG | Yes — hardened D-01..D-03 values | FLOWING |
| `meter_tool.py` | `usage_metadata` | always `None` for data-fetch tools (no token cost) | Expected `None` for Phase 1 | STATIC (by design) |

Note: Tool events carry `usage_metadata=None` — this is intentional for Phase 1. Tool dollar cost requires Phase 4 work (pricingDimensions).

---

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| DEFAULT_CONFIG has valid models and Revenium keys | Python assertion script | All assertions PASS | PASS |
| ReveniumCallbackHandler disabled when no key | Python assertion | `enabled=False` confirmed | PASS |
| Billing stub is a no-op | Python assertion | returns `None` | PASS |
| TradingAgentsGraph imports without key | Python import | No exception | PASS |
| Mocked unit tests (29) pass without live key | `REVENIUM_METERING_API_KEY= pytest test_revenium_*.py -q` | 29 passed in 0.48s | PASS |
| setup_revenium.py --dry-run | `python setup_revenium.py --dry-run` | Exits 0, prints intended actions | PASS |
| i18n coverage test | `pytest test_i18n_coverage.py -q` | 14 passed | PASS |
| No LLM-level streaming | `grep -rn "llm.stream\|streaming=True" agents/ llm_clients/` | Zero matches | PASS |
| No OTLP/opentelemetry imports | `grep -rn "opentelemetry\|otlp" revenium/ trading_graph.py` | Zero matches | PASS |
| No archived revenium-middleware-langchain | `importlib.util.find_spec("revenium_middleware_langchain")` | Returns None | PASS |
| gpt-4.1-mini in model_catalog.py | `grep "gpt-4.1-mini" model_catalog.py` | Found at line 87 | PASS |
| Fail-open: BLE001 annotations in hot path | `grep "noqa: BLE001" client.py callback.py meter_tool.py` | 6 occurrences across 3 files | PASS |
| meter_tool configures prod endpoint | `grep "metering_url" meter_tool.py` | configure() called at line 111 | PASS |

---

### Anti-Patterns Found

| File | Pattern | Severity | Notes |
|------|---------|----------|-------|
| `tradingagents/revenium/billing.py` | `pass` in `emit_signal_unit` | INFO | Intentional stub; Phase 4 scope. Documented with `# noqa: PIE790 — intentional stub` comment |
| `tradingagents/revenium/meter_tool.py` | `usage_metadata=None` in `_send_tool_event` | INFO | By design for Phase 1 — data-fetch tools have no token cost. Phase 4 adds pricingDimensions |

No TBD/FIXME/XXX debt markers in any phase-modified files.

---

### Gaps Summary

**One gap (SC-3 / MTR-04):** Live two-provider (Anthropic + OpenAI) dashboard proof was not obtained. The capability is fully implemented:
- `_detect_provider()` in `callback.py` correctly maps `langchain_anthropic` → `"anthropic"` and `langchain_openai` → `"openai"`
- `--multi-provider` flag in `validate_metering.py` makes two LLM calls and asserts distinct provider labels
- All 12 agent nodes set `_rev_agent.set("<node_name>")` so per-agent attribution works across providers

The live proof was blocked because `ANTHROPIC_API_KEY` returned 401. The user explicitly accepted Phase 1 as proven on the OpenAI/gpt-4.1-mini path alone and decided the demo will move to OpenRouter (single integration point for multi-provider). This is documented in `01-03-SUMMARY.md` under "MTR-04 cross-provider live verification de-scoped by user."

**This looks intentional.** To accept this deviation, add to this VERIFICATION.md frontmatter:

```yaml
overrides:
  - must_have: "Revenium cost breakdown shows two distinct provider labels (Anthropic and OpenAI) for a multi-provider run"
    reason: "ANTHROPIC_API_KEY returned 401; user explicitly accepted Phase 1 as proven on OpenAI/gpt-4.1-mini path; demo moving to OpenRouter. Code capability fully verified: _detect_provider() maps providers correctly, --multi-provider flag in validate_metering.py, agent contextvar wiring complete. Live two-provider proof will be obtained via OpenRouter in a later phase."
    accepted_by: "john.demic"
    accepted_at: "2026-06-27T00:00:00Z"
```

---

### Human Verification Required

None beyond the MTR-04 override decision above. All automated checks pass. Human verification of the Revenium dashboard (FND-03 attribution hierarchy, FND-04 single event, MTR-01/02 per-agent attribution, SC-4 tool events) was already performed by the user as part of the plan execution checkpoints.

---

## Cross-Phase Risks

| Risk | Phase | Severity | Notes |
|------|-------|----------|-------|
| FRED fail-soft gap | Phase 5 | HIGH (demo-reliability) | When `FRED_API_KEY` is absent, `route_to_vendor` raises `FredNotConfiguredError` instead of returning `NO_DATA_AVAILABLE` sentinel — crashes full runs with exit 1. Workaround: add `FRED_API_KEY` to env. Proper fix: make macro/news vendor chain fail-soft per repo convention |
| Tool dollar cost ($0.00) | Phase 4 | MEDIUM | `@meter_tool` sends `usage_metadata=None`; no dollar cost assigned to tool events in Phase 1. Phase 4 must add `usage_metadata` + `pricingDimensions` on the `trading-signal` Revenium product |
| $2.00/signal pricing not configured | Phase 4 | MEDIUM | `trading-signal` product provisioned with minimal SUBSCRIPTION/MONTH plan. Per-signal priced billing deferred. `billing.py:emit_signal_unit()` is a no-op stub |
| OpenRouter migration | Phase 2 | MEDIUM | MTR-04 live two-provider story will be re-framed around OpenRouter. `_detect_provider()` may label OpenRouter-routed calls as `"openai"` since they use `ChatOpenAI`. Phase 2 planning should account for this |
| trace_id not surfaced to stdout | Phase 5 | LOW | `current_trace_id` is used in every metered event but never printed; dashboard lookup requires time-window search rather than direct trace_id lookup |

---

## Phase 1 Verdict

**Goal substantially achieved.** All implementation is complete and correct:
- Model blockers fixed; valid model IDs in config; provider split wired without hardcoding
- Revenium SDK installed and pinned; attribution hierarchy provisioned
- Every LLM call across all 12 agents metered with per-agent identity, billing context, and provider/model labels
- Single-handler design with dedup guard; fail-open proven at all levels
- 29/29 mocked tests pass without live Revenium key
- Live NVDA pipeline run: exit 0, BUY/Overweight, 0 metering errors, 0 connection-refused, dashboard confirmed per-agent attribution

The single partial item (SC-3: live dual-provider dashboard proof) was explicitly de-scoped by the user due to an invalid Anthropic key. The code is correct for dual-provider operation. A user override entry will resolve the `gaps_found` status.

---

_Verified: 2026-06-27T23:00:00Z_
_Verifier: Claude (gsd-verifier)_
