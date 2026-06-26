# TradingAgents × Revenium Demo

## What This Is

An integration of **Revenium** (AI cost-management / FinOps platform) into the existing **TradingAgents** multi-agent LLM trading-research framework, built to **fully demonstrate Revenium's capabilities** on a real agentic workload. It is the CTO's hands-on vehicle for getting familiar with the agentic-trading problem space ahead of an engagement with **Fidelity's FCAT** group, and the artifact used to **demo Revenium live** to the FCAT team. TradingAgents' trading logic stays intact; the work is instrumentation, control, and a demo narrative layered on top.

## Core Value

A single live ticker run tells the complete Revenium story end to end — **meter → trace → control → monetize** — on a genuinely agentic, multi-provider trading workload. If everything else is cut, that one run must land for FCAT.

## Requirements

### Validated

<!-- Existing TradingAgents capabilities, confirmed from the codebase map (.planning/codebase/). These are relied upon and not being rebuilt. -->

- ✓ Multi-agent LangGraph pipeline (analysts → researcher debate → trader → risk debate → portfolio manager → BUY/HOLD/SELL) — existing
- ✓ Multi-provider LLM client layer (`llm_clients/`) routing Anthropic/Google/Azure/Bedrock natively and everything else via OpenAI-compatible clients — existing
- ✓ Vendor-routed data layer (`dataflows/interface.py`) with explicit per-category/per-tool vendor config — existing
- ✓ Tool/function calling grouped into per-analyst LangGraph ToolNodes — existing
- ✓ Cross-run decision log + reflection memory (`~/.tradingagents/`) — existing
- ✓ Interactive Rich CLI with live progress and token/tool usage tracking via LangChain callbacks (`cli/stats_handler.py`) — existing

### Active

<!-- The Revenium demo. All are hypotheses until shipped and validated in a dry-run of the demo. -->

- [ ] **Metering**: Every LLM call across all providers is metered to Revenium with per-agent, per-model, per-provider cost, token, and latency context, via Python middleware wrapping `llm_clients/`
- [ ] **Trace / squad analytics**: A full `propagate()` run appears in Revenium as a single trace/squad showing the multi-agent flow, with the debate loops surfacing as the cost hotspot (bottleneck / circular-communication insight)
- [ ] **Cost controls**: A threshold/limit (per-run spend or debate-round cost) that visibly alerts or halts a runaway analysis during the demo
- [ ] **Billing / monetization**: A run's cost attributed to a customer (desk/strategy) and turned into a priced unit — **"cost per trading signal"** with margin — shown in Revenium's FinOps view
- [ ] **In-repo CLI cost panel**: A live per-agent cost panel added to the existing Rich CLI so cost is visible in-app, not only in Revenium's UI
- [ ] **Demo narrative**: A repeatable, reliable single-run script that walks the meter→trace→control→monetize arc on a chosen ticker

### Out of Scope

- Changing TradingAgents' trading/decision logic — this is an instrumentation + demo project, not a trading-quality project
- Productionizing / hardening for real money or real trading — demo-grade is sufficient
- Replacing the existing data-vendor or LLM-provider abstractions — Revenium attaches to them, it does not refactor them
- Building a bespoke analytics dashboard — Revenium's own product UI is the analytics surface (plus the lightweight in-repo CLI panel)
- Broad multi-ticker / backtest cost reporting — the demo is a focused single live run

## Context

- **Audience**: Fidelity FCAT (Center for Applied Technology) — a technical R&D group evaluating agentic trading. The demo must be credible to engineers and resonate with a trading/FinOps mindset.
- **Dual purpose**: (1) CTO familiarization with the agentic-trading use case and problem space; (2) live capability demo of Revenium.
- **Why TradingAgents fits**: it is a real agentic workload — many LLM calls, multiple providers, tool calls, and looping bull/bear and risk debates — exactly the spend pattern Revenium meters, traces, and controls. The debate loops are the natural cost hotspot the trace/control pillars showcase.
- **Existing seam**: `cli/stats_handler.py` already collects token/tool usage via LangChain callbacks, and all model construction funnels through `llm_clients/factory.py` — both are natural attachment points for Revenium metering and the CLI cost panel.
- **Revenium pillars to exercise**: metering & cost tracking, trace/squad analytics & insights, cost controls, and billing/monetization — all four.
- Revenium docs / LLM reference: https://revenium.readme.io/llms.txt

## Constraints

- **Tech stack**: Python, LangGraph/LangChain, Revenium Python SDK/middleware. Integration must respect the existing multi-provider abstraction — no hardcoding a provider in agents or clients (per repo conventions).
- **Providers**: Multi-provider in the demo (e.g., different agents on Anthropic vs OpenAI) to show Revenium's cross-provider cost view; balanced against live-demo reliability.
- **Timeline**: ~2–4 weeks of runway to the FCAT demo — room to build all four pillars plus polish.
- **Demo reliability**: Live-on-stage; the single-run arc must be repeatable and resilient (graceful fallback if a provider hiccups).
- **Revenium environment**: Targets a Revenium instance/account for live data (a Revenium MCP dev connector is available in this environment) — exact account/org and credentials to be confirmed.
- **Test discipline**: Repo tests must pass without live API keys (mocked); Revenium calls must be mockable and not required for the suite to pass.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Demonstrate all four Revenium pillars | "Fully demonstrate capabilities" for FCAT | — Pending |
| Integrate via Python SDK/middleware wrapping `llm_clients/` | Automatic, provider-agnostic metering at the single seam all calls pass through | — Pending |
| Multi-provider in the demo | Strengthens the cross-provider cost narrative for FCAT | — Pending |
| Demo spine: meter → trace → control → monetize (single run) | One continuous live story maps cleanly onto the four pillars | — Pending |
| Billing unit = "cost per trading signal", attributed to a desk/strategy, with margin | A FinOps unit a trading audience immediately understands | — Pending |
| Both Revenium product UI and a new in-repo CLI cost panel | Cost visible in-app and in Revenium; richer live demo | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-06-26 after initialization*
