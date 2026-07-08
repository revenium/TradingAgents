# Stack Research

**Domain:** Revenium instrumentation of a multi-provider LangChain/LangGraph Python application
**Researched:** 2026-06-26
**Confidence:** HIGH (package names, versions, and provider coverage verified against PyPI JSON API and official GitHub README; all claims sourced from official Revenium repositories and docs)

---

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| `revenium-python-sdk[langchain]` | 0.1.9 | LangChain callback handler for automatic LLM metering across all providers | The unified SDK; the individual `revenium-middleware-langchain` package is archived and redirects to this. Single install covers every LangChain provider class (OpenAI, Anthropic, Google, Bedrock, Azure, Ollama). Matches TradingAgents' existing LangChain callback pattern (`cli/stats_handler.py`). |
| `revenium-metering` | 6.8.2 | Low-level typed Python client for explicit REST API calls to `/v1/meter_ai_completion`, `/v1/meter_tool_event`, etc. | Required as a transitive dep of `revenium-python-sdk`, but also the right tool for any calls outside the auto-instrumented surface: the tool-metering `@meter_tool` decorator, the `AgenticOutcomeClient`, and any explicit `create_completion` calls for providers not covered by the callback handler. Pydantic-typed request/response models, sync and async clients. |
| `revenium-python-sdk` (core only, no extra) | 0.1.9 | Provides `revenium_middleware.revenium_metadata`, `revenium_middleware.revenium_meter`, `revenium_middleware.meter_tool`, `idempotency_key`, and `configure()` | Core SDK ships these cross-cutting utilities regardless of provider extra. Install without an extra when you only need decorators or explicit metering (not provider monkey-patching). |

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `python-dotenv` | >=1.0.0 (already in project) | Load `REVENIUM_METERING_API_KEY` and other env vars from `.env` | Always; already declared in TradingAgents `pyproject.toml`. |
| `opentelemetry-sdk` + `opentelemetry-exporter-otlp-proto-http` | current | Ship spans/metrics to Revenium OTLP endpoint | Only if switching to OTLP path (see "OTLP vs Middleware" section below). Not recommended for this project. |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| `REVENIUM_LOG_LEVEL=DEBUG` | Expose provider detection decisions, metering payloads, and routing | Set in `.env` during development; set to `INFO` or `WARNING` in demo mode to reduce terminal noise. |
| Revenium dashboard at `https://api.revenium.ai` | Visualise metered traces, squad analytics, cost controls, billing | All four pillars live here; no extra tooling needed. |

---

## Installation

```bash
# In the TradingAgents venv (.venv), activate then:

# Primary: LangChain callback-based automatic metering for all providers
pip install "revenium-python-sdk[langchain]"

# If the LangChain extra doesn't pull revenium-metering transitively at >=6.8.2,
# pin it explicitly (it is required for @meter_tool and AgenticOutcomeClient):
pip install "revenium-metering>=6.8.2"
```

Add to `pyproject.toml` under `[project.dependencies]`:

```toml
"revenium-python-sdk[langchain]>=0.1.9",
"revenium-metering>=6.8.2",
```

---

## Provider Coverage Matrix

This is the critical table for TradingAgents. The `[langchain]` extra installs `revenium_middleware_langchain.ReveniumCallbackHandler`, which auto-detects providers from LangChain class names and model name prefixes.

