# Phase 2: Trace & Squad Analytics — Pattern Map

**Mapped:** 2026-06-27
**Files analyzed:** 5 (3 modified, 2 new)
**Analogs found:** 5 / 5

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `tradingagents/revenium/context.py` | utility | request-response | same file — `current_trace_id` / `current_run_meta` contextvar block (lines 47-107) | exact |
| `tradingagents/revenium/callback.py` | middleware | event-driven | same file — `on_chat_model_start` (lines 172-207) + `on_llm_end` (lines 209-342) | exact |
| `tradingagents/default_config.py` | config | n/a | same file — `_ENV_OVERRIDES` Revenium block (lines 23-28) + config keys (lines 154-176) | exact |
| `scripts/validate_tracing.py` | utility | request-response | `scripts/validate_metering.py` (all 443 lines) | exact |
| `tests/test_revenium_tracing.py` | test | event-driven | `tests/test_revenium_metering.py` (all 383 lines) | exact |

---

## Pattern Assignments

### `tradingagents/revenium/context.py` (utility, request-response — MODIFY)

**Analog:** Same file, existing contextvar block + `revenium_run_context`.

**ContextVar declaration pattern** (lines 47-63):
```python
current_trace_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "revenium_trace_id",
    default="",
)
"""One UUID4 string per propagate() call, linking all agent LLM calls in a run."""

current_agent_name: contextvars.ContextVar[str] = contextvars.ContextVar(
    "revenium_agent_name",
    default="unknown",
)
```
Copy this pattern verbatim for `current_parent_transaction_id`, using `default=""` (empty string = "no parent yet") and the internal name `"revenium_parent_transaction_id"`.

**Token-based reset pattern** in `revenium_run_context` (lines 96-107):
```python
trace_id = str(uuid.uuid4())
token_trace = current_trace_id.set(trace_id)
token_meta = current_run_meta.set(
    {"ticker": ticker, "trade_date": str(trade_date), **meta}
)
logger.debug("revenium_run_context enter: ticker=%r trace_id=%r", ticker, trace_id)
try:
    yield trace_id
finally:
    current_trace_id.reset(token_trace)
    current_run_meta.reset(token_meta)
    logger.debug("revenium_run_context exit: trace_id=%r", trace_id)
```
Add `token_parent = current_parent_transaction_id.set("")` after `token_meta = ...` and add `current_parent_transaction_id.reset(token_parent)` inside the `finally` block alongside the other two resets. The set/reset is symmetric — always reset to default `""` on entry AND via token on exit.

**Docstring pattern** (lines 1-31): The module docstring enumerates each ContextVar by name, default, and semantics. Add `current_parent_transaction_id` to that enumeration list in the same bullet style.

---

### `tradingagents/revenium/callback.py` (middleware, event-driven — MODIFY)

**Analog:** Same file.

**Import addition pattern** (lines 53-54):
```python
from tradingagents.revenium.context import current_agent_name, current_trace_id
```
Extend this import to also import `current_parent_transaction_id` and `current_run_meta` from the same module:
```python
from tradingagents.revenium.context import (
    current_agent_name,
    current_parent_transaction_id,
    current_run_meta,
    current_trace_id,
)
```

**`__init__` instance-variable pattern** (lines 102-133): All handler state is stored as `self._<name>` attributes. Add `self._trace_type` here, read from config at construction time — captured once so the background thread never needs to call `get_config()`:
```python
# In __init__ signature and body, parallel to existing self._attribution / self._task_type_map
self._trace_type: str = task_type_map  # <-- NEW: pass in from from_config
```
The `from_config` factory (lines 139-157) reads config and passes values to `__init__`. Read `config.get("revenium_trace_type", "trading-run")` there and store as `self._trace_type`. Follow the same pattern as `task_type_map` — passed via constructor, stored in `__init__`.

**`on_chat_model_start` capture pattern** (lines 196-202):
```python
with self._lock:
    self._call_state[run_id] = {
        "start_time": datetime.now(timezone.utc),
        "model": model,
        "provider": provider,
        "agent": agent,
    }
```
Add `"parent_tid": current_parent_transaction_id.get()` as a new key in the same dict. Reading the contextvar here (on the main thread, before `on_llm_end`) is the critical invariant — it captures the parent before the current call's transaction_id is generated. The `except Exception` guard at line 203 already wraps this block; no additional protection needed.

