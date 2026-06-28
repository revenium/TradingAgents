"""Run-scoped context variable machinery for Revenium tracing.

Exposes four module-level ContextVars that carry identity across every
agent node for the duration of a single propagate() call:

  - current_trace_id:                unique UUID per run, links every agent LLM call
  - current_agent_name:              the LangGraph node name set at each agent's entry
  - current_run_meta:                {ticker, trade_date, ...} from the propagate() call
  - current_parent_transaction_id:   transaction_id of the most recently completed LLM call

Design rationale:
- contextvars are chosen over global state because propagate() runs
  synchronously inside a single thread context and ContextVar.set() tokens
  are safe for nested and re-entrant call sites (e.g., reflection running
  after the main graph).  Unlike threading.local, contextvars propagate
  correctly when code is executed in executors or sub-threads that copy the
  current context.
- revenium_run_context() is the sole writer of trace_id and run_meta;
  individual agent nodes write current_agent_name at their own entry points
  (Plan 03 adds those one-liners).
- On context exit both tokens are reset via ContextVar.reset(), even when
  an exception propagates, so state never bleeds between consecutive
  propagate() calls in a long-lived process.

Key invariants:
- current_agent_name defaults to "unknown" so a missing set() call does not
  crash the callback handler or produce UNCLASSIFIED attribution gaps (D-04).
- current_trace_id defaults to "" (the disabled / outside-of-run state);
  the callback handler skips the trace_id API field when it is empty.
- current_run_meta defaults to {} (empty dict); the default object is never
  mutated because the context manager always sets a new dict on entry.
"""

from __future__ import annotations

import contextvars
import logging
import uuid
from contextlib import contextmanager
from typing import Any, Generator

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level context variables
# ---------------------------------------------------------------------------

current_trace_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "revenium_trace_id",
    default="",
)
"""One UUID4 string per propagate() call, linking all agent LLM calls in a run."""

current_agent_name: contextvars.ContextVar[str] = contextvars.ContextVar(
    "revenium_agent_name",
    default="unknown",
)
"""The LangGraph node name of the currently-executing agent (set by each node)."""

current_run_meta: contextvars.ContextVar[dict] = contextvars.ContextVar(
    "revenium_run_meta",
    default={},
)
"""Dict carrying {ticker, trade_date, ...extra} for the current propagate() run."""

current_parent_transaction_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "revenium_parent_transaction_id",
    default="",
)
"""transaction_id of the most recently completed LLM call; "" at run start."""


# ---------------------------------------------------------------------------
# Context manager
# ---------------------------------------------------------------------------

@contextmanager
def revenium_run_context(
    ticker: str,
    trade_date: str,
    **meta: Any,
) -> Generator[str, None, None]:
    """Set run-scoped Revenium context for the duration of one propagate() call.

    Generates a unique trace_id UUID and makes it (plus the run metadata)
    available to every LangChain callback that fires during the run via
    module-level ContextVars.  Both vars are reset to their defaults in the
    ``finally`` block so state never leaks across consecutive runs.

    Args:
        ticker:     Ticker symbol being analysed (e.g. "NVDA").
        trade_date: ISO date string for the analysis date (e.g. "2026-06-27").
        **meta:     Additional metadata forwarded into current_run_meta.

    Yields:
        The trace_id UUID string set for this run.

    Example::

        with revenium_run_context("NVDA", "2026-06-27") as trace_id:
            result = graph.invoke(state)
    """
    trace_id = str(uuid.uuid4())
    token_trace = current_trace_id.set(trace_id)
    token_meta = current_run_meta.set(
        {"ticker": ticker, "trade_date": str(trade_date), **meta}
    )
    token_parent = current_parent_transaction_id.set("")
    logger.debug("revenium_run_context enter: ticker=%r trace_id=%r", ticker, trace_id)
    try:
        yield trace_id
    finally:
        current_trace_id.reset(token_trace)
        current_run_meta.reset(token_meta)
        current_parent_transaction_id.reset(token_parent)
        logger.debug("revenium_run_context exit: trace_id=%r", trace_id)
