# Phase 4: CLI Cost Panel & Billing Monetization — Discussion Log

**Date:** 2026-06-28
**Mode:** discuss (default)
*Human-reference only — not consumed by downstream agents (see 04-CONTEXT.md for the canonical decisions).*

## Areas selected for discussion
All four: Cost panel content & placement, Debate ×N annotation, Pricing & margin model, Billing trigger & halted runs.

## Questions & selections

### Cost panel content & placement (CLI-01)
- Options: dedicated panel ($+tokens, hotspot highlighted) / fold into footer / cost column in Progress panel
- **Selected:** Dedicated panel, $ primary + tokens secondary, hotspot highlighted → D-01..D-04

### Debate ×N annotation (CLI-02)
- Options: collapse to one row per agent with ×N + summed cost / one row per call / collapse with per-round expand
- **Selected:** Collapse to one row per agent role with ×N + summed cost → D-05..D-06

### Pricing & margin model (BIL-01/02)
- Options: flat $2.00/signal (margin = price − AI cost), configurable default / cost-plus multiplier / configurable no default
- **Selected:** Flat $2.00/signal, configurable default, margin = price − measured AI cost → D-07..D-08

### Billing trigger & halted runs
- Options: only on delivered decisions (halts don't bill) / every completed run / all runs, halts cost-only
- **Selected:** Only on runs that deliver a PM decision; circuit-breaker-halted runs emit no billing event → D-09..D-10

## Deferred ideas
- OpenRouter migration (later phase) — Phase 4 billing/cost work stays provider-agnostic; no direct Anthropic support.

## Claude's discretion
- Rich panel styling; exact Revenium billing/invoice API call; config key name for the configurable signal price.
