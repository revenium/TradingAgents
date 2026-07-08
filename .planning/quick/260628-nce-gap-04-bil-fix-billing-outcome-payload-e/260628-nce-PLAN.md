---
phase: quick-260628-nce
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - tradingagents/revenium/billing.py
  - scripts/validate_billing.py
  - .env.example
  - tests/test_billing_emitter.py
autonomous: true
requirements: [BIL-01, BIL-02]
must_haves:
  truths:
    - "emit_billing_event posts an outcome payload that report_outcome accepts live (executionStatus + JSON-string metadata)"
    - "validate_billing.py posts the same corrected payload and documents the host-only profitstream base URL"
    - ".env.example documents REVENIUM_PROFITSTREAM_BASE_URL as host-only with a rev_sk_ write-key note"
    - "Keyless billing tests pass and assert the corrected payload shape (no result key; metadata is a round-trippable JSON string)"
  artifacts:
    - path: "tradingagents/revenium/billing.py"
      provides: "Corrected outcome payload in emit_billing_event"
      contains: "executionStatus"
    - path: "scripts/validate_billing.py"
      provides: "Corrected payload + host-only docstring guidance"
      contains: "executionStatus"
    - path: ".env.example"
      provides: "Host-only profitstream base URL guidance + write-key note"
      contains: "REVENIUM_PROFITSTREAM_BASE_URL"
    - path: "tests/test_billing_emitter.py"
      provides: "Assertions for executionStatus + JSON-string metadata"
      contains: "json.loads"
  key_links:
    - from: "tradingagents/revenium/billing.py"
      to: "report_outcome"
      via: "outcome payload dict"
      pattern: "executionStatus"
---

<objective>
GAP-04-BIL: the Revenium Jobs/Outcomes `report_outcome` call fails live because the
outcome payload and host guidance are wrong. Three confirmed defects, all root-caused
against the real account during Phase 04 Wave 3 verification:

1. Payload sends `"result": "SUCCESS"` — the server requires `"executionStatus"`
   (allowed values: SUCCESS / FAILED / CANCELLED; "COMPLETED" is rejected).
   Missing it returns "Missing required parameter executionStatus".
2. Payload sends `metadata` as a dict — the server requires a String, returning
   "Expected type String for field metadata". It must be `json.dumps(...)`.
3. Host guidance points at the full path `https://api.prod.ai.hcapp.io/profitstream/v2/api`
   — the SDK appends `/profitstream/v2/api` itself, producing a doubled path and 404.
   The base URL must be HOST-ONLY `https://api.prod.ai.hcapp.io`, with a `rev_sk_`
   write-key note (the default `api.revenium.io` 403s on jobs writes).

Purpose: make `report_outcome` succeed against the live account (BIL-01/BIL-02) so the
monetize pillar lands for the FCAT demo.
Output: corrected payload in code + script, corrected host docs, updated keyless tests.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@./CLAUDE.md
@tradingagents/revenium/billing.py
@scripts/validate_billing.py
@.env.example
@tests/test_billing_emitter.py
</context>

<tasks>

