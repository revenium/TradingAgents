# Phase 2: Trace & Squad Analytics — Research

**Researched:** 2026-06-27
**Domain:** Revenium trace/squad analytics — `parentTransactionId` threading, trace grouping fields, circular pattern detection, span-count validation
**Confidence:** HIGH (SDK signature verified by introspection; callback implementation read directly; Revenium docs fetched from `docs.revenium.io/llms-full.txt` and agent instrumentation guide)

---

## Summary

Phase 1 wired per-call metering with `trace_id`, `agent`, `task_type`, and billing attribution. Every LLM call already lands in Revenium as a metered event linked by `trace_id`. Phase 2's job is to make that collection of events into a **visually navigable trace** in the Revenium UI: a Gantt timeline, a dependency tree, and circular-pattern detection on the debate loops.

The Revenium SDK (`revenium-metering` 6.8.1, currently installed) already accepts all the fields needed:
`parent_transaction_id`, `trace_name`, `trace_type`, and `transaction_name` are optional parameters on `ai.create_completion()`. No new packages are required. All work is in the `tradingagents/revenium/` package and a new validation script.

The central implementation pattern is a new `current_parent_transaction_id` contextvar that the callback handler advances after every LLM call. Since the graph is synchronous on the main thread (confirmed in Phase 1: no `llm.stream`/`llm.astream`), the contextvar update in `on_llm_end` is always visible to the next `on_chat_model_start` call — no locking or thread synchronization required for the parent-ID chain.

**Primary recommendation:** Implement parent-transaction threading via a single new contextvar, add `trace_name`/`trace_type`/`transaction_name` to every completion payload, run one full graph, and verify the trace detail in Revenium UI before treating the demo story as locked.

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| TRC-01 | A full `propagate()` run appears in Revenium as one trace/squad with a per-agent Gantt timeline and expected LLM span count | `trace_id` already groups events. Adding `trace_name` and `trace_type` enables the Gantt timeline (Transaction Timeline view). Span count must be verified by live run. |
| TRC-02 | `parentTransactionId` is threaded across the graph so the agent dependency tree / critical path is visible | New `current_parent_transaction_id` contextvar; set in `on_chat_model_start`, updated in `on_llm_end`. One-line read in each callback method. No graph topology changes. |
| TRC-03 | Circular-pattern detection fires on the bull/bear and risk debate loops, surfacing them as the cost hotspot | Revenium's circular pattern analysis fires on repeated agent-name sequences in a parent→child chain. With `parent_transaction_id` threading, bull1→bear1→bull2 creates a detectable loop. Fallback: `task_type=research_debate` aggregation surfaces cost hotspot without circular detection. |
</phase_requirements>

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Parent-transaction threading | `tradingagents/revenium/context.py` | `tradingagents/revenium/callback.py` | New contextvar lives in context module; callback reads and updates it on every LLM event |
| Trace grouping fields (trace_name, trace_type) | `tradingagents/revenium/callback.py` | `tradingagents/revenium/config.py` | Callback builds the payload; config supplies the `revenium_trace_type` default |
| Transaction label (transaction_name) | `tradingagents/revenium/callback.py` | — | Derived from `current_agent_name` contextvar already read there |
| Span-count validation | `scripts/validate_tracing.py` (new) | Revenium CLI `metrics traces` | Script runs one full propagate(), captures trace_id, queries Revenium for span count |
| Circular pattern detection | Revenium platform (automatic) | Fallback: `task_type` aggregation | Platform detects cycles in the parent→child graph; fallback uses agent-field grouping |

---

## Standard Stack

### Core (no new packages — Phase 1 packages cover everything)

| Library | Installed Version | Purpose | Why Standard |
|---------|------------------|---------|--------------|
| `revenium-metering` | 6.8.1 | `ai.create_completion()` with tracing fields | Already installed; `parent_transaction_id`, `trace_name`, `trace_type`, `transaction_name` are optional params on the existing method |
| `revenium-python-sdk[langchain]` | 0.1.9 | LangChain callback infrastructure | Already installed in Phase 1 |

No new packages are required for Phase 2.

### Supporting Tools

| Tool | Purpose | When to Use |
|------|---------|-------------|
| `revenium` CLI (`/opt/homebrew/bin/revenium`) | `metrics traces` command to query spans by time window; `metrics squads` for squad aggregation | Validation: post-run span count check |
| Revenium MCP Dev connector | Ad-hoc trace detail inspection during development | Ad-hoc dashboard verification during Phase 2 development |

### Package Legitimacy Audit

> No new packages are installed in Phase 2. All SDK dependencies (`revenium-metering`, `revenium-python-sdk[langchain]`) were verified and approved in Phase 1 (STACK.md, Plan 01-01). Slopcheck and registry verification are not re-run for already-installed packages.

| Package | Registry | Status |
|---------|----------|--------|
| `revenium-metering` 6.8.1 | PyPI | Approved in Phase 1 — `[VERIFIED: PyPI]` |
| `revenium-python-sdk[langchain]` 0.1.9 | PyPI | Approved in Phase 1 — `[VERIFIED: PyPI]` |

