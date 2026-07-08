# Phase 6: Jentic Tool Metering & Monetization - Research

**Researched:** 2026-07-03
**Domain:** Jentic async SDK integration, Revenium tool-event pipeline, per-call pricing via ToolResource API
**Confidence:** HIGH (all mechanics confirmed against installed SDK + OAS; one pricing host discrepancy flagged)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- SDK-wrap `client.execute()` (NOT MCP-native). Wrap with `@meter_tool` in `tradingagents/revenium/meter_tool.py`.
- News analyst carries the demo. Add a Jentic-backed news tool alongside the existing vendor path.
- Meter AND price each Jentic tool call. `ExecuteResponse` returns no cost/latency/tokens — measure `duration_ms` ourselves.
- Pricing is applied server-side via a Revenium price model / metering-element-definition keyed on `toolId`. Per-call flat price is the model.
- API-agnostic / config-driven target: target op-id or search-query comes from config.
- Async→sync bridge: Jentic tool is a sync function that runs `asyncio.run(client.execute(...))` internally. No event-loop changes to graph.
- Fail-soft: on any Jentic error return `NO_DATA_AVAILABLE: ...` sentinel. Never crash the run.
- Stable `toolId` scheme, e.g. `jentic:news` (config-derived).
- Add `jentic` to `pyproject.toml` (+ `uv.lock`). Currently installed but NOT declared.
- Add `jentic_agent_api_key` + `JENTIC_AGENT_API_KEY` in `_ENV_OVERRIDES`.
- Mock `jentic.Jentic` so full suite passes with no `JENTIC_AGENT_API_KEY` and no network.
- Gated live-verify script for when a news API is credentialed.

### Claude's Discretion
- Exact additional config key names and defaults.
- Precise async→sync bridge pattern (asyncio.run vs loop isolation).
- Whether to add to `route_to_vendor` or as a direct analyst tool.
- Exact inputs discovery flow from `LoadResponse.tool_info`.
- How to handle `conftest.py` / `_dummy_api_keys` for the new env var.

### Deferred Ideas (OUT OF SCOPE)
- MCP-native metering via `https://api.jentic.com/mcp`.
- FRED-via-Jentic pivot.
- Route ALL data tools through Jentic.
- Deriving richer `usage_metadata` from `ExecuteResponse.output` (payload size, etc.).
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| JEN-01 | Jentic async SDK integrated via sync wrapper; `jentic` declared in pyproject/uv.lock; `JENTIC_AGENT_API_KEY` as config key + env override; fail-soft sentinel on any error | Confirmed: SDK mechanics, config pattern, exception hierarchy, pyproject gap |
| JEN-02 | Metered Jentic-backed tool wired into news analyst; each `execute()` emits exactly one Revenium tool event to `/v2/tool/events`; priced via server-side `ToolResource` price model | Confirmed: tool event pipeline, `POST /v2/api/tools` pricing endpoint, decorator order |
| JEN-03 | Jentic client mockable; full test suite passes with no key and no network | Confirmed: `AsyncMock` pattern, config-gate before SDK init, conftest gap |
| JEN-04 | Gated live-verify script for a real metered+priced `execute()` end-to-end | Confirmed: pattern from existing `validate_*.py` scripts; gate condition documented |
</phase_requirements>

---

## Summary

Phase 6 adds one new sync-wrapped async tool (`get_jentic_news`) backed by the Jentic SDK, wires it into the news analyst, meters every call via `@meter_tool`, and prices each call server-side through a Revenium `ToolResource` price model. The Jentic client (`jentic==0.10.0`) is already installed in `.venv` but is **not declared** in `pyproject.toml` or tracked in `uv.lock` — both must be fixed as a Wave 0 action or CI will not install it.

The Jentic call sequence is `search → load → execute`. The `search` step can be skipped at runtime by pinning the op UUID in config (`jentic_op_id`), making the tool fast and reliable for the demo. Inputs required by the operation are discovered from `LoadResponse.tool_info[id].inputs`, which is a JSON schema dict — the caller must map tool parameters to those field names. The `ExecuteResponse` has no cost or token fields; `@meter_tool` measures `duration_ms` itself.

Revenium tool pricing is applied by registering a `ToolResource` (via `POST /v2/api/tools`) with a `pricing.elements` list specifying `unitPrice` per `COUNT`. The `toolId` in this registration must exactly match the string passed to `@meter_tool`. There is a host discrepancy between the OAS spec (`api.revenium.ai/profitstream`) and the live profitstream path used in Phase 4 billing (`api.prod.ai.hcapp.io`); both must be tested, and the operator must confirm which accepts the `rev_sk_*` key for tool registration.

**Primary recommendation:** Ship a single `tradingagents/agents/utils/jentic_news_tools.py`, wired as a direct analyst tool (NOT via `route_to_vendor`), with a `jentic_tool_enabled` bool config key gating instantiation. Every code path starts by checking that key, so keyless/disabled runs are a no-op with zero SDK interaction.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Jentic SDK execution (async) | Agent Tool Layer | — | Tool is a data-fetch callable wrapped by `@tool`; matches existing data-tool pattern |
| Async→sync bridge | Agent Tool Layer | — | Contained inside the tool function; no loop changes propagate upward |
| Revenium tool event emission | Revenium Metering Layer (`meter_tool.py`) | — | Same `@meter_tool` decorator already used on 12 data tools |
| Tool pricing (dollar amounts) | Revenium Platform (server-side) | Operator / `setup_revenium.py` | No price field in `_send_tool_event`; pricing is a `ToolResource` registration in Revenium |
| Config / env wiring | `default_config.py` + `_ENV_OVERRIDES` | — | Follows existing env-override pattern |
| Keyless test isolation | `conftest.py` `_dummy_api_keys` fixture | Test `set_config` helpers | Same discipline as all other Revenium/API keys |

---

## Standard Stack

### Core (all already installed)
| Library | Installed Version | Purpose | Why Standard |
|---------|----------|---------|--------------|
| `jentic` | 0.10.0 (`.venv`; **undeclared**) | Async SDK: search/load/execute external APIs | The integration subject; spike-confirmed at this version |
| `revenium-metering` | >=6.8.2 (declared) | `_send_tool_event` → POST `/v2/tool/events` | Already wires the 12 data tools |
| `langchain-core` | >=0.3.81 (declared) | `@tool` decorator + `StructuredTool` | Existing pattern for all agent tools |

### Package Legitimacy Audit

> `slopcheck` was not available in this environment. `jentic==0.10.0` is confirmed on PyPI and installed; no slopcheck verdict available.

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| `jentic` | PyPI | N/A | N/A | github.com/jentic/jentic (official SDK) [ASSUMED] | unavailable | Approved — confirmed installed at 0.10.0; official Jentic product |

*slopcheck unavailable — the planner should treat `jentic` as `[ASSUMED]` and the first plan wave must include a human-verify checkpoint confirming the package origin before declaring it green.*