<task type="auto">
  <name>Task 1: Fix the outcome payload in billing.py and validate_billing.py</name>
  <files>tradingagents/revenium/billing.py, scripts/validate_billing.py</files>
  <read_first>
    - tradingagents/revenium/billing.py lines 29-35 (imports) and 237-262 (the
      `_report_outcome_safe` closure with the broken payload at ~240-247).
    - scripts/validate_billing.py lines 37-49 (imports) and 159-174 (the
      `report_outcome` call with the broken payload at ~163-170).
  </read_first>
  <action>
    In tradingagents/revenium/billing.py: add `import json` to the module imports
    (alongside the existing `import logging` / `import threading`, keeping ruff isort
    ordering). In `emit_billing_event`'s `_report_outcome_safe` closure, rewrite the
    `payload` dict so it: (a) replaces the `"result": "SUCCESS"` key with
    `"executionStatus": "SUCCESS"`; (b) sets `"metadata"` to `json.dumps(meta)` (a JSON
    string, NOT the raw dict); (c) keeps `"outcomeType": "CONVERTED"`,
    `"outcomeValue": signal_price`, `"outcomeCurrency": "USD"`, and
    `"reportedBy": attributed_to` exactly as they are. The `_log_state`/debug log line
    that says `result=SUCCESS` may keep its wording (it is a log string, not the payload),
    but do not log the metadata or key.

    In scripts/validate_billing.py: add `import json` near the existing stdlib imports
    (argparse/os/sys/uuid), preserving ruff isort ordering. In the `client.report_outcome`
    call (~163-170), apply the identical payload fix: `"executionStatus": "SUCCESS"`
    instead of `"result": "SUCCESS"`, and `json.dumps({"ticker": ticker, "trade_date":
    trade_date})` for `"metadata"` instead of the raw dict. The line 198 dashboard-print
    that references `result=SUCCESS` may keep its prose wording.

    Do NOT introduce any fenced code or real API key. Do NOT touch the two pre-existing
    unrelated failing tests.
  </action>
  <verify>
    <automated>.venv/bin/python -c "import ast,sys; [ast.parse(open(f).read()) for f in ['tradingagents/revenium/billing.py','scripts/validate_billing.py']]; print('parse ok')" && grep -c 'executionStatus' tradingagents/revenium/billing.py scripts/validate_billing.py && grep -L 'json.dumps' tradingagents/revenium/billing.py scripts/validate_billing.py | grep -q . && echo "MISSING json.dumps" || echo "json.dumps present in both"</automated>
  </verify>
  <done>Both files import json; both payloads use `executionStatus: SUCCESS` and `metadata: json.dumps(...)`; neither payload contains a `result` key; outcomeType/outcomeValue/outcomeCurrency/reportedBy unchanged.</done>
</task>

