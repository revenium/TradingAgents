# Phase 3: Cost Controls - Context

**Gathered:** 2026-06-28
**Status:** Ready for planning

<domain>
## Phase Boundary

Deliver the **control** pillar: a full `propagate()` run **halts mid-analysis** when a Revenium **enforce-mode** cost rule is breached, the halt is surfaced **gracefully in the CLI** with cost context, and the **enforcement event is visible on the Revenium dashboard** during the run.

Requirements: CTL-01, CTL-02, CTL-03, CTL-04 (Mode: mvp). Depends on Phase 1 (metering) + Phase 2 (trace).

**Core decision (this phase):** Phase 3 is **totally reliant on Revenium's built-in circuit breaker** for enforcement. No hand-rolled in-process spend counter or client-side floor. The trading run halts because Revenium's enforcement engine says so.

In scope: wiring the SDK circuit breaker into the existing callback path, provisioning an enforce-mode cost rule, the graceful CLI halt, and demo-timing reliability. Out of scope: CLI cost panel + billing (Phase 4), demo hardening / Slack second-screen polish (Phase 5), any change to trading logic.
</domain>

<decisions>
## Implementation Decisions

### Enforcement architecture
- **D-01: Total reliance on Revenium's circuit breaker — no client-side gate.** Phase 3 uses the SDK's `revenium_middleware._core.enforcement.check_enforcement()` as the **sole** enforcement mechanism. We do NOT build an in-process spend counter or local price map. (User changed direction from an earlier hybrid proposal to full Revenium reliance — cleaner "Revenium enforces this" story for FCAT, least code.)
- **D-02: Integration seam = pre-call hook in `ReveniumCallbackHandler.on_chat_model_start`.** Call `check_enforcement(usage_metadata)` before each LLM call; it raises `BudgetExceededError` when an enforce-mode rule is breached. Reuse ONLY the enforcement engine — do NOT adopt the provider-patch middleware. Confirmed: `check_enforcement` / `BudgetExceededError` are importable from `revenium_middleware._core` in the current `.venv` and importing them does NOT trigger provider patching (no double-counting with the existing Phase 1 callback/metering path).
- **D-03: Deliberate re-raise of `BudgetExceededError`.** The handler's fail-open `except Exception` would swallow it (`BudgetExceededError` subclasses `Exception`), so the gate must explicitly let it propagate. This is the documented **D-06 exception** from Phase 1 ("the Phase 3 cost gate is the deliberate exception that DOES halt"). Everything else in the handler stays fail-open.
- **D-04: Budget unit = whatever the Revenium rule measures server-side.** For the "$ spend" FinOps story this is a **dollar cost-limit rule**. No local AI-cost price map is needed (the earlier client-floor unit question is moot under full reliance).

### CLI halt experience
- **D-05: Rich panel on halt, no fabricated decision.** `propagate()` (and the CLI path) catches `BudgetExceededError` and renders a **Rich panel** built from the exception fields (`rule_name`, `current_value`/`threshold`, `resets_at`, `rule_id`) plus the stage/agent that tripped it, the run `trace_id`, and a per-agent cost breakdown (handler `agent_costs`). **Non-zero exit code.** It does NOT print a BUY/HOLD/SELL — the run halted mid-analysis and fabricating a decision would mislead the audience.

### Rule provisioning & enforce vs shadow
- **D-06: Provision the rule via the committed idempotent setup script.** Extend `scripts/setup_revenium.py` (Phase 1 D-08) to create/verify the cost-limit rule in **enforce mode (`shadowMode: false`)** — version-controlled, re-runnable, rebuildable if the account is reset. The Revenium MCP dev connector may be used ad-hoc, but the script is the source of truth.
- **D-07: CTL-04 (enforce, not shadow) is satisfied directly.** `check_enforcement` skips `shadowMode` rules; the setup script sets `shadowMode: false`; the DMO-02 pre-flight checklist confirms enforce mode before demo day.

