# Phase 3: Cost Controls - Research

**Researched:** 2026-06-28
**Domain:** Revenium enforcement engine wiring, budget-rule provisioning, Rich halt panel
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** Total reliance on Revenium's circuit breaker — no client-side gate. `check_enforcement()` is the sole enforcement mechanism. No in-process spend counter, no local price map.
- **D-02:** Integration seam = pre-call hook in `ReveniumCallbackHandler.on_chat_model_start`. Reuse ONLY the enforcement engine — do NOT adopt the provider-patch middleware. Confirmed: importing `check_enforcement`/`BudgetExceededError` does NOT trigger provider patching.
- **D-03:** Deliberate re-raise of `BudgetExceededError`. The handler's fail-open `except Exception` must NOT catch it. The cost gate is the ONE deliberate exception to the fail-open convention.
- **D-04:** Budget unit = dollar cost-limit rule. No local AI-cost price map needed.
- **D-05:** Rich panel on halt, no fabricated decision. `propagate()` and CLI catch `BudgetExceededError` and render a panel with rule_name, current_value/threshold, resets_at, rule_id, stage/agent, trace_id, per-agent cost breakdown. Non-zero exit code. No BUY/HOLD/SELL printed.
- **D-06:** Provision the rule via the committed idempotent setup script (`scripts/setup_revenium.py`). The Revenium CLI may be used ad-hoc but the script is source of truth.
- **D-07:** CTL-04 satisfied directly. Setup script sets `shadowMode: false`. Pre-flight checklist (DMO-02) confirms enforce mode.
- **D-08:** CTL-01 reinterpreted. "Revenium's circuit breaker gates the run; demo timing is reliable **operationally**." No in-process counter.
- **D-09:** Timing reliability via: low `REVENIUM_CB_POLL_INTERVAL_SECONDS` (~5–10s), low threshold so rule is breached early, stop-watch dry-run validation.
- **D-10:** Circuit-breaker config via `.env`: `REVENIUM_CIRCUIT_BREAKER_ENABLED=true`, `REVENIUM_TEAM_ID=<hashed>`, `REVENIUM_CB_POLL_INTERVAL_SECONDS`, `REVENIUM_CB_FAIL_MODE` (default open), `REVENIUM_BYPASS=true` (disables enforcement; keeps keyless test suite green).

### Claude's Discretion

- Exact module placement of the enforcement call and `usage_metadata` assembly within `tradingagents/revenium/`
- Precise Rich panel layout
- Where `BudgetExceededError` catch sits (`_run_graph` vs CLI vs both)
- `stop_polling()` lifecycle wiring

### Deferred Ideas (OUT OF SCOPE)

- Optional Slack notification on enforcement event (second screen) — defer to Phase 5 hardening or treat as polish
- Client-side / in-process spend gate — explicitly rejected for this phase (D-01)
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| CTL-01 | Revenium's circuit breaker gates the run — `check_enforcement()` pre-call hook raises `BudgetExceededError` when an enforce-mode cost rule is breached; timing is made reliable operationally (reworded per D-08) | Wiring pattern in §Architecture Patterns; timing analysis in §Common Pitfalls |
| CTL-02 | Breached rule raises `BudgetExceededError`, caught in `propagate()`/CLI, surfaced gracefully with cost context | `BudgetExceededError` field inventory in §Code Examples; CLI path analysis in §Architecture Patterns |
| CTL-03 | A Revenium dashboard enforcement event is visible during the run | Enforcement event format confirmed in §Architecture Patterns; `ENFORCEMENT_VIOLATION` operation type verified |
| CTL-04 | Cost-control rules confirmed in enforce mode (`shadowMode: false`) before demo | Rule provisioning schema in §Code Examples; idempotency path documented |
</phase_requirements>

---

## Summary

Phase 3 wires Revenium's existing enforcement engine into the callback handler so a breached cost rule halts the live demo mid-analysis. The enforcement engine (`revenium_middleware._core.enforcement`) is already installed in `.venv`, identical to the internal SDK, and exposes `check_enforcement()`, `BudgetExceededError`, and `stop_polling()` as stable public symbols. No new packages are required.

The integration has three touch-points: (1) a `check_enforcement()` call added to `on_chat_model_start` **outside** the fail-open `try/except` block so `BudgetExceededError` escapes; (2) `stop_polling()` added to cleanup paths in both `_run_graph` and the CLI streaming loop; (3) a Rich halt panel caught in the CLI's `run_analysis` function that renders cost context and exits with a non-zero code.

Budget rule provisioning extends `scripts/setup_revenium.py` with idempotent create/verify logic at `POST /ai/cost-controls`. The rule uses `metricType: TOTAL_COST`, `windowType: DAILY`, `action: BLOCK`, `shadowMode: false`, and an `ORGANIZATION:IS:Revenium-Research-Desk` filter so only demo-org spend counts server-side. Demo timing reliability comes from setting `REVENIUM_CB_POLL_INTERVAL_SECONDS=5` and pre-calibrating the threshold to fire mid-debate (~$1.00 DAILY with current model costs).

