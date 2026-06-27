"""Revenium instrumentation package for TradingAgents.

This package provides the metering, tracing, and cost-control integration
between the TradingAgents multi-agent graph and the Revenium FinOps platform.

Design rationale:
- Imports are kept lazy/minimal here so that the package can be imported
  (e.g. in tests) without requiring a live Revenium account or API key.
- The callback handler (Plan 02) will be re-exported from this __init__ once
  implemented; for now only config utilities are surfaced.
- All outbound Revenium HTTP calls are fail-open: a Revenium error never
  blocks or fails a trading analysis run.

Key invariants:
- REVENIUM_METERING_API_KEY absent => silent no-op (D-05); tests pass without a key.
- Key material is never logged; only symbolic org/product/subscriber names appear in logs.
- Attribution hierarchy (D-01..D-03) is the source of truth; do not duplicate literals.

Module plan:
  __init__.py   — re-export surface (this file)
  config.py     — attribution helpers and config key constants (Plan 01)
  callback.py   — ReveniumCallbackHandler extending BaseCallbackHandler (Plan 02)
  context.py    — ContextVar helpers for trace_id / agent_name (Plan 02)
  client.py     — thin wrapper around revenium-metering HTTP client (Plan 02)
  cost_gate.py  — hard-spend-limit enforcement (Plan 03)
  billing.py    — end-of-run billing signal emit stub (Plan 04)
"""

from __future__ import annotations

__all__: list[str] = []