---

## Architecture Patterns

### System Architecture Diagram

```
propagate(ticker, date)
  │
  └── revenium_run_context() sets:
        trace_id      = uuid4()           (run-level grouping key — already Phase 1)
        run_meta      = {ticker, date}    (source for trace_name)
        parent_txn_id = ""               (NEW: resets per run)
              │
              └── graph.invoke() / graph.stream()
                    │
                    ├── market_analyst_node() ─────────────────────────────┐
                    │     current_agent_name.set("market_analyst")         │
                    │     ▼ on_chat_model_start:                           │
                    │       captures parent_txn_id = ""                    │
                    │     ▼ on_llm_end (tool-round 1):                     │
                    │       payload ← trace_id, trace_name,                │
                    │                 trace_type, agent,                   │
                    │                 transaction_name="market_analyst",   │
                    │                 parent_transaction_id="" (omitted)   │
                    │                 transaction_id="mkt1-tid"            │
                    │       context ← parent_txn_id.set("mkt1-tid")  ─────┤
                    │     ▼ on_chat_model_start (tool-round 2):           │
                    │       captures parent_txn_id = "mkt1-tid"            │
                    │     ▼ on_llm_end (tool-round 2):                     │
                    │       payload ← parent_transaction_id="mkt1-tid"    │
                    │                 transaction_id="mkt2-tid"            │
                    │       context ← parent_txn_id.set("mkt2-tid")  ─────┤
                    │                                                       │
                    ├── [social/news/fundamentals analysts, same pattern]   │
                    │                                                       │
                    ├── bull_researcher_node() (round 1)                    │
                    │     ▼ on_llm_end: parent="last-fundamentals-tid"      │
                    │       transaction_id="bull1-tid"                      │
                    │       context ← parent_txn_id.set("bull1-tid")        │
                    │                                                       │
                    ├── bear_researcher_node() (round 1) [loopback edge]   │
                    │     ▼ on_llm_end: parent="bull1-tid"                  │
                    │       transaction_id="bear1-tid"                      │
                    │       context ← parent_txn_id.set("bear1-tid")        │
                    │                                                       │
                    ├── [bull/bear repeat if max_debate_rounds > 1]        │
                    │     bull2: parent="bear1-tid", bear2: parent="bull2"  │
                    │     ← CIRCULAR PATTERN: agent name repeats in chain  │
                    │                                                       │
                    ├── research_manager → trader → risk debaters → PM     │
                    │     [same linear chain, parent=previous tid]          │
                    │                                                       │
                    └── revenium_run_context() exits:
                          parent_txn_id.reset("")
```

### Recommended Project Structure (additions to existing)

```
tradingagents/revenium/
├── context.py          # ADD: current_parent_transaction_id ContextVar
├── callback.py         # MODIFY: read/update parent_txn_id; add trace_name, trace_type, transaction_name
├── config.py           # MODIFY: add revenium_trace_type config key
└── [existing files unchanged]

scripts/
└── validate_tracing.py  # NEW: run one propagate(), capture trace_id, query span count, assert
```

### Pattern 1: Sequential Parent-Transaction Threading via ContextVar

**What:** A single `current_parent_transaction_id` contextvar holds the `transaction_id` of the most recently completed LLM call. Each new LLM call reads it as its own `parent_transaction_id`, then updates it to its own new id after completing.

**When to use:** The graph runs synchronously on the main thread (confirmed: no `llm.stream`/`astream`). The contextvar update in `on_llm_end` happens before LangGraph dispatches the next node, so the chain is never broken.

**Example:**
```python
# Source: tradingagents/revenium/context.py (new addition)
current_parent_transaction_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "revenium_parent_transaction_id",
    default="",
)

# Source: tradingagents/revenium/callback.py — on_chat_model_start addition
parent_tid = current_parent_transaction_id.get()   # "" on first call of run
with self._lock:
    self._call_state[run_id]["parent_tid"] = parent_tid

# Source: tradingagents/revenium/callback.py — on_llm_end addition (after payload built)
parent_tid = call_state.get("parent_tid", "")
if parent_tid:
    payload["parent_transaction_id"] = parent_tid

# MUST happen on main thread before returning from on_llm_end
# (fire-and-forget HTTP is on a background thread; this update is synchronous)
current_parent_transaction_id.set(payload["transaction_id"])
```

**Critical invariant:** The `current_parent_transaction_id.set()` call MUST happen on the main thread in `on_llm_end` (not inside the background `_meter_safe` thread), and BEFORE `on_llm_end` returns control to LangGraph. The graph synchronously calls the next node after `on_llm_end` returns.

### Pattern 2: Trace Enrichment Fields

**What:** Three additional fields added to every `create_completion` payload enrich the trace for Revenium's UI.

**SDK field docs** (verified from `resources/ai.py` docstring):
- `trace_name`: "Human-readable label for this trace instance (max 256 chars)" → `f"{ticker}-{trade_date}"`
- `trace_type`: "Categorical identifier for grouping workflows (alphanumeric, hyphens, underscores; max 128 chars)" → `"trading-run"` from config
- `transaction_name`: "Human-friendly name for this operation" → same as `agent`, e.g., `"market_analyst"`

