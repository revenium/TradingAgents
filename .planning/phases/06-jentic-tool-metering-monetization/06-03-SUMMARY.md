---
plan: 06-03
phase: 06-jentic-tool-metering-monetization
status: complete
requirements: [JEN-02, JEN-04]
date: 2026-07-03
commits:
  - 873213c  # register_jentic_tool (ToolResource per-call pricing) in setup_revenium.py
  - e4deb9b  # scripts/validate_jentic.py gated live-verify
---

# Plan 06-03 — Summary

## What was built

**Task 1 — `register_jentic_tool` in `scripts/setup_revenium.py` (commit 873213c):**
`register_jentic_tool(profitstream_host, sk_key, team_id, tool_id, unit_price, dry_run)` POSTs a `ToolResource` to `{host}/profitstream/v2/api/tools` with `pricing.elements:[{aggregationType:"COUNT", unitPrice}]`. `toolId` is sourced from the `jentic_tool_id` config (`jentic:news`) so it matches the emitted tool event. Host is HOST-ONLY from `revenium_profitstream_url`; 401/404 prints the alternate-host hint; 409 / "already exists" = idempotent success; missing SK key = keyless SKIP (DMO-04). Added `--jentic-tool` standalone flag.

**Task 2 — `scripts/validate_jentic.py` (commit e4deb9b):**
Gated live-verify (keyless SKIP without `JENTIC_AGENT_API_KEY`). JEN-LIST preflight (`list_apis()` asserts the news API is credentialed), prints the op inputs schema, JEN-EXEC (real `get_jentic_news.func()` execute, asserts non-sentinel), JEN-METER (patches `_send_tool_event`, asserts exactly 1 event `toolId=jentic:news`, forwards it live). Keys never printed.

**Task 3 — Operator live-verify: PASSED (2026-07-03).**

## Live verification (JEN-04) — PASSED 3/3

- **ToolResource registered** on host **`https://api.prod.ai.hcapp.io`** (resolves RESEARCH Open Question 1 / Assumption A1 — the live billing host accepts `POST /profitstream/v2/api/tools`; NOT `api.revenium.ai`). `toolId=jentic:news`, **$0.05/call COUNT**, idempotent.
- `validate_jentic.py --query "NVDA latest earnings news"` → **Jentic PASSED: 3/3**:
  - JEN-LIST: `newsapi.org/main` found among credentialed APIs
  - JEN-EXEC: real NewsAPI content (41 articles, e.g. Yahoo "Nvidia, Micron, and Broadcom…") — not the sentinel
  - JEN-METER: `@meter_tool` fired exactly 1 event with `toolId='jentic:news'`
- Metering key (`REVENIUM_METERING_API_KEY`) present in `.env`, so the event posts live to Revenium.

**Remaining operator glance:** confirm in the Revenium **Tools view** that `jentic:news` shows the event with a **non-zero per-call cost ($0.05)** — the final visual proof that the emitted `toolId` matches the registered `ToolResource`.

## Verification

- Full keyless suite: **556 passed** (551 + 5 new Jentic tests), 2 known-unrelated pre-existing failures — no regression.
- ruff clean on both scripts.
