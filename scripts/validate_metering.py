"""Live end-to-end metering validation for Revenium + TradingAgents.

Doubles as a pre-demo sanity check (D-07): makes ONE real LLM call with
the ReveniumCallbackHandler attached inside a revenium_run_context, then
asserts that exactly ONE metering event was dispatched with:
  - Non-zero input and output token counts
  - subscriber.id == john.demic+trading@revenium.io  (not UNCLASSIFIED)
  - organizationName and productName populated
  - agent, trace_id, and task_type set

The script prints a PASS or FAIL line per check and exits 0 on all-PASS,
1 on any FAIL.

Requirements:
  - REVENIUM_METERING_API_KEY set to a valid rev_mk_* key
  - At least one LLM provider key set (ANTHROPIC_API_KEY or OPENAI_API_KEY)
  - pip install ".[dev]" (tests/dev deps)

Usage:
    # Anthropic (deep-think model, default):
    REVENIUM_METERING_API_KEY=rev_mk_... ANTHROPIC_API_KEY=... \\
        python scripts/validate_metering.py

    # OpenAI — auto-resolves to gpt-4.1-mini (the configured quick-think model):
    REVENIUM_METERING_API_KEY=rev_mk_... OPENAI_API_KEY=... \\
        python scripts/validate_metering.py --provider openai

    # Explicit model override (e.g. a provider not in the configured pair list):
    REVENIUM_METERING_API_KEY=rev_mk_... OPENAI_API_KEY=... \\
        python scripts/validate_metering.py --provider openai --model gpt-4o

    # Fail-open check (Revenium unreachable → should WARN, not crash):
    REVENIUM_METERING_API_KEY=rev_mk_... REVENIUM_METERING_BASE_URL=https://unreachable.invalid \\
    ANTHROPIC_API_KEY=... python scripts/validate_metering.py --skip-revenium-check

    # MTR-04 multi-provider check (Anthropic + OpenAI, DISTINCT provider labels):
    REVENIUM_METERING_API_KEY=rev_mk_... ANTHROPIC_API_KEY=... OPENAI_API_KEY=... \\
        python scripts/validate_metering.py --multi-provider

After the script exits 0 (local assertions pass), confirm in the Revenium
dashboard that exactly ONE event arrived for trace_id printed below with:
  - organizationName: Revenium-Research-Desk
  - productName: trading-signal
  - subscriber: john.demic+trading@revenium.io
  - Non-zero token counts
  - No UNCLASSIFIED attribution
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


def _run_multi_provider(config: dict, skip_revenium_check: bool) -> int:
    """Execute the MTR-04 two-provider validation.

    Makes one call via the Anthropic deep-think model and one via the OpenAI
    quick-think model; validates that both events carry DISTINCT provider labels
    ('anthropic' and 'openai') and that no event is UNCLASSIFIED.

    Returns 0 on all-PASS, 1 on any FAIL.
    """
    from tradingagents.llm_clients import create_llm_client
    from tradingagents.revenium.callback import ReveniumCallbackHandler
    from tradingagents.revenium.context import current_agent_name, revenium_run_context

    # Provider→model pairs for MTR-04 (matches DEFAULT_CONFIG demo setup).
    providers_to_check = [
        ("anthropic", config.get("deep_think_llm", "claude-sonnet-4-6"), "market_analyst"),
        ("openai",    config.get("quick_think_llm", "gpt-4.1-mini"),      "bull_researcher"),
    ]

    api_key: str = config.get("revenium_api_key", "")

    print(f"\nMTR-04 Multi-Provider Validation — {datetime.utcnow().isoformat()}Z")
    print("  Verifying DISTINCT provider labels for Anthropic and OpenAI.")
    print()

    all_passed = True
    providers_seen: set[str] = set()

    for provider, model, agent_name in providers_to_check:
        print(f"[{provider.upper()}] {model}  (agent={agent_name})")

        captured: list[dict] = []
        handler = ReveniumCallbackHandler.from_config(config)
        _original_meter = handler._client.meter_ai_completion

        def _capture(payload: dict, _orig=_original_meter) -> None:
            captured.append(payload)
            if not skip_revenium_check:
                _orig(payload)

        handler._client.meter_ai_completion = _capture  # type: ignore[method-assign]

        trace_id = ""
        llm_exception: Exception | None = None

        try:
            client = create_llm_client(
                provider=provider,
                model=model,
                callbacks=[handler],
            )
            llm = client.get_llm()

            with revenium_run_context("VALIDATE-MP", datetime.utcnow().strftime("%Y-%m-%d")) as trace_id:
                current_agent_name.set(agent_name)
                print(f"  trace_id: {trace_id}")
                print(f"  Making call to {provider}/{model}...")
                response = llm.invoke("Reply with exactly three words: metering is working")
                print(f"  Response: {str(response.content)[:60]!r}")

        except Exception as exc:
            llm_exception = exc
            print(f"  ERROR: {exc}")

        for t in list(handler._threads):
            t.join(timeout=5.0)

        print()
        checks: list[tuple[str, bool]] = []
        checks.append(("LLM call succeeded", llm_exception is None))
        checks.append(("Exactly 1 event dispatched", len(captured) == 1))

        if captured:
            p = captured[0]
            payload_provider = p.get("provider", "") or ""
            checks.append((
                f"provider label == '{provider}' (got {payload_provider!r})",
                payload_provider.lower() == provider,
            ))
            checks.append(("Non-zero input_token_count", p.get("input_token_count", 0) > 0))
            checks.append(("Non-zero output_token_count", p.get("output_token_count", 0) > 0))
            checks.append(("agent not empty", bool(p.get("agent"))))
            checks.append(("trace_id matches", p.get("trace_id") == trace_id))

            provider_label = payload_provider.lower()
            if provider_label and provider_label not in ("unknown", "unclassified", ""):
                providers_seen.add(provider_label)
        else:
            checks.append(("Payload content checks skipped (no payload)", False))

        p_passed, p_failed = _run_checks(checks)
        if p_failed > 0:
            all_passed = False

        if trace_id:
            print(f"\n  Dashboard trace_id: {trace_id}")
        print()

    # Final cross-provider assertion
    print("Cross-provider assertion:")
    distinct_check = (
        "DISTINCT 'anthropic' and 'openai' provider labels",
        "anthropic" in providers_seen and "openai" in providers_seen,
    )
    xp, xf = _run_checks([distinct_check])
    if xf > 0:
        all_passed = False

    print()
    print("MTR-04 dashboard checklist:")
    print("  1. Two events with the trace_ids above — one Anthropic, one OpenAI")
    print("  2. provider field clearly 'anthropic' vs 'openai' (not UNCLASSIFIED)")
    print("  3. agent: 'market_analyst' for Anthropic, 'bull_researcher' for OpenAI")
    print("  4. organizationName: Revenium-Research-Desk")
    print("  5. productName: trading-signal")
    print("  6. subscriber: john.demic+trading@revenium.io")
    print("  7. Non-zero token counts on both events")
    print()

    if all_passed:
        print("MTR-04 Multi-Provider PASSED: all checks green.")
        return 0
    else:
        print("MTR-04 Multi-Provider FAILED: one or more checks failed.")
        return 1


def main() -> int:
    """Run the live metering validation.  Returns 0 on success, 1 on failure."""
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--provider",
        default=None,
        help="LLM provider override (anthropic, openai).  Defaults to config default.",
    )
    parser.add_argument(
        "--model",
        default=None,
        help=(
            "LLM model override; defaults to the model configured for the chosen provider."
            "  Use this when --provider names a provider that is not in the configured"
            " deep_think_provider / quick_think_provider pair."
        ),
    )
    parser.add_argument(
        "--skip-revenium-check",
        action="store_true",
        help="Skip the Revenium connectivity check (useful for fail-open testing).",
    )
    parser.add_argument(
        "--multi-provider",
        action="store_true",
        help=(
            "MTR-04 mode: make one Anthropic call (deep-think) and one OpenAI call"
            " (quick-think) and assert DISTINCT provider labels in metering events."
            " Requires both ANTHROPIC_API_KEY and OPENAI_API_KEY."
        ),
    )
    args = parser.parse_args()

    # ------------------------------------------------------------------
    # Imports (inside main to keep module-level clean)
    # ------------------------------------------------------------------
    from dotenv import load_dotenv

    load_dotenv()

    from tradingagents.dataflows.config import get_config, set_config
    from tradingagents.default_config import DEFAULT_CONFIG
    from tradingagents.llm_clients import create_llm_client
    from tradingagents.revenium.callback import ReveniumCallbackHandler
    from tradingagents.revenium.context import current_agent_name, revenium_run_context

    config = dict(DEFAULT_CONFIG)

    # Capture the ORIGINAL provider→model pairs before any override so the
    # matching logic below can still find the right model after the override
    # clobbers both provider keys to the same value.
    orig_deep_think_provider = config.get("deep_think_provider", "")
    orig_deep_think_llm = config.get("deep_think_llm", "")
    orig_quick_think_provider = config.get("quick_think_provider", "")
    orig_quick_think_llm = config.get("quick_think_llm", "")

    # ------------------------------------------------------------------
    # Gate: REVENIUM_METERING_API_KEY must be set
    # ------------------------------------------------------------------
    api_key = config.get("revenium_api_key", "")
    if not api_key and not args.skip_revenium_check:
        print("FAIL  REVENIUM_METERING_API_KEY is not set — metering disabled.")
        print(
            "      Set it in your .env file and retry, or pass --skip-revenium-check"
            " to test the fail-open path."
        )
        return 1

    # ------------------------------------------------------------------
    # Route: --multi-provider delegates to dedicated function
    # ------------------------------------------------------------------
    if args.multi_provider:
        set_config(config)
        config = get_config()
        return _run_multi_provider(config, skip_revenium_check=args.skip_revenium_check)

    # ------------------------------------------------------------------
    # Single-provider path (existing behaviour)
    # ------------------------------------------------------------------

    # Apply provider override if requested (updates all provider keys so that
    # create_llm_client always routes to the right backend).
    if args.provider:
        config["llm_provider"] = args.provider
        config["deep_think_provider"] = args.provider
        config["quick_think_provider"] = args.provider

    set_config(config)
    config = get_config()

    # Resolve the effective (provider, model) pair for the single validation call.
    # Priority for provider: --provider flag → deep_think_provider → llm_provider.
    # Priority for model:    --model flag → configured model whose provider matches
    #                        effective_provider (matched against ORIGINAL pairs,
    #                        captured above before the override) → fail-fast.
    effective_provider = (
        config.get("deep_think_provider")
        or config.get("llm_provider", "anthropic")
    )

    if args.model:
        effective_model = args.model
    elif effective_provider == orig_quick_think_provider and orig_quick_think_llm:
        effective_model = orig_quick_think_llm
    elif effective_provider == orig_deep_think_provider and orig_deep_think_llm:
        effective_model = orig_deep_think_llm
    else:
        print(
            f"ERROR: no configured model found for provider '{effective_provider}'."
            "  Pass --model to specify one explicitly."
        )
        return 1

    # ------------------------------------------------------------------
    # Build handler + intercept client calls for local assertion
    # ------------------------------------------------------------------
    captured_payloads: list[dict] = []
    handler = ReveniumCallbackHandler.from_config(config)

    # Wrap the client's meter_ai_completion to also record payloads locally.
    _original_meter = handler._client.meter_ai_completion

    def _capture_and_meter(payload: dict) -> None:
        captured_payloads.append(payload)
        if not args.skip_revenium_check:
            _original_meter(payload)

    handler._client.meter_ai_completion = _capture_and_meter  # type: ignore[method-assign]

    print(f"\nValidating Revenium metering — {datetime.utcnow().isoformat()}Z")
    print(f"  Provider      : {effective_provider}")
    print(f"  Model         : {effective_model}")
    print(f"  Metering key  : {api_key[:12]}... (hidden)" if api_key else "  Metering key  : (absent)")
    print()

    # ------------------------------------------------------------------
    # Make ONE real LLM call inside revenium_run_context
    # ------------------------------------------------------------------
    trace_id = ""
    llm_exception: Exception | None = None

    try:
        provider = effective_provider
        model = effective_model
        client = create_llm_client(provider=provider, model=model, callbacks=[handler])
        llm = client.get_llm()

        with revenium_run_context("VALIDATE", datetime.utcnow().strftime("%Y-%m-%d")) as trace_id:
            current_agent_name.set("market_analyst")
            print(f"  trace_id      : {trace_id}")
            print(f"  Making one {provider}/{model} call...")
            response = llm.invoke("Reply with exactly three words: metering is working")
            print(f"  LLM response  : {str(response.content)[:80]!r}")

    except Exception as exc:
        llm_exception = exc
        print(f"  ERROR: LLM call failed: {exc}")

    # Wait for background threads to finish (give them up to 5 s)
    for t in list(handler._threads):
        t.join(timeout=5.0)

    print()

    # ------------------------------------------------------------------
    # Local assertions
    # ------------------------------------------------------------------
    print("Checking local metering assertions:")

    checks: list[tuple[str, bool]] = []

    checks.append(("LLM call succeeded (no exception)", llm_exception is None))
    checks.append(("Exactly 1 metering event dispatched", len(captured_payloads) == 1))

    if captured_payloads:
        p = captured_payloads[0]

        checks.append((
            "Non-zero input_token_count",
            p.get("input_token_count", 0) > 0,
        ))
        checks.append((
            "Non-zero output_token_count",
            p.get("output_token_count", 0) > 0,
        ))
        checks.append((
            "organizationName non-empty",
            bool(p.get("organization_name")),
        ))
        checks.append((
            "productName non-empty",
            bool(p.get("product_name")),
        ))
        sub = p.get("subscriber", {})
        subscriber_id = sub.get("id", "") or sub.get("email", "")
        checks.append((
            f"subscriber.id == 'john.demic+trading@revenium.io' (got {subscriber_id!r})",
            subscriber_id == "john.demic+trading@revenium.io",
        ))
        checks.append((
            "agent == 'market_analyst'",
            p.get("agent") == "market_analyst",
        ))
        checks.append((
            f"trace_id == run trace_id (got {p.get('trace_id')!r})",
            p.get("trace_id") == trace_id,
        ))
        checks.append((
            "task_type non-empty",
            bool(p.get("task_type")),
        ))
    else:
        checks.append(("Payload content checks skipped (no payload captured)", False))

    passed, failed = _run_checks(checks)

    print()

    # ------------------------------------------------------------------
    # Dashboard reminder for the human
    # ------------------------------------------------------------------
    if trace_id:
        print(f"Dashboard trace_id to find: {trace_id}")
        print("Confirm in the Revenium dashboard:")
        print("  1. Exactly ONE event with the trace_id above")
        print("  2. organizationName: Revenium-Research-Desk")
        print("  3. productName: trading-signal")
        print("  4. subscriber: john.demic+trading@revenium.io")
        print("  5. Non-zero token counts, NOT UNCLASSIFIED")
        print()

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    if failed == 0:
        print(f"Metering PASSED: {passed}/{passed + failed} checks.")
        return 0
    else:
        print(f"Metering FAILED: {failed}/{passed + failed} check(s) failed.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