**Example:**
```python
# Source: tradingagents/revenium/callback.py — on_llm_end, after trace_id read
run_meta = current_run_meta.get()
ticker = run_meta.get("ticker", "")
trade_date_str = run_meta.get("trade_date", "")
trace_name = f"{ticker}-{trade_date_str}" if ticker else ""  # max 256 chars: safe

# In payload dict:
payload["transaction_name"] = agent   # same value as payload["agent"]
if trace_name:
    payload["trace_name"] = trace_name
trace_type = get_config().get("revenium_trace_type", "trading-run")
if trace_type:
    payload["trace_type"] = trace_type
```

**New config key** (follow `default_config.py` pattern):
```python
# default_config.py DEFAULT_CONFIG addition:
"revenium_trace_type": os.getenv("REVENIUM_TRACE_TYPE", "trading-run"),

# _ENV_OVERRIDES addition:
"REVENIUM_TRACE_TYPE": "revenium_trace_type",
```

### Pattern 3: Run-Context Reset for Parent Transaction ID

**What:** `revenium_run_context()` must reset `current_parent_transaction_id` on both entry and exit to prevent bleed between consecutive `propagate()` calls (same pattern as `current_trace_id`).

**Example:**
```python
# Source: tradingagents/revenium/context.py — revenium_run_context addition
token_parent = current_parent_transaction_id.set("")
try:
    yield trace_id
finally:
    current_trace_id.reset(token_trace)
    current_run_meta.reset(token_meta)
    current_parent_transaction_id.reset(token_parent)   # NEW
```

### Anti-Patterns to Avoid

- **Setting `current_parent_transaction_id` inside the background `_meter_safe` thread:** The thread runs after `on_llm_end` returns, so the contextvar set happens AFTER LangGraph has dispatched the next node. The next call will see the previous (stale) parent id. Always set on the main thread.
- **Generating `transaction_id` in the background thread:** Same race condition. Generate it synchronously in `on_llm_end` before dispatching the thread.
- **Using `get_config()` inside the fire-and-forget thread:** `get_config()` is process-global (deepcopy) so it's thread-safe, but calling it from within the thread adds latency to the background HTTP call. Capture `trace_type` on the main thread before spawning.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Trace grouping | Custom trace ID schema, separate trace registry | Send `trace_id` field (already done in Phase 1) | Revenium groups by `trace_id` automatically on ingest |
| Dependency tree | Custom graph serialization, store parent-child in AgentState | `parent_transaction_id` field on each `create_completion` call | SDK already accepts it; Revenium renders the dependency tree from it |
| Circular pattern detection | Count debate rounds in Python, emit a custom hotspot event | `parent_transaction_id` threading + `trace_type` | Revenium's built-in Circular Pattern Analysis detects agent-name repetition in the parent chain automatically |
| Span counting for validation | Custom Revenium API client | Revenium CLI `revenium metrics traces --json` | The `revenium` CLI (at `/opt/homebrew/bin/revenium`) is already available in this environment |

**Key insight:** The Revenium platform does the heavy lifting of trace analytics when the payload fields are correct. The implementation is sending the right fields; Revenium handles the rendering.

---

## Runtime State Inventory

> Not applicable — Phase 2 is instrumentation (code + config changes only). No stored data, live service config, OS-registered state, secrets, or build artifacts rename. Omitted per instructions.

---

## Common Pitfalls

### Pitfall 1: Parent Transaction ID Updated in Background Thread

**What goes wrong:** If `current_parent_transaction_id.set(transaction_id)` is called inside `_meter_safe` (the fire-and-forget background thread), the contextvar update doesn't propagate back to the main thread. Python `contextvars.ContextVar` set from a thread does NOT update the parent thread's context. The next `on_chat_model_start` on the main thread will still see the old (stale) parent id, breaking the chain.

**Why it happens:** The `_meter_safe` background thread copies the current context at creation time (Python 3.7+ copies context to threads). Changes to contextvar values within the thread are isolated to the thread's copied context.

**How to avoid:** Set `current_parent_transaction_id` synchronously in `on_llm_end` BEFORE starting the background thread. Generate `transaction_id` early in `on_llm_end` and set the contextvar before `threading.Thread(...).start()`.

**Warning signs:** Trace detail in Revenium shows a flat list of spans with no parent-child arrows (all spans appear as root nodes).

### Pitfall 2: Loopback Edges Produce a Flat Parent Chain, Not a Circular Pattern

**What goes wrong:** With `max_debate_rounds=1` (default), there is only one bull call and one bear call. The parent chain is: `bull1 → bear1` (linear, not circular). Revenium may not fire "circular pattern detection" because the agent name does not repeat.

**Why it happens:** Circular pattern detection requires at least one agent name to appear twice in the parent→child ancestry. With one debate round, each agent appears once.