### Demo-timing reliability (the CTL-01 tension)
- **D-08: CTL-01 is reinterpreted.** As originally written ("an *in-process* spend counter… in real time, *not dependent on server-side enforcement latency*"), CTL-01 is **contradicted** by full Revenium reliance — the breach is computed server-side and surfaced by polling. Reinterpretation: *"Revenium's circuit breaker gates the run; demo timing is made reliable **operationally**, not via an in-process counter."* **Action: reword CTL-01 in REQUIREMENTS.md** to match this decision (do at phase wrap / planning).
- **D-09: Timing reliability levers (operational, validated by dry-run).** (a) Low poll interval `REVENIUM_CB_POLL_INTERVAL_SECONDS` (~5–10s) so a breach surfaces fast; (b) pre-warm / set the threshold low enough that the rule is already breached early in the run, so the *next* call halts predictably; (c) a stop-watch **dry-run** (the roadmap's timing research flag) to confirm where in the run the halt fires before demo day.

### Configuration
- **D-10: Circuit-breaker config via `.env` env vars** (matches Phase 1 D-09 `.env` pattern): `REVENIUM_CIRCUIT_BREAKER_ENABLED=true`, `REVENIUM_TEAM_ID=<hashed team id>`, `REVENIUM_CB_POLL_INTERVAL_SECONDS`, optional `REVENIUM_CB_FAIL_MODE` (default open). `REVENIUM_BYPASS=true` disables enforcement (keeps the keyless test suite green — DMO-04). The threshold value itself lives in the Revenium rule (provisioned by the setup script), not in `DEFAULT_CONFIG`.

### Claude's Discretion
- Exact module placement of the enforcement call and `usage_metadata` assembly within `tradingagents/revenium/`, the precise Rich panel layout, and where the `BudgetExceededError` catch sits (`_run_graph` vs CLI vs both) — follow research + repo conventions.
- `stop_polling()` lifecycle wiring (stop the enforcement daemon poll thread on graph teardown, mirroring the `end_run` pattern) — implement per research.
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase scope & requirements
- `.planning/PROJECT.md` — core value (meter→trace→control→monetize), constraints, fail-open + no-hardcoded-provider conventions
- `.planning/REQUIREMENTS.md` — CTL-01..04 + DMO-02 (pre-flight checklist) acceptance criteria; **CTL-01 to be reworded per D-08**
- `.planning/ROADMAP.md` — Phase 3 goal, 4 success criteria, planning notes (timing dry-run; `shadow: false` 24h before demo; optional Slack)
- `.planning/STATE.md` — accumulated decisions and validation gates
- `.planning/phases/01-foundation-metering/01-CONTEXT.md` — carry-forward decisions: D-02/03/04 (attribution: org/product/subscriber so nothing lands UNCLASSIFIED), D-05 (auto-on when key present), **D-06 (fail-open EXCEPT the cost gate)**, D-08 (idempotent `setup_revenium.py`), D-09 (`.env` creds)

### Revenium SDK (enforcement engine) — `/Users/johndemic/Development/projects/revenium/revenium-python-sdk-internal`
- `revenium_middleware/_core/enforcement.py` — `check_enforcement(usage_metadata)` pre-call hook; daemon-thread polling of `GET /v2/api/ai/enforcement-rules/{team_id}`; breach detection (`breached`/`blocked`), `shadowMode` skip, `credential` matching; env knobs (`REVENIUM_CIRCUIT_BREAKER_ENABLED`, `REVENIUM_TEAM_ID`, `REVENIUM_CB_POLL_INTERVAL_SECONDS`, `REVENIUM_CB_FAIL_MODE`, `REVENIUM_BYPASS`); `stop_polling()`
- `revenium_middleware/_core/exceptions.py` — `BudgetExceededError(message, rule_name, current_value, threshold, resets_at, rule_id)`; inherits `Exception` directly (won't be swallowed by provider error decorators — and must be deliberately re-raised past the handler's fail-open catch)
- `revenium_middleware/_core/config.py` — enforcement env-var names
- Revenium docs / LLM reference: https://revenium.readme.io/llms.txt

### TradingAgents integration points
- `tradingagents/revenium/callback.py` — `ReveniumCallbackHandler`; `on_chat_model_start` (pre-call seam for `check_enforcement`), the fail-open `except Exception` pattern, `agent_costs` per-agent dict (CLI breakdown)
- `tradingagents/graph/trading_graph.py` — `_run_graph` try/finally (natural `BudgetExceededError` catch + `stop_polling` teardown point)
- `cli/main.py` — Rich UI; where the halt panel renders and the non-zero exit happens
- `scripts/setup_revenium.py` — idempotent provisioning script to extend with the enforce-mode rule
- `scripts/validate_metering.py`, `scripts/validate_tracing.py` — the standalone live-validation-script pattern (a `validate_controls.py` likely mirrors these for the timing dry-run)
</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `revenium_middleware._core.check_enforcement` / `BudgetExceededError` — the entire enforcement mechanism, already installed in `.venv`; no new dependency, no provider patching.
- `ReveniumCallbackHandler.on_chat_model_start` — existing pre-call callback; drop-in seam for the enforcement check.
- `ReveniumCallbackHandler.agent_costs` — per-agent token/cost accumulator already populated; feeds the CLI halt panel's per-agent breakdown.
- `scripts/setup_revenium.py` — idempotent Org→Subscriber→Product→Subscription provisioning; extend for the cost rule.

### Established Patterns
- Fail-open everywhere via `# noqa: BLE001 — fail open, never block the run` — the cost gate is the ONE deliberate exception (re-raise `BudgetExceededError`).
- Auto-on when key present (D-05) + keyless test discipline (DMO-04) — enforcement must be mockable and default-off so the suite stays green without keys (`REVENIUM_BYPASS` / `REVENIUM_CIRCUIT_BREAKER_ENABLED` unset).
- Validation as a standalone re-runnable script (D-07 pattern) — a controls/timing dry-run script fits here.

### Integration Points
- Pre-call: `check_enforcement(usage_metadata)` inside `on_chat_model_start`.
- Catch + render: `BudgetExceededError` caught in `_run_graph` / CLI → Rich halt panel + non-zero exit.
- Teardown: `stop_polling()` on graph completion (mirror `end_run`).
- Provisioning: enforce-mode rule created by `scripts/setup_revenium.py`.
</code_context>

<specifics>
## Specific Ideas

- The on-stage moment: the audience watches the **Revenium dashboard enforcement event fire** during a live run, and the CLI **halts mid-analysis** with a clear cost-context panel — Revenium itself is what stops the run, not local code.
- `usage_metadata` passed to `check_enforcement` must carry the right `subscriber_credential` so the breached rule's `credential` matches the demo subscriber (ties to Phase 1 D-02/D-04 attribution).
</specifics>

<deferred>
## Deferred Ideas

- **Optional Slack notification on the enforcement event** (second screen during demo) — CTL-03 marks it optional; defer to Phase 5 hardening or treat as polish.
- A client-side / in-process spend gate — explicitly rejected for this phase (D-01); could revisit only if dry-runs prove the server-side timing unreliable on stage.

## Open Questions for Research (gsd-phase-researcher)

- **`REVENIUM_TEAM_ID` sourcing** — it's a *hashed* team ID; how to obtain it for the demo account (MCP connector / dashboard / API).
- **Enforcement-rule CREATE path** — `enforcement.py` only POLLs (`GET /v2/api/ai/enforcement-rules/{team_id}`). Find the create/update API (or MCP verb) and the rule schema (name, metric=cost, threshold, `shadowMode`, credential/subscriber scoping, reset window/`resetsAt`) so `setup_revenium.py` can provision it idempotently.
- **`subscriber_credential` matching** — confirm exactly what value `check_enforcement` reads from `usage_metadata` and how the handler must populate it so the rule applies to the demo subscriber.
- **No double-counting / no patching on import** — validate (keyless test) that importing the enforcement engine never activates provider middleware or emits duplicate meter events.
- **Timing dry-run** — measure meter→ingest→breach→poll latency end-to-end; tune `REVENIUM_CB_POLL_INTERVAL_SECONDS` + threshold + pre-warm so the halt reliably lands mid-debate (the roadmap stop-watch flag).
- **Keyless testability** — how to mock the enforcement cache / `_fetch_rules` so CTL tests pass without live keys (DMO-04).
- **`stop_polling()` lifecycle** — where to call it so the daemon poll thread shuts down cleanly per run.
</deferred>

---

*Phase: 03-cost-controls*
*Context gathered: 2026-06-28*
