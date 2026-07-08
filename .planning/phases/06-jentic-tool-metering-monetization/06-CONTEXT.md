# Phase 6: Jentic Tool Metering & Monetization - Context

**Gathered:** 2026-07-03
**Status:** Ready for planning
**Source:** Live discussion + hands-on spike (jentic==0.10.0 installed & introspected; Revenium OAS + SDK inspected)

<domain>
## Phase Boundary

Weave Jentic's tool-execution SDK into TradingAgents so the **news analyst** fetches external data through Jentic's async `execute()` (search→load→execute), and every Jentic tool call is **metered by Revenium** (existing `@meter_tool` → `/v2/tool/events` pipeline) **and priced** via a server-side per-call Revenium tool price model. Demonstrates Revenium's tool-usage metering + monetization on REAL third-party API calls — extends MTR-03 (which already meters the 12 internal data-fetch tools) from internal wrappers to real external APIs.

IN scope: Jentic SDK sync-wrapper + config/env; one metered+priced Jentic-backed news tool wired into the news analyst; keyless-mockable tests; a gated live-verify script.
OUT of scope: MCP-native path; routing ALL data tools through Jentic; replacing existing vendors.
</domain>

<decisions>
## Implementation Decisions (LOCKED — do not revisit)

### Integration surface
- **SDK-wrap `client.execute()`** (NOT MCP-native). Wrap the Jentic call with the repo's existing tool-metering pattern (`@meter_tool` in `tradingagents/revenium/meter_tool.py`). MCP-native was considered and deferred.

### Where it plugs in
- **News analyst** carries the demo (`tradingagents/agents/analysts/news_analyst.py`, tools list incl. `get_news`/`get_global_news`). Add a Jentic-backed news tool alongside/within the news vendor path. Strongest single-run story: real external news call metered inline during the pipeline.

### Metering + pricing
- **Meter AND price** each Jentic tool call.
- `ExecuteResponse` returns **NO cost/latency/tokens** (spike-confirmed: `{success, status_code, output, error, step_results, inputs}`) → measure `duration_ms` ourselves (the `@meter_tool` wrapper already does), derive `success` from `response.success`/`status_code`, `error` from `response.error`.
- The Revenium tool event (`_send_tool_event` → POST `{url}/v2/tool/events`) has **NO price field** → **pricing is applied server-side** via a Revenium price model / metering-element-definition keyed on `toolId` (OAS `/v2/api/metering-element-definitions`). **Per-call flat price** is the model (nothing else to price on). Code side just emits a stable, well-formed `toolId`; the dollars come from Revenium config.

### Tool design
- **API-agnostic / config-driven target**: the target operation-id or search-query comes from config, so the tool can point at any credentialed Jentic API. Only `anthropic`/`openai`/`fred` are credentialed today; the user will credential a news API in the Jentic dashboard, which swaps in via config with ZERO code change.
- **Async→sync bridge**: the Jentic SDK is async; the LangGraph pipeline + `@meter_tool` wrapper are sync. The Jentic tool is a **sync function that runs `asyncio.run(client.execute(...))` internally**. No event-loop changes to the graph.
- **Fail-soft**: on any Jentic error (auth, network, no-data), return the vendor-router "no data" sentinel (`NO_DATA_AVAILABLE: ...`) — NEVER crash the run. Matches `route_to_vendor` convention. Agents must not fabricate data.
- Stable `toolId` scheme, e.g. `jentic:news:<api_name>` (or config-derived), so the Revenium price model + dashboard rows are stable.

### LIVE TARGET (confirmed 2026-07-03 — newsapi.org credentialed in Jentic)
- Credentialed APIs now: `anthropic`, `openai`, `stlouisfed/fred-api`, **`newsapi.org/main`**.
- **Pin this op in config:** `op_ba86fdce1bade1b7` = NewsAPI `getEverything` (`GET /everything`), inputs `{q: <keywords>, searchIn?, ...}`, outputs `{status, articles[], totalResults}`. Pass `inputs={"q": <company/ticker/instrument>}`. Fallback op `op_8ae297966b7f6da3` = `getTopHeadlines`. **NOTE these `op_...` ids are account/catalog-specific — keep them in config, not hardcoded; the tool should optionally search by query if the pinned op-id is unset (fail-soft).**
- `LoadResponse.tool_info[id].inputs` is a JSON-SCHEMA dict (not values) — build the `inputs` payload from the target op's known params (`q` for getEverything). Pinning the op-id lets us skip `search`/`load` at runtime for demo speed/reliability.