| TradingAgents Provider | LangChain Class Used | Auto-Metered by Callback Handler? | Notes |
|------------------------|---------------------|----------------------------------|-------|
| Anthropic (native) | `ChatAnthropic` | YES | Auto-detected from class name. |
| Google Gemini (native) | `ChatGoogleGenerativeAI` | YES | Auto-detected as `google`. |
| Azure OpenAI | `AzureChatOpenAI` | YES | Auto-detected from class name; deployment name resolved to standard model name for pricing. |
| AWS Bedrock | `ChatBedrockConverse` (via `langchain-aws`) | YES | `ChatBedrock` / `BedrockLLM` listed in provider matrix. `ChatBedrockConverse` is the Converse API subclass — verify in first integration test; fall back to `revenium-metering` explicit call if not detected. |
| OpenAI (direct) | `ChatOpenAI` | YES | Auto-detected from class name. |
| xAI / DeepSeek / Qwen / GLM / MiniMax / OpenRouter / Mistral / Kimi / Groq / NVIDIA | `ChatOpenAI` (subclass via `OpenAIClient`) | PARTIAL — LOW CONFIDENCE | These all use `ChatOpenAI` under the hood with a different `base_url`. The callback handler detects the LangChain class name (`ChatOpenAI`), so it will meter them as "openai" — meaning token counts are captured but the provider label will be wrong (shows "openai" not "deepseek" etc.). Cost calculation may be inaccurate for non-OpenAI pricing. Mitigation: pass `usage_metadata={"agent": "market-analyst", "task_type": "deepseek"}` via the `trace_id`/`agent` fields to add context. |
| Ollama | `ChatOpenAI` (via `OpenAIClient` with local base URL) | PARTIAL — same issue as above | Shows as "openai" provider in Revenium. For accurate Ollama labeling, use the `[ollama]` extra separately and instrument the native `ollama` SDK directly; but TradingAgents routes through LangChain, not native Ollama SDK. |
| `openai_compatible` | `ChatOpenAI` | PARTIAL | Same as above. |

**Key insight:** Any provider that flows through `ChatOpenAI` with a custom `base_url` (i.e., all 15 OpenAI-compatible providers in TradingAgents) will be labeled "openai" by the LangChain callback handler. For the FCAT demo, the multi-provider story is best told by running Anthropic (native `ChatAnthropic`) for some agents and OpenAI (direct) for others — those two will show correct provider labels. The mislabeling of base-URL variants is a Revenium limitation on the LangChain path, not a TradingAgents issue.

---

## Auth / Config

### Required

| Env Var | Description |
|---------|-------------|
| `REVENIUM_METERING_API_KEY` | API key for the Revenium account/instance. Must start with `hak_` or `rev_`. Set in `.env` (already in `.gitignore`). |

### Optional but Relevant for This Project

| Env Var | Default | What It Does |
|---------|---------|--------------|
| `REVENIUM_METERING_BASE_URL` | `https://api.revenium.ai` | Override to point at a self-hosted or staging Revenium instance. |
| `REVENIUM_ENVIRONMENT` | auto-detected | Tag all metering events with `production` / `staging` / `dev`. |
| `REVENIUM_TRACE_TYPE` | — | Workflow category; set to e.g. `trading-analysis` to group all TradingAgents runs. |
| `REVENIUM_LOG_LEVEL` | `INFO` | Set to `DEBUG` during development. |
| `REVENIUM_CAPTURE_PROMPTS` | `false` | Enable to capture prompt/response text in Revenium. Off by default; enable only if the demo needs it. |
| `REVENIUM_CIRCUIT_BREAKER_ENABLED` | `false` | Enable the cost-control circuit breaker (OpenAI provider only in current SDK). Set `true` + `REVENIUM_TEAM_ID` for the cost-control demo pillar. |
| `REVENIUM_TEAM_ID` | — | Required when circuit breaker is enabled. Hashed team ID from Revenium account. |
| `REVENIUM_CB_FAIL_MODE` | `open` | `open` lets calls through if rules haven't loaded yet; `closed` blocks. Use `open` for demo reliability. |
| `REVENIUM_CB_POLL_INTERVAL_SECONDS` | `60` | How often the background thread refreshes enforcement rules. |

### Billing / Monetization Attribution

These are per-call metadata fields passed to `ReveniumCallbackHandler` or `usage_metadata={}`. They are not env vars.