**`on_llm_end` per-call state retrieval pattern** (lines 240-246):
```python
with self._lock:
    call_state = self._call_state.pop(run_id, {})

start_time: datetime = call_state.get("start_time", end_time)
model: str = call_state.get("model", "unknown")
provider: str = call_state.get("provider", "unknown")
agent: str = call_state.get("agent", current_agent_name.get())
```
Add `parent_tid: str = call_state.get("parent_tid", "")` after this block to retrieve the captured parent id. Follow the exact same `.get(key, default)` pattern with a string default.

**`on_llm_end` context field read pattern** (lines 258-259):
```python
trace_id: str = current_trace_id.get()
task_type: str = self._task_type_map.get(agent, "analysis")
```
Add `run_meta: dict = current_run_meta.get()` immediately after and derive `trace_name` from it:
```python
run_meta: dict = current_run_meta.get()
ticker: str = run_meta.get("ticker", "")
trade_date_str: str = run_meta.get("trade_date", "")
trace_name: str = f"{ticker}-{trade_date_str}" if ticker else ""
```

**`on_llm_end` payload construction pattern** (lines 270-301):
```python
payload: dict[str, Any] = {
    # Required fields
    "completion_start_time": request_time,
    ...
    "transaction_id": str(uuid.uuid4()),
    # Attribution (MTR-02)
    ...
    # Identity (MTR-01)
    "agent": agent,
    "task_type": task_type,
    # Tracing
    "operation_type": "CHAT",
    "middleware_source": "tradingagents",
}
# Only include trace_id when it is non-empty (avoid sending blank UUIDs)
if trace_id:
    payload["trace_id"] = trace_id
```
The `transaction_id` is already generated with `str(uuid.uuid4())` inside the payload dict literal (line 284). Phase 2 requires extracting it to a local variable BEFORE the dict literal so it can be used for `current_parent_transaction_id.set()` synchronously on the main thread. Refactor to:
```python
transaction_id: str = str(uuid.uuid4())
payload: dict[str, Any] = {
    ...
    "transaction_id": transaction_id,
    "transaction_name": agent,   # NEW: human label same as agent field
    ...
}
if trace_id:
    payload["trace_id"] = trace_id
if parent_tid:
    payload["parent_transaction_id"] = parent_tid   # NEW: omit when empty (first call)
if trace_name:
    payload["trace_name"] = trace_name               # NEW: omit when empty
if self._trace_type:
    payload["trace_type"] = self._trace_type         # NEW: omit when empty
```
Then, **before** starting the background thread (currently line 327), set the contextvar synchronously on the main thread:
```python
current_parent_transaction_id.set(transaction_id)   # NEW: main thread, before t.start()
```
The background thread start pattern (lines 327-335) is unchanged.

**Fail-open guard pattern** (lines 337-342): The entire `on_llm_end` body is already wrapped in `except Exception` with `# noqa: BLE001 — fail open, never block the run`. No additional guard is needed for the new fields. The `current_parent_transaction_id.set()` call must be placed inside this guard (i.e., inside the outer `try`) so a contextvar failure is also swallowed.

---

### `tradingagents/default_config.py` (config — MODIFY)

**Analog:** Same file.

**`_ENV_OVERRIDES` entry pattern** (lines 23-28):
```python
# Revenium metering — env vars map to revenium_* config keys
"REVENIUM_METERING_API_KEY":    "revenium_api_key",
"REVENIUM_METERING_BASE_URL":   "revenium_api_url",
"REVENIUM_ORGANIZATION_NAME":   "revenium_organization_name",
"REVENIUM_PRODUCT_NAME":        "revenium_product_name",
"REVENIUM_SUBSCRIBER_ID":       "revenium_subscriber_id",
```
Add one new entry in this block (after `"REVENIUM_SUBSCRIBER_ID"`):
```python
"REVENIUM_TRACE_TYPE":          "revenium_trace_type",
```

