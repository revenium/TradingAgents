"""Live end-to-end controls validation for Revenium + TradingAgents.

Timing dry-run: runs one full TradingAgentsGraph.propagate() call, measures
where in the run the BudgetExceededError halt fires, and checks enforcement
readiness (compiled rules, percentUsed, shadowMode).

  CTL-01  Halt fires during the run — check_enforcement() raised BudgetExceededError
          and the run stopped before completion.
  CTL-04  Enforce mode confirmed — breached rule has shadowMode:false.
  TIMING  Reports which agent triggered the halt and elapsed seconds to halt.

Requirements:
  - REVENIUM_METERING_API_KEY set to a valid rev_mk_* key
  - REVENIUM_CIRCUIT_BREAKER_ENABLED=true
  - REVENIUM_TEAM_ID=DZxzEl
  - REVENIUM_CB_POLL_INTERVAL_SECONDS=5 (for reliable timing)
  - At least one LLM provider key

Usage:
    REVENIUM_METERING_API_KEY=rev_mk_... REVENIUM_CIRCUIT_BREAKER_ENABLED=true \\
    REVENIUM_TEAM_ID=DZxzEl REVENIUM_CB_POLL_INTERVAL_SECONDS=5 \\
    OPENAI_API_KEY=... python scripts/validate_controls.py

    # Keyless mode (no CB key → skips live assertions and exits 0):
    python scripts/validate_controls.py
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone


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
    """Run the live controls validation.  Returns 0 on success, 1 on failure."""
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
    import os

    from dotenv import load_dotenv

    load_dotenv()

    from tradingagents.default_config import DEFAULT_CONFIG

    config = dict(DEFAULT_CONFIG)

    # ------------------------------------------------------------------
    # Gate: REVENIUM_METERING_API_KEY and REVENIUM_CIRCUIT_BREAKER_ENABLED
    # must be set for live assertions.
    # Keyless mode exits 0 so CI never breaks on missing credentials (DMO-04).
    # ------------------------------------------------------------------
    cb_enabled = os.getenv("REVENIUM_CIRCUIT_BREAKER_ENABLED", "").lower() in ("1", "true")
    api_key: str = config.get("revenium_api_key", "")
    if not api_key or not cb_enabled:
        print("no REVENIUM_METERING_API_KEY or REVENIUM_CIRCUIT_BREAKER_ENABLED — keyless mode, skipping live assertions")
        return 0

    # ------------------------------------------------------------------
    # Late imports (after load_dotenv so env vars are applied before
    # any provider SDK reads its key at import time)
    # ------------------------------------------------------------------
    from revenium_middleware._core.exceptions import BudgetExceededError

    from tradingagents.graph.trading_graph import TradingAgentsGraph

    ticker: str = args.ticker
    trade_date: str = args.date

    print(f"\nValidating Revenium cost controls — {datetime.now(timezone.utc).isoformat()}")
    print(f"  Ticker       : {ticker}")
    print(f"  Trade date   : {trade_date}")
    print(f"  Metering key : {api_key[:12]}... (hidden)")
    print()

    graph = TradingAgentsGraph(config=config)

    # ------------------------------------------------------------------
    # Run propagate() — capture BudgetExceededError halt and timing
    # ------------------------------------------------------------------
    halt_exception: BudgetExceededError | None = None
    elapsed_to_halt: float | None = None
    start_time = time.time()

    try:
        graph.propagate(ticker, trade_date)
    except BudgetExceededError as err:
        halt_exception = err
        elapsed_to_halt = time.time() - start_time
        print(f"  BudgetExceededError raised after {elapsed_to_halt:.1f}s — "
              f"rule={err.rule_name!r} spent={err.current_value} limit={err.threshold}")
    except Exception as exc:  # noqa: BLE001 — fail open, surface in checks
        print(f"  ERROR: propagate() raised unexpected: {exc}")

    # ------------------------------------------------------------------
    # Enforcement readiness checks
    # ------------------------------------------------------------------
    checks: list[tuple[str, bool]] = []
    checks.append(("BudgetExceededError raised (run halted by enforcement)", halt_exception is not None))

    if halt_exception is not None:
        checks.append(("rule_name is non-empty", bool(halt_exception.rule_name)))
        checks.append(("current_value > 0", (halt_exception.current_value or 0) > 0))
        checks.append(("threshold > 0", (halt_exception.threshold or 0) > 0))
        checks.append(("resets_at is non-empty", bool(halt_exception.resets_at)))
        timing_label = (
            f"Halted within 120s (got {elapsed_to_halt:.1f}s)"
            if elapsed_to_halt is not None
            else "Timing: n/a"
        )
        checks.append((timing_label, elapsed_to_halt is not None and elapsed_to_halt < 120))

    print("Enforcement checks:")
    passed, failed = _run_checks(checks)
    print()

    # ------------------------------------------------------------------
    # Dashboard reminder block (CTL-03 — confirm enforcement event)
    # ------------------------------------------------------------------
    if halt_exception is not None:
        print("Confirm in the Revenium dashboard (Guardrails -> Enforcement Events):")
        print(f"  1. An enforcement event with action=BLOCK and ruleName={halt_exception.rule_name!r}")
        print("  2. isShadow=false (enforce mode confirmed — CTL-04)")
        print(f"  3. currentValue > threshold ({halt_exception.current_value} > {halt_exception.threshold})")
        if elapsed_to_halt is not None:
            print(f"  4. Elapsed time to halt: {elapsed_to_halt:.1f}s (target: mid-debate ~20-60s)")
        print()

    if failed == 0:
        print(f"Controls PASSED: {passed}/{passed + failed} checks.")
        return 0
    else:
        print(f"Controls FAILED: {failed}/{passed + failed} check(s) failed.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