**Primary recommendation:** Wire `check_enforcement()` into `on_chat_model_start`, extend setup_revenium.py, catch `BudgetExceededError` in the CLI streaming loop, add `stop_polling()` to both teardown paths, and write a `validate_controls.py` timing dry-run script.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Enforcement check (pre-call gate) | Callback Handler (`callback.py`) | Enforcement engine (`_core/enforcement.py`) | `on_chat_model_start` is the only pre-call hook available in the LangChain callback path |
| Budget rule breach detection | Revenium server-side (background poller) | Enforcement in-memory cache | Server computes `breached: true`; client polls and caches; `check_enforcement()` reads cache |
| Rule provisioning | `scripts/setup_revenium.py` | Revenium management REST API | Version-controlled, idempotent, rebuildable; script is source of truth (D-06) |
| Halt rendering | CLI (`cli/main.py run_analysis`) | `_run_graph` (propagate path) | Rich panel with per-agent costs requires access to handler state; CLI is the demo display layer |
| Poll thread lifecycle | `_run_graph` finally / `run_analysis` finally | — | Both graph paths need teardown; `stop_polling()` is safe to call unconditionally (no-op if thread not started) |
| Dashboard enforcement event | Revenium server | — | `operation: ENFORCEMENT_VIOLATION` fires automatically when `shadowMode: false` rule is breached; no code needed |
| Keyless bypass | `REVENIUM_BYPASS=true` env var | `REVENIUM_CIRCUIT_BREAKER_ENABLED` unset | Both short-circuit `check_enforcement()` before any cache read; test suite stays green without keys |

---

## Standard Stack

### No New Packages Required

All enforcement functionality is already in `.venv` via `revenium-python-sdk[langchain]>=0.1.9`.

| Symbol | Import Path | Purpose |
|--------|-------------|---------|
| `check_enforcement` | `revenium_middleware._core` | Pre-call hook; raises `BudgetExceededError` when enforce-mode rule is breached |
| `BudgetExceededError` | `revenium_middleware._core` | Exception with fields: `rule_name`, `current_value`, `threshold`, `resets_at`, `rule_id` |
| `stop_polling` | `revenium_middleware._core` | Gracefully shuts down the background enforcement polling daemon thread |

[VERIFIED: venv] - Installed SDK is identical to internal SDK source. `check_enforcement`, `BudgetExceededError`, `stop_polling` confirmed importable from `revenium_middleware._core` without triggering provider patching.

### Package Legitimacy Audit

No new packages in this phase. The enforcement engine ships as part of `revenium-python-sdk[langchain]` which was verified in Phase 1 (Plan 01-01).

**Packages removed due to slopcheck [SLOP] verdict:** none

**Packages flagged as suspicious [SUS]:** none

---

## Architecture Patterns

### System Architecture Diagram

```
CLI run_analysis()
       |
       |  graph.graph.stream(init_agent_state, **args)
       |         |
       |    [LangGraph node: any agent]
       |         |
       |    LangChain dispatcher
       |         |
       |    on_chat_model_start()
       |         |
       |    check_enforcement({"subscriber_credential": subscriber_id})
       |         |
       |    [REVENIUM_BYPASS=true or CB_DISABLED]  --> no-op
       |         |
       |    [cache empty or not breached]           --> pass through to LLM call
       |         |
       |    [breached + shadowMode:false + credential match]
       |         |
       |    raise BudgetExceededError <--- propagates up through LangChain
       |                                   --> escapes graph.graph.stream()
       |                                   --> exits with Live() context
       v
  except BudgetExceededError as err:
       |
  render Rich halt panel (rule context + agent_costs)
       |
  stop_polling()
       |
  raise typer.Exit(code=1)

Background daemon thread (per-process):
  REVENIUM_CB_POLL_INTERVAL_SECONDS (default: 60, demo: 5)
       |
  GET https://api.revenium.ai/v2/api/ai/enforcement-rules/{team_id}
       |
  updates _cached_rules, _cache_initialized
```

For the `propagate()` path (non-CLI callers / debug mode):
```
propagate() --> _run_graph() --> graph.invoke()
                     |
              try block: begin_run(), graph.invoke(), end_run() in finally
              BudgetExceededError propagates through the try block
              finally: end_run(), stop_polling()
              BudgetExceededError re-raised to propagate() caller
```

**Important:** The CLI path calls `graph.graph.stream()` directly, bypassing `_run_graph()` and the `propagate()` method entirely. `begin_run()`/`end_run()` are NOT called in the CLI streaming path. Enforcement via `check_enforcement()` in `on_chat_model_start` works regardless because it reads from the in-memory cache, independent of trace state. `stop_polling()` must be wired in BOTH teardown paths.

### Enforcement Engine Internals (key facts for planner)

- **Cache model:** Rules are fetched by a daemon thread on `_poll_interval_seconds()` cadence and stored in `_cached_rules` (module-global). `check_enforcement()` reads from this in-memory cache under a lock — zero network calls in the hot path.
- **Breach detection logic:** For each cached rule: (1) `breached` or `blocked` must be True; (2) `shadowMode` must be False; (3) if `credential` field is non-empty, it must match `usage_metadata["subscriber_credential"]`. First matching rule raises.
- **Fail modes:** Default `REVENIUM_CB_FAIL_MODE=open` → empty/uninitialized cache passes through. `closed` → blocks when cache never loaded (not needed for demo).
- **Thread restart:** After `stop_polling()`, the `_ensure_poller_running()` call in the next `check_enforcement()` starts a fresh daemon thread. Safe to call after each run.
- **No-op guards:** Disabled when `REVENIUM_CIRCUIT_BREAKER_ENABLED` unset OR `REVENIUM_BYPASS=true`.

### Budget Rule CREATE Schema (enforcement side)

The compiled enforcement rule (from `GET /v2/api/ai/enforcement-rules/{team_id}`) has this shape when a demo rule fires: [VERIFIED from live API]

```json
{
  "ruleId": 2508,
  "name": "TradingAgents Demo Budget",
  "breached": true,
  "shadowMode": false,
  "action": "BLOCK",
  "metricType": "TOTAL_COST",
  "currentValue": 1.25,
  "threshold": 1.00,
  "warnThreshold": 0.50,
  "warnBreached": true,
  "windowStart": "2026-06-28T00:00:00Z",
  "windowEnd": "2026-06-28T23:59:59.999Z",
  "resetsAt": "2026-06-29T00:00:00Z",
  "filters": [{"dimension": "ORGANIZATION", "operator": "IS", "value": "Revenium-Research-Desk"}],
  "teamId": 26211,
  "percentUsed": 125.0
}
```

