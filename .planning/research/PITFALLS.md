# Pitfalls Research

**Domain:** Revenium metering/traces/controls/billing instrumentation on a multi-provider LangGraph agentic app — live FCAT demo
**Researched:** 2026-06-26
**Confidence:** HIGH (Revenium OTLP docs + PyPI packages verified; LangChain/LangGraph issues verified from upstream GitHub; codebase issues verified from .planning/codebase/)

---

## Critical Pitfalls

### Pitfall 1: Double-Counting — Callback Layer and OTLP Layer Both Fire

**What goes wrong:**
Token costs appear doubled in Revenium. A run that costs ~$0.80 shows up as ~$1.60. The demo's "cost per trading signal" figure is wrong on stage.

**Why it happens:**
Two metering paths can fire simultaneously for the same LLM invocation:

1. The legacy `revenium-middleware-langchain` callback handler (archived as of June 15, 2026; superseded by `revenium-python-sdk`) attaches at the LangChain callback layer — `on_llm_end` — and meters once per LLM call.
2. The OTLP path via `opentelemetry-instrumentation-langchain` (or `openinference`) emits a GenAI span per LLM invocation, which Revenium's OTLP ingress also meters.

If both are active simultaneously, every LLM call registers two metering events. This is a documented failure mode in Langfuse (issue #10914) and DataDog (dd-trace-js issue #8936) and is equally applicable to Revenium.

The existing `cli/stats_handler.py` `StatsCallbackHandler` already attaches at both graph compilation level and individual LLM level for token accumulation — the same structural risk.

**How to avoid:**
Choose exactly one metering path before writing any instrumentation code. The recommended path for this project is **OTLP via `revenium-python-sdk`** (the unified, maintained package) with `opentelemetry-instrumentation-langchain` emitting GenAI spans. Do not also install or activate `revenium-middleware-langchain` (archived). Explicitly verify no Revenium callback handler is passed to both `TradingAgentsGraph(callbacks=...)` and to individual `llm.invoke()` calls.

Add a startup assertion or test: after one graph run in a test harness, assert that the number of metering events received by a mock Revenium endpoint equals the number of `on_llm_end` events — they should be 1:1, not 2:1.

**Warning signs:**
- Revenium cost dashboard shows a total that is approximately 2x the sum of per-model costs from the provider dashboard.
- `cli/stats_handler.py` token tallies match provider invoices, but Revenium shows double.
- Debate loop rounds appear with 2N LLM spans for N actual model calls.

**Phase to address:**
Metering phase (Phase 1). Must be validated with a single-LLM sanity-check call before wiring the full graph.

---

### Pitfall 2: Streaming / Async Token Counts Missing from `on_llm_end`

**What goes wrong:**
Some LLM calls produce zero or wildly wrong token counts in Revenium. Specifically: any call that uses `stream=True` or LangChain's async path (`ainvoke`) may deliver an `LLMResult` to `on_llm_end` without the `llm_output` field, which is where token usage metadata lives. The cost for those calls shows as $0 or is omitted entirely.

**Why it happens:**
This is a documented LangChain bug (issues #34057 and #30429). The `stream()` code path constructs `LLMResult(generations=[[generation]])` without the `llm_output` dict, so any callback handler that reads `response.llm_output.get("token_usage")` gets `None`. The OTLP path is unaffected because OpenTelemetry instrumentation reads usage directly from the provider response before LangChain processes it — but only if the OTel instrumentation hooks into the provider SDK, not just into LangChain's callback layer.

In this codebase, the sentiment analyst (`sentiment_analyst.py:69`) calls `get_news.func(...)` directly, bypassing the `@tool` wrapper. Any OTel or callback instrumentation on that tool is invisible for that call. CONCERNS.md flags this explicitly. Tool-call costs from ToolNodes (market/social/news/fundamentals) are data-fetch calls, not LLM calls, so they are not token-metered — but confirm Revenium's span filter skips `execute_tool` spans as documented (`gen_ai.operation.name` filter).

**How to avoid:**
Use the OTLP integration path (provider-level OTel instrumentation via `opentelemetry-instrumentation-openai` and `opentelemetry-instrumentation-anthropic`) rather than relying solely on LangChain's `on_llm_end` callback for token counts. The OTel instrumentation captures usage from the provider SDK response before LangChain processes it, so it is immune to the `stream()` path's missing `llm_output`.

For the `.func` bypass in `sentiment_analyst.py`: the fix is to call `route_to_vendor("get_news", ...)` directly or restore the tool wrapper call — not because it affects LLM token counts (it's a data fetch) but to avoid confusion about what is and is not metered.

**Warning signs:**
- Revenium shows some agents with $0 LLM cost but the provider invoice shows charges.
- Token counts for debate-loop rounds vary wildly between rounds despite similar prompt sizes.
- The Revenium trace shows a model span with `gen_ai.usage.input_tokens = 0`.

**Phase to address:**
Metering phase (Phase 1). Verify with a streaming-mode test call against the mock Revenium endpoint before integrating the full graph.

---

### Pitfall 3: Reasoning Tokens Not Counted or Double-Counted

**What goes wrong:**
If Anthropic Claude thinking mode or OpenAI reasoning models (o-series) are used in the demo, the "input tokens" figure in Revenium is wrong — either understated (thinking tokens absent) or overstated (thinking tokens counted at input rate when they should be counted at a different rate).

**Why it happens:**
Anthropic extended thinking returns a separate `thinking` content block with its own `input_tokens` / `output_tokens` metadata that is distinct from the main response token counts. LangChain's `usage_metadata` aggregation for reasoning models is incomplete — the `thinking_input_tokens` are not reliably surfaced in `on_llm_end`'s `llm_output["token_usage"]` in all versions. OpenAI o-series returns `reasoning_tokens` as a separate field inside `completion_tokens_details`, which standard LangChain token-counting callbacks may not extract.

Revenium's OTLP path depends on the provider instrumentation library correctly emitting `gen_ai.usage.input_tokens` and `gen_ai.usage.output_tokens` — if the OTel library predates reasoning-token schema extensions, it silently drops them.

**How to avoid:**
For the demo, use models that do NOT require thinking/reasoning mode unless showcasing it explicitly. If you use Claude with extended thinking enabled (e.g., for the deep-think Research Manager or Portfolio Manager), verify the OTel instrumentation version supports `thinking_input_tokens` by checking a single call's span attributes in the Revenium trace detail. The `capabilities.py` table already tracks per-model quirks — add a `reasoning_tokens_separate` flag and document the counting approach.

Pin `anthropic` SDK and `opentelemetry-instrumentation-anthropic` to tested versions during the demo window.

**Warning signs:**
- Anthropic invoice shows higher cost than Revenium's attribution for the same model.
- Revenium trace detail shows `gen_ai.usage.output_tokens` matching only the visible response, not the full usage.
- Cost-per-signal calculation is consistently low when using reasoning-enabled models.

**Phase to address:**
Metering phase (Phase 1), specifically the multi-provider verification step. Flag in STACK.md if reasoning models are used.

---

### Pitfall 4: Trace / Squad Fragmentation — Debate Loops and Message-Clearing Nodes Break Continuity

**What goes wrong:**
The Revenium trace for a full `propagate()` run shows not one connected agent flow but multiple disconnected fragments. The Bull/Bear debate loop appears as 4–6 separate traces instead of one squad. The message-clearing nodes (which wipe `messages` from `AgentState` between analysts) cause observability tools to lose the parent span context. On stage, the "trace" view does not tell the complete meter→trace→control→monetize story.

**Why it happens:**
LangGraph trace continuity depends on a consistent `run_id` or `thread_id` being propagated through the callback/span context. Message-clearing nodes reset `AgentState["messages"]` — if the observability layer uses the messages list to carry a trace context header or parent run ID, clearing messages severs the chain.

LangGraph's interrupt-resume mechanism has a documented fragmentation issue (Langfuse issue #10962): each interrupt-resume cycle creates a new trace object. While TradingAgents doesn't use interrupt for human-in-the-loop, its debate loop conditional edges (`should_continue_debate`, `should_continue_risk_analysis`) with loopback edges are structurally similar — if the callback handler does not persist parent context across conditional loopback edges, spans become orphaned.

Async context loss (Last9 analysis) means that when LangGraph executes nodes across async boundaries, `context.attach()` must be called explicitly or child spans become orphaned.

The `string.startswith("Aggressive")` coupling in `conditional_logic.py` (flagged in CONCERNS.md) also means that a mis-named node silently falls through, creating a topological skip that can leave span parent references dangling.

**How to avoid:**
Inject a single `trace_id` (e.g., UUID generated at `propagate()` start) into the initial `AgentState` and propagate it as a custom field — not through `messages`. Pass it explicitly as a `revenium.trace.id` OTel span attribute in a custom node-wrapping decorator. Do not rely on the LangChain callback `run_id` alone for cross-loop continuity; it resets on conditional loopback edges.

Use `revenium.squad.id` and `revenium.squad.name` attributes (available in the OTLP attribution schema) to group all spans from a single `propagate()` call into one squad, even if individual spans are emitted from separate graph invocations.

Validate trace continuity before the demo by running one full graph invocation and checking that Revenium shows exactly one squad with the expected node count — not multiple disconnected traces.

**Warning signs:**
- Revenium shows multiple short traces for a single ticker run instead of one long squad trace.
- Debate rounds appear as sibling traces rather than children of the analysis trace.
- Portfolio Manager span has no parent in the Revenium trace view.
- The "critical path analysis" feature shows only a partial chain.

**Phase to address:**
Trace / squad phase (Phase 2). A trace-continuity integration test should run before the demo dry-run.

---

### Pitfall 5: Cost Control Race Condition — Limit Fires After the Expensive Node, Not Before

**What goes wrong:**
A spend limit fires mid-debate after the most expensive node has already completed. On stage, the halt looks laggy and unconvincing — the graph has already spent past the threshold by the time Revenium's enforcement fires.

**Why it happens:**
Cost controls in Revenium are evaluated server-side on metering events received by the API. The latency from LLM call completion → span export → OTLP ingress → enforcement rule evaluation → response returned to the app is non-zero, typically 200ms–2s depending on batching intervals and API latency. LangGraph's synchronous `graph.invoke()` path does not check an external enforcement response between nodes; there is no built-in "check budget before running next node" hook in LangGraph.

If the enforcement check is implemented as a conditional node that calls the Revenium API synchronously before each expensive node, it adds per-node latency. If it is implemented as an async side-channel that the graph polls via a shared flag, race conditions arise: the flag may not be set before the next node starts.

The OTLP batching default (typically 5-second export intervals in the OTel Python SDK) means metering events can lag actual spend by up to 5 seconds, making real-time enforcement unreliable unless the export interval is reduced to near-zero or metering events are sent synchronously.

**How to avoid:**
For the demo, implement a lightweight in-process spend counter that increments after each LLM call (using the same token data fed to Revenium) and checks against a locally configured threshold before each new node execution. This avoids the network round-trip for enforcement. The Revenium enforcement system is the authoritative backstop for production; the in-process counter is the demo-reliable gate.

Set the OTel exporter batch timeout to 1 second (not the default 5 seconds) so Revenium's dashboard updates in near-real-time during the live demo — even if the in-process counter gates execution.

If using Revenium's enforcement API directly: call it synchronously at the start of each debate round (not after each LLM call), with a 500ms timeout and a fail-open policy (proceed if API is unreachable) to prevent Revenium API latency from blocking the graph.

**Warning signs:**
- Revenium dashboard shows spend crossing the threshold 3–5 seconds after the demo expected the halt.
- The graph completes an additional debate round after the "stop" animation was supposed to fire.
- Enforcement API responds with 200 but the graph continues running because the response was not awaited.

**Phase to address:**
Cost controls phase (Phase 3). Validate timing with a stop-watch dry-run before the demo.

---

### Pitfall 6: Shadow Mode vs. Enforce Mode Confusion on Stage

**What goes wrong:**
The cost control triggers during the demo, but the graph continues running because the rule was left in shadow mode (observe-only). The FCAT audience sees the limit fire in the Revenium UI but the system ignores it — undermining the "control" narrative.

**Why it happens:**
Revenium's cost controls have two modes per the API schema: shadow (record violations, do not halt) and enforce (halt). The shadow mode is the safer default for initial testing because it does not interrupt graph execution. Teams testing their integration leave controls in shadow mode and forget to switch before the live demo.

**How to avoid:**
Create a pre-demo checklist item: "Confirm enforcement rules are in enforce mode, not shadow mode." Set the rule in enforce mode at least 24 hours before the demo and run a full dry-run with enforcement active. Store the rule ID and mode in the demo configuration file so it is visible and auditable.

**Warning signs:**
- Revenium shows a "violation recorded" event but no enforcement action.
- The graph runs to completion despite spending above the threshold.
- The `shadow` field in the enforcement rule API response is `true`.

**Phase to address:**
Cost controls phase (Phase 3). Include a "mode check" step in the demo run-script.

---

### Pitfall 7: Missing Billing Identifiers Cause UNCLASSIFIED Attribution

**What goes wrong:**
The "cost per trading signal" metric in Revenium's FinOps view is blank or rolls up into an UNCLASSIFIED bucket instead of appearing under the "Fidelity FCAT / Equity Desk" customer. Margin calculation is unavailable. The monetization narrative falls flat on stage.

**Why it happens:**
Revenium's billing system requires three identifiers on every metering event: `subscriber.id` (end customer), `productName` (commercial tier), and `organizationName` (top-level account). If any of these is missing, the event is captured but unbillable and lands in UNCLASSIFIED. This is explicitly documented in the Revenium billing tutorial.

The OTLP path uses `revenium.*` span attributes for attribution. These must be set as OTel span attributes on the LLM span — they are not inferred from model name or API key. If the span attribute injection code is added later than the metering instrumentation, early runs will be UNCLASSIFIED and will not retroactively reclassify when the attribute is added (historical data cannot be re-attributed).

**How to avoid:**
Set up the Revenium customer/product/organization hierarchy before writing any instrumentation code. Wire `revenium.subscriber.id`, `revenium.product.name`, and `revenium.organization.name` into the very first OTel span emitted, even during development. Use a test customer ID (e.g., `"fcat-demo"`) throughout development so all test runs accumulate under the correct attribution from day one.

Validate attribution in the Revenium UI after the first successful test call — do not wait until the full graph is wired.

**Warning signs:**
- Revenium "Get cost per customer" API returns empty results for the demo customer ID.
- UNCLASSIFIED bucket in the Revenium dashboard grows alongside each test run.
- Revenium `subscriber.id` attribute is absent from span attributes in the trace detail view.

**Phase to address:**
Billing / monetization phase (Phase 4), but customer hierarchy must be created in Phase 1 before metering begins.

---

### Pitfall 8: Wrong API Key Type — Metering Key vs. Platform Key

**What goes wrong:**
Revenium API calls return 401 Unauthorized during integration despite having a valid-looking API key. The app silently fails to meter (fail-open by design) and the demo runs without any data in Revenium.

**Why it happens:**
Revenium uses different key formats for different surfaces:
- Metering keys start with `rev_mk_` (OTLP ingress, metering API)
- The archived `revenium-middleware-langchain` expected keys starting with `hak_` (legacy format)
- Platform API keys (for reading analytics, managing rules) use a different format

Using a platform key for the OTLP exporter, or a metering key for the management API, results in 401 errors with no clear error message in the OTel exporter logs (OTel exporters swallow HTTP errors by default).

**How to avoid:**
Confirm the key type before writing any integration code. The OTLP endpoint (`https://api.revenium.ai/meter/v2/otlp`) requires a metering key (`rev_mk_`). The management API requires a platform key. Store them in separate environment variables (`REVENIUM_METERING_KEY`, `REVENIUM_PLATFORM_KEY`) and validate format at startup.

Enable OTel exporter debug logging (`OTEL_LOG_LEVEL=debug`) during development so HTTP 401 errors surface visibly rather than being silently swallowed.

**Warning signs:**
- No spans appear in Revenium despite the graph running successfully.
- OTel exporter logs show "Export failed" or "StatusCode.ERROR" without a clear HTTP status.
- The metering key environment variable is set but starts with `hak_` (legacy format).

**Phase to address:**
Phase 1 (first day of integration). Cannot proceed without confirming the correct key type and format.

---

### Pitfall 9: Speculative Default Models Cause Out-of-Box API Failures

**What goes wrong:**
The demo run fails immediately with an API error (model not found) before any Revenium instrumentation is exercised. The codebase's `DEFAULT_CONFIG` hardcodes `"gpt-5.5"` and `"gpt-5.4-mini"` as default models, which do not exist in the OpenAI API as of the analysis date.

**Why it happens:**
`tradingagents/default_config.py:56-57` sets speculative model names that OpenAI does not currently serve. The `validate_model()` check in `model_catalog.py` emits a warning but does not block. The first LLM call in the graph hits the OpenAI API with an invalid model name and fails hard.

This is flagged in CONCERNS.md as a known issue. It is listed here because it will surface as a Revenium-specific failure mode if the demo relies on a default-config run without explicit model overrides.

**How to avoid:**
Override `deep_think_llm` and `quick_think_llm` explicitly in the demo configuration. Do not rely on `DEFAULT_CONFIG` model names. Pin to currently available models (e.g., `gpt-4.1` / `gpt-4.1-mini` for OpenAI, `claude-sonnet-4-6` for Anthropic). Include model validation in the demo pre-flight script.

**Warning signs:**
- Graph fails at the first analyst node with `InvalidRequestError: model not found`.
- `validate_model` log warning appears at startup referencing `gpt-5.5`.
- The default config is used without an explicit override dict.

**Phase to address:**
Phase 1 (demo configuration). Fix before any integration work.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Keep `revenium-middleware-langchain` callback handler alongside OTLP | Faster initial integration using familiar callback pattern | Double-counting; archived package receives no bugfixes; breaks on LangChain version bumps | Never — choose one path |
| Hardcode `revenium.subscriber.id = "fcat-demo"` in the graph call | No customer setup required on day one | All runs attributed to one subscriber; margin math uses wrong denominator | Acceptable for Phase 1 dev runs only; replace before demo |
| Use shadow mode for all enforcement rules during development | Safe — no accidental graph halts during testing | Enforcement silently does nothing if not switched to enforce mode before demo | Acceptable during Phases 1–3; must switch before demo dry-run |
| Skip OTel exporter debug logging to reduce noise | Cleaner logs during dev | 401/network errors are silently swallowed; hours lost debugging missing Revenium data | Never during development; safe to disable in production |
| Use LangChain `on_llm_end` callback instead of provider-level OTel | Simpler one-library setup | Misses streaming token counts, misses reasoning tokens, double-counts if OTLP also active | Never for this project — OTLP is the right path |

---

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| Revenium OTLP ingress | Using a platform API key (`rev_pk_*`) or legacy `hak_` key for the OTLP endpoint | Use metering key (`rev_mk_*`) for OTLP; platform key only for management API |
| OTel exporter headers (Python) | Setting `Authorization: Bearer <key>` literally | Must percent-encode the space: `Authorization: Bearer%20<key>` — documented Python caveat in Revenium OTLP docs |
| `revenium-middleware-langchain` | Installing the archived package as the integration path | Migrate to `revenium-python-sdk`; the middleware-langchain package is inactive as of June 2026 |
| LangChain callback attachment | Attaching callback at both `graph.compile().with_config()` and individual `llm.invoke()` | Attach at exactly one level; graph-level is preferred for LangGraph to avoid double-firing |
| LangGraph ToolNode spans | Expecting tool-call spans to appear in Revenium cost data | Revenium filters `execute_tool` spans by design; only actual LLM invocations are metered |
| Global config singleton | Constructing two `TradingAgentsGraph` instances simultaneously (e.g., test + live) | `dataflows/config.py` is not thread-safe; the second `set_config` call corrupts the first's config |
| Memory log at demo start | `get_past_context()` reads and regex-parses the full `trading_memory.md` on every `propagate()` call | Enable `memory_log_max_entries` (suggested: 200) before demo to bound parse time |

---

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| OTel batch export interval at default (5 seconds) | Revenium dashboard lags by up to 5 seconds; enforcement decisions are stale | Set `OTEL_BSP_EXPORT_TIMEOUT=1000` and `OTEL_BSP_MAX_EXPORT_BATCH_SIZE=1` for the demo | Immediately visible in live demo when cost panel and Revenium UI are out of sync |
| Synchronous Revenium enforcement API call per node | Each node adds 200ms–2s latency; a 12-node graph adds 2–24 seconds | Use in-process spend counter as the gate; Revenium API as the audit log | At any scale; especially visible on stage with a watching audience |
| Sentiment analyst's three sequential blocking fetches (30s worst case) | Demo stalls visibly at the sentiment step | Fix by fetching concurrently (CONCERNS.md item); or disable sentiment analyst for the demo run | Any network-degraded environment including demo venue WiFi |
| OHLCV cache invalidates on every calendar day | Cold-start yfinance download adds 1–5s per ticker | Pre-warm cache before the demo by running the ticker the same day | Day-of-demo environment |
| `get_past_context` reads full memory log on each run | Startup delay grows with log size | Enable `memory_log_max_entries = 200` in demo config | After ~50–100 prior runs with long PM decisions |

---

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Enabling `REVENIUM_CAPTURE_PROMPTS=true` in the demo environment | Full LLM prompts (including trading rationale) are sent to Revenium and visible to anyone with `canViewPromptData` permission | Leave prompt capture disabled for the FCAT demo; the cost/trace data is sufficient |
| Committing the `.env` file written by the CLI (`cli/utils.py:645`) | API keys (LLM providers + Revenium metering key) exposed in git history | Verify `.gitignore` covers `.env`; run `git status` before every commit during integration |
| Using a shared Revenium metering key across dev and demo environments | Dev noise pollutes the demo customer's cost attribution; a compromised dev key exposes demo data | Use separate metering keys for dev and demo; rotate the demo key after the FCAT presentation |

---

## "Looks Done But Isn't" Checklist

- [ ] **Metering:** A single test call shows exactly one Revenium metering event — not zero (key wrong) and not two (double-counting). Verify via Revenium API `GET /metering/events`.
- [ ] **Trace continuity:** A full `propagate()` run appears as one squad in Revenium with the expected number of LLM spans (not fragments). Verify by counting spans in Revenium trace detail.
- [ ] **Token counts match:** Revenium's attributed token total for one run matches the provider's usage dashboard within 5%. Discrepancy > 5% indicates a counting path mismatch.
- [ ] **Billing attribution:** After one metering call, the Revenium "cost per customer" API returns a non-zero result for the demo subscriber ID — not an empty response or UNCLASSIFIED entry.
- [ ] **Enforcement mode:** The cost control rule's `shadow` field is `false`. Confirmed by calling the Revenium rules API and inspecting the response.
- [ ] **Model names:** Demo config explicitly overrides `deep_think_llm` and `quick_think_llm` with valid, currently-available model IDs. No `gpt-5.5` in the active config.
- [ ] **Test suite passes without live keys:** All new Revenium-touching code is behind a mockable interface; `pytest` passes with `REVENIUM_METERING_KEY=placeholder`.
- [ ] **`.func` bypass addressed:** `sentiment_analyst.py:69` calls `get_news.func()` directly. Confirm this data-fetch path is correctly excluded (not an LLM call) and document the exemption so it is not misread as a tracking gap.

---

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Double-counting discovered day-of-demo | HIGH | Disable one metering path immediately (remove callback handler or set exporter to `console` only). Re-run a single test call to confirm 1:1 ratio. Accept that historical data for the day is inflated; present only the live demo run. |
| Revenium shows no data (API key wrong) | LOW | Swap to correct metering key; restart the demo app. OTLP exporter will immediately start delivering pending spans. |
| Trace fragmentation (multiple traces per run) | MEDIUM | Add `revenium.squad.id = run_uuid` to all spans in the current run; re-run demo. Old fragmented traces remain but the live demo run will be unified. |
| Enforcement fires too late (after expensive node) | MEDIUM | Switch from OTLP-based enforcement to in-process spend counter with a hard-coded threshold. Takes 30 minutes to implement; use as the demo gate. |
| Provider outage mid-demo | MEDIUM | Pre-configure a fallback provider in `DEFAULT_CONFIG["data_vendors"]`; the vendor routing layer already supports comma-separated fallback chains. For LLM outage: switch `llm_provider` to a backup provider in the demo config. Have a backup ticker run cached from a prior day as a last resort. |
| Billing attribution all-UNCLASSIFIED | MEDIUM | Add the three required span attributes (`revenium.subscriber.id`, `revenium.product.name`, `revenium.organization.name`) and re-run. Old events cannot be retroactively attributed — only future runs will classify correctly. |

---

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Double-counting (callback + OTLP) | Phase 1: Metering | Single-call test: assert 1 Revenium event per LLM invocation |
| Streaming/async token counts missing | Phase 1: Metering | Stream-mode test call: assert token count > 0 in Revenium span |
| Reasoning tokens miscounted | Phase 1: Metering (model selection step) | Spot-check Anthropic invoice vs Revenium attribution for one Claude call |
| Trace/squad fragmentation | Phase 2: Trace/squad | Full graph run: assert exactly 1 squad with N expected spans in Revenium |
| Cost control race condition | Phase 3: Controls | Stop-watch test: measure time from threshold crossing to graph halt |
| Shadow/enforce mode confusion | Phase 3: Controls (pre-demo checklist) | Call rules API; assert `shadow: false` on all enforcement rules |
| Missing billing identifiers | Phase 4: Billing (setup before Phase 1) | Call `GET /billing/customers`; assert demo subscriber ID appears with non-zero cost |
| Wrong API key type | Phase 1: Day 1 setup | OTEL debug log shows successful export (not 401) after first test call |
| Speculative default model names | Phase 1: Day 1 configuration | Demo config explicitly sets model names; `validate_model` warning absent from startup log |

---

## Sources

- Revenium OTLP Integration docs: https://docs.revenium.io/integrations/otlp-integration
- Revenium billing tutorial: https://docs.revenium.io/monetize-your-ai/tutorial-build-usage-based-billing
- Revenium customer management: https://docs.revenium.io/monetize-your-ai/manage-customers-and-credentials
- `revenium-middleware-langchain` PyPI (archived, v0.1.3): https://pypi.org/project/revenium-middleware-langchain/
- `revenium-python-sdk` PyPI (unified, maintained): https://pypi.org/project/revenium-python-sdk/
- Revenium PyPI org page (all 12 packages): https://pypi.org/org/revenium/
- Double token counting — Langfuse issue #10914: https://github.com/langfuse/langfuse/issues/10914
- Double-counting at provider+LangChain layer — DataDog dd-trace-js #8936: https://github.com/DataDog/dd-trace-js/issues/8936
- Incomplete LLMResult in streaming (missing `llm_output`) — LangChain #34057: https://github.com/langchain-ai/langchain/issues/34057
- Incorrect token count in streaming — LangChain #30429: https://github.com/langchain-ai/langchain/issues/30429
- Token usage missing in LangGraph stream_mode="messages" — langgraph.js #1219: https://github.com/langchain-ai/langgraphjs/issues/1219
- LangGraph interrupt-resume trace fragmentation — Langfuse #10962: https://github.com/langfuse/langfuse/issues/10962
- LangGraph async context loss and orphaned spans — Last9 blog: https://last9.io/blog/troubleshooting-langchain-langgraph-traces-issues-and-fixes/
- LangGraph OTel instrumentation guide: https://last9.io/blog/langchain-and-langgraph-instrumentation-guide/
- .planning/codebase/CONCERNS.md (known issues: global config singleton, `.func` bypass, speculative model names, SQLite double-open)
- .planning/codebase/TESTING.md (test-without-live-keys discipline, mock patterns)
- .planning/codebase/ARCHITECTURE.md (LLM client factory, callback attachment points, vendor routing layer)

---
*Pitfalls research for: Revenium × TradingAgents FCAT demo — metering/traces/controls/billing on multi-provider LangGraph*
*Researched: 2026-06-26*