**Config key pattern** (lines 154-160):
```python
"revenium_api_key":            os.getenv("REVENIUM_METERING_API_KEY", ""),
"revenium_api_url":            os.getenv("REVENIUM_METERING_BASE_URL", "https://api.revenium.ai"),
# Attribution hierarchy — locked demo values (D-01..D-03).
"revenium_organization_name":  "Revenium-Research-Desk",
"revenium_product_name":       "trading-signal",
"revenium_subscriber_id":      "john.demic+trading@revenium.io",
```
Add one new key at the end of the Revenium block (after `"revenium_task_type_map"`, line 176), following the same `os.getenv(ENV_VAR, default)` pattern:
```python
"revenium_trace_type":         os.getenv("REVENIUM_TRACE_TYPE", "trading-run"),
```

---

### `scripts/validate_tracing.py` (utility, request-response — NEW)

**Analog:** `scripts/validate_metering.py`

**Module docstring pattern** (lines 1-47 of validate_metering.py):
```python
"""Live end-to-end metering validation for Revenium + TradingAgents.

Doubles as a pre-demo sanity check (D-07): makes ONE real LLM call with
the ReveniumCallbackHandler attached inside a revenium_run_context, then
asserts that exactly ONE metering event was dispatched with:
...
"""
```
Use the same triple-quoted docstring style describing: purpose, usage examples (with env vars), and what to confirm in the dashboard after exit.

**Import pattern** (lines 49-54 of validate_metering.py):
```python
from __future__ import annotations

import argparse
import sys
from datetime import datetime
```
Replicate exactly. Defer all `tradingagents.*` imports into `main()` to keep module-level clean (established pattern throughout the script).

**`_run_checks` helper** (lines 56-66 of validate_metering.py):
```python
def _run_checks(checks: list[tuple[str, bool]]) -> tuple[int, int]:
    """Print PASS/FAIL for each check tuple and return (passed, failed) counts."""
    passed, failed = 0, 0
    for name, ok in checks:
        label = "PASS" if ok else "FAIL"
        print(f"  {label}  {name}")
        if ok:
            passed += 1
        else:
            failed += 1
    return passed, failed
```
Copy verbatim — this helper is shared validation infrastructure for all Revenium scripts.

**`main()` structure pattern** (lines 196-442 of validate_metering.py):
- `argparse.ArgumentParser` with `description=__doc__` (line 198)
- `load_dotenv()` inside `main()` before any imports (line 237)
- `dict(DEFAULT_CONFIG)` as the base config (line 245)
- Gate on `revenium_api_key` presence before proceeding (lines 258-265)
- `ReveniumCallbackHandler.from_config(config)` construction (line 316)
- Monkeypatch `handler._client.meter_ai_completion = _capture_and_meter` to intercept payloads locally (lines 319-326)
- `revenium_run_context(ticker, date)` as context manager (line 346)
- `for t in list(handler._threads): t.join(timeout=5.0)` after the run (lines 358-359)
- `_run_checks(checks)` with `list[tuple[str, bool]]` pattern (line 413)
- Dashboard reminder print block (lines 419-428)
- Return `0` on all-pass, `1` on any fail; `sys.exit(main())` at bottom (line 442)

For `validate_tracing.py`, replace the single LLM call with a full `TradingAgentsGraph.propagate()` call and replace the payload-content assertions with tracing-specific assertions:
- `"parent_transaction_id" in payload` for every captured payload after the first
- `payload.get("trace_name")` matches `f"{ticker}-{date}"` pattern
- `payload.get("trace_type")` equals `"trading-run"`
- `payload.get("transaction_name")` equals `payload.get("agent")`
- Span count >= expected minimum

**Handler thread flush pattern** (lines 357-359 of validate_metering.py):
```python
# Wait for background threads to finish (give them up to 5 s)
for t in list(handler._threads):
    t.join(timeout=5.0)
```
Copy verbatim after the graph run completes, before assertions.

---

### `tests/test_revenium_tracing.py` (test — NEW)

**Analog:** `tests/test_revenium_metering.py`

**Module docstring pattern** (lines 1-19 of test_revenium_metering.py):
```python
"""Tests for the Revenium metering slice — context, client, and callback handler.

All tests are unit-level (marker: unit) and pass without any live
REVENIUM_METERING_API_KEY.  All Revenium HTTP calls are mocked.
...
"""
```
Use the same style: state what is tested, assert keyless requirement, list key invariants.