**Installation (pyproject.toml gap — Wave 0 required):**
```bash
# Add to pyproject.toml [project].dependencies:
#   "jentic>=0.10.0"
# Then regenerate lockfile:
uv lock
pip install ".[dev]"    # or uv sync
```

---

## Research Question Answers

### Q1: Jentic call sequence for a news operation [VERIFIED: SDK introspection]

**Full flow — config-driven (recommended):**

```python
import asyncio
from jentic import Jentic
from jentic.lib.models import SearchRequest, LoadRequest, ExecutionRequest
from jentic.lib.cfg import AgentConfig

# Step 0: Auth — raises MissingAgentKeyError if JENTIC_AGENT_API_KEY not set
client = Jentic(AgentConfig.from_env())

# Step 1: Search (skippable if op_id is pinned in config)
search_resp = await client.search(SearchRequest(
    query="get news headlines for a stock ticker",
    limit=5,
    filter_by_credentials=True,   # only APIs you have credentials for
))
# search_resp.results: list[SearchResult]
# SearchResult fields (spike-confirmed):
#   id:          "op_abc123..." or "wf_abc123..."  — UUID, pass to load/execute
#   api_name:    "alphanews" (varies by credentialed API)
#   entity_type: "operation" or "workflow"
#   summary:     human label
#   operation_id: OpenAPI operationId (str | None)
#   workflow_id:  friendly wf id (str | None)
#   match_score:  float, lower = better

op_id = search_resp.results[0].id   # "op_..." or "wf_..."
api_name = search_resp.results[0].api_name

# Step 2: Load — discover required inputs
load_resp = await client.load(LoadRequest(ids=[op_id]))
tool_info = load_resp.tool_info[op_id]
# tool_info is OperationDetail or WorkflowDetail (or None if not found)
# OperationDetail.inputs is a JSON-schema dict, e.g.:
#   {"type": "object", "properties": {"ticker": {"type": "string"}, ...}, "required": ["ticker"]}
# WorkflowDetail.inputs is the same shape (merged across steps)

# Step 3: Shape inputs from schema + tool arguments
# Read tool_info.inputs["properties"] to know which keys are needed.
# Example for a news API: inputs dict is built from the tool's parameters.
inputs = {"ticker": ticker, "from": start_date, "to": end_date}

# Step 4: Execute
exec_resp = await client.execute(ExecutionRequest(id=op_id, inputs=inputs))
# exec_resp fields (spike-confirmed):
#   success:      bool
#   status_code:  int (HTTP code from downstream API)
#   output:       Any | None  — the actual data returned
#   error:        str | None  — populated when success=False
#   step_results: dict | None — per-step traces for workflows
#   inputs:       dict | None — echo of the inputs sent
```

**Pinning the op_id in config to skip search at runtime:**
```python
# In config: jentic_op_id = "op_abc123def456..."
# Tool reads: op_id = get_config().get("jentic_op_id")
# If non-empty: skip search, go directly to load (or skip load if inputs are known)
# For the demo: after first successful search, log the op_id and pin it in .env
```

**OperationDetail vs WorkflowDetail dispatch:**
- Both have `.id` and `.inputs` (JSON schema). The `id` prefix (`op_` vs `wf_`) tells you the type, but `execute()` handles both transparently via the same `ExecutionRequest`.
- `WorkflowDetail.inputs` is merged across all workflow steps (the SDK flattens it), so you interact with it the same way.

---

### Q2: Async→sync bridge [VERIFIED: SDK source inspection]

**Key fact:** `Jentic` is a pure async class (`async def search/load/execute`). LangGraph nodes are sync. The `@meter_tool` wrapper is sync. The tool function must be sync.

**Recommended pattern — thread-isolated event loop:**

```python
import asyncio
import concurrent.futures


def _run_async(coro):
    """Run an async coroutine from sync code, thread-safely.

    Using asyncio.run() is correct when no event loop is running on the
    current thread (LangGraph is synchronous today). The
    concurrent.futures fallback handles the pathological case where a
    running loop is detected (e.g. Jupyter-style environments or if
    LangGraph ever adopts async in a future version).
    """
    try:
        # Fast path — no running loop on this thread (normal LangGraph case)
        return asyncio.run(coro)
    except RuntimeError as exc:
        if "cannot be called from a running loop" not in str(exc):
            raise
        # Fallback — submit to a fresh thread with its own event loop
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(asyncio.run, coro)
            return future.result()
```

**Why `asyncio.run` is safe (not `loop.run_until_complete`):**
- `asyncio.run()` creates a new event loop, runs the coroutine to completion, and closes the loop — no shared state.
- `loop.run_until_complete()` on an existing loop is NOT re-entrant.
- LangGraph is synchronous (`StateGraph.invoke` is sync); the thread that calls the tool has no running loop.

**Do NOT use `nest_asyncio`** — it monkey-patches the event loop globally, is not thread-safe, and is an implicit external dependency the project has not adopted.

---

### Q3: Revenium per-call tool pricing [VERIFIED: OAS scratchpad/oas.json]

**OAS server:** `https://api.revenium.ai/profitstream` (from OAS `.servers[]`)
**Auth:** `x-api-key: <rev_sk_*>` (write-scope key, same as used for billing)

**The pricing mechanism is the `ToolResource` object — NOT `MeteringElementDefinitionResource`.**

`MeteringElementDefinitionResource` defines custom dimension metadata (STRING/NUMBER values for analytics segmentation like "country"). That is a different concept and is NOT where dollar prices live.

**Step-by-step: register a priced tool**

```
POST https://api.revenium.ai/profitstream/v2/api/tools
x-api-key: rev_sk_...
Content-Type: application/json

{
  "teamId": "<revenium_team_id from config, e.g. vQgNV5>",
  "toolId": "jentic:news",
  "name": "Jentic News Tool",
  "description": "External news data via Jentic tool-execution SDK",
  "toolType": "CUSTOM",
  "toolProvider": "jentic",
  "enabled": true,
  "pricing": {
    "currency": "USD",
    "elements": [
      {
        "name": "requests",
        "unitPrice": "0.05",
        "aggregationType": "COUNT"
      }
    ]
  }
}
```

**Field semantics (from OAS schema):**
- `toolId` (string) — unique identifier within the team. **Must exactly match** the string passed to `@meter_tool("jentic:news")` and emitted in the `toolId` field of the tool event.
- `toolType` — enum: `MCP_SERVER | MULTIMODAL | TOOL_CALL | CUSTOM`. Use `CUSTOM` for Jentic-backed tools.
- `pricing.elements[].aggregationType` — enum: `SUM | COUNT | AVERAGE | MAXIMUM | DISTINCT`. For per-call flat fee: use `COUNT` (counts events) with `unitPrice`.
- `pricing.elements[].unitPrice` — string (decimal), e.g. `"0.05"` = $0.05/call.
- `pricing.elements[].tiers` — optional volume tiers; null/omit for flat rate.

**This is API-automatable** (add to `scripts/setup_revenium.py`) using the `rev_sk_*` key already in config as `revenium_sk_api_key`.

