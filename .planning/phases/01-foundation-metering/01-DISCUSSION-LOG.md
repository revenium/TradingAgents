# Phase 1: Foundation & Metering - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-27
**Phase:** 1-Foundation & Metering
**Areas discussed:** Attribution values, Metering toggle, Account setup path, Metering labels/scope

---

## Attribution values

### Organization name
| Option | Description | Selected |
|--------|-------------|----------|
| FCAT-Research-Desk | Research placeholder; customer-framed for Fidelity | |
| Revenium-Demo | Vendor-framed; clearer it's a demo | |
| Revenium-Research-Desk (free text) | Blend of both | ✓ |

### Subscriber identity
| Option | Description | Selected |
|--------|-------------|----------|
| desk-a@fidelity.com | Research placeholder | |
| Use a real address | An address the owner controls | ✓ |

**Follow-up:** `john.demic+trading@revenium.io` (plus-addressed alias — deliverable, owner-controlled).

### Product & pricing
| Option | Description | Selected |
|--------|-------------|----------|
| trading-signal @ $2.00 | $1.20 AI cost + $0.80 margin | ✓ |
| Adjust the price | Tune margin to measured cost | |

**Notes:** Attribution is not retroactive — values must exist before the first metered call. Margin must stay positive vs measured run cost; revisit price if the ~$1.20 estimate is off.

---

## Metering toggle

### When to meter
| Option | Description | Selected |
|--------|-------------|----------|
| Auto when key present | Meter if REVENIUM_METERING_API_KEY set; silent no-op otherwise | ✓ |
| Explicit flag only | Meter only with --meter flag | |

### On failure
| Option | Description | Selected |
|--------|-------------|----------|
| Fail open (never block) | Log + drop event, run continues | ✓ |
| Fail loud | Surface error / stop run | |

### FND-04 validation delivery
| Option | Description | Selected |
|--------|-------------|----------|
| Standalone script | Re-runnable one-event live check | ✓ |
| Pytest (mocked + live marker) | Suite-friendly, live can't run in CI | |
| Both | Script + mocked unit test | |

**Notes:** Keeps suite green with no keys (DMO-04). Phase 3 cost gate is the deliberate exception that halts.

---

## Account setup path

### How to create the hierarchy
| Option | Description | Selected |
|--------|-------------|----------|
| Committed setup script | Idempotent scripts/setup_revenium.py, version-controlled | ✓ |
| MCP Dev connector now | Fast, not reproducible | |
| Manual Revenium UI | Simplest, undocumented | |

### Credentials location
| Option | Description | Selected |
|--------|-------------|----------|
| .env + .env.example | Documented placeholder, dotenv pattern | ✓ |
| Env only, no example | Less discoverable | |

### API key scope
| Option | Description | Selected |
|--------|-------------|----------|
| Metering key only (rev_mk_) | Least privilege for phases 1–4 | |
| Both rev_mk_ and rev_sk_ | Stage write key in case v2 Jobs/ROI pulled forward | ✓ |

**Notes:** Phase 1 consumes only rev_mk_; rev_sk_ provisioned but unused until v2.

---

## Metering labels & scope

### task_type taxonomy
| Option | Description | Selected |
|--------|-------------|----------|
| Pipeline-stage granular | analysis/research_debate/planning/trade/risk_debate/decision | ✓ |
| Coarse (3 buckets) | analysis/debate/decision | |

### Agent label
| Option | Description | Selected |
|--------|-------------|----------|
| Internal node names | 1:1 with graph code, no mapping | ✓ |
| Human-readable display names | Prettier, needs sync'd mapping table | |

### @meter_tool scope
| Option | Description | Selected |
|--------|-------------|----------|
| All analyst data-fetch tools | Fullest cost-iceberg; sentiment .func exempt | ✓ |
| Representative subset | Heaviest tools only | |

---

## Claude's Discretion

- Module/file layout within `tradingagents/revenium/`.
- Exact location of the model-name override (demo config dict vs `TRADINGAGENTS_*` env overrides).
- Precise contextvar wiring (follows research architecture + repo conventions).

## Deferred Ideas

- `rev_sk_` write-scope usage / Jobs API / ROI view — v2 (JOBS-01), key staged now.
- Finer per-agent provider routing beyond deep/quick split — not needed for the demo.
- Two Mermaid architecture diagrams requested by the owner as a comprehension/FCAT aid — produced alongside context (`01-ARCHITECTURE-DIAGRAMS.md`), not Phase 1 implementation scope.