**Shared helper pattern** (lines 38-62 of test_revenium_metering.py):
```python
def _make_llm_result(input_tokens: int = 100, output_tokens: int = 50) -> LLMResult:
    """Build a synthetic LLMResult with usage_metadata that mimics a real provider."""
    msg = AIMessage(content="Test response")
    msg.usage_metadata = {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
    }
    gen = ChatGeneration(message=msg)
    return LLMResult(generations=[[gen]])


def _make_serialized(model: str = "gpt-4.1-mini", provider: str = "openai") -> dict:
    ...

def _flush_handler_threads(handler: Any, timeout: float = 2.0) -> None:
    """Join all background threads the handler launched (for test synchronisation)."""
    for t in list(handler._threads):
        t.join(timeout=timeout)
```
Copy these three helpers verbatim — they are used throughout every test class.

**`pytest.fixture` handler pattern** (lines 263-286 of test_revenium_metering.py):
```python
@pytest.fixture
def handler_with_mock_client(self):
    """Return a handler with a mock client that captures payloads."""
    from tradingagents.revenium.callback import ReveniumCallbackHandler

    captured: list[dict] = []
    mock_client = MagicMock()
    mock_client.meter_ai_completion.side_effect = lambda p: captured.append(p)

    handler = ReveniumCallbackHandler.from_config({
        "revenium_api_key": "rev_mk_test",
        "revenium_api_url": "https://api.revenium.ai",
        "revenium_organization_name": "Revenium-Research-Desk",
        "revenium_product_name": "trading-signal",
        "revenium_subscriber_id": "john.demic+trading@revenium.io",
        "revenium_task_type_map": {...},
    })
    handler._client = mock_client
    return handler, captured
```
Copy this fixture structure. For Phase 2, add `"revenium_trace_type": "trading-run"` to the config dict passed to `from_config`.

**`@pytest.mark.unit` test class pattern** (lines 201-234 of test_revenium_metering.py):
```python
class TestOneEventPerCallInvariant:
    @pytest.mark.unit
    def test_one_event_per_llm_end(self):
        from tradingagents.revenium.callback import ReveniumCallbackHandler
        from tradingagents.revenium.context import revenium_run_context

        mock_client = MagicMock()
        handler = ReveniumCallbackHandler.from_config({...})
        handler._client = mock_client

        with revenium_run_context("NVDA", "2026-06-27"):
            for _ in range(n_calls):
                run_id = uuid.uuid4()
                handler.on_chat_model_start(serialized, [[]], run_id=run_id)
                handler.on_llm_end(_make_llm_result(), run_id=run_id)

        _flush_handler_threads(handler)

        assert mock_client.meter_ai_completion.call_count == n_calls
```
Use the same class-per-invariant structure with `@pytest.mark.unit` on every test method. All imports inside test methods (not at module level). All assertions after `_flush_handler_threads(handler)`.

**ContextVar reset fixture pattern** (lines 41-55 of test_revenium_tool_metering.py):
```python
@pytest.fixture(autouse=True)
def _reset_contextvars():
    """Isolate Revenium ContextVars across every test in this module."""
    from tradingagents.revenium.context import (
        current_agent_name,
        current_trace_id,
        current_run_meta,
    )
    tok_agent = current_agent_name.set("unknown")
    tok_trace = current_trace_id.set("")
    tok_meta = current_run_meta.set({})
    yield
    current_agent_name.reset(tok_agent)
    current_trace_id.reset(tok_trace)
    current_run_meta.reset(tok_meta)
```
For `test_revenium_tracing.py`, extend this autouse fixture to also reset `current_parent_transaction_id` to `""`. Add it to the import list and mirror the `tok_X = ContextVar.set(default)` + `ContextVar.reset(tok_X)` pattern.

**Context reset assertion pattern** (lines 72-80 of test_revenium_metering.py):
```python
@pytest.mark.unit
def test_trace_id_is_set_and_reset(self):
    from tradingagents.revenium.context import current_trace_id, revenium_run_context

    assert current_trace_id.get() == "", "trace_id should be empty before context"
    with revenium_run_context("NVDA", "2026-06-27") as tid:
        assert len(tid) == 36
        assert current_trace_id.get() == tid
    assert current_trace_id.get() == "", "trace_id should be reset to '' after context"
```
Mirror this exact before/inside/after assertion structure for `current_parent_transaction_id`. Verify it is `""` before the context, `""` at the start of the run (first call has no parent), non-empty after the first `on_llm_end`, and `""` again after `revenium_run_context` exits.