Note: no `"credential"` field → credential check skipped in `check_enforcement()` → rule blocks all callers when breached. Server-side, only Revenium-Research-Desk org spend accumulates toward the threshold.

### Budget Rule CREATE (management API) [VERIFIED from CLI dry-run]

```
POST https://api.prod.ai.hcapp.io/profitstream/v2/api/ai/cost-controls
Headers: x-api-key: rev_sk_...

Body:
{
  "name": "TradingAgents Demo Budget",
  "description": "Demo cost gate for FCAT — enforce mode, daily $1.00 limit",
  "metricType": "TOTAL_COST",
  "windowType": "DAILY",
  "action": "BLOCK",
  "groupBy": "AGENT",
  "hardLimit": 1.0,
  "warnThreshold": 0.5,
  "shadowMode": false,
  "enabled": true,
  "filters": [
    {"dimension": "ORGANIZATION", "operator": "IS", "value": "Revenium-Research-Desk"}
  ],
  "teamId": "DZxzEl",
  "notificationChannelIds": []
}
```

Idempotency:
- `GET /ai/cost-controls?teamId=DZxzEl` → list existing rules
- Match by `name == "TradingAgents Demo Budget"` client-side
- If found: verify `shadowMode == False` and `enabled == True`; PATCH if mismatched
- If not found: POST to create
- PATCH path: `PATCH /ai/cost-controls/{rule_id}` with `{"shadowMode": false}` or `{"enabled": true}`

### Dashboard Enforcement Events [VERIFIED from live API]

When an enforce-mode rule fires, Revenium creates an enforcement event:

```json
{
  "id": "vPJ0nB",
  "action": "BLOCK",
  "operation": "ENFORCEMENT_VIOLATION",
  "isShadow": false,
  "ruleName": "TradingAgents Demo Budget",
  "currentValue": 1.25,
  "threshold": 1.00,
  "usagePercent": 125.0,
  "created": "2026-06-28T15:30:00Z"
}
```

Shadow-mode events show `"operation": "ENFORCEMENT_SHADOW_VIOLATION"` and `"isShadow": true`. The FCAT audience sees the live event under Guardrails → Enforcement Events in the Revenium dashboard. No additional code is needed to emit this event — it is created server-side automatically.

### Recommended Project Structure (new files this phase)

```
tradingagents/revenium/
└── callback.py          # MODIFY: add check_enforcement() gate in on_chat_model_start

tradingagents/graph/
└── trading_graph.py     # MODIFY: add stop_polling() to _run_graph finally

cli/
└── main.py              # MODIFY: wrap stream loop in try/except BudgetExceededError;
                         #         render halt panel; call stop_polling() in finally

scripts/
├── setup_revenium.py    # MODIFY: add _setup_cost_rule() for budget rule provisioning
└── validate_controls.py # NEW: timing dry-run + enforcement readiness check

tests/
└── test_revenium_enforcement.py  # NEW: keyless unit tests for enforcement gate wiring
```

### Anti-Patterns to Avoid

- **Placing `check_enforcement()` inside the fail-open `try/except Exception` block:** `BudgetExceededError` inherits from `Exception` and would be swallowed. Place it BEFORE the try block.
- **Calling `stop_polling()` before `end_run()`:** `end_run()` clears run-scoped state; do it first, then tear down the daemon. Both belong in the `finally` block.
- **Credential-scoping the rule with CREDENTIAL filter without matching `subscriber_credential` in usage_metadata:** If the compiled rule has `"credential": "x"` but `usage_metadata["subscriber_credential"]` is `""`, the rule never fires. Use ORGANIZATION filter instead (no credential field in compiled rule → credential check skipped → all callers affected server-side).
- **Setting `shadowMode: true` in the setup script:** Enforcement engine skips shadow-mode rules even when `breached: true`. This is the demo stopper — D-07 requires `shadowMode: false`.
- **Calling `stop_polling()` and expecting it to reset `_cache_initialized`:** `stop_polling()` only stops the daemon thread. The module-global cache state persists. The next `check_enforcement()` call starts a fresh thread but reads the existing cache until the thread fetches fresh rules.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Cost breach detection | In-process token counter + price table | `check_enforcement()` from `revenium_middleware._core` | Server already tracks cumulative cost; client just polls; any price-table would need continuous maintenance and drift from Revenium's billing model |
| Rule breach polling | Custom background thread with httpx | Enforcement daemon built into SDK | Already handles: cache TTL, thundering-herd prevention, disk persistence, fail-open/closed, team-id auth, `stop_polling()` |
| Shadow-mode check | `if rule.get("shadow_mode"):` custom logic | SDK enforcement engine handles internally | The `shadowMode` skip, `breached` vs `blocked` duality, cache stale logic — already covered |
| CLI panel text | Custom cost string | Rich `Panel`, `Table`, `Text` (already imported in `cli/main.py`) | Already used throughout the CLI |
| Budget rule CRUD | Hand-crafted REST client | Extend `setup_revenium.py` with the same `_post`/`_get` helpers already there | Consistent auth, error handling, and `_extract_list` defensive parsing |

**Key insight:** The enforcement engine does all the hard work (polling, breach detection, credential scoping, fail-mode, cache persistence). `check_enforcement()` is a 1-line call.

---

## Common Pitfalls

### Pitfall 1: `BudgetExceededError` Swallowed by Fail-Open Block

**What goes wrong:** Adding `check_enforcement()` inside the existing `try: ... except Exception:` block in `on_chat_model_start` causes enforcement to be silently swallowed. The run continues, no halt occurs, no error message.

**Why it happens:** `BudgetExceededError` subclasses `Exception` directly (by design — to escape provider error decorators). The handler's catch-all is intentionally broad.