**Operator steps for the demo (also automatable):**
1. `POST /v2/api/tools` (above) — creates the tool + price model. Idempotent if done before any tool events.
2. Emit tool events via `@meter_tool("jentic:news")` — Revenium matches incoming `toolId` to the registered tool and applies the price.
3. Verify in dashboard: Tools → `jentic:news` → cost per event.

**Host discrepancy — FLAGGED [ASSUMED]:**
The OAS file states `https://api.revenium.ai/profitstream` as the server. But STATE.md (Phase 01-01) records that the Platform API live host is `https://api.prod.ai.hcapp.io/profitstream`. The billing emitter (`validate_billing.py`) uses `api.prod.ai.hcapp.io`. The `revenium_profitstream_url` config key defaults to `https://api.revenium.io` and is overridden to `api.prod.ai.hcapp.io` for live runs. The operator must confirm which host accepts the tool registration `POST` with the `rev_sk_*` key. The `setup_revenium.py` script should try the same host as `revenium_profitstream_url` (i.e. `api.prod.ai.hcapp.io`) since that is what works for billing.

---

### Q4: Tool wiring — direct analyst tool, NOT route_to_vendor [VERIFIED: codebase inspection]

**Decision: direct analyst tool, NOT a new vendor in `route_to_vendor`.**

Rationale:
1. `route_to_vendor` routes by data _type_ (stock, news, macro) across interchangeable vendor implementations. Jentic is not a news-data vendor in that sense — it is a cross-cutting tool-execution platform that can call any credentialed API.
2. Adding Jentic to `VENDOR_METHODS["get_news"]` would require it to match the existing `get_news(ticker, start_date, end_date) -> str` signature exactly, but Jentic inputs are API-specific and unknown until load time.
3. The `route_to_vendor` sentinel path (`NO_DATA_AVAILABLE`) is already the convention the tool must follow — the tool imports and returns that string directly, not by registering with the router.
4. Existing `get_news` / `get_global_news` continue to work unchanged; the Jentic tool is additive.

**Exact wiring pattern — mirror `news_data_tools.py`:**

New file: `tradingagents/agents/utils/jentic_news_tools.py`
```python
# tradingagents/agents/utils/jentic_news_tools.py
from __future__ import annotations

from typing import Annotated

from langchain_core.tools import tool

from tradingagents.revenium.meter_tool import meter_tool


@tool
@meter_tool("jentic:news")          # innermost: metering fires on .func() calls too
def get_jentic_news(
    query: Annotated[str, "Search query, e.g. 'NVDA earnings news'"],
) -> str:
    """Retrieve news via Jentic's managed-auth tool-execution layer.

    Uses the Jentic SDK to execute a credentialed news API operation.
    Requires JENTIC_AGENT_API_KEY and jentic_tool_enabled=True in config.
    Returns NO_DATA_AVAILABLE sentinel on any error (fail-soft).
    """
    return _jentic_news_impl(query)


def _jentic_news_impl(query: str) -> str:
    """Sync implementation — separated for testability."""
    from tradingagents.dataflows.config import get_config  # call-time read
    cfg = get_config()
    if not cfg.get("jentic_tool_enabled", False):
        return "NO_DATA_AVAILABLE: Jentic tool disabled (jentic_tool_enabled=False)."
    api_key = cfg.get("jentic_agent_api_key", "")
    if not api_key:
        return "NO_DATA_AVAILABLE: JENTIC_AGENT_API_KEY not configured."
    # ... async execution ...
```

**`agent_utils.py` additions:**
```python
# In tradingagents/agents/utils/agent_utils.py
from tradingagents.agents.utils.jentic_news_tools import get_jentic_news  # new import

__all__ = [
    ...,
    "get_jentic_news",   # add to public surface
]
```

**`news_analyst.py` wiring:**
```python
from tradingagents.agents.utils.agent_utils import (
    get_global_news,
    get_jentic_news,   # NEW
    get_instrument_context_from_state,
    get_language_instruction,
    get_macro_indicators,
    get_news,
    get_prediction_markets,
)

# In create_news_analyst:
tools = [
    get_news,
    get_global_news,
    get_macro_indicators,
    get_prediction_markets,
    get_jentic_news,   # NEW — appears only when jentic_tool_enabled=True AND key set
]
```

> Note: even when the tool is in the tools list, if `jentic_tool_enabled=False` or key is missing, the tool returns the `NO_DATA_AVAILABLE` sentinel on invocation. The LLM will try the tool; it will get the sentinel; it will not use that data. Alternatively, filter the list at build time: `tools = [...] + ([get_jentic_news] if cfg.get("jentic_tool_enabled") else [])` — this avoids the LLM ever calling the disabled tool, which is cleaner for demo reliability.

**Recommendation:** build the tools list conditionally (check `jentic_tool_enabled` in `news_analyst_node` before appending `get_jentic_news`) — this prevents the LLM from calling a tool that will always return no data.

---

### Q5: Config keys [VERIFIED: default_config.py + SDK cfg.py]

Add to `DEFAULT_CONFIG` in `tradingagents/default_config.py`:

```python
# Jentic tool metering (Phase 6, JEN-01..04)
# jentic_tool_enabled gates whether the Jentic news tool appears in the news analyst.
# Must be True AND jentic_agent_api_key must be set for any live Jentic calls.
"jentic_tool_enabled":   False,                              # bool — safe off-by-default
"jentic_agent_api_key":  os.getenv("JENTIC_AGENT_API_KEY", ""),
# Pinned op UUID — skip search at runtime for demo reliability (JEN-01).
# Set this to the op_ UUID of the credentialed news operation after first discovery run.
# Empty string = fall back to jentic_search_query each call.
"jentic_op_id":          os.getenv("JENTIC_OP_ID", ""),
# Search query used when jentic_op_id is not pinned.
"jentic_search_query":   os.getenv("JENTIC_SEARCH_QUERY", "get news headlines for a stock ticker"),
# The Revenium toolId emitted to /v2/tool/events — must match the ToolResource registration.
"jentic_tool_id":        os.getenv("JENTIC_TOOL_ID", "jentic:news"),
```

Add to `_ENV_OVERRIDES` (BEFORE `DEFAULT_CONFIG` is populated, following existing pattern):

```python
# Jentic tool metering (Phase 6)
"JENTIC_TOOL_ENABLED":    "jentic_tool_enabled",   # coerced to bool by _coerce
"JENTIC_AGENT_API_KEY":   "jentic_agent_api_key",
"JENTIC_OP_ID":           "jentic_op_id",
"JENTIC_SEARCH_QUERY":    "jentic_search_query",
"JENTIC_TOOL_ID":         "jentic_tool_id",
```

**Coercion note:** `jentic_tool_enabled` defaults to `False` (bool), so `_coerce` will correctly convert the env var string `"true"` / `"1"` → `True`.