**Exception-reset invariant pattern** (lines 111-118 of test_revenium_metering.py):
```python
@pytest.mark.unit
def test_trace_id_reset_even_on_exception(self):
    from tradingagents.revenium.context import current_trace_id, revenium_run_context

    with pytest.raises(ValueError):
        with revenium_run_context("NVDA", "2026-06-27"):
            raise ValueError("deliberate error")
    assert current_trace_id.get() == ""
```
Add an equivalent test for `current_parent_transaction_id` — verify it is also `""` after an exception propagates through `revenium_run_context`.

---

## Shared Patterns

### ContextVar Declaration
**Source:** `tradingagents/revenium/context.py` lines 47-63
**Apply to:** `tradingagents/revenium/context.py` (the new `current_parent_transaction_id` addition)
```python
current_parent_transaction_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "revenium_parent_transaction_id",
    default="",
)
"""transaction_id of the most recently completed LLM call; "" at run start."""
```

### Token-Based ContextVar Reset (context manager)
**Source:** `tradingagents/revenium/context.py` lines 96-107
**Apply to:** `tradingagents/revenium/context.py` — `revenium_run_context` finally block
Pattern: `token = var.set(initial_value)` on entry; `var.reset(token)` in `finally`. Never use `var.set(default)` in `finally` — always use the token from entry to be re-entrant safe.

### Fail-Open Exception Guard
**Source:** `tradingagents/revenium/callback.py` lines 337-342
**Apply to:** `tradingagents/revenium/callback.py` — all new code in `on_llm_end` and `on_chat_model_start`
```python
except Exception:  # noqa: BLE001 — fail open, never block the run
    logger.warning(
        "Revenium on_llm_end failed for agent %r — event dropped",
        current_agent_name.get(),
        exc_info=True,
    )
```
All new Phase 2 code in `on_llm_end` is already inside the existing outer `try`/`except Exception` block. No additional guard needed.

### Background Thread — Synchronous-First Pattern
**Source:** `tradingagents/revenium/callback.py` lines 313-335
**Apply to:** `tradingagents/revenium/callback.py` — `on_llm_end` transaction_id + parent update sequencing
Critical ordering constraint (NOT to violate):
1. Generate `transaction_id` as a local variable (before building `payload` dict)
2. Build `payload` dict including `"transaction_id": transaction_id`
3. Call `current_parent_transaction_id.set(transaction_id)` — synchronous, main thread
4. Start background thread via `threading.Thread(...).start()`
5. Append thread to `self._threads` under lock
Step 3 MUST precede step 4. Any contextvar write inside the thread's closure is invisible to the main thread.

### _ENV_OVERRIDES Entry Convention
**Source:** `tradingagents/default_config.py` lines 10-28
**Apply to:** `tradingagents/default_config.py` — new `REVENIUM_TRACE_TYPE` entry
Pattern: `"SCREAMING_SNAKE_CASE": "snake_case_config_key"`. Entry belongs in the Revenium metering block (after `"REVENIUM_SUBSCRIBER_ID"`). The `_coerce` function automatically type-coerces based on the default value's type — since `revenium_trace_type` default is a `str`, no special coercion handling is needed.

### Test Payload Capture via Mock Side Effect
**Source:** `tests/test_revenium_metering.py` lines 263-286
**Apply to:** `tests/test_revenium_tracing.py` — every test class that inspects payload fields
```python
captured: list[dict] = []
mock_client = MagicMock()
mock_client.meter_ai_completion.side_effect = lambda p: captured.append(p)
handler._client = mock_client
```
Use `mock_client.meter_ai_completion.side_effect = lambda p: captured.append(p)` (not `return_value`) so the captured list grows with each call and can be inspected by index.

---

## No Analog Found

All five files have close analogs in the codebase. No files require falling back to RESEARCH.md-only patterns.

---

## Metadata

**Analog search scope:** `tradingagents/revenium/`, `scripts/`, `tests/`, `tradingagents/default_config.py`
**Files scanned:** 7 (context.py, callback.py, config.py, default_config.py, validate_metering.py, test_revenium_metering.py, test_revenium_tool_metering.py)
**Pattern extraction date:** 2026-06-27