| Field | Type | Use in TradingAgents |
|-------|------|---------------------|
| `trace_id` | str | One UUID per `propagate()` run — links every agent call within a single analysis. |
| `agent` | str | Agent name: `"market-analyst"`, `"bull-researcher"`, `"portfolio-manager"`, etc. |
| `organizationName` | str | Desk / strategy name for the FCAT demo billing story (e.g., `"FCAT-Research-Desk"`). Auto-created if not found. |
| `productName` | str | `"trading-signal"` — the billing unit. Auto-created if not found. |
| `subscriber.id` | str | Analyst / strategy ID for per-user attribution. |
| `task_type` | str | Phase label: `"analysis"`, `"research-debate"`, `"risk-debate"`, `"decision"`. |
| `parent_transaction_id` | str | Wire the debate-loop LLM calls under a parent transaction to reconstruct the agent hierarchy in Revenium traces. |
| `transaction_name` | str | Human-readable name: `"Bull vs Bear Round 2"`, `"Portfolio Decision"`. |

---

## OTLP vs Native Middleware / SDK

**Recommendation: Use the native `[langchain]` middleware. Do not use OTLP for this project.**

| Criterion | Native Middleware (`[langchain]` extra) | OTLP |
|-----------|----------------------------------------|------|
| Setup complexity | Single `pip install` + `REVENIUM_METERING_API_KEY` | Requires `opentelemetry-sdk`, `opentelemetry-instrumentation-openai`/`anthropic`, OTLP exporter config |
| Provider label accuracy | Good for native LangChain classes; wrong for base-URL variants | Depends on OTel instrumentation library (also imperfect) |
| Token counting | Handled by Revenium callback handler | Depends on OTel semantic conventions implementation |
| Cost controls / circuit breaker | Built-in (`BudgetExceededError`) | Not available via OTLP path |
| Agent attribution (`agent`, `trace_id`) | First-class fields in `ReveniumCallbackHandler` | Manual span attribute tagging |
| Billing metadata | `organizationName`, `productName`, `subscriber.id` in handler constructor | Manual span attribute tagging |
| Fit with existing code | Drops into `cli/stats_handler.py` pattern exactly — LangChain callback | Requires instrumentation at a lower layer |
| When OTLP makes sense | If your app already emits OTel and you don't control its code | — |

The existing `cli/stats_handler.py` (`TradingAgentsStats`) already uses a LangChain `BaseCallbackHandler`. The `ReveniumCallbackHandler` is the same contract. The integration seam is adding it alongside the existing stats handler in `TradingAgentsGraph(callbacks=[stats_handler, revenium_handler])`.

---

## Cost Controls

Cost control rules are configured server-side in Revenium's UI or REST API. The Python SDK enforces them client-side via a circuit breaker that polls compiled rules.

**Current limitation (MEDIUM confidence):** The README explicitly states "Currently wired for the OpenAI provider (other providers land via per-provider follow-on tickets)." For the demo, this means `BudgetExceededError` on the circuit breaker path is only guaranteed when an OpenAI (`ChatOpenAI`) LLM call trips the rule. For Anthropic or Google agents, the budget check fires at metering time (server-side), not pre-call (client-side). This affects the demo narrative: either use an OpenAI model for the agent that demonstrates budget enforcement, or accept that the block happens asynchronously (spend is recorded but not pre-blocked).

```python
from revenium_middleware.openai import BudgetExceededError

try:
    response = llm.invoke(prompt)  # ChatOpenAI-backed agent
except BudgetExceededError as exc:
    # exc.rule_name, exc.current_value, exc.threshold, exc.resets_at
    print(f"Budget enforced: {exc.message}")
```

---

## Billing / Monetization

Billing attribution flows entirely through the `usage_metadata` fields on `ReveniumCallbackHandler` — no separate Python SDK calls needed for the per-run attribution story.

For the "cost per trading signal" unit, the pattern is:
1. Pass `productName="trading-signal"` on the handler (auto-creates in Revenium on first use).
2. Pass `organizationName="FCAT-Research-Desk"` to attribute to the customer.
3. In Revenium's UI under Revenue Sources, define a Pricing Tier or Metering Element for `trading-signal` with a per-unit rate and margin.
4. Full CRUD for products and subscribers is available via the Revenium REST API at `/api/v2/cost-controls` and `/api/v2/credentials`. The `revenium-metering` library's `ReveniumMetering` client can call these directly if programmatic customer/product creation is needed; or use the Revenium MCP connector (available in this environment) for ad-hoc setup.

