# GAP-04-LINK: Billing uses rev_sk_ key; per-agent meter linked via agenticJobId

**Task ID:** 260629-mde-gap-04-link-billing-uses-rev-sk-key-per-
**Date:** 2026-06-29

## Objective

Unify the billing key under `revenium_sk_api_key` (the `rev_sk_*` write key already
used for setup/enforcement), and link each per-agent metering completion to the
billing job via `extra_body={"agenticJobId": trace_id}`.

## Tasks

1. `default_config.py` — add `revenium_sk_api_key` config key + `_ENV_OVERRIDES` entry.
2. `billing.py` `from_config` — read billing key from `revenium_sk_api_key` (primary).
3. `callback.py` `on_llm_end` — attach `extra_body={"agenticJobId": trace_id}` when trace_id non-empty.
4. `validate_billing.py` — keyless gate reads `revenium_sk_api_key`.
5. `.env.example` — update billing subsection to use `REVENIUM_SK_API_KEY`.
6. Tests — `test_billing_emitter.py` + `test_revenium_enforcement.py`.