**How to avoid:** Place `check_enforcement()` BEFORE the `try` block, after the `if not self.enabled: return` guard. The only thing between the `enabled` check and the `try` block should be the enforcement gate.

**Warning signs:** CLI never halts even with a breached rule; `test_budget_exceeded_propagates_from_on_chat_model_start` test fails.

### Pitfall 2: Timing Misfire — Rule Breaches Too Late in the Run

**What goes wrong:** The halt fires at the very last LLM call (Portfolio Manager), or never fires during a demo run, because the threshold is too high or the poll interval is too long.

**Why it happens:** The latency chain is: LLM call completes → meter event sent (async daemon thread) → Revenium ingests → marks `breached: true` in compiled rules → enforcement poller fetches updated rules (every `REVENIUM_CB_POLL_INTERVAL_SECONDS`) → next `check_enforcement()` call sees `breached: true` → halt. Total latency: typically 15–60 seconds.

**How to avoid:**
1. Set `REVENIUM_CB_POLL_INTERVAL_SECONDS=5` for demo.
2. Set threshold at ~$1.00 DAILY with ORGANIZATION filter. At current model costs (~$0.05–0.15 per analyst call, ~$0.30 for Research Manager deep-think), the run accumulates ~$0.50–0.80 through the four analysts + Research Manager. The halt fires during the bull/bear debate or risk debate — which is the visually ideal moment for FCAT.
3. Pre-warm: do a "pre-demo run" the same day (not necessarily to completion) so the daily accumulator already has $0.50+ on it. Confirm with `revenium guardrails enforcement-rules get DZxzEl --json` that `breached: true` before the demo.
4. Confirm the timing dry-run via `validate_controls.py` the day before demo.

**Warning signs:** `percentUsed` in compiled enforcement rules is < 50% going into the demo; poll interval > 30s; no enforcement event in dashboard after a trial run.

### Pitfall 3: Enforcement Check Runs in CLI Path but `stop_polling()` Is Only in `_run_graph`

**What goes wrong:** When the CLI streams directly (`graph.graph.stream()` bypassing `_run_graph()`), the enforcement daemon thread is never stopped after the run. It continues polling in the background until the process exits.

**Why it happens:** `_run_graph` and CLI streaming are two independent execution paths. The `finally` block in `_run_graph` doesn't execute in CLI mode.

**How to avoid:** Add `stop_polling()` to a `finally` clause in the CLI `run_analysis` function, alongside the `BudgetExceededError` catch. Since `stop_polling()` is idempotent and safe when the thread is already stopped, add it unconditionally.