**`.env.example` additions:**
```bash
# Jentic tool metering (Phase 6 — optional, requires credentialed news API)
JENTIC_AGENT_API_KEY=           # from https://app.jentic.com/dashboard
JENTIC_TOOL_ENABLED=false       # set true once a news API is credentialed
JENTIC_OP_ID=                   # pin operation UUID after discovery; skip search at runtime
```

---

### Q6: Keyless mocking [VERIFIED: existing test patterns + SDK source]

**The critical pre-condition:** `jentic.lib.cfg.AgentConfig.from_env()` raises `MissingAgentKeyError` (subclass of `JenticEnvironmentError → JenticException → Exception`) if `JENTIC_AGENT_API_KEY` is not set.

**Defense in the tool itself (config-gate before SDK init):**
```python
# In _jentic_news_impl:
api_key = cfg.get("jentic_agent_api_key", "")
if not api_key:
    return "NO_DATA_AVAILABLE: ..."   # never instantiates Jentic
```

This means: as long as `jentic_agent_api_key` is `""` in config (the default), `Jentic()` is never instantiated, `AgentConfig.from_env()` is never called, and NO env var is needed. Tests that don't set the key pass without any mocking.

**For tests that DO exercise the Jentic execution path (testing the async bridge, output handling, etc.):**

```python
from unittest.mock import AsyncMock, MagicMock, patch

def test_jentic_news_executes_and_returns_output():
    from tradingagents.agents.utils.jentic_news_tools import _jentic_news_impl
    from tradingagents.dataflows.config import set_config, get_config

    mock_exec_resp = MagicMock()
    mock_exec_resp.success = True
    mock_exec_resp.status_code = 200
    mock_exec_resp.output = {"articles": [{"title": "NVDA soars"}]}
    mock_exec_resp.error = None

    mock_load_resp = MagicMock()
    mock_tool_info = MagicMock()
    mock_tool_info.inputs = {"properties": {"query": {"type": "string"}}}
    mock_load_resp.tool_info = {"op_test_123": mock_tool_info}

    mock_search_resp = MagicMock()
    mock_result = MagicMock()
    mock_result.id = "op_test_123"
    mock_result.api_name = "testnews"
    mock_search_resp.results = [mock_result]

    mock_client = MagicMock()
    mock_client.search = AsyncMock(return_value=mock_search_resp)
    mock_client.load = AsyncMock(return_value=mock_load_resp)
    mock_client.execute = AsyncMock(return_value=mock_exec_resp)

    orig = get_config()
    set_config({
        "jentic_tool_enabled": True,
        "jentic_agent_api_key": "ak_test_key",
        "jentic_op_id": "op_test_123",
        "jentic_tool_id": "jentic:news",
    })
    try:
        with patch(
            "tradingagents.agents.utils.jentic_news_tools.Jentic",
            return_value=mock_client,
        ):
            result = _jentic_news_impl("NVDA latest news")
        assert "NVDA soars" in result or isinstance(result, str)
    finally:
        set_config(orig)
```

**For fail-soft sentinel test (Jentic error → NO_DATA_AVAILABLE):**
```python
mock_client.execute = AsyncMock(side_effect=Exception("Jentic network error"))
# result must be "NO_DATA_AVAILABLE: ..."
```

**`conftest.py` gap:** `JENTIC_AGENT_API_KEY` is NOT in `_API_KEY_ENV_VARS` in `conftest.py`. If the env var is set in `.env` (which it now is) and `python-dotenv` loads it at import time, tests that import the jentic tool module at module level could pick it up. The safest fix: add `"JENTIC_AGENT_API_KEY"` to `_API_KEY_ENV_VARS` in `conftest.py` with a `monkeypatch.setenv(var, os.environ.get(var, ""))` — setting it to empty string overrides any loaded `.env` value and prevents accidental live calls.

---

### Q7: Landmines

**L1 — `jentic` not in pyproject.toml OR uv.lock**
The package is installed in `.venv` but is NOT declared in `pyproject.toml` and NOT tracked in `uv.lock`. This means `pip install ".[dev]"` in CI will not install jentic. Wave 0 must add `"jentic>=0.10.0"` to `[project].dependencies` and run `uv lock` to regenerate the lockfile. [VERIFIED: pyproject.toml grep + uv.lock grep both empty]

**L2 — `AgentConfig.from_env()` raises on missing key**
`MissingAgentKeyError` (extends `JenticEnvironmentError → JenticException → Exception`) is raised by `AgentConfig.from_env()` if `JENTIC_AGENT_API_KEY` is not in env. The config-gate (`if not jentic_agent_api_key: return NO_DATA_AVAILABLE`) must execute BEFORE `Jentic()` is instantiated to prevent this. Do NOT call `AgentConfig.from_env()` unconditionally at module import time. [VERIFIED: jentic/lib/cfg.py]

**L3 — `asyncio.run()` cannot be called from a running event loop**
If code is running inside an async event loop (Jupyter, future async LangGraph), `asyncio.run(coro)` raises `RuntimeError: This event loop is already running`. The `_run_async()` helper in Q2 handles this defensively with a `ThreadPoolExecutor` fallback. LangGraph today is synchronous — this is a guard, not a required path. [VERIFIED: Python docs; LangGraph is sync per CLAUDE.md]

**L4 — `OperationDetail.inputs` is a JSON schema, not an inputs dict**
`LoadResponse.tool_info[op_id].inputs` returns a JSON schema dict (e.g. `{"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}`). It is NOT the runtime inputs dict. The tool must read `.inputs["properties"]` to know what keys to build, then construct `{"query": user_query}` for `ExecutionRequest.inputs`. [VERIFIED: SDK model_json_schema]

**L5 — `ExecuteResponse.output` is `Any | None`**
The output type is declared as `Any | None`. For a news API it might be a dict, a list, or a string. The tool must stringify it safely (e.g. `str(exec_resp.output)` or `json.dumps`) and handle `None` by returning the sentinel. Do not assume a string. [VERIFIED: ExecuteResponse schema]

**L6 — `toolId` must exactly match ToolResource registration**
The string passed to `@meter_tool("jentic:news")` (and emitted in tool events as `toolId`) MUST exactly match the `toolId` field of the registered `ToolResource` in Revenium. A mismatch means the event arrives with no price model → $0.00. The `jentic_tool_id` config key in DEFAULT_CONFIG provides a stable, operator-configurable value for both the decorator call and the setup script. [VERIFIED: OAS ToolResource + decorator.py `_build_event_payload`]

**L7 — News API not yet credentialed in Jentic**
As of the spike, `jentic.list_apis()` returns only `anthropic`, `openai`, `fred`. A news API must be credentialed in the Jentic dashboard before `execute()` can return real data. The live-verify script (`scripts/validate_jentic.py`) must be gated on this: add a pre-flight check that calls `list_apis()` and asserts the expected news API is present; exit early with a clear message if not. [VERIFIED: spike findings in CONTEXT.md]

