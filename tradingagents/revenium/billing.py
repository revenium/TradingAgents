"""Phase 4 stub — per-run billing signal emitter for Revenium.

This module will house ``ReveniumBillingEmitter`` once the monetize pillar
is implemented in Phase 4 (D-03: $2.00/signal unit pricing on the
``trading-signal`` product).  It exists as a stub now so Phase 4 can add
the implementation and the call site in ``_run_graph`` without any topology
changes to the graph or its imports.

Design rationale:
- ``emit_signal_unit`` is called at the same point in ``_run_graph`` as
  ``memory_log.store_decision`` — after a successful graph run, before
  returning.  The call will be wrapped in fail-open try/except at the call
  site (D-06) so a billing failure never aborts a run.
- The emitter is constructed once in ``TradingAgentsGraph.__init__`` and
  stored as ``self._billing_emitter``; it receives the trace_id and total
  per-run cost from the callback handler's ``run_total_tokens`` accumulator
  when Phase 4 wires the cost model.

Phase 4 scope (out of scope this phase):
- Configure per-signal pricing on the ``trading-signal`` product in Revenium.
- Implement ``emit_signal_unit`` to call the Revenium billing / outcome API.
- Add the call to ``_run_graph`` after the ``store_decision`` call.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class ReveniumBillingEmitter:
    """Phase 4 stub — emits a per-signal billing unit to Revenium at run end.

    All methods are no-ops in this phase.  Phase 4 will fill in
    ``emit_signal_unit`` with the actual billing API call.
    """

    def emit_signal_unit(
        self,
        trace_id: str,
        total_cost_usd: float,
        **kwargs: object,
    ) -> None:
        """Emit one billing signal unit for a completed trading analysis run.

        STUB — no-op in Phase 1; Phase 4 will implement this.

        Args:
            trace_id:       The run's Revenium trace_id UUID.
            total_cost_usd: Estimated total LLM cost in USD for the run.
            **kwargs:       Reserved for future fields (e.g. signal rating).
        """
        # Phase 4: call the Revenium AgenticOutcomeClient or billing API here.
        pass  # noqa: PIE790 — intentional stub; Phase 4 fills this in