**Warning signs:** Daemon thread logs continue after CLI exits; multiple poll threads accumulate if the handler is reused (won't affect demo but is a resource leak).

### Pitfall 4: Management API vs Enforcement Polling API — Different Hosts

**What goes wrong:** Using `https://api.prod.ai.hcapp.io/profitstream/v2/api` to construct the enforcement polling URL, or using `https://api.revenium.ai` for the budget rule CREATE.

**Why it happens:** Two separate APIs with different hosts/paths:
- **Management (rule CRUD):** `https://api.prod.ai.hcapp.io/profitstream/v2/api/ai/cost-controls` — uses `rev_sk_*` key
- **Enforcement polling:** `https://api.revenium.ai/v2/api/ai/enforcement-rules/{team_id}` — uses `rev_mk_*` key

**How to avoid:** `setup_revenium.py` uses the management host (same as existing script). The enforcement engine derives its polling URL from `REVENIUM_METERING_BASE_URL` automatically — no change needed to enforcement.py or env vars for the demo account. The metering base URL default (`https://api.revenium.ai`) yields the correct enforcement polling origin.

**Warning signs:** 404 on budget rule GET; 401 on enforcement poll (wrong key type).

### Pitfall 5: `REVENIUM_BYPASS=true` Not Set in Test Environment

**What goes wrong:** Tests that import the callback handler and trigger `on_chat_model_start` start enforcement polling (daemon thread) and may block when a rule is accidentally cached.

**Why it happens:** If `REVENIUM_CIRCUIT_BREAKER_ENABLED=true` leaks from the environment, enforcement is active during tests.

**How to avoid:** Test conftest should either: (a) set `REVENIUM_BYPASS=true`, or (b) use `monkeypatch.delenv("REVENIUM_CIRCUIT_BREAKER_ENABLED", raising=False)`. Tests that specifically test the enforcement gate use the `_seed_rules` monkeypatch pattern (see §Code Examples).

### Pitfall 6: `teamId` in Budget Rule POST Body

**What goes wrong:** Creating a budget rule without `teamId` in the POST body results in the rule being created globally (or a 400 error).

**Why it happens:** The management API may accept the request but scope it wrong; the CLI injects `teamId` via a global flag that maps to a query param or header differently from the REST body.

**How to avoid:** Always include `"teamId": team_id` in the POST body for `/ai/cost-controls`, mirroring the product provisioning pattern in `_setup_product()`. Verify the created rule appears in `budget-rules list` scoped to `DZxzEl`.

---

## Code Examples

### 1. Enforcement Gate in `on_chat_model_start`

```python
# tradingagents/revenium/callback.py
# Source: enforcement.py _core module + D-03 decision

from revenium_middleware._core import check_enforcement, BudgetExceededError  # noqa: F401

def on_chat_model_start(
    self,
    serialized: dict[str, Any],
    messages: list[list[Any]],
    **kwargs: Any,
) -> None:
    """Capture provider, model, agent name, and start time for this call.

    Enforcement gate (CTL-01): check_enforcement() is called BEFORE the
    fail-open try/except so BudgetExceededError is deliberately allowed to
    propagate (D-03 exception to the fail-open convention).
    """
    if not self.enabled:
        return

    # Enforcement gate — D-03: deliberate exception to the fail-open
    # convention. BudgetExceededError must NOT be caught below; it must
    # propagate to _run_graph / CLI so the run halts cleanly (CTL-01/02).
    # No-op when REVENIUM_CIRCUIT_BREAKER_ENABLED is unset or
    # REVENIUM_BYPASS=true (keeps keyless test suite green — DMO-04).
    check_enforcement({
        "subscriber_credential": self._attribution.get("subscriber_id", ""),
    })

    try:
        run_id = str(kwargs.get("run_id", uuid.uuid4()))
        # ... existing state capture code ...
    except Exception:  # noqa: BLE001 — fail open, never block the run
        logger.warning("Revenium on_chat_model_start failed ...", exc_info=True)
```

### 2. `stop_polling()` in `_run_graph` Finally Block

```python
# tradingagents/graph/trading_graph.py
# Source: enforcement.py stop_polling() + D-10 decision

from revenium_middleware._core import stop_polling

def _run_graph(self, company_name, trade_date, asset_type="stock"):
    with revenium_run_context(ticker=company_name, trade_date=str(trade_date)) as _trace_id:
        try:
            self._revenium_handler.begin_run(_trace_id, company_name, str(trade_date))
            # ... graph.invoke() / graph.stream() ...
        finally:
            # end_run() clears handler instance state (WR-01/WR-02).
            # stop_polling() stops the enforcement daemon thread.
            # Both are fail-open no-ops; order matters: state clear first.
            self._revenium_handler.end_run()
            # Stop the background enforcement poller so it does not outlive
            # this run. _ensure_poller_running() will restart it on the next
            # propagate() call's first check_enforcement() invocation.
            stop_polling()
```

### 3. CLI Halt Panel in `run_analysis`

```python
# cli/main.py — inside run_analysis()
# Source: BudgetExceededError fields (exceptions.py) + D-05 decision

from revenium_middleware._core import BudgetExceededError, stop_polling

def run_analysis(...):
    # ... setup ...
    try:
        with Live(layout, refresh_per_second=4):
            for chunk in graph.graph.stream(init_agent_state, **args):
                # ... existing chunk processing ...
    except BudgetExceededError as err:
        # Run halted by Revenium enforcement (CTL-02).
        # Live context has already exited; render halt panel to console.
        _render_budget_halt_panel(console, err, revenium_handler)
        raise typer.Exit(code=1)
    finally:
        # Stop enforcement daemon thread on every exit path (normal + halt).
        stop_polling()


def _render_budget_halt_panel(
    console: Console,
    err: BudgetExceededError,
    handler: "ReveniumCallbackHandler",
) -> None:
    """Render the Rich halt panel for a budget enforcement stop (CTL-02, D-05)."""
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text

    # Per-agent cost breakdown from the handler accumulator
    cost_table = Table(show_header=True, header_style="bold magenta")
    cost_table.add_column("Agent", style="cyan")
    cost_table.add_column("Input Tokens", justify="right")
    cost_table.add_column("Output Tokens", justify="right")
    for agent, counts in sorted(handler.agent_costs.items()):
        cost_table.add_row(
            agent,
            str(counts["input_tokens"]),
            str(counts["output_tokens"]),
        )

    current = f"${err.current_value:.4f}" if err.current_value is not None else "—"
    threshold = f"${err.threshold:.4f}" if err.threshold is not None else "—"
    resets = err.resets_at or "—"

    body = Text()
    body.append(f"\nRule:      ", style="bold")
    body.append(err.rule_name or "cost limit")
    body.append(f"\nSpent:     ", style="bold")
    body.append(current, style="red bold")
    body.append(f"  /  Limit: ")
    body.append(threshold, style="yellow")
    body.append(f"\nResets at: ", style="bold")
    body.append(resets)
    body.append(f"\nRule ID:   ", style="bold")
    body.append(str(err.rule_id or "—"))

    console.print(Panel(
        body,
        title="[bold red]Run Halted — Budget Limit Reached[/bold red]",
        subtitle="Revenium enforcement rule blocked this request",
        border_style="red",
    ))
    console.print("\n[bold]Per-Agent Token Usage:[/bold]")
    console.print(cost_table)
    console.print(
        "\n[dim]Check the Revenium dashboard > Guardrails > Enforcement Events "
        "to see the enforcement event.[/dim]"
    )
    console.print("[yellow]Run exiting with non-zero status (no trading decision produced).[/yellow]")
```

### 4. Budget Rule Provisioning in `setup_revenium.py`

```python
# scripts/setup_revenium.py — new function _setup_cost_rule()
# Source: verified from CLI dry-run output + budget-rules list response

DEMO_RULE_NAME = "TradingAgents Demo Budget"
DEMO_RULE_HARD_LIMIT = 1.00    # $1.00 DAILY — tune per timing dry-run
DEMO_RULE_WARN_THRESHOLD = 0.50

def _setup_cost_rule(
    base_url: str,
    sk_key: str,
    team_id: str,
    dry_run: bool,
) -> bool:
    """Create or verify the enforce-mode cost rule (CTL-04, D-06).

    Idempotency: look up by name, create if missing, PATCH to enforce mode
    if found in shadow mode.  Returns True on success or dry-run.
    """
    print(f"  Cost rule: '{DEMO_RULE_NAME}' (TOTAL_COST DAILY ${DEMO_RULE_HARD_LIMIT})")
    if dry_run:
        print(f"    [dry-run] Would GET /ai/cost-controls?teamId={team_id} (find by name)")
        print("    [dry-run] Would POST /ai/cost-controls {name, metricType, DAILY, BLOCK,"
              " hardLimit, shadowMode:false, ORGANIZATION filter} if not found")
        print("    [dry-run] Would PATCH /ai/cost-controls/{id} {shadowMode:false} if found"
              " in shadow mode")
        return True

    # Lookup existing rules for this team
    try:
        data = _get(base_url, "/ai/cost-controls", sk_key, params={"teamId": team_id})
        for rule in _extract_list(data):
            if rule.get("name") == DEMO_RULE_NAME or rule.get("label") == DEMO_RULE_NAME:
                rule_id = str(rule.get("id", ""))
                shadow = rule.get("shadowMode", True)
                enabled = rule.get("enabled", False)
                if not shadow and enabled:
                    print(f"    exists in enforce mode (id={rule_id}) — OK")
                    return True
                # Found but in wrong state — PATCH to enforce mode
                try:
                    _patch(base_url, f"/ai/cost-controls/{rule_id}", sk_key,
                           {"shadowMode": False, "enabled": True})
                    print(f"    updated to enforce mode (id={rule_id})")
                    return True
                except requests.HTTPError as exc:
                    _handle_http_error("Cost rule PATCH", exc)
                    return False
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 404:
            pass  # No rules yet — fall through to create
        else:
            _handle_http_error("Cost rule lookup", exc)
            return False

    # Create in enforce mode (shadowMode defaults to false when omitted)
    try:
        result = _post(base_url, "/ai/cost-controls", sk_key, {
            "name": DEMO_RULE_NAME,
            "description": (
                "Demo cost gate for FCAT — enforce mode. "
                "Scoped to Revenium-Research-Desk org. "
                "Halts the run mid-debate for the control pillar demo."
            ),
            "metricType": "TOTAL_COST",
            "windowType": "DAILY",
            "action": "BLOCK",
            "groupBy": "AGENT",
            "hardLimit": DEMO_RULE_HARD_LIMIT,
            "warnThreshold": DEMO_RULE_WARN_THRESHOLD,
            "shadowMode": False,
            "enabled": True,
            "filters": [
                {
                    "dimension": "ORGANIZATION",
                    "operator": "IS",
                    "value": ORG_NAME,  # "Revenium-Research-Desk"
                }
            ],
            "teamId": team_id,
            "notificationChannelIds": [],
        })
        rule_id = str(result.get("id", ""))
        print(f"    created in enforce mode (id={rule_id or 'n/a'})")
        return True
    except requests.HTTPError as exc:
        _handle_http_error("Cost rule create", exc)
        return False
```

### 5. Keyless Mock Pattern for Tests

```python
# tests/test_revenium_enforcement.py
# Source: SDK tests/test_openai/test_enforcement.py pattern (VERIFIED locally)

import importlib
import pytest
from revenium_middleware._core import enforcement
from revenium_middleware._core.exceptions import BudgetExceededError


@pytest.fixture(autouse=True)
def _reset_enforcement(monkeypatch):
    """Isolate enforcement module state across tests."""
    for var in (
        "REVENIUM_CIRCUIT_BREAKER_ENABLED",
        "REVENIUM_BYPASS",
        "REVENIUM_CB_FAIL_MODE",
        "REVENIUM_TEAM_ID",
        "REVENIUM_METERING_API_KEY",
    ):
        monkeypatch.delenv(var, raising=False)
    importlib.reload(enforcement)
    yield
    enforcement.stop_polling()


def _seed_rules(monkeypatch, rules: list, *, initialized: bool = True) -> None:
    """Inject rules into the enforcement cache, bypassing the network poller."""
    monkeypatch.setattr(enforcement, "_cached_rules", list(rules))
    monkeypatch.setattr(enforcement, "_cache_timestamp", float("inf"))
    monkeypatch.setattr(enforcement, "_cache_initialized", initialized)
    monkeypatch.setattr(enforcement, "_ensure_poller_running", lambda: None)
    monkeypatch.setattr(enforcement, "_fetch_rules", lambda: None)


@pytest.mark.unit
def test_check_enforcement_raises_when_rule_breached(monkeypatch):
    """check_enforcement raises BudgetExceededError for a breached enforce-mode rule."""
    monkeypatch.setenv("REVENIUM_CIRCUIT_BREAKER_ENABLED", "true")
    _seed_rules(monkeypatch, [{
        "ruleId": 1,
        "name": "demo-budget",
        "breached": True,
        "shadowMode": False,
        "threshold": 1.0,
        "currentValue": 1.5,
        "resetsAt": "2026-06-29T00:00:00Z",
    }])
    with pytest.raises(BudgetExceededError) as exc_info:
        enforcement.check_enforcement({})
    err = exc_info.value
    assert err.rule_name == "demo-budget"
    assert err.threshold == 1.0
    assert err.current_value == 1.5


@pytest.mark.unit
def test_bypass_env_disables_enforcement(monkeypatch):
    """REVENIUM_BYPASS=true short-circuits even when a rule is breached."""
    monkeypatch.setenv("REVENIUM_CIRCUIT_BREAKER_ENABLED", "true")
    monkeypatch.setenv("REVENIUM_BYPASS", "true")
    _seed_rules(monkeypatch, [{"name": "would-block", "breached": True, "shadowMode": False}])
    enforcement.check_enforcement({})  # must not raise


@pytest.mark.unit
def test_shadow_mode_rule_does_not_block(monkeypatch):
    """shadowMode:true rules are observe-only; must never block the run."""
    monkeypatch.setenv("REVENIUM_CIRCUIT_BREAKER_ENABLED", "true")
    _seed_rules(monkeypatch, [{"name": "shadow", "breached": True, "shadowMode": True}])
    enforcement.check_enforcement({})  # must not raise


@pytest.mark.unit
def test_on_chat_model_start_propagates_budget_exceeded(monkeypatch):
    """BudgetExceededError from check_enforcement escapes the callback handler."""
    from revenium_middleware._core import enforcement as enf
    from tradingagents.revenium.callback import ReveniumCallbackHandler

    monkeypatch.setenv("REVENIUM_CIRCUIT_BREAKER_ENABLED", "true")
    _seed_rules(monkeypatch, [{
        "name": "demo-budget", "breached": True, "shadowMode": False,
        "threshold": 1.0, "currentValue": 1.5,
    }])

    from unittest.mock import MagicMock
    mock_client = MagicMock()
    mock_client.enabled = True
    handler = ReveniumCallbackHandler(
        client=mock_client,
        attribution={"subscriber_id": "john.demic+trading@revenium.io",
                     "organizationName": "Revenium-Research-Desk",
                     "productName": "trading-signal", "api_key": "rev_mk_test"},
        task_type_map={},
    )
    serialized = {"id": ["langchain_openai", "chat_models", "ChatOpenAI"],
                  "kwargs": {"model_name": "gpt-4.1-mini"}}

    with pytest.raises(BudgetExceededError):
        handler.on_chat_model_start(serialized, [], run_id="test-run-id")
```

---

## Runtime State Inventory

Not applicable — this is a code instrumentation phase, not a rename/refactor/migration phase. No stored data, live service config, OS-registered state, secrets, or build artifacts reference strings being changed.

---

## Open Questions (Resolved)

### OQ-1: `REVENIUM_TEAM_ID` sourcing

**Resolved:** `REVENIUM_TEAM_ID = DZxzEl` (hashed team ID). Confirmed from `~/.config/revenium/config.yaml` and validated by live `enforcement-rules get DZxzEl` returning the correct compiled rules. The same value is already used by `setup_revenium.py` for product scoping. The `enforcement.py` polling URL uses the hashed ID: `GET https://api.revenium.ai/v2/api/ai/enforcement-rules/DZxzEl`. [VERIFIED: live API]

### OQ-2: Enforcement-rule CREATE path

**Resolved:** `POST /ai/cost-controls` relative to the management base URL (`https://api.prod.ai.hcapp.io/profitstream/v2/api`). Confirmed from `revenium guardrails budget-rules create --dry-run`. Full body schema documented in §Code Examples. Idempotency: GET by teamId, match by name, create or PATCH. [VERIFIED: CLI dry-run]

### OQ-3: `subscriber_credential` matching

**Resolved:** No credential scoping needed for the demo. Use `ORGANIZATION:IS:Revenium-Research-Desk` filter only. The compiled rule will have no `credential` field → `rule_credential = ""` → credential check skipped → rule blocks all callers client-side when `breached: true`. Pass `{"subscriber_credential": subscriber_id}` in `usage_metadata` for completeness/future use — it has no effect on matching without a CREDENTIAL filter. [VERIFIED: enforcement.py source + SDK tests + live compiled rules response]

### OQ-4: No double-counting / no patching on import

**Resolved:** Confirmed via Python execution in the project venv. Importing `from revenium_middleware._core import check_enforcement, BudgetExceededError` does NOT activate provider patching. `check_enforcement()` reads from in-memory cache only — zero network calls inline. The metering path (`on_llm_end` → fire-and-forget thread) and the enforcement check (`on_chat_model_start` → cache read) are fully independent. [VERIFIED: local execution]

### OQ-5: Timing dry-run

**Resolved (guidance):** Latency chain is approximately 15–45 seconds from the triggering LLM call to halt, depending on Revenium ingestion speed and poll interval. For demo:
- Set `REVENIUM_CB_POLL_INTERVAL_SECONDS=5`.
- Set `DEMO_RULE_HARD_LIMIT = 1.00` (DAILY). At current model costs ($0.03–0.15 per analyst, ~$0.30 for Research Manager), the run hits ~$0.50–0.80 through analysts + Research Manager, triggering mid-debate.
- Pre-warm: the day before demo, do a trial run (or validate_controls.py timing check) to confirm the rule reaches `breached: true` before FCAT.
- The `validate_controls.py` script should: (1) read compiled enforcement rules and report `percentUsed`; (2) run a timed `propagate()` call and record which agent triggers the halt; (3) report total elapsed time to halt.

### OQ-6: Keyless testability

**Resolved:** Two strategies: (a) `monkeypatch.setenv("REVENIUM_BYPASS", "true")` disables enforcement entirely — for tests that should not see `BudgetExceededError`. (b) `_seed_rules(monkeypatch, [...])` pattern (see §Code Examples) seeds the in-memory cache without network — for tests that specifically assert enforcement fires. Neither strategy requires live Revenium keys. [VERIFIED: local execution of mock pattern]

### OQ-7: `stop_polling()` lifecycle

**Resolved:** Call in TWO places: (1) `_run_graph` finally block (covers `propagate()` path); (2) `run_analysis` finally block in CLI (covers streaming path). `stop_polling()` joins the daemon thread with a 5-second timeout, then returns. On the next run's first `check_enforcement()`, `_ensure_poller_running()` restarts a fresh thread. Module-global cache (`_cached_rules`, `_cache_initialized`) persists between calls — this is correct behavior, not a bug. [VERIFIED: enforcement.py source]

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `revenium_middleware._core.enforcement` | CTL-01 enforcement gate | ✓ | SDK 0.1.9 installed in .venv | — |
| `REVENIUM_METERING_API_KEY` | Enforcement polling auth (enforcement.py uses same key) | ✓ (in .env) | rev_mk_* | REVENIUM_BYPASS=true for tests |
| `REVENIUM_TEAM_ID=DZxzEl` | Enforcement polling URL, budget rule scoping | ✓ (confirmed from config.yaml) | DZxzEl | — |
| `REVENIUM_SK_API_KEY` (rev_sk_*) | Budget rule CREATE/PATCH in setup script | ✓ (in config.yaml) | rev_sk_* | — |
| `REVENIUM_CB_POLL_INTERVAL_SECONDS` | Demo timing reliability | set to 5 in .env before demo | configurable | default 60s (too slow for demo) |
| Revenium dashboard (enforcement events view) | CTL-03 visible event for FCAT audience | ✓ | live | — |
| `rich.Panel`, `rich.Table`, `rich.Text` | Halt panel rendering (CTL-02) | ✓ (already in cli/main.py imports) | >=14.0.0 | — |

**Missing dependencies with no fallback:** None.

**Missing dependencies with fallback:** `REVENIUM_CB_POLL_INTERVAL_SECONDS` — defaults to 60s which is too slow for demo; must be set to 5 in `.env` before demo day.

---

## Security Domain

`security_enforcement: true` (default) per config.json. ASVS Level 1 applies.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | No new auth flows introduced |
| V3 Session Management | No | No session state added |
| V4 Access Control | Yes (partial) | `check_enforcement()` acts as an access control gate: the enforcement API key is the rev_mk_* metering key (least privilege — read-only enforcement polling, not write scope) |
| V5 Input Validation | Yes | `quote(team_id, safe="")` in enforcement.py percent-encodes the team_id URL segment to prevent path traversal (already in SDK, not our code) |
| V6 Cryptography | No | No new crypto; TLS inherited from httpx for enforcement polling |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| API key logged in halt panel | Info Disclosure | `_render_budget_halt_panel()` must NEVER print raw key values — log only rule names, cost values, rule IDs (repo convention: log symbolic names only) |
| `subscriber_credential` printed in logs | Info Disclosure | Treat as sensitive — do not log the value passed to `check_enforcement()`. The subscriber email is PII; send only over TLS to Revenium (already the case) |
| `BudgetExceededError` message contains rule details | Info Disclosure | Acceptable — rule names/costs are not secrets in this demo context; they're the point of the halt message |

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | The management API budget rule POST at `https://api.prod.ai.hcapp.io/profitstream/v2/api/ai/cost-controls` accepts `teamId` in the JSON body (following the product provisioning pattern) | Code Examples §4 | If `teamId` is not accepted in body, the rule may be created without team scoping — verify by checking `budget-rules list` after first live run of setup_revenium.py |
| A2 | Revenium ingestion + breach compilation latency is 5–30 seconds, making the meter→halt latency ~10–45s with POLL_INTERVAL=5 | Common Pitfalls §2 / Timing guidance | If ingestion is slower (>60s), pre-warm strategy becomes more critical; timing dry-run in validate_controls.py will quantify actual latency before demo |
| A3 | `ENFORCEMENT_VIOLATION` (non-shadow) events appear in Guardrails → Enforcement Events dashboard tab immediately or within ~30s of the halt | CTL-03 | Dashboard confirmation required during timing dry-run; if events are delayed, alert FCAT to check "after the halt" rather than "during" |
| A4 | A PATCH endpoint `PATCH /ai/cost-controls/{id}` exists for updating shadowMode (inferred from `budget-rules update` CLI help) | Code Examples §4 | If PATCH is not supported, the idempotency path must DELETE + CREATE; validate with `budget-rules update <id> --dry-run` |

---

## Sources

### Primary (HIGH confidence)
- `revenium_middleware._core.enforcement` (installed .venv, identical to internal SDK) — enforcement engine mechanics, env vars, `check_enforcement()` / `stop_polling()` / `_seed_rules` mock pattern
- `revenium_middleware._core.exceptions` — `BudgetExceededError` fields and inheritance
- `revenium_middleware._core.config` — `Config` class env var constants
- `tests/test_openai/test_enforcement.py` (internal SDK) — authoritative keyless mock pattern
- `tradingagents/revenium/callback.py` — existing fail-open pattern, `on_chat_model_start` seam, `agent_costs` accumulator
- `tradingagents/graph/trading_graph.py` — `_run_graph` try/finally structure, `end_run()` placement
- `scripts/setup_revenium.py` — management API pattern, `_post`/`_get` helpers, idempotency approach
- `cli/main.py` — streaming loop structure, `Live` context, `revenium_handler` access pattern

### Secondary (MEDIUM confidence — live API)
- `revenium guardrails budget-rules create --dry-run` output: confirms `Path: /v2/api/ai/cost-controls`, request body shape
- `revenium guardrails budget-rules list --json` output: confirms existing rule schema, `_links.self.href` path, `shadowMode`/`enabled` fields
- `revenium guardrails enforcement-rules get DZxzEl --json` output: confirms compiled enforcement rule schema (team_id=DZxzEl, rules array, `breached`/`shadowMode`/`filters` fields)
- `revenium guardrails enforcement-events list --json` output: confirms enforcement event format (`operation: ENFORCEMENT_SHADOW_VIOLATION`, `isShadow`, `currentValue`, `threshold`)
- `~/.config/revenium/config.yaml`: confirms `team-id: DZxzEl`, `tenant-id: vMqzJv`, `owner-id: v988pD`
- Local Python execution: confirmed `check_enforcement` + `BudgetExceededError` import without provider patching; `REVENIUM_BYPASS=true` disables enforcement; `_seed_rules` mock pattern raises `BudgetExceededError` correctly

### Tertiary (ASSUMED — see Assumptions Log)
- Budget rule PATCH endpoint exists with same path pattern (A4)
- Revenium ingestion latency is <30s per run (A2)

---

## Metadata

**Confidence breakdown:**
- Enforcement engine wiring: HIGH — source code read, imports verified, mock pattern tested locally
- Budget rule provisioning schema: HIGH — confirmed via CLI dry-run and existing rule inspection
- CLI halt panel placement: HIGH — confirmed by reading the full CLI streaming path in main.py
- Timing guidance: MEDIUM — latency chain is understood but exact Revenium ingestion speed is ASSUMED
- PATCH idempotency for shadowMode: MEDIUM — ASSUMED from CLI help; not tested live

**Research date:** 2026-06-28
**Valid until:** 2026-07-28 (enforcement engine API is stable; Revenium management API schema may evolve)