<task type="auto">
  <name>Task 2: Correct profitstream host guidance in validate_billing.py docstring and .env.example</name>
  <files>scripts/validate_billing.py, .env.example</files>
  <read_first>
    - scripts/validate_billing.py module docstring lines 1-35 (especially the
      REVENIUM_PROFITSTREAM_BASE_URL note at 18-21 and Usage example at 33-34) and the
      dashboard-confirmation block at lines 196-201.
    - .env.example lines 59-87 (the Revenium metering / platform block) — note there is
      currently NO entry for REVENIUM_BILLING_API_KEY or REVENIUM_PROFITSTREAM_BASE_URL.
    - tradingagents/default_config.py lines 32-33 and 190-194 confirm the env-var names
      `REVENIUM_BILLING_API_KEY` -> `revenium_billing_api_key` and
      `REVENIUM_PROFITSTREAM_BASE_URL` -> `revenium_profitstream_url`.
  </read_first>
  <action>
    In scripts/validate_billing.py: rewrite the REVENIUM_PROFITSTREAM_BASE_URL docstring
    note (lines 18-21) and the dashboard-confirmation hint (lines 200-201) so they state
    the base URL must be HOST-ONLY `https://api.prod.ai.hcapp.io` (the SDK appends
    `/profitstream/v2/api` itself; supplying the full path produces a doubled path and a
    404). Keep the existing rev_sk_ write-key requirement note and add that the default
    host `https://api.revenium.io` returns 403 on jobs write endpoints. Update the Usage
    example on lines 33-34 if it shows a full-path host so it shows the host-only form.

    In .env.example: add a billing subsection (place it logically near the existing
    Revenium metering block ending at line ~87, before the circuit-breaker block at 89).
    Document `REVENIUM_BILLING_API_KEY=` (commented, empty default) with a note that it
    must be a `rev_sk_` write-scope key — a metering-only `rev_mk_` key 403s on jobs
    writes, and an empty value makes the billing emitter a silent no-op (DMO-04). Document
    `#REVENIUM_PROFITSTREAM_BASE_URL=https://api.prod.ai.hcapp.io` as HOST-ONLY (the SDK
    appends `/profitstream/v2/api`; do NOT include the path), and note the default
    `https://api.revenium.io` 403s on jobs writes. Match the existing comment style in the
    file (leading `#`, wrapped prose). Do NOT put any real key value in the file.
  </action>
  <verify>
    <automated>grep -q 'api.prod.ai.hcapp.io' .env.example && grep -q 'REVENIUM_PROFITSTREAM_BASE_URL' .env.example && grep -q 'REVENIUM_BILLING_API_KEY' .env.example && ! grep -E 'hcapp\.io/profitstream/v2/api' scripts/validate_billing.py && echo "host guidance corrected (no doubled path)"</automated>
  </verify>
  <done>.env.example documents both REVENIUM_BILLING_API_KEY (rev_sk_ write-key note) and REVENIUM_PROFITSTREAM_BASE_URL as host-only; validate_billing.py docstring no longer recommends the full-path host and explains the SDK appends the path; no real keys committed.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: Update keyless billing tests to assert the corrected payload shape</name>
  <files>tests/test_billing_emitter.py</files>
  <read_first>
    - tests/test_billing_emitter.py top docstring lines 1-17 (mentions `result == "SUCCESS"`)
      and the payload-shape test `test_emit_billing_event_payload_shape` at lines 176-213
      (currently asserts `payload["result"] == "SUCCESS"` at 207 and dict metadata access
      at 212-213, which break after Task 1).
  </read_first>
  <behavior>
    - test_emit_billing_event_payload_shape: payload has `executionStatus` in
      {SUCCESS, FAILED, CANCELLED} (specifically "SUCCESS" here); payload has NO `result`
      key (`"result" not in payload`); `payload["metadata"]` is a `str`; `json.loads`
      of it round-trips to a dict whose `ticker == "NVDA"` and `trade_date == "2026-06-28"`.
    - Unchanged assertions still hold: outcomeValue == signal_price, outcomeType ==
      "CONVERTED", outcomeCurrency == "USD", reportedBy == "test@example.com".
    - All tests remain keyless (no live REVENIUM_BILLING_API_KEY; SDK mocked).
  </behavior>
  <action>
    Add `import json` to the test module's imports. In `test_emit_billing_event_payload_shape`,
    replace the `assert payload["result"] == "SUCCESS"` assertion with
    `assert payload["executionStatus"] == "SUCCESS"` plus `assert payload["executionStatus"]
    in {"SUCCESS", "FAILED", "CANCELLED"}` and `assert "result" not in payload`. Replace the
    two dict-style metadata assertions (212-213) with: assert `payload["metadata"]` is a
    `str`, then `meta = json.loads(payload["metadata"])` and assert `meta["ticker"] ==
    "NVDA"` and `meta["trade_date"] == "2026-06-28"`. Update the module docstring (lines
    9-14) wording that references `result == "SUCCESS"` to reflect the executionStatus +
    JSON-string-metadata contract. Leave the float/env-override, disabled-emitter,
    fail-open, and keyless-skip tests untouched. Do NOT modify the two pre-existing
    unrelated failing tests (test_ollama_base_url, test_temperature_config deepseek) —
    they live in other files and are out of scope.
  </action>
  <verify>
    <automated>.venv/bin/python -m pytest tests/test_billing_emitter.py -x -q</automated>
  </verify>
  <done>tests/test_billing_emitter.py passes keyless; the payload-shape test asserts executionStatus, absence of `result`, and a JSON-string metadata that json.loads round-trips with ticker/trade_date.</done>
</task>

</tasks>

<verification>
- `.venv/bin/python -m pytest tests/test_billing_emitter.py -q` passes (keyless, no live key).
- `.venv/bin/ruff check tradingagents/revenium/billing.py scripts/validate_billing.py tests/test_billing_emitter.py` is clean (import sorting for the new `import json`).
- `grep` confirms `executionStatus` present and `result` absent in both payloads.
- No real API key string appears in any committed file: `! grep -RE 'rev_sk_[A-Za-z0-9]{8,}' tradingagents/ scripts/ tests/ .env.example`.
</verification>

<success_criteria>
- emit_billing_event and validate_billing.py both post `executionStatus: SUCCESS` with `metadata` as a `json.dumps` string; no `result` key remains.
- validate_billing.py docstring and .env.example document REVENIUM_PROFITSTREAM_BASE_URL as host-only `https://api.prod.ai.hcapp.io` with a rev_sk_ write-key note and the api.revenium.io 403 caveat.
- Keyless test suite for billing passes and asserts the corrected payload shape.
- The two pre-existing unrelated failing tests are untouched.
</success_criteria>

<output>
Create `.planning/quick/260628-nce-gap-04-bil-fix-billing-outcome-payload-e/260628-nce-SUMMARY.md` when done.
</output>