---

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| `revenium-middleware-langchain` (standalone) | Archived; final version 0.1.3; no new features or bug fixes. | `revenium-python-sdk[langchain]` 0.1.9 |
| `revenium-middleware-openai` (standalone) | Also consolidated into `revenium-python-sdk`. The standalone package at 0.6.2 may lag the unified SDK's bug fixes. | `revenium-python-sdk[openai]` |
| OTLP path | Extra setup, no circuit breaker support, no native billing metadata fields, worse fit with LangChain callback pattern. | `revenium-python-sdk[langchain]` |
| `revenium-griptape` | Griptape-specific; irrelevant to this project. | — |
| Injecting `revenium_middleware_openai` as a side-effect import for LangChain metering | The `[openai]` extra monkey-patches the raw `openai` SDK, not LangChain — it conflicts with how LangChain manages the OpenAI client lifecycle and will double-meter or miss calls. | Use `ReveniumCallbackHandler` from `[langchain]` extra for all LangChain-mediated calls. |
| Using `revenium_middleware_anthropic` import alongside LangChain | Same issue — wraps the native `anthropic` SDK, not `langchain-anthropic`. | Use `ReveniumCallbackHandler` for LangChain paths. |

---

## Alternatives Considered

| Recommended | Alternative | When Alternative Makes Sense |
|-------------|-------------|------------------------------|
| `revenium-python-sdk[langchain]` callback handler | Individual provider middleware imports (`revenium_middleware_openai`, `revenium_middleware_anthropic`) | Only if the application calls provider SDKs directly (not via LangChain). TradingAgents does not — all calls go through LangChain classes. |
| Single `ReveniumCallbackHandler` per run with shared `trace_id` | Separate handler per agent | Never — one shared handler per `propagate()` call, with per-call `agent` metadata in `usage_metadata`. |
| Native middleware for cost controls demo | Server-side-only cost controls | Only if enforcing across all providers simultaneously; acceptable for demo if OpenAI handles the budget-trip segment. |

---

## Version Compatibility

| Package | Compatible With | Notes |
|---------|-----------------|-------|
| `revenium-python-sdk[langchain]` 0.1.9 | `langchain-core>=0.1.0`, `langchain>=0.1.16`, `langchain-openai>=0.1.0` | TradingAgents pins `langchain-core>=0.3.81` and `langchain-openai>=0.3.23` — both well above the minimum. No conflict expected. |
| `revenium-metering` 6.8.2 | `httpx<1,>=0.23.0`, `pydantic<3,>=1.9.0` | TradingAgents uses pydantic via LangChain; no direct conflict. Check `uv.lock` after install. |
| `revenium-python-sdk[langchain]` 0.1.9 | Python 3.8+ | TradingAgents uses Python 3.11; compatible. |

---

## Sources

- PyPI JSON API — `https://pypi.org/pypi/{package}/json` — version numbers for all 8 packages verified (HIGH confidence)
- GitHub README — `https://github.com/revenium/revenium-python-sdk/README.md` — provider support matrix, LangChain integration pattern, cost controls circuit breaker, env vars, metadata fields (HIGH confidence)
- PyPI package page — `https://pypi.org/org/revenium/` — full package list and release dates (HIGH confidence)
- `revenium-middleware-langchain` PyPI JSON — archive notice and supported LangChain classes confirmed (HIGH confidence)
- `docs.revenium.io/integrations/otlp-integration` — OTLP endpoint URLs, OTel env var names (MEDIUM confidence; page loaded partially)
- `docs.revenium.io` — billing/monetization structure (products, metering elements, subscriber attribution) (MEDIUM confidence; page loaded partially)

---

*Stack research for: Revenium instrumentation of TradingAgents (multi-provider LangChain/LangGraph)*
*Researched: 2026-06-26*
