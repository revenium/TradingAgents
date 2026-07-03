"""Live end-to-end Jentic tool metering validation for Revenium + TradingAgents.

Verifies the full JEN-04 pipeline:

  JEN-LIST  ``list_apis()`` succeeds and shows a credentialed news API
  JEN-EXEC  ``get_jentic_news`` returns real content (not NO_DATA_AVAILABLE)
  JEN-METER ``@meter_tool`` fired exactly one tool event with toolId=jentic:news

Prints PASS/FAIL per check and exits 0 on all-PASS, 1 on any FAIL.

Keyless mode:
  When JENTIC_AGENT_API_KEY is absent the script prints a skip message and
  exits 0 so CI never breaks on missing credentials (DMO-04 / JEN-03 discipline).

Prerequisites (live mode):
  - JENTIC_AGENT_API_KEY set (from https://app.jentic.com/dashboard)
  - A news API credentialed in the Jentic dashboard (e.g. newsapi.org/main) so
    op_ba86fdce1bade1b7 (NewsAPI getEverything) can execute (L7 gate)
  - JENTIC_TOOL_ENABLED=true in .env or environment (or pass it on the command line)

Usage:
    # Keyless (CI-safe — exits 0):
    python scripts/validate_jentic.py

    # Live (requires credentialed newsapi.org in Jentic):
    JENTIC_AGENT_API_KEY=... JENTIC_TOOL_ENABLED=true \\
        python scripts/validate_jentic.py

    # Custom query:
    JENTIC_AGENT_API_KEY=... JENTIC_TOOL_ENABLED=true \\
        python scripts/validate_jentic.py --query "NVDA latest earnings news"

    # Pin op-id to skip search step (faster, more reliable for demo):
    JENTIC_AGENT_API_KEY=... JENTIC_TOOL_ENABLED=true \\
        python scripts/validate_jentic.py --op-id op_ba86fdce1bade1b7

Security:
  - JENTIC_AGENT_API_KEY and REVENIUM_SK_API_KEY are never printed (T-06-01).
  - Keys are read from config / env only; log output uses symbolic names.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# sys.path setup — allow running from scripts/ or repo root without install
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


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
    """Run the live Jentic tool metering validation.  Returns 0 on success or keyless skip."""
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--query",
        default="NVDA latest earnings news",
        help="News search query for the execute() call (default: 'NVDA latest earnings news').",
    )
    parser.add_argument(
        "--op-id",
        default=None,
        dest="op_id",
        help=(
            "Pin a Jentic operation UUID, overriding the jentic_op_id config key. "
            "Default op is op_ba86fdce1bade1b7 (NewsAPI getEverything, pinned in config)."
        ),
    )
    args = parser.parse_args()

    # ------------------------------------------------------------------
    # Imports (inside main to keep module-level clean — repo convention)
    # ------------------------------------------------------------------
    from dotenv import load_dotenv

    load_dotenv()

    from tradingagents.dataflows.config import get_config, set_config
    from tradingagents.default_config import DEFAULT_CONFIG

    config = dict(DEFAULT_CONFIG)

    # ------------------------------------------------------------------
    # Gate: JENTIC_AGENT_API_KEY must be set for live assertions.
    # Keyless mode exits 0 so CI never breaks on missing credentials (DMO-04).
    # ------------------------------------------------------------------
    api_key: str = config.get("jentic_agent_api_key", "")
    if not api_key:
        print("no JENTIC_AGENT_API_KEY — keyless mode, skipping live assertions")
        print("  Set JENTIC_AGENT_API_KEY in .env and credential a news API in the")
        print("  Jentic dashboard (https://app.jentic.com) to run live mode.")
        print("  Also set JENTIC_TOOL_ENABLED=true before running.")
        return 0

    # Apply CLI op-id override before merging into process config
    if args.op_id:
        config["jentic_op_id"] = args.op_id

    # Force-enable the tool for this validation run (operator may not have it in .env)
    config["jentic_tool_enabled"] = True
    set_config(config)
    config = get_config()

    tool_id: str = config.get("jentic_tool_id", "jentic:news")
    op_id_cfg: str = config.get("jentic_op_id", "")

    print(f"\nValidating Jentic tool metering — {datetime.now(timezone.utc).isoformat()}")
    print(f"  Query         : {args.query!r}")
    print(f"  Op ID         : {op_id_cfg or '(discovery mode — will search)'}")
    print(f"  Tool ID       : {tool_id}")
    print("  Jentic key    : (set, hidden)")
    print()

    # ------------------------------------------------------------------
    # PREFLIGHT (JEN-LIST): list_apis() must show a credentialed news API.
    # Gate: if no news API is credentialed, exit 1 with a clear message (L7).
    # ------------------------------------------------------------------
    list_ok = False
    news_api_found = False
    list_exc: Exception | None = None
    credentialed_apis: list[str] = []

    print("Preflight: checking Jentic API credentials (list_apis)...")
    try:
        from jentic import Jentic  # noqa: PLC0415
        from jentic.lib.cfg import AgentConfig  # noqa: PLC0415

        # Ensure the env var is set before AgentConfig.from_env() (mirrors _do_jentic_news)
        os.environ["JENTIC_AGENT_API_KEY"] = api_key
        jentic_client = Jentic(AgentConfig.from_env())

        async def _list_apis() -> list[str]:
            """Call jentic.list_apis() or fall back to a credentials-filtered search."""
            try:
                # list_apis() is an async method on the Jentic client instance
                resp = await jentic_client.list_apis()
                if isinstance(resp, list):
                    return [str(a) for a in resp]
                if hasattr(resp, "apis"):
                    return [str(a) for a in resp.apis]
                return [str(resp)]
            except (AttributeError, TypeError):
                # Fallback: use search with filter_by_credentials=True
                from jentic.lib.models import SearchRequest  # noqa: PLC0415

                s = await jentic_client.search(
                    SearchRequest(query="", limit=30, filter_by_credentials=True)
                )
                seen: set[str] = set()
                names: list[str] = []
                for r in (s.results or []):
                    name = str(getattr(r, "api_name", r))
                    if name not in seen:
                        seen.add(name)
                        names.append(name)
                return names

        credentialed_apis = asyncio.run(_list_apis())
        print(f"  Credentialed APIs: {credentialed_apis}")

        # A news API is credentialed when one of the API names contains a news keyword
        _news_keywords = ("news", "newsapi", "alphanews", "gnews", "headline")
        news_api_found = any(
            any(kw in str(api).lower() for kw in _news_keywords)
            for api in credentialed_apis
        )
        list_ok = True

    except Exception as exc:  # noqa: BLE001
        list_exc = exc
        print(f"  ERROR: list_apis() failed: {type(exc).__name__}: {exc}")

    # Hard gate: cannot proceed without a credentialed news API (L7)
    if list_ok and not news_api_found:
        print()
        print("  FAIL: No news API found in Jentic credentials.")
        print(f"        Credentialed: {credentialed_apis}")
        print()
        print("  Action required before live verify:")
        print("    1. Go to https://app.jentic.com/dashboard -> APIs")
        print("    2. Credential newsapi.org/main (or another news source)")
        print("    3. Re-run this script")
        print()
        print("  op_ba86fdce1bade1b7 (NewsAPI getEverything) cannot execute without")
        print("  a credentialed news API in your Jentic account (L7 gate).")
        return 1

    # ------------------------------------------------------------------
    # INPUTS SCHEMA (Open Question 2): print op inputs for operator confirmation
    # ------------------------------------------------------------------
    inputs_schema: dict | None = None
    if list_ok and news_api_found and op_id_cfg:
        print()
        print(f"Discovering op inputs schema via load step (op={op_id_cfg})...")
        try:
            from jentic.lib.models import LoadRequest  # noqa: PLC0415

            async def _load() -> object:
                return await jentic_client.load(LoadRequest(ids=[op_id_cfg]))

            load_resp = asyncio.run(_load())
            tool_info = None
            if load_resp and hasattr(load_resp, "tool_info") and load_resp.tool_info:
                tool_info = load_resp.tool_info.get(op_id_cfg)
            if tool_info and hasattr(tool_info, "inputs") and tool_info.inputs:
                inputs_schema = tool_info.inputs
                print(f"  Inputs schema (op={op_id_cfg}):")
                print(f"  {json.dumps(inputs_schema, indent=4)}")
            else:
                print(f"  (inputs schema not available for op={op_id_cfg})")
                print("  Using known param: q=<query> (NewsAPI getEverything, CONTEXT LIVE TARGET)")
        except Exception as exc:  # noqa: BLE001
            print(f"  WARNING: load step error: {type(exc).__name__}: {exc}")
            print("  Continuing — inputs are known (q=<query> for getEverything).")
    elif list_ok and news_api_found and not op_id_cfg:
        print()
        print("  Op ID not pinned — skipping load step (search will discover it at execute time).")

    # ------------------------------------------------------------------
    # JEN-EXEC: call get_jentic_news.func(query) — a REAL execute()
    # Capture the @meter_tool _send_tool_event call locally for JEN-METER check.
    # ------------------------------------------------------------------
    exec_ok = False
    exec_result: str = ""
    exec_exc: Exception | None = None
    meter_call_count = 0
    meter_tool_id_seen: str = ""

    print()
    print(f"Executing get_jentic_news query={args.query!r}...")

    try:
        from unittest.mock import patch  # noqa: PLC0415

        import revenium_metering.decorator as _dec_module  # noqa: PLC0415

        from tradingagents.agents.utils.jentic_news_tools import get_jentic_news  # noqa: PLC0415

        _orig_send = _dec_module._send_tool_event  # type: ignore[attr-defined]  # noqa: SLF001
        captured_calls: list[dict] = []

        def _capture_and_forward(**kwargs: object) -> None:
            """Record meter-event kwargs and forward to the real sender (fail-open)."""
            import contextlib  # noqa: PLC0415
            captured_calls.append(dict(kwargs))
            with contextlib.suppress(Exception):
                _orig_send(**kwargs)

        with patch.object(_dec_module, "_send_tool_event", side_effect=_capture_and_forward):
            exec_result = str(get_jentic_news.func(args.query))

        meter_call_count = len(captured_calls)
        if captured_calls:
            meter_tool_id_seen = str(captured_calls[0].get("tool_id", ""))

        exec_ok = bool(exec_result) and not exec_result.startswith("NO_DATA_AVAILABLE")

    except Exception as exc:  # noqa: BLE001
        exec_exc = exc
        print(f"  ERROR: get_jentic_news.func() raised: {type(exc).__name__}: {exc}")

    if exec_result:
        snippet = exec_result[:300].replace("\n", " ")
        print(f"  Result snippet : {snippet!r}")
    if meter_call_count:
        print(f"  Meter events   : {meter_call_count} (toolId={meter_tool_id_seen!r})")

    # ------------------------------------------------------------------
    # Report checks
    # ------------------------------------------------------------------
    print()
    checks: list[tuple[str, bool]] = []
    checks.append((
        f"JEN-LIST  list_apis() succeeded; news API found in {credentialed_apis!r}",
        list_ok and news_api_found,
    ))
    checks.append((
        "JEN-EXEC  get_jentic_news returned real content (not NO_DATA_AVAILABLE sentinel)",
        exec_ok,
    ))
    checks.append((
        f"JEN-METER @meter_tool fired {meter_call_count} event(s) with"
        f" toolId={meter_tool_id_seen!r} (expected {tool_id!r})",
        meter_call_count == 1 and meter_tool_id_seen == tool_id,
    ))

    passed, failed = _run_checks(checks)
    print()

    if list_exc is not None:
        print(f"  list_apis error : {type(list_exc).__name__}: {list_exc}")
    if exec_exc is not None:
        print(f"  execute error   : {type(exec_exc).__name__}: {exec_exc}")

    # ------------------------------------------------------------------
    # Dashboard confirmation reminder
    # ------------------------------------------------------------------
    print("Confirm in the Revenium dashboard (Tools view):")
    print(f"  1. Tool '{tool_id}' shows ONE tool event per execute() call")
    print("  2. Non-zero per-call cost (proves toolId matches registered ToolResource, L6)")
    print("  3. success=true and durationMs > 0 in event details")
    print("  If no cost appears: register the ToolResource first —")
    print("    .venv/bin/python scripts/setup_revenium.py --jentic-tool")
    print()

    if failed == 0:
        print(f"Jentic PASSED: {passed}/{passed + failed} checks.")
        return 0
    else:
        print(f"Jentic FAILED: {failed}/{passed + failed} check(s) failed.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