**L8 — Decorator order: `@meter_tool` must be innermost**
`@tool` must be outermost (so LangChain sees a `StructuredTool`), `@meter_tool` must be innermost (so `StructuredTool.func` IS the metered wrapper — `tool.func(...)` calls also pass through metering). Reversing the order makes `@tool` see the unwrapped function and metering only fires when the LLM invokes the tool, not on `.func()` direct calls from tests. [VERIFIED: meter_tool.py docstring + agent_utils.py pattern]

**L9 — `configure()` must be called before `_send_tool_event`**
`revenium_metering.decorator` has module-level defaults `_metering_url = None` and `_api_key = None`, falling back to `http://localhost:8082 / demo-key`. The existing `meter_tool.py` already calls `_configure_tool_metering(metering_url=..., api_key=...)` before `_send_tool_event`. The Jentic tool reuses `@meter_tool` from `tradingagents.revenium.meter_tool` (not the SDK decorator directly), so this is handled. Do NOT call the SDK's `meter_tool` decorator from `revenium_metering` directly. [VERIFIED: meter_tool.py lines 108-111]

---

## Architecture Patterns

### System Architecture Diagram

```
news_analyst_node (sync)
    │
    ├─ get_news / get_global_news     (existing vendor route → yfinance/alpha_vantage)
    │
    └─ get_jentic_news                (@tool outermost, @meter_tool("jentic:news") innermost)
           │
           ├─ config gate: jentic_tool_enabled? jentic_agent_api_key set?
           │       NO  → return "NO_DATA_AVAILABLE: ..."
           │
           ├─ _run_async(execute_jentic(query))
           │       │
           │       ├─ [if op_id pinned] skip search
           │       │
           │       ├─ [else] Jentic.search(SearchRequest) → pick top result id
           │       │
           │       ├─ Jentic.load(LoadRequest(ids=[id])) → tool_info → inputs schema
           │       │
           │       └─ Jentic.execute(ExecutionRequest(id, inputs)) → ExecuteResponse
           │               success=False or output=None → "NO_DATA_AVAILABLE: ..."
           │               success=True → str(output)
           │
           ├─ @meter_tool wrapper fires AFTER return:
           │       _configure_tool_metering(url, key)
           │       _send_tool_event(tool_id="jentic:news", duration_ms, success, ctx)
           │       → POST api.revenium.ai/meter/v2/tool/events
           │
           └─ return str result to LLM
```

### Recommended Project Structure

```
tradingagents/
├── agents/
│   ├── analysts/
│   │   └── news_analyst.py           # add get_jentic_news to tools list (conditional)
│   └── utils/
│       ├── jentic_news_tools.py      # NEW: @tool + @meter_tool + _run_async + fail-soft
│       └── agent_utils.py            # add get_jentic_news import + __all__ entry
├── default_config.py                 # add 5 jentic_* keys + 5 _ENV_OVERRIDES entries
scripts/
└── validate_jentic.py                # NEW: gated live-verify (mirrors validate_metering.py)
tests/
└── test_jentic_tool.py               # NEW: unit tests (JEN-03)
```

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Async→sync bridge | Custom event-loop juggling | `asyncio.run()` + `ThreadPoolExecutor` fallback | Safe, stdlib, no extra deps |
| API discovery | Hard-code operation paths | Jentic `search` + `load` | SDK handles auth, discovery, schema |
| Tool event HTTP | Custom HTTP post to Revenium | `_send_tool_event` via `@meter_tool` | Already wires auth, URL, context, fail-open |
| Tool pricing | Custom price field in the event payload | Revenium `ToolResource.pricing` registration | `_build_event_payload` has NO price field by design; pricing is server-side |

---

## Code Examples

### Full sync wrapper with config gate and fail-soft

```python
# Source: confirmed patterns from tradingagents/revenium/meter_tool.py + jentic/jentic.py
# tradingagents/agents/utils/jentic_news_tools.py

from __future__ import annotations

import asyncio
import concurrent.futures
import json
import logging
from typing import Annotated

from langchain_core.tools import tool

from tradingagents.revenium.meter_tool import meter_tool

logger = logging.getLogger(__name__)

_NO_DATA = (
    "NO_DATA_AVAILABLE: Jentic news call failed — {reason}. "
    "Do not estimate or fabricate news data."
)


def _run_async(coro):
    """Run a coroutine from sync context, thread-safely."""
    try:
        return asyncio.run(coro)
    except RuntimeError as exc:
        if "cannot be called from a running loop" not in str(exc):
            raise
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result()


async def _do_jentic_news(query: str, cfg: dict) -> str:
    """Async body: search→load→execute via Jentic SDK."""
    from jentic import Jentic
    from jentic.lib.cfg import AgentConfig
    from jentic.lib.models import ExecutionRequest, LoadRequest, SearchRequest

    # Instantiate with explicit key so we don't depend on JENTIC_AGENT_API_KEY env
    # (it's in config, not necessarily re-exported to env at call time).
    import os
    os.environ.setdefault("JENTIC_AGENT_API_KEY", cfg["jentic_agent_api_key"])
    client = Jentic(AgentConfig.from_env())

    op_id: str = cfg.get("jentic_op_id", "")
    if not op_id:
        # Discovery path — run once, then pin op_id in config for demo
        search_resp = await client.search(
            SearchRequest(query=cfg.get("jentic_search_query", query), limit=5)
        )
        if not search_resp.results:
            return _NO_DATA.format(reason="no Jentic operations matched the search query")
        op_id = search_resp.results[0].id

    # Shape inputs — for pinned ops we pass the user query directly.
    # When discovery runs, inputs schema is in load_resp.tool_info[op_id].inputs.
    inputs: dict = {"q": query}  # NewsAPI getEverything param is `q` (CONTEXT LIVE TARGET) — NOT `query`

    exec_resp = await client.execute(ExecutionRequest(id=op_id, inputs=inputs))
    if not exec_resp.success or exec_resp.output is None:
        reason = exec_resp.error or f"status_code={exec_resp.status_code}"
        return _NO_DATA.format(reason=reason)

    output = exec_resp.output
    if isinstance(output, (dict, list)):
        return json.dumps(output, ensure_ascii=False)
    return str(output)


def _jentic_news_impl(query: str) -> str:
    """Sync implementation — called by the @tool wrapper; separated for testability."""
    from tradingagents.dataflows.config import get_config  # call-time, not import-time

    cfg = get_config()
    if not cfg.get("jentic_tool_enabled", False):
        return _NO_DATA.format(reason="jentic_tool_enabled is False")
    api_key: str = cfg.get("jentic_agent_api_key", "") or ""
    if not api_key:
        return _NO_DATA.format(reason="JENTIC_AGENT_API_KEY not configured")

    try:
        return _run_async(_do_jentic_news(query, cfg))
    except Exception as exc:  # noqa: BLE001 — fail open, never block the run
        logger.warning("Jentic news call failed: %s", exc)
        return _NO_DATA.format(reason=str(exc)[:200])


@tool
@meter_tool("jentic:news")
def get_jentic_news(
    query: Annotated[str, "News search query, e.g. 'NVDA latest earnings news'"],
) -> str:
    """Retrieve news via Jentic's managed-auth external API layer.

    Requires jentic_tool_enabled=True and JENTIC_AGENT_API_KEY in config.
    Returns NO_DATA_AVAILABLE on any error (fail-soft — never crashes the run).
    """
    return _jentic_news_impl(query)
```