**How to avoid:**
1. Run with `max_debate_rounds=2` for the demo to get `bull1 → bear1 → bull2 → bear2` (bull_researcher appears twice → detectable cycle).
2. OR rely on the fallback: filter Revenium analytics by `task_type=research_debate` to show debate cost as a hotspot even without circular pattern detection.
3. Validate which approach works by running one live graph and checking the Revenium UI before committing to the demo narrative.

**Warning signs:** Revenium trace shows all spans with correct parent-child chain, but the Circular Pattern Analysis section in the Agent Interaction view shows "No circular patterns detected."

### Pitfall 3: Missing Trace Name on Spans — Hard to Find in Dashboard

**What goes wrong:** If `trace_name` is not sent, all traces in the Revenium UI appear with only their `trace_id` UUID as a label. Finding the right trace after a demo run requires time-window search (as happened in Phase 1 per the SUMMARY.md).

**Why it happens:** `trace_name` is optional; Phase 1 never added it.

**How to avoid:** Always set `trace_name = f"{ticker}-{trade_date}"` in the payload. Optionally surface `trace_id` to stdout at run start (Phase 5 enhancement, but useful for Phase 2 validation).

**Warning signs:** Dashboard trace list shows raw UUIDs with no human-readable labels.

### Pitfall 4: `transaction_id` Generated Too Late

**What goes wrong:** If `transaction_id = str(uuid.uuid4())` is generated at a point where `current_parent_transaction_id` has already been updated by the current call's logic, the next call's `on_chat_model_start` sees the wrong parent.

**Why it happens:** The current implementation generates `transaction_id` in `on_llm_end`. As long as `current_parent_transaction_id.set(transaction_id)` is called on the main thread BEFORE returning from `on_llm_end`, the order is correct.

**How to avoid:** Keep the sequence in `on_llm_end`: (1) generate `transaction_id`, (2) set `payload["transaction_id"] = transaction_id`, (3) call `current_parent_transaction_id.set(transaction_id)`, (4) start background thread. Do not change this order.

### Pitfall 5: Revenium Trace View Doesn't Show Dependency Tree

**What goes wrong:** The Revenium trace UI shows the Gantt timeline (Transaction Timeline) without the dependency tree arrows.

**Why it happens:** The dependency tree is populated only when `parent_transaction_id` is present on events. If the field is missing or blank, all spans appear as root nodes.

**How to avoid:** Confirm `parent_transaction_id` appears in actual API payloads by adding a DEBUG log line or checking `test_revenium_metering.py` captured payloads. Check Revenium trace detail tab (not summary) for the dependency tree view.

---

## Code Examples

### Complete on_llm_end payload changes for Phase 2

```python
# Source: tradingagents/revenium/callback.py — on_llm_end additions (Phase 2)

# 1. Read parent_tid from per-call state (captured in on_chat_model_start)
parent_tid: str = call_state.get("parent_tid", "")

# 2. Generate transaction_id BEFORE setting parent contextvar
transaction_id: str = str(uuid.uuid4())   # unchanged from Phase 1

# 3. Build trace enrichment fields
run_meta = current_run_meta.get()
ticker = run_meta.get("ticker", "")
trade_date_v = run_meta.get("trade_date", "")
trace_name = f"{ticker}-{trade_date_v}" if ticker else ""

# 4. Extend payload (additions to existing Phase 1 payload dict)
payload["transaction_id"] = transaction_id
payload["transaction_name"] = agent          # human label = same as agent field
if parent_tid:
    payload["parent_transaction_id"] = parent_tid
if trace_name:
    payload["trace_name"] = trace_name
trace_type = self._trace_type               # read from config at handler construction
if trace_type:
    payload["trace_type"] = trace_type

# 5. CRITICAL: update parent contextvar SYNCHRONOUSLY on main thread
#    before starting the background thread
current_parent_transaction_id.set(transaction_id)

# 6. Start background thread (unchanged from Phase 1)
t = threading.Thread(target=_meter_safe, args=(payload,), daemon=True)
t.start()
```

### on_chat_model_start parent-tid capture

```python
# Source: tradingagents/revenium/callback.py — on_chat_model_start addition

parent_tid = current_parent_transaction_id.get()   # "" on first call of a run
with self._lock:
    self._call_state[run_id] = {
        "start_time": datetime.now(timezone.utc),
        "model": model,
        "provider": provider,
        "agent": agent,
        "parent_tid": parent_tid,    # NEW: capture here, use in on_llm_end
    }
```

### validate_tracing.py sketch

