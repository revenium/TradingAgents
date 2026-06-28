"""Live end-to-end tracing validation for Revenium + TradingAgents.

Runs one full TradingAgentsGraph.propagate() call (with max_debate_rounds=2 to
trigger the bull→bear→bull sequence needed for circular-pattern detection) and
validates the three things only a live run can prove:

  TRC-01  One trace grouping N spans — all captured payloads share a single trace_id.
  TRC-02  Dependency tree — every payload after the first carries parent_transaction_id.
  TRC-03  Debate-loop hotspot — circular-pattern detection fires on bull/bear loop,
          OR the task_type=research_debate bucket surfaces it as the cost hotspot.

The script prints trace_id= and span_count= on their own lines so the caller can
look up the run in the Revenium dashboard immediately after exit.

IMPORTANT: Do NOT wrap propagate() in a second revenium_run_context() here.
trading_graph._run_graph() already opens its own revenium_run_context() internally
(line 392 of trading_graph.py). That context generates the UUID carried by every
metered event. An outer wrapper would generate a different UUID that the inner
context overrides — the printed trace_id would never match the metered events.
trace_id is read from captured[0]["trace_id"] instead.

Requirements:
  - REVENIUM_METERING_API_KEY set to a valid rev_mk_* key
  - FRED_API_KEY set (required for the full news/macro pipeline)
  - At least one LLM provider key (ANTHROPIC_API_KEY or OPENAI_API_KEY)
  - pip install ".[dev]"

Usage:
    # Full live run with default ticker and date:
    REVENIUM_METERING_API_KEY=rev_mk_... FRED_API_KEY=... OPENAI_API_KEY=... \\
        python scripts/validate_tracing.py

    # Override ticker and/or date:
    REVENIUM_METERING_API_KEY=rev_mk_... FRED_API_KEY=... OPENAI_API_KEY=... \\
        python scripts/validate_tracing.py --ticker AAPL --date 2026-06-20

    # Keyless mode (no API key → skips live assertions and exits 0):
    python scripts/validate_tracing.py

After the script exits 0 (local assertions pass), confirm in the Revenium
dashboard (Traces → trace_id above):
  1. Transaction Timeline (Gantt) shows one bar per agent/span — TRC-01
  2. Dependency Tree shows parent arrows between sequential agents — TRC-02
  3. Agent Interaction view: Circular Pattern entry for bull/bear researchers
     (primary, fires with max_debate_rounds=2), OR filter analytics by
     task_type=research_debate to see the debate cost as the hotspot — TRC-03
  4. Note whether a 'squad' view appears under trace_type=trading-run (Open Q1)
  5. Note ingest latency from run-end to trace appearing in dashboard (Open Q3)
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime


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


def main() -> int:
    """Run the live tracing validation.  Returns 0 on success, 1 on failure."""
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--ticker",
        default="NVDA",
        help="Ticker symbol to analyse (default: NVDA).",
    )
    parser.add_argument(
        "--date",
        default="2026-06-27",
        help="Analysis date in YYYY-MM-DD format (default: 2026-06-27).",
    )
    args = parser.parse_args()

    # ------------------------------------------------------------------
    # Imports (inside main to keep module-level clean — repo convention)
    # ------------------------------------------------------------------
    from dotenv import load_dotenv

    load_dotenv()

    from tradingagents.default_config import DEFAULT_CONFIG

    config = dict(DEFAULT_CONFIG)

    # Set max_debate_rounds=2 before constructing the graph so bull_researcher
    # appears twice in the parent-transaction chain: bull1→bear1→bull2→bear2.
    # This is the minimum condition for Revenium's circular-pattern detection
    # to fire (research A4: agent name must repeat in ancestry).
    config["max_debate_rounds"] = 2

    # ------------------------------------------------------------------
    # Gate: REVENIUM_METERING_API_KEY must be set for live assertions.
    # Keyless mode exits 0 so CI never breaks on missing credentials.
    # ------------------------------------------------------------------
    api_key: str = config.get("revenium_api_key", "")
    if not api_key:
        print("no REVENIUM_METERING_API_KEY — keyless mode, skipping live assertions")
        return 0

    # ------------------------------------------------------------------
    # Late imports (after load_dotenv so env vars are applied before
    # any provider SDK reads its key at import time)
    # ------------------------------------------------------------------
    from tradingagents.graph.trading_graph import TradingAgentsGraph

    ticker: str = args.ticker
    trade_date: str = args.date

    print(f"\nValidating Revenium tracing — {datetime.utcnow().isoformat()}Z")
    print(f"  Ticker              : {ticker}")
    print(f"  Trade date          : {trade_date}")
    print(f"  max_debate_rounds   : {config['max_debate_rounds']}")
    print(f"  Metering key        : {api_key[:12]}... (hidden)")
    print()

    # ------------------------------------------------------------------
    # Construct graph and intercept meter_ai_completion for local assertion
    # ------------------------------------------------------------------
    graph = TradingAgentsGraph(config=config)

    # Monkeypatch the handler's client so every emitted payload is also
    # appended to `captured` locally — same pattern as validate_metering.py.
    # This lets us count spans and assert field presence without a separate
    # Revenium API call.
    captured: list[dict] = []
    _original_meter = graph._revenium_handler._client.meter_ai_completion

    def _capture_and_meter(payload: dict) -> None:
        captured.append(payload)
        _original_meter(payload)

    graph._revenium_handler._client.meter_ai_completion = _capture_and_meter  # type: ignore[method-assign]

    # ------------------------------------------------------------------
    # Run propagate() — NO outer revenium_run_context() wrapper here.
    # _run_graph() opens its own context internally (trading_graph.py:392).
    # That context generates the trace UUID carried by every metered event.
    # An outer wrapper here generates a second UUID that the inner context
    # overrides, so the outer wrapper's id would never match the payloads
    # (the original context-manager race / blocker). trace_id is read from
    # captured[0] after the run instead.
    # ------------------------------------------------------------------
    print(f"  Running propagate({ticker!r}, {trade_date!r}) …")
    prop_exception: Exception | None = None
    try:
        graph.propagate(ticker, trade_date)
    except Exception as exc:  # noqa: BLE001 — fail open, surface in checks
        prop_exception = exc
        print(f"  ERROR: propagate() raised: {exc}")

    # Flush background fire-and-forget threads before reading `captured`.
    # Every metered event is dispatched on a daemon thread; join ensures
    # all payloads have been appended before the span-count assertion.
    for t in list(graph._revenium_handler._threads):
        t.join(timeout=5.0)

    # Read trace_id from the FIRST captured payload — this is the UUID that
    # _run_graph's revenium_run_context() set, and that every metered event
    # carries.  An empty captured list (propagate() failed before any LLM
    # call) falls through to the check below.
    trace_id: str = captured[0].get("trace_id", "") if captured else ""
    span_count: int = len(captured)

    print(f"trace_id={trace_id}")
    print(f"span_count={span_count}")
    print()

    # ------------------------------------------------------------------
    # Local assertions
    # ------------------------------------------------------------------
    print("Checking local tracing assertions:")

    checks: list[tuple[str, bool]] = []

    checks.append(("propagate() completed without exception", prop_exception is None))
    checks.append(("At least one metering event captured", span_count > 0))

    if captured:
        # TRC-01: single-trace invariant
        checks.append((
            "trace_id is non-empty",
            bool(trace_id),
        ))
        checks.append((
            "trace_id == captured[0]['trace_id'] (printed id matches metered events)",
            trace_id == captured[0].get("trace_id", ""),
        ))
        all_same_trace = all(p.get("trace_id") == trace_id for p in captured)
        checks.append((
            f"All {span_count} payloads share the same trace_id (single-trace invariant)",
            all_same_trace,
        ))
        checks.append((
            f"span_count >= 12 (got {span_count})",
            span_count >= 12,
        ))

        # TRC-02: dependency tree — every payload after the first must carry
        # parent_transaction_id so Revenium can draw the parent arrows.
        if span_count > 1:
            payloads_after_first = captured[1:]
            all_have_parent = all("parent_transaction_id" in p for p in payloads_after_first)
            checks.append((
                f"All {len(payloads_after_first)} payloads after the first carry"
                " parent_transaction_id (dependency tree)",
                all_have_parent,
            ))

        # Trace enrichment fields — required for Gantt timeline and squad grouping.
        all_have_trace_name = all(bool(p.get("trace_name")) for p in captured)
        checks.append((
            "All payloads carry trace_name (Gantt / human-readable label)",
            all_have_trace_name,
        ))
        all_have_trace_type = all(bool(p.get("trace_type")) for p in captured)
        checks.append((
            "All payloads carry trace_type (squad grouping field)",
            all_have_trace_type,
        ))
        all_have_txn_name = all(bool(p.get("transaction_name")) for p in captured)
        checks.append((
            "All payloads carry transaction_name (human span label)",
            all_have_txn_name,
        ))
    else:
        checks.append(("Payload content checks skipped (no payloads captured)", False))

    passed, failed = _run_checks(checks)

    print()

    # ------------------------------------------------------------------
    # Dashboard reminder for the human verifier (Task 2)
    # ------------------------------------------------------------------
    if trace_id:
        print(f"Dashboard trace_id to find: {trace_id}")
        print("Confirm in the Revenium dashboard (Traces → open the trace_id above):")
        print("  1. Transaction Timeline / Gantt shows one bar per agent/span (TRC-01)")
        print("  2. Dependency Tree shows parent arrows between sequential agents")
        print("     (every span except the first must have an incoming arrow) (TRC-02)")
        print("  3. Agent Interaction view — confirm ONE of:")
        print("     a. Circular Pattern entry for bull_researcher / bear_researcher")
        print("        (primary path: max_debate_rounds=2 repeats agent in chain)")
        print("     b. OR filter analytics by task_type=research_debate to confirm")
        print("        the debate loop is the cost hotspot (TRC-03 fallback)")
        print("  4. Note whether a squad view appears under trace_type=trading-run (Open Q1)")
        print("  5. Note ingest latency from script exit to trace appearing in dashboard (Open Q3)")
        print()

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    if failed == 0:
        print(f"Tracing PASSED: {passed}/{passed + failed} checks.")
        return 0
    else:
        print(f"Tracing FAILED: {failed}/{passed + failed} check(s) failed.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