### ToolResource registration — for `setup_revenium.py`

```python
# Source: OAS /v2/api/tools POST + existing validate_billing.py pattern
import requests

def register_jentic_tool(cfg: dict) -> None:
    """Register Jentic news tool with pricing in Revenium Platform API."""
    # Use same host as billing (api.prod.ai.hcapp.io confirmed for live runs)
    profitstream_url = (cfg.get("revenium_profitstream_url") or "").rstrip("/")
    api_key = cfg.get("revenium_sk_api_key") or cfg.get("revenium_billing_api_key")
    team_id = cfg.get("revenium_team_id")
    tool_id = cfg.get("jentic_tool_id", "jentic:news")

    payload = {
        "teamId": team_id,
        "toolId": tool_id,
        "name": "Jentic News Tool",
        "description": "External news data via Jentic tool-execution SDK (Phase 6)",
        "toolType": "CUSTOM",
        "toolProvider": "jentic",
        "enabled": True,
        "pricing": {
            "currency": "USD",
            "elements": [
                {
                    "name": "requests",
                    "unitPrice": "0.05",
                    "aggregationType": "COUNT",
                }
            ],
        },
    }
    resp = requests.post(
        f"{profitstream_url}/v2/api/tools",
        headers={"x-api-key": api_key, "Content-Type": "application/json"},
        json=payload,
        timeout=10,
    )
    resp.raise_for_status()
    print(f"[PASS] Tool registered: {resp.json().get('id')} toolId={tool_id}")
```

### Test skeleton — JEN-03 coverage

```python
# tests/test_jentic_tool.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def _make_exec_resp(success=True, output=None, error=None, status_code=200):
    r = MagicMock()
    r.success = success
    r.status_code = status_code
    r.output = output
    r.error = error
    return r


@pytest.mark.unit
def test_jentic_tool_disabled_returns_sentinel():
    """jentic_tool_enabled=False → NO_DATA_AVAILABLE without SDK call."""
    from tradingagents.agents.utils.jentic_news_tools import _jentic_news_impl
    from tradingagents.dataflows.config import get_config, set_config

    orig = get_config()
    set_config({"jentic_tool_enabled": False})
    try:
        result = _jentic_news_impl("NVDA news")
        assert result.startswith("NO_DATA_AVAILABLE")
    finally:
        set_config(orig)


@pytest.mark.unit
def test_jentic_tool_keyless_returns_sentinel():
    """No jentic_agent_api_key → NO_DATA_AVAILABLE without SDK call."""
    from tradingagents.agents.utils.jentic_news_tools import _jentic_news_impl
    from tradingagents.dataflows.config import get_config, set_config

    orig = get_config()
    set_config({"jentic_tool_enabled": True, "jentic_agent_api_key": ""})
    try:
        result = _jentic_news_impl("NVDA news")
        assert result.startswith("NO_DATA_AVAILABLE")
    finally:
        set_config(orig)


@pytest.mark.unit
def test_jentic_tool_fires_meter_event(monkeypatch):
    """@meter_tool fires exactly one tool event per call with tool_id='jentic:news'."""
    from tradingagents.agents.utils.jentic_news_tools import get_jentic_news
    from tradingagents.dataflows.config import get_config, set_config

    mock_client = MagicMock()
    mock_exec = MagicMock()
    mock_exec.success = True
    mock_exec.status_code = 200
    mock_exec.output = "headline: NVDA surges"
    mock_exec.error = None
    mock_client.execute = AsyncMock(return_value=mock_exec)
    mock_client.search = AsyncMock()  # should not be called (op_id pinned)

    orig = get_config()
    set_config({
        "jentic_tool_enabled": True,
        "jentic_agent_api_key": "ak_test",
        "jentic_op_id": "op_test123",
        "revenium_api_key": "rev_mk_test",
        "revenium_api_url": "https://api.revenium.ai",
        "revenium_organization_name": "Revenium-Research-Desk",
        "revenium_product_name": "trading-signal",
        "revenium_subscriber_id": "test@example.com",
    })
    try:
        with patch(
            "tradingagents.agents.utils.jentic_news_tools.Jentic",
            return_value=mock_client,
        ), patch("revenium_metering.decorator._send_tool_event") as mock_send:
            result = get_jentic_news.func("NVDA latest news")

        assert mock_send.call_count == 1
        assert mock_send.call_args.kwargs["tool_id"] == "jentic:news"
        assert isinstance(result, str)
    finally:
        set_config(orig)


@pytest.mark.unit
def test_jentic_tool_fail_soft_on_execute_error():
    """Jentic execute() exception → NO_DATA_AVAILABLE, never raises."""
    from tradingagents.agents.utils.jentic_news_tools import _jentic_news_impl
    from tradingagents.dataflows.config import get_config, set_config

    mock_client = MagicMock()
    mock_client.execute = AsyncMock(side_effect=Exception("network timeout"))
    mock_client.search = AsyncMock()

    orig = get_config()
    set_config({
        "jentic_tool_enabled": True,
        "jentic_agent_api_key": "ak_test",
        "jentic_op_id": "op_test123",
    })
    try:
        with patch(
            "tradingagents.agents.utils.jentic_news_tools.Jentic",
            return_value=mock_client,
        ):
            result = _jentic_news_impl("NVDA news")
        assert result.startswith("NO_DATA_AVAILABLE")
    finally:
        set_config(orig)


@pytest.mark.unit
def test_jentic_async_bridge_returns_output():
    """Async→sync bridge (_run_async) returns the coroutine result correctly."""
    from tradingagents.agents.utils.jentic_news_tools import _run_async

    async def _coro():
        return "bridge_ok"

    assert _run_async(_coro()) == "bridge_ok"
```

---

## Common Pitfalls

### Pitfall 1: `jentic` missing from pyproject.toml breaks CI
**What goes wrong:** `pip install ".[dev]"` in CI skips jentic (not declared). Import fails at test collection with `ModuleNotFoundError: No module named 'jentic'`.
**Why it happens:** Package was installed manually into venv during spike; neither `pyproject.toml` nor `uv.lock` reflects it.
**How to avoid:** Wave 0 task: add `"jentic>=0.10.0"` to `[project].dependencies`, run `uv lock`, commit both files.
**Warning signs:** `ModuleNotFoundError` on CI; `uv lock` shows jentic absent.

### Pitfall 2: `AgentConfig.from_env()` raises before config gate
**What goes wrong:** If `Jentic()` is instantiated before the `if not api_key: return` guard, Python calls `AgentConfig.from_env()` which raises `MissingAgentKeyError` even in keyless test runs.
**Why it happens:** SDK reads `JENTIC_AGENT_API_KEY` from env at instantiation time, not at call time.
**How to avoid:** Always check `cfg.get("jentic_agent_api_key")` BEFORE instantiating `Jentic`. Never call `Jentic()` at module import time.
**Warning signs:** Tests fail with `MissingAgentKeyError` despite mocking.