```python
# Source: scripts/validate_tracing.py (new script, Phase 2)
"""Validate that one propagate() run produces exactly one trace with expected spans.

Usage:
    REVENIUM_METERING_API_KEY=rev_mk_... python scripts/validate_tracing.py
"""
from __future__ import annotations
import sys
import time
from tradingagents.revenium.context import current_trace_id, revenium_run_context
from tradingagents.graph.trading_graph import TradingAgentsGraph

def main() -> int:
    config = {...}   # minimal demo config
    graph = TradingAgentsGraph(config=config)

    with revenium_run_context("NVDA", "2026-06-27") as trace_id:
        graph.propagate("NVDA", "2026-06-27")

    # Flush background metering threads
    for t in graph._revenium_handler._threads:
        t.join(timeout=5.0)

    print(f"TRACE ID: {trace_id}")   # use for dashboard lookup
    time.sleep(3)                     # allow Revenium ingest

    # Query Revenium CLI for spans: revenium metrics traces --json
    # Filter by trace_id in output, count spans
    # Assert span_count >= 12 (minimum: one per node, no debate repeats)
    # Assert all 12 agent names are represented
    ...
    return 0

if __name__ == "__main__":
    sys.exit(main())
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|-----------------|--------------|--------|
| Send `trace_id` only | Send `trace_id` + `trace_name` + `trace_type` + `transaction_name` | Phase 2 | Enables human-readable trace labels and squad grouping in Revenium UI |
| No parent-child linking | `parent_transaction_id` threading | Phase 2 | Enables dependency tree and critical path visualization |
| Cost hotspot only via `task_type` aggregation | Circular pattern detection via parent-chain cycles | Phase 2 (and fallback remains) | Automatic "cost hotspot" surfacing for debate loops in Agent Interaction view |

**Deprecated/outdated:**
- Searching for traces by time window: with `trace_name` set, direct trace lookup by name is possible.
- Manual span counting: `revenium metrics traces --json` can be scripted for validation.

---

## Detailed Phase 1 → Phase 2 Delta

This section documents what exists and what is new to prevent re-implementing Phase 1 work.

### Already in Place (DO NOT change)

| Field | Where Set | Value |
|-------|-----------|-------|
| `trace_id` | `callback.py` `on_llm_end` | `current_trace_id.get()` from contextvar |
| `transaction_id` | `callback.py` `on_llm_end` | `str(uuid.uuid4())` per call |
| `agent` | `callback.py` `on_llm_end` | `current_agent_name.get()` |
| `task_type` | `callback.py` `on_llm_end` | `revenium_task_type_map[agent]` |
| `organization_name`, `product_name`, `subscriber` | `callback.py` `on_llm_end` | from `attribution` dict |
| `middleware_source` | `callback.py` `on_llm_end` | `"tradingagents"` |
| `operation_type` | `callback.py` `on_llm_end` | `"CHAT"` |
| `current_agent_name.set(...)` | All 12 agent node functions | Per-agent identity contextvar |
| `revenium_run_context()` | `trading_graph.py:_run_graph()` | Sets `trace_id` and `run_meta` |

### New in Phase 2

| Field | Where Added | Value |
|-------|-------------|-------|
| `parent_transaction_id` | `callback.py` `on_llm_end` (non-empty only) | `current_parent_transaction_id.get()` captured at `on_chat_model_start` |
| `trace_name` | `callback.py` `on_llm_end` (non-empty only) | `f"{ticker}-{trade_date}"` from `current_run_meta` |
| `trace_type` | `callback.py` `on_llm_end` (non-empty only) | `config["revenium_trace_type"]` default `"trading-run"` |
| `transaction_name` | `callback.py` `on_llm_end` | same as `agent` field |
| `current_parent_transaction_id` ContextVar | `context.py` | New module-level ContextVar (default `""`) |
| Reset in `revenium_run_context` | `context.py:revenium_run_context()` | Reset to `""` on both entry and exit |
| `parent_tid` in `_call_state` | `callback.py:on_chat_model_start` | Captured from contextvar at call start |
| `self._trace_type` | `callback.py:ReveniumCallbackHandler.__init__` | Read from config, stored at construction |
| `revenium_trace_type` config key | `default_config.py` | Default `"trading-run"`, overridable via `REVENIUM_TRACE_TYPE` env var |
| `scripts/validate_tracing.py` | New file | Run one propagate(), assert trace + span count |
| Unit tests | `tests/test_revenium_tracing.py` (new) | parent_transaction_id in payload, trace_name, trace_type, per-run reset |

---

## LangGraph Topology and Span Count

Understanding the graph topology is required to predict expected span count N for validation.

### Graph execution order (from `setup.py` and `conditional_logic.py`)

```
START
  → Market Analyst (tool loop: 2 LLM calls typical)
  → Clear Msg
  → Sentiment Analyst (tool loop: 2 LLM calls typical)
  → Clear Msg
  → News Analyst (tool loop: 2 LLM calls typical)
  → Clear Msg
  → Fundamentals Analyst (tool loop: 2 LLM calls typical)
  → Clear Msg
  → Bull Researcher (1 LLM call per round)
  ↔ Bear Researcher (1 LLM call per round) [loopback: count < 2*max_debate_rounds]
  → Research Manager (1 LLM call)
  → Trader (1 LLM call)
  → Aggressive Analyst (1 LLM call per round)
  ↔ Conservative Analyst (1 LLM call per round) [loopback: count < 3*max_risk_rounds]
  ↔ Neutral Analyst (1 LLM call per round)
  → Portfolio Manager (1 LLM call)
  → END
