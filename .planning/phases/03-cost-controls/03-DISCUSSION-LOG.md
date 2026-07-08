# Phase 3: Cost Controls - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-28
**Phase:** 03-cost-controls
**Areas discussed:** Enforcement architecture, Budget unit, CLI halt UX, Threshold/rule provisioning, Demo-timing reliability

---

## Pivot: does the Revenium middleware already enforce?

User asked whether Revenium's Python middleware enforces the halt automatically, pointing at the internal SDK repo (`revenium-python-sdk-internal`). Investigation confirmed it does: `revenium_middleware/_core/enforcement.py` ships a circuit breaker — `check_enforcement(usage_metadata)` is a pre-call hook that raises `BudgetExceededError` when a polled, server-side enforce-mode rule is breached (skips `shadowMode`). Confirmed importable in `.venv` without triggering provider patching (no double-counting with the Phase 1 callback path). This reframed the whole phase away from hand-rolling a counter.

## Enforcement architecture

| Option | Description | Selected |
|--------|-------------|----------|
| Hybrid: circuit breaker + thin client floor | Authentic Revenium rule + deterministic client backstop (same BudgetExceededError) | (first chosen, then reversed) |
| SDK circuit breaker only | Wire `check_enforcement()` + enforce-mode rule; tune poll interval. Least code, fully authentic; server-side timing | ✓ |
| Client-side $ gate only | Reinvents enforcement; decouples dashboard event | |

**User's choice:** Initially picked **Hybrid**, then changed their mind to **be totally reliant on Revenium for the circuit breaking** (SDK circuit breaker only).
**Notes:** Cleaner "Revenium enforces this" story for FCAT and the least code. Accepted the trade-off that CTL-01's original "in-process, not server-dependent" wording no longer holds — to be reworded; timing handled operationally.

## Budget unit

**Resolved by the architecture choice.** Under full reliance, the unit is whatever the Revenium rule measures server-side (a dollar cost-limit rule for the "$ spend" story). No local price map. The earlier "client floor unit" question became moot.

## CLI halt UX

| Option | Description | Selected |
|--------|-------------|----------|
| Rich panel with cost context, no fabricated decision | Panel from BudgetExceededError fields + stage/agent, trace_id, per-agent breakdown; non-zero exit; no BUY/HOLD/SELL | ✓ |
| Minimal one-line error | Single line + exit 1 | |
| Halt but emit partial results | Risks implying a usable signal | |

**User's choice:** Rich panel, no fabricated decision.
**Notes:** Confirmed alongside rule provisioning ("they work for me").

## Threshold / rule provisioning

| Option | Description | Selected |
|--------|-------------|----------|
| Extend committed `scripts/setup_revenium.py` to create the enforce-mode rule (`shadowMode: false`) | Version-controlled, idempotent, rebuildable; MCP ad-hoc only | ✓ |
| Hand-click the rule in the dashboard | Not reproducible | |

**User's choice:** Provision via the committed setup script (extends Phase 1 D-08).

## Demo-timing reliability

**Decision (Claude-proposed, user-accepted):** Reliability is operational, not an in-process counter — low `REVENIUM_CB_POLL_INTERVAL_SECONDS`, pre-warmed/low threshold so the next call halts predictably, and a stop-watch dry-run to confirm where the halt fires. CTL-01 reworded in REQUIREMENTS.md to match.

## Claude's Discretion

- Exact `usage_metadata` assembly and module placement of the enforcement call within `tradingagents/revenium/`.
- Precise Rich panel layout and where `BudgetExceededError` is caught (`_run_graph` vs CLI vs both).
- `stop_polling()` teardown wiring.

## Deferred Ideas

- Optional Slack notification on the enforcement event (second screen) — CTL-03 optional; defer to Phase 5 hardening.
- A client-side / in-process spend gate — explicitly rejected (D-01); revisit only if dry-runs prove server-side timing unreliable on stage.