### Pitfall 3: `toolId` mismatch breaks per-call pricing
**What goes wrong:** Tool events arrive in Revenium with `toolId="jentic:news"` but the registered ToolResource has `toolId="jentic-news"` (dash vs colon) — no price model matches → $0.00/call.
**Why it happens:** `toolId` is a free-form string; the decorator and the registration must be byte-identical.
**How to avoid:** Single source of truth via `jentic_tool_id` config key; both the `@meter_tool(cfg["jentic_tool_id"])` call in the tool and the `setup_revenium.py` registration read from config.
**Warning signs:** Tool events appear in dashboard with `$0.00` tool cost despite pricing setup.

### Pitfall 4: `@meter_tool` decorator order reversed
**What goes wrong:** If `@meter_tool` is outermost and `@tool` is innermost, LangChain sees a `meter_tool` closure as the tool function (not a `StructuredTool`), and direct `.func()` calls bypass metering.
**Why it happens:** Decorator application order: Python applies innermost first. `@tool` outermost means `@tool` wraps whatever is below it (the `@meter_tool`-wrapped function).
**How to avoid:** Always: `@tool` on top, `@meter_tool` directly below, decorated function at bottom.
**Warning signs:** Tool imported by `bind_tools` shows type errors; `.func()` calls in tests return unwrapped results.

### Pitfall 5: `JENTIC_AGENT_API_KEY` leaks from `.env` into tests
**What goes wrong:** `python-dotenv` loads `.env` at startup; if `JENTIC_AGENT_API_KEY` is set, keyless tests that check `jentic_agent_api_key` from config will find a non-empty value (from `os.getenv` in DEFAULT_CONFIG), defeating the keyless guard.
**Why it happens:** DEFAULT_CONFIG reads `os.getenv("JENTIC_AGENT_API_KEY", "")` at process start; tests that use `_isolate_config()` reset to DEFAULT_CONFIG — which already captured the env value.
**How to avoid:** Add `"JENTIC_AGENT_API_KEY"` to `_API_KEY_ENV_VARS` in `conftest.py` (with `monkeypatch.setenv(var, "")` to clear it). OR: always pass `jentic_agent_api_key=""` explicitly in `set_config()` in tests.
**Warning signs:** Keyless tests pass locally (no key set) but fail on developer machines with `.env` loaded.

### Pitfall 6: OAS host vs live profitstream host discrepancy
**What goes wrong:** ToolResource registration `POST /v2/api/tools` sent to `api.revenium.ai/profitstream` may return 401/403 if the live tenant is on `api.prod.ai.hcapp.io`.
**Why it happens:** OAS states `api.revenium.ai/profitstream` as server; Phase 4 billing proven to work on `api.prod.ai.hcapp.io`. May be two environments (public vs. tenant-specific cluster).
**How to avoid:** Use `revenium_profitstream_url` config key (same host as billing) in `setup_revenium.py`. Test with both hosts if the first 401s.
**Warning signs:** 401 or 404 on tool registration despite valid `rev_sk_*` key.

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `asyncio.get_event_loop().run_until_complete()` | `asyncio.run()` (clean loop per call) | Python 3.10+ | Safer; no shared loop state |
| SDK `meter_tool` decorator (revenium-metering) called directly | Repo-owned `tradingagents.revenium.meter_tool.meter_tool` adapter | Phase 1 | Adds `configure()` call (fixes localhost default), reads config at call time |
| Manual HTTP for tool pricing | Revenium `ToolResource` API + `pricing.elements[].aggregationType=COUNT` | OAS current | Per-call pricing is server-side registration, not in event payload |

**Deprecated / avoid:**
- Calling `revenium_metering.decorator.meter_tool` directly from new tools — use the repo's adapter at `tradingagents.revenium.meter_tool` which handles `configure()` and config-at-call-time.
- `nest_asyncio` — not needed; thread-pool fallback handles running-loop edge case without monkey-patching.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | The Revenium `ToolResource` registration on `api.prod.ai.hcapp.io` accepts the same `rev_sk_*` key used for billing | Q3 — Pricing | If not, `setup_revenium.py` fails; operator must use dashboard instead |
| A2 | `jentic==0.10.0` API is stable (search/load/execute signatures unchanged from spike) | Q1 | If SDK upgrades and breaks API, call sequence fails; pin `jentic>=0.10.0,<1.0` in pyproject |
| A3 | `jentic` source repo is the official Jentic SDK (legitimacy) | Package Legitimacy | Unlikely — confirmed name matches docs.jentic.com — but slopcheck not run |
| A4 | `OperationDetail.inputs` is always a JSON schema dict (non-null) for credentialed ops | Q1 | If null, the `inputs={"query": query}` construction might fail; must guard for None |
| A5 | `JENTIC_AGENT_API_KEY` in `.env` is already set (per CONTEXT.md "Key is now present in `.env`") | Q6 | If not, all live tests need the key; no impact on unit tests due to config gate |

---

## Open Questions (RESOLVED)

**RESOLVED (2026-07-03):**
- **OQ1** (host for `POST /v2/api/tools`): RESOLVED — config-driven via `revenium_profitstream_url`; `setup_revenium.py` tries it, falls back, and logs a hint; operator confirms at the 06-03 Task 3 checkpoint (Assumption A1).
- **OQ2** (news API inputs schema): RESOLVED — op `op_ba86fdce1bade1b7` (newsapi.org `getEverything`) confirmed credentialed; input param is `q` per CONTEXT.md LIVE TARGET.
- **OQ3** (conditional tool inclusion): RESOLVED — conditional append at call time inside `news_analyst_node` when `jentic_tool_enabled=True` (06-02 Task 3).

1. **Which profitstream host accepts `POST /v2/api/tools`?**
   - What we know: OAS says `api.revenium.ai/profitstream`; billing proven on `api.prod.ai.hcapp.io`.
   - What's unclear: Are both valid endpoints? Is there a redirect? Is the Tools API behind the same tenant-scoped host?
   - Recommendation: `setup_revenium.py` tries `revenium_profitstream_url` (config-driven); if 401/404 try `api.revenium.ai/profitstream`; log both results.

2. **What is the exact inputs schema for the credentialed news API?**
   - What we know: `OperationDetail.inputs` returns a JSON schema; `WorkflowDetail.inputs` merged across steps.
   - What's unclear: The actual news API operation id and input field names are unknown until the user credentials a news API and runs `search`.
   - Recommendation: The live-verify script should run `search` + `load` and print the inputs schema so the operator can validate the `inputs` dict before executing.