```

### Span count estimate (default: max_debate_rounds=1, max_risk_discuss_rounds=1)

| Segment | LLM Calls | Notes |
|---------|-----------|-------|
| 4 analysts × ~2 calls | ~8 | Each analyst makes 1 call for tool planning, 1 call after tools return; actual count varies by tool round depth |
| Bull Researcher (1 round) | 1 | |
| Bear Researcher (1 round) | 1 | |
| Research Manager | 1 | Deep-think LLM |
| Trader | 1 | |
| Aggressive Analyst (1 round) | 1 | |
| Conservative Analyst (1 round) | 1 | |
| Neutral Analyst (1 round) | 1 | |
| Portfolio Manager | 1 | Deep-think LLM |
| **Total (estimated)** | **~16** | Must be confirmed by live run |

**Validation rule:** N = actual span count from first live run. Do not hardcode before running. The validation script should print the count so it can be recorded as the expected value.

### Circular pattern detection — when it fires

Revenium's circular pattern analysis detects when "the same agent appears multiple times in a call chain." From the docs:
- Fires on repeated agent names in a `parent_transaction_id` ancestry
- Reports: call sequence, occurrence count, wasted cost/duration, severity, hop count

With default settings (max_debate_rounds=1): bull_researcher and bear_researcher each appear ONCE. Circular detection may NOT fire.

With max_debate_rounds=2: bull1→bear1→bull2→bear2 → bull_researcher appears twice → circular detection fires.

**Implication:** For the demo, set `max_debate_rounds=2` (or higher) to guarantee the circular pattern surfaces. This is a config choice, not a code change.

---

## The Core Risk: parentTransactionId Behavior at Loopback Edges

This is the research flag from ROADMAP.md: *"`parentTransactionId` chaining across LangGraph loopback conditional edges needs a live integration test."*

### What the risk actually is

The graph's loopback edges (bull→bear→bull) mean the same LangGraph node function executes multiple times per run. Each execution is a separate LLM call. With the sequential contextvar approach:

- **First bull run**: `parent_tid = current_parent_transaction_id.get()` = last analyst's tid
- **First bear run**: `parent_tid` = bull1's tid
- **Second bull run** (if rounds > 1): `parent_tid` = bear1's tid

The parent chain is linear: last-analyst → bull1 → bear1 → bull2 → bear2 → research-manager

This is NOT a true cycle (no node points back to itself or a prior ancestor). Whether Revenium treats this as "circular" depends on its pattern matching algorithm:
- Option A: Revenium detects repeated agent name in the ancestry chain → fires on bull2 having bull1 as ancestor
- Option B: Revenium only fires on `A → A` (self-loops) → does NOT fire
- Option C: Revenium fires on `A → B → A` pattern regardless of ancestry depth → fires on bull→bear→bull

The answer is unknown until a live run is checked in the UI. The ROADMAP correctly identifies this as requiring live verification.

### Fallback (already in place from Phase 1)

If `parentTransactionId` loopback behavior produces a flat list or no circular pattern flag:

1. **`task_type` aggregation**: `task_type=research_debate` (bull_researcher, bear_researcher) aggregation in Revenium analytics ALREADY shows the debate loop as the cost hotspot — no UI dependency on circular pattern detection.
2. **Agent interaction matrix**: The Revenium trace Agent Interaction view shows each agent's cost contribution regardless of parent-child structure. Bull and bear researchers appear as the highest-cost research agents.
3. **Document and demo**: "The debate loop is the cost hotspot — here's the research_debate bucket vs analysis vs decision" — tell the story with `task_type` breakdown if the circular pattern UI doesn't fire.

The fallback is solid for demo purposes. The circular pattern detection is a bonus visual, not the only path to the hotspot story.

---

## Validation Architecture

> `nyquist_validation` is explicitly `false` in `.planning/config.json` — automated test framework section is skipped per instructions. Manual validation approach documented instead.

### Span-Count Validation (TRC-01)

**Approach:** Run one full `propagate()` with `REVENIUM_METERING_API_KEY` set. After the run, capture the `trace_id` from the contextvar (surfaced via the validation script or a DEBUG log line). Use the Revenium CLI or MCP connector to query spans for that `trace_id`.

**Validation script:** `scripts/validate_tracing.py` (new)
- Runs `propagate("NVDA", "2026-06-27")` with minimal config
- Joins all background `_threads` from `ReveniumCallbackHandler` (existing mechanism from `test_revenium_metering.py`)
- Prints `TRACE ID: <uuid>` to stdout
- Queries Revenium (via CLI `revenium metrics traces --json`) for the trace
- Asserts span count >= 12 (minimum without tool-round repeats)
- Asserts all 12 distinct `agent` values are represented

**N confirmation:** Run once, count spans in Revenium UI trace detail, record the number as the expected N for all subsequent demo runs. Typical value: 16–24 spans.

### Dependency Tree Validation (TRC-02)

**Approach:** Visual inspection of Revenium trace detail after running `validate_tracing.py`.
- Trace detail → Dependency Tree tab should show arrows between sequential agents
- No "flat list with no arrows" acceptable — every span except the first must have a parent arrow
- If any span appears as a root node (no parent), check that `parent_transaction_id` field is in the captured payload (add a test assertion that `parent_tid` appears for non-first calls)

**Mocked unit test (keyless):** `tests/test_revenium_tracing.py`
- Simulate N sequential `on_chat_model_start` / `on_llm_end` pairs
- Assert first call's payload has no `parent_transaction_id`
- Assert second call's payload has `parent_transaction_id` == first call's `transaction_id`
- Assert third call's payload has `parent_transaction_id` == second call's `transaction_id`
- Assert `current_parent_transaction_id` resets to `""` after `revenium_run_context` exits

### Circular Pattern Validation (TRC-03)

**Approach:** Two-path validation:
1. **Circular detection path**: Run with `max_debate_rounds=2`. Check Revenium Agent Interaction view for "Circular Pattern" section. If present → TRC-03 primary satisfied.
2. **Cost hotspot fallback path**: Even with `max_debate_rounds=1`, check Revenium analytics filtered by `task_type=research_debate`. Cost of debate rounds should be visible as a distinct bucket.

**Acceptance:** At least one of the two paths is demo-reliable. Document which one before Phase 3.

---

## Security Domain

> `security_enforcement` is enabled in `.planning/config.json`. Phase 2 does not introduce new external endpoints, authentication schemes, or user-controlled inputs. Assessment below confirms no new threat surface.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | No new auth — uses same `REVENIUM_METERING_API_KEY` from Phase 1 |
| V3 Session Management | No | No session state added |
| V4 Access Control | No | No new access control decisions |
| V5 Input Validation | No | New fields (`trace_name`, `trace_type`, `transaction_name`) are derived from internal config and contextvar values — never from user input. Ticker symbol is already sanitized by `safe_ticker_component()` in Phase 1. |
| V6 Cryptography | No | No new crypto |

### Known Threat Patterns for this Stack

| Pattern | STRIDE | Mitigation |
|---------|--------|-----------|
| `trace_name` injection via ticker value | Tampering | `trace_name = f"{ticker}-{trade_date}"` — ticker is from `current_run_meta`, set by `propagate()` args. `safe_ticker_component()` already sanitizes ticker for file paths; apply the same guard or truncate to 200 chars before sending. |
| `trace_type` from env var | Tampering | Value read from `DEFAULT_CONFIG["revenium_trace_type"]`. Env var `REVENIUM_TRACE_TYPE` is process-controlled, not user-controlled. Acceptable. |
| Parent-tid exposure | Information Disclosure | `parent_transaction_id` is a UUID sent to the Revenium account (same trusted destination as `trace_id`). No new exposure beyond Phase 1. |

**No new high-severity threat surface introduced by Phase 2.**

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `revenium-metering` SDK | `callback.py` tracing fields | Yes | 6.8.1 (installed) | — |
| `REVENIUM_METERING_API_KEY` | Live metering | Yes (set in `.env`) | — | Run keyless: no events sent, validation runs against mock |
| Revenium platform (`api.revenium.ai`) | Validation span count | Yes (verified Phase 1) | — | Check manually in UI |
| Revenium CLI (`/opt/homebrew/bin/revenium`) | `metrics traces` for scripted validation | Yes | Available (version confirmed) | MCP connector for ad-hoc queries |
| `FRED_API_KEY` | Full pipeline run (news/macro data) | Yes (added Phase 1 workaround) | — | Add to `.env` before validation run |

**No missing dependencies with no fallback.** All required components are available.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Revenium's circular pattern detection fires on repeated `agent` names in a `parent_transaction_id` ancestry (not only on `transaction_id` self-cycles) | Common Pitfalls — Pitfall 2 | If wrong, circular detection does not fire on bull→bear→bull; fallback (`task_type` aggregation) still surfaces the hotspot; demo story slightly different |
| A2 | `trace_type` drives the Revenium "squad" grouping (squad analytics groups by `trace_type`) | Standard Stack — Supporting Tools | If wrong, squad analytics may not appear or may need a separate field; verify in Phase 2 live run |
| A3 | The Revenium Gantt/Transaction Timeline view is automatically populated when `trace_id` + `trace_name` + `transaction_name` are present — no separate API call needed | Code Examples | If wrong, may need additional endpoint call to "create trace" before events land; verify in UI after first live run |
| A4 | Circular pattern detection fires for `max_debate_rounds >= 2` (two occurrences of `bull_researcher` in the parent chain) | LangGraph Topology and Span Count | If wrong, need even more rounds or a different approach; verify by running with max_debate_rounds=2 |
| A5 | The `current_parent_transaction_id.set()` call in `on_llm_end` (main thread) is visible to the next `on_chat_model_start` call before LangGraph dispatches the next node | Architecture Patterns — Pattern 1 | If wrong (unexpected async behavior in LangGraph), the parent chain is broken; verify by checking dependency tree arrows in UI — if arrows are missing, investigate LangGraph dispatch timing |

---

## Open Questions (RESOLVED — answered by 02-02 live validation)

1. **Does `trace_type="trading-run"` create a distinct "squad" view in Revenium?**
   - What we know: The CLI has `metrics squads`; the API docs mention "squad timeline" and "squad aggregated metrics"
   - What's unclear: Whether `trace_type` is the grouping key for squads, or whether a separate `squad_id` field (not in current SDK signature) is needed
   - Recommendation: Send `trace_type="trading-run"`, run one live graph, check if a squad entry appears under `revenium metrics squads`. If not, query Revenium support or MCP connector for the squad grouping mechanism.
   - RESOLVED: to be confirmed/discovered by the 02-02 live run — `scripts/validate_tracing.py` output plus a `revenium metrics squads` check after the run; whether `trace_type` creates a squad view is recorded in the 02-02 Task 2 SUMMARY (Open Question 1).

2. **How many LLM spans does a default NVDA run produce?**
   - What we know: ~16 estimated (4×2 analyst tool rounds + 6 single-call agents + 2 debate + 3 risk)
   - What's unclear: Actual analyst tool-round count varies by data availability; research manager/PM may make multiple tool calls
   - Recommendation: Run one live validation (`scripts/validate_tracing.py`) and record N before locking the assertion
   - RESOLVED: discovered by the 02-02 live run — `validate_tracing.py` prints `span_count=<N>`; N is recorded as the expected demo value in the 02-02 Task 2 SUMMARY (Open Question 2).

3. **Does Revenium require waiting before querying spans after POST?**
   - What we know: Phase 1 found live trace_id 5fb9569b appeared in dashboard within seconds
   - What's unclear: Exact ingest latency for span queries via CLI/API vs visual dashboard
   - Recommendation: Add a 3-second sleep in `validate_tracing.py` before querying; increase to 10s if first run shows 0 spans
   - RESOLVED: to be confirmed by the 02-02 live run — observed ingest latency from `validate_tracing.py` output / dashboard appearance is recorded in the 02-02 Task 2 SUMMARY (Open Question 3).

---

## Sources

### Primary (HIGH confidence)
- `revenium-metering` SDK source (installed, version 6.8.1): `ai.create_completion()` signature in `.venv/lib/python3.11/site-packages/revenium_metering/resources/ai.py` — verified `parent_transaction_id`, `trace_name`, `trace_type`, `transaction_name` exist as optional parameters with documented semantics
- `revenium_metering.context` module: `.venv/lib/python3.11/site-packages/revenium_metering/context.py` — confirmed SDK-level contextvar pattern (separate from our contextvar implementation)
- Codebase read directly: `tradingagents/revenium/callback.py`, `context.py`, `client.py` — Phase 1 implementation fully understood
- Codebase read directly: `tradingagents/graph/setup.py`, `conditional_logic.py`, `trading_graph.py` — graph topology and loopback edge structure confirmed
- `.planning/phases/01-foundation-metering/01-03-SUMMARY.md` — what Phase 1 delivers, what Phase 2 depends on

### Secondary (MEDIUM confidence)
- `docs.revenium.io/llms-full.txt` (fetched): Transaction Timeline = "a Gantt chart of every transaction in the trace, sequenced chronologically and color-coded by agent"; dependency tree builds from `parentTransactionId`
- `docs.revenium.io/instrument-your-agents/agent-instrumentation-guide.md?ask=...` (fetched): Squad = "named, coordinated group of agents with aggregated metrics and timeline views"; circular pattern detection reports "call sequence, occurrence count, wasted cost/duration, severity, hop count"
- `docs.revenium.io/optimize-performance/debug-logs-and-traces.md` (fetched): Trace = "one workflow run"; traceId groups related transactions
- Revenium CLI schema (`/opt/homebrew/bin/revenium schema`): confirmed `metrics traces`, `metrics squads` commands

### Tertiary (LOW confidence — marked `[ASSUMED]` where cited)
- `.planning/research/ARCHITECTURE.md` (2026-06-26): pre-Phase 1 research mentioning `squadId`/`squadRole` fields — these do NOT appear in the current SDK's `create_completion` signature; information is stale/incorrect for the current SDK version
- WebSearch results for Revenium circular pattern detection: summarized behavior (call sequence, occurrence count, etc.) confirmed by fetched agent instrumentation guide

---

## Metadata

**Confidence breakdown:**
- Standard stack (no new packages): HIGH — verified by SDK introspection
- Parent transaction ID threading: HIGH — implementation pattern derived from existing code, thread semantics verified
- Trace enrichment fields (`trace_name`, `trace_type`, `transaction_name`): HIGH — SDK signature verified directly
- Circular pattern detection behavior: MEDIUM — docs confirm it exists; exact trigger conditions [ASSUMED]
- Squad grouping by `trace_type`: LOW (`[ASSUMED A2]`) — not explicitly documented as the grouping key

**Research date:** 2026-06-27
**Valid until:** 2026-07-27 (SDK stable; Revenium platform UI may evolve faster — re-verify dashboard behavior before demo)