### Pricing mechanism (confirmed via OAS + research)
- Per-call price = register a **`ToolResource` via `POST /v2/api/tools`** with `pricing.elements: [{name, unitPrice, aggregationType: "COUNT"}]`; the `ToolResource.toolId` MUST exactly equal the `toolId` we emit in tool events. NOT `metering-element-definitions` (that's analytics-dimension metadata). Likely an operator/Revenium-side step (dashboard or API), scriptable in the gated live-verify.
- **[ASSUMED] host discrepancy:** OAS server = `api.revenium.ai/profitstream`, but the live billing host is `api.prod.ai.hcapp.io` (see [[revenium-billing-jobs-api]]). Operator must verify which accepts `POST /v2/api/tools`. Use a config key, not a hardcoded host.

### Config / secrets
- Add `jentic` to `pyproject.toml` (+ `uv.lock`). Currently installed in `.venv` but NOT declared.
- Add a `jentic_agent_api_key` config key in `default_config.py` + `JENTIC_AGENT_API_KEY` entry in `_ENV_OVERRIDES` (repo convention). Key is now present in `.env`.
- Additional config: target op-id/query, enable flag, tool price (for the Revenium-side model / docs).

### Test discipline (DMO-04)
- Mock `jentic.Jentic` (patch `search`/`load`/`execute`) so the full suite is GREEN without `JENTIC_AGENT_API_KEY` or network. Assert: the metered tool fires a Revenium tool event with the right `toolId` + measured duration; fail-soft returns the sentinel on Jentic errors; async→sync bridge returns the mocked output.
- Ship a `scripts/validate_jentic.py`-style live-verify script (mirrors existing `validate_*.py`) — but LIVE verification is GATED on a news API being credentialed in Jentic.
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Revenium tool metering (existing pattern to reuse)
- `tradingagents/revenium/meter_tool.py` — the `@meter_tool(tool_id)` decorator: times the wrapped func, calls `_send_tool_event(tool_id, operation, duration_ms, success, error_message, usage_metadata=None, context)`; fail-open, keyless no-op. THIS is what wraps the Jentic call.
- `revenium_metering/decorator.py` (installed SDK) — `_send_tool_event` → POST `{metering_url}/v2/tool/events`; `_build_event_payload` fields: `{transactionId, toolId, operation, durationMs, success, timestamp, errorMessage?, usageMetadata?, agent, organizationName, productName, subscriberCredential, workflowId, traceId}` — NO price field.
- `tradingagents/agents/utils/agent_utils.py` — tool re-export hub + how `@meter_tool` + `@tool` compose on the 12 data tools (decorator order: `@tool` outermost, `@meter_tool` innermost).

### Data / vendor conventions
- `tradingagents/dataflows/interface.py` — `route_to_vendor` + `NO_DATA_AVAILABLE` sentinel (fail-soft convention the Jentic tool must follow).
- `tradingagents/agents/analysts/news_analyst.py` — where the tool wires in.
- `tradingagents/default_config.py` — `DEFAULT_CONFIG` + `_ENV_OVERRIDES` (add `JENTIC_AGENT_API_KEY` here).

### Jentic SDK (spike-confirmed, jentic==0.10.0)
- `from jentic import Jentic, SearchRequest, LoadRequest, ExecutionRequest` (models in `jentic.lib.models`), ASYNC.
- `search(SearchRequest(query)) -> SearchResponse{results:[SearchResult{id, api_name, operation_id, workflow_id, summary, match_score}], total_count}`
- `load(LoadRequest(ids)) -> LoadResponse{tool_info}`
- `execute(ExecutionRequest(id, inputs)) -> ExecuteResponse{success:bool, status_code:int, output:Any|None, error:str|None, step_results:dict|None, inputs:dict|None}`
- Auth via env `JENTIC_AGENT_API_KEY`. `jentic.list_apis()` shows credentialed APIs (today: anthropic, openai, fred).

### Memory / external
- Memory `jentic-integration` (full spike findings), `revenium-cost-read-api`, `revenium-fcat-demo`.
- Jentic docs https://docs.jentic.com/ ; Revenium OAS saved at scratchpad/oas.json.
</canonical_refs>

<specifics>
## Specific Ideas

- Nice demo beat: "same news, but via Jentic's managed-auth tool layer — and Revenium meters + prices every external call" (tool-vs-token cost iceberg, now with real third-party APIs).
- Keep `@meter_tool` innermost, `@tool` outermost so LangChain sees the StructuredTool and metering still fires on `.func()` calls.
- The async bridge must handle "already in an event loop" defensively (LangGraph is sync today, but guard with a fallback to a fresh loop / `asyncio.new_event_loop` if `asyncio.run` raises "cannot be called from a running loop").
</specifics>

<deferred>
## Deferred Ideas

- **MCP-native metering** via `https://api.jentic.com/mcp` (`search_apis`/`load_execution_info`/`execute`) — deferred; only pursue if Revenium meters MCP tool calls natively.
- **FRED-via-Jentic** pivot — NOT chosen (user will credential a news API instead).
- **Route ALL data tools through Jentic** — bigger scope, deferred.
- Deriving richer usage_metadata from `ExecuteResponse.output` (payload size, etc.) — optional polish, not required for the meter+price beat.
</deferred>

---

*Phase: 06-jentic-tool-metering-monetization*
*Context gathered: 2026-07-03 via live discussion + spike*