3. **Should `get_jentic_news` always appear in the news analyst tools list, or only when `jentic_tool_enabled=True`?**
   - What we know: Always-in costs one extra tool in the LLM prompt even when disabled; conditionally-in is cleaner but the news analyst must read config at node-creation time.
   - What's unclear: Whether `news_analyst_node` closure should read config at build time (factory call) or at call time (node invocation). Config is call-time by convention.
   - Recommendation: Read config at call time inside `news_analyst_node`, build the tools list there, and conditionally append `get_jentic_news` only when `jentic_tool_enabled=True`. This keeps the factory pattern and avoids importing jentic at module level.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `jentic` package | JEN-01..04 | Yes (`.venv`) | 0.10.0 | None (must be declared) |
| `JENTIC_AGENT_API_KEY` | JEN-02, JEN-04 (live only) | Present in `.env` | — | Config-gate returns sentinel |
| Jentic news API credential | JEN-04 live verify | NOT YET (anthropic/openai/fred only) | — | Gated; unit tests mock |
| `asyncio` | Q2 bridge | stdlib | always | — |
| `concurrent.futures` | Q2 bridge fallback | stdlib | always | — |
| `revenium_profitstream_url` host for tool registration | JEN-02 pricing setup | Confirmed for billing (`api.prod.ai.hcapp.io`) | — | Dashboard manual |

**Missing dependencies with no fallback:**
- `jentic` not declared in `pyproject.toml` / `uv.lock` — Wave 0 must fix before any CI run.

**Missing dependencies with fallback:**
- Jentic news API credential — unit tests mock; live verify gated on user credentialing.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest >=8.0 |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `pytest tests/test_jentic_tool.py -m unit -x` |
| Full suite command | `pytest tests/ -m unit -x` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| JEN-01 | Fail-soft sentinel on disabled/keyless | unit | `pytest tests/test_jentic_tool.py::test_jentic_tool_disabled_returns_sentinel tests/test_jentic_tool.py::test_jentic_tool_keyless_returns_sentinel -x` | ❌ Wave 0 |
| JEN-01 | Async→sync bridge returns result | unit | `pytest tests/test_jentic_tool.py::test_jentic_async_bridge_returns_output -x` | ❌ Wave 0 |
| JEN-01 | `jentic` importable (declared in pyproject) | unit/smoke | `python -c "import jentic"` | ❌ after Wave 0 pyproject fix |
| JEN-02 | `@meter_tool` fires one event per execute() with correct toolId | unit | `pytest tests/test_jentic_tool.py::test_jentic_tool_fires_meter_event -x` | ❌ Wave 0 |
| JEN-03 | Full suite passes with no JENTIC_AGENT_API_KEY | unit | `pytest tests/ -m unit -x` | ❌ Wave 0 |
| JEN-04 | Live execute() emits metered+priced event | manual/live | `python scripts/validate_jentic.py` (gated) | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `pytest tests/test_jentic_tool.py -m unit -x`
- **Per wave merge:** `pytest tests/ -m unit -x`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/test_jentic_tool.py` — all JEN-01..03 unit tests
- [ ] `tradingagents/agents/utils/jentic_news_tools.py` — implementation
- [ ] `pyproject.toml`: add `"jentic>=0.10.0"` to dependencies
- [ ] `uv lock` regenerate after pyproject update
- [ ] `tradingagents/default_config.py`: add 5 `jentic_*` keys + 5 `_ENV_OVERRIDES` entries
- [ ] `scripts/validate_jentic.py` — gated live-verify script
- [ ] `tests/conftest.py`: add `"JENTIC_AGENT_API_KEY"` to `_API_KEY_ENV_VARS` (set to `""`)

---

## Security Domain

> `security_enforcement` not explicitly disabled.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | Yes (Jentic auth) | `JENTIC_AGENT_API_KEY` in env/config, never logged, lazy import |
| V5 Input Validation | Yes | `query` parameter is a string from the LLM; no SQL/shell injection risk (passed to Jentic HTTP API); no sanitization needed beyond type assertion |
| V6 Cryptography | No | No crypto operations in this phase |
| V4 Access Control | No | Tool-level; existing agent permission model unchanged |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| API key logged | Information Disclosure | `meter_tool.py` already: "Never log secrets or API keys; log only symbolic model names" — apply same to jentic key; `logger.debug` must not print `api_key` |
| LLM prompt injection via news output | Tampering | `ExecuteResponse.output` is passed to LLM as tool result; rely on LangChain's existing tool-result handling; do not eval output |
| `jentic_agent_api_key` leaked via `get_config()` repr | Information Disclosure | `get_config()` returns a deepcopy dict; redact key in any debug logging |

---

## Sources

### Primary (HIGH confidence)
- `jentic==0.10.0` SDK source — introspected directly: `jentic/jentic.py`, `jentic/lib/models.py`, `jentic/lib/cfg.py`, `jentic/lib/core_api.py` — all call sequences, schemas, and exception types confirmed
- `revenium_metering/decorator.py` (installed) — `_build_event_payload` fields, `_send_tool_event` HTTP path, NO price field confirmed
- `scratchpad/oas.json` — OAS for `api.revenium.ai/profitstream`: `/v2/api/tools` POST + `ToolResource` + `ToolPricing` + `ToolPricingElement` schemas confirmed
- `tradingagents/revenium/meter_tool.py` — decorator order, `configure()` call, fail-open pattern confirmed
- `tradingagents/agents/utils/news_data_tools.py` — exact `@tool` + `@meter_tool` composition confirmed
- `tradingagents/default_config.py` — `_ENV_OVERRIDES` pattern, existing Revenium config keys confirmed
- `tests/test_revenium_tool_metering.py` — mocking patterns for `revenium_metering.decorator._send_tool_event` confirmed
- `tests/conftest.py` — `_dummy_api_keys` + `_isolate_config` fixtures confirmed

### Secondary (MEDIUM confidence)
- STATE.md Phase 01-01 decision log — live profitstream host `api.prod.ai.hcapp.io` confirmed by billing validation
- CONTEXT.md Phase 6 spike findings — `jentic.list_apis()` confirmed anthropic/openai/fred, no news API; spike date 2026-07-03

### Tertiary (LOW confidence)
- A2: jentic SDK version stability assumption (`jentic>=0.10.0,<1.0` recommended pin)
- A3: jentic package legitimacy (slopcheck unavailable; official Jentic product assumed)

---

## Metadata

**Confidence breakdown:**
- Jentic call sequence: HIGH — confirmed via direct SDK introspection
- Async→sync bridge: HIGH — confirmed via SDK source + Python stdlib
- Revenium tool pricing: HIGH (mechanism) / LOW (host) — OAS schema confirmed; live host needs operator validation
- Tool wiring pattern: HIGH — mirrors exact existing pattern from 12 data tools
- Config pattern: HIGH — mirrors `_ENV_OVERRIDES` + `DEFAULT_CONFIG` exactly
- Keyless mocking: HIGH — mirrors existing test patterns

**Research date:** 2026-07-03
**Valid until:** 2026-08-03 (jentic SDK is actively developed; re-verify if version changes beyond 0.10.x)
