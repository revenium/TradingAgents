"""SAIF safety/assurance gate: Revenium-metered governance check (PIL-03).

Purpose
-------
Provides two public objects:

``run_saif_assurance(decision_text: str) -> str``
    A metered mock governance gate decorated with
    ``@meter_tool(DEFAULT_CONFIG["saif_tool_id"])`` (default ``saif_assurance``).
    It inspects the rendered Portfolio Manager decision (the same markdown
    produced by ``render_pm_decision``) and returns a deterministic pass/flag
    governance verdict.

``create_saif_gate_node() -> Callable``
    Factory that returns a LangGraph node function
    ``saif_gate_node(state) -> {"saif_verdict": <verdict_json>}``.
    The node reads ``state["final_trade_decision"]``, calls
    ``run_saif_assurance``, and stores the result in the ``saif_verdict``
    state field.  It is wired into the graph ONLY when
    ``saif_tool_enabled=True`` in config (build-time flag in ``setup.py``).

Design invariants
-----------------
- **GATE, not a data tool** — ``run_saif_assurance`` is NOT a LangChain
  ``@tool`` and is NOT re-exported through ``agent_utils``.  SAIF sits
  AFTER the Portfolio Manager decision, not inside the analyst tool loop.
- **Fail-open** — ``create_saif_gate_node``'s inner node never raises;
  any exception from ``run_saif_assurance`` is caught and a fallback
  ``{"verdict": "PASS", ..., "source": "saif (fail-open)"}`` is returned
  as ``saif_verdict`` so the run always terminates cleanly (T-07-09).
- **No mutation of PM decision** — the node returns only ``{"saif_verdict":
  ...}``; ``final_trade_decision`` is never modified (T-07-07).
- **Single source of truth for toolId** — ``DEFAULT_CONFIG["saif_tool_id"]``
  is the ONLY place the toolId is defined; ``@meter_tool`` reads it at
  decoration time (T-07-10).  Never hardcode the string elsewhere.
- **Keyless no-op** — when ``revenium_api_key`` is empty, ``@meter_tool``
  is a silent no-op; the gate still returns a verdict (fully local mock).
- **Attribution** — the node sets ``current_agent_name`` to ``"saif_assurance"``
  for Revenium cost attribution (D-12 pattern, matches other agent nodes).
- **No key logging** — never logs ``decision_text`` in a way that could
  contain sensitive info; logs only symbolic verdicts (repo convention).
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.revenium.meter_tool import meter_tool

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Ratings that trigger a FLAG verdict (case-insensitive substring match on
# the extracted rating value from the rendered PM decision).
# ---------------------------------------------------------------------------

_FLAG_RATINGS: frozenset[str] = frozenset({"sell", "underweight"})

# Fallback verdict JSON returned when the gate is fail-open (T-07-09).
_FAIL_OPEN_VERDICT: str = json.dumps({
    "verdict": "PASS",
    "checks": [{"check": "fail_open", "status": "PASS", "note": "gate ran in fail-open mode"}],
    "notes": "SAIF gate: exception caught — fail open (T-07-09).",
    "source": "saif (fail-open)",
}, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _parse_rating(decision_text: str) -> str:
    """Extract the rating value from a rendered PM decision markdown string.

    The rendered PM decision uses ``**Rating**: <value>`` (produced by
    ``render_pm_decision`` in ``schemas.py``).  A simple regex extracts
    the value; returns an empty string if no match.
    """
    m = re.search(r"\*\*Rating\*\*:\s*(.+)", decision_text, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return ""


def _saif_mock_verdict(decision_text: str) -> str:
    """Deterministic local mock governance check.

    Parses the rating from the rendered PM decision and returns a JSON
    verdict string.  Verdict is deterministic (PASS/FLAG based on rating
    value) so tests can assert exact outcomes without mocking the gate
    logic itself.

    No network, no API key, no external dependency.
    """
    rating = _parse_rating(decision_text)
    rating_lower = rating.lower()

    # FLAG on negative disposition ratings (sell / underweight).
    verdict = "FLAG" if rating_lower in _FLAG_RATINGS else "PASS"

    checks = [
        {
            "check": "rating_appropriateness",
            "status": verdict,
            "note": (
                f"Rating '{rating}' triggers governance FLAG — adverse disposition"
                if verdict == "FLAG"
                else f"Rating '{rating}' within governance parameters"
            ),
        },
        {
            "check": "decision_completeness",
            "status": "PASS",
            "note": (
                "PM decision contains required fields (rating, executive summary, thesis)"
                if "Executive Summary" in decision_text
                else "PM decision may be incomplete"
            ),
        },
        {
            "check": "compliance_screening",
            "status": "PASS",
            "note": "No compliance keywords triggered in PM decision text",
        },
    ]

    output = {
        "verdict": verdict,
        "checks": checks,
        "notes": (
            f"SAIF governance review: {verdict}. "
            f"Rating='{rating}'. "
            f"{len(checks)} checks run."
        ),
        "source": "saif (mock)",
    }
    return json.dumps(output, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Public gate: @meter_tool wraps the mock implementation
# ---------------------------------------------------------------------------


@meter_tool(DEFAULT_CONFIG["saif_tool_id"])  # single source of truth (L6); no colon (T-07-10)
def run_saif_assurance(decision_text: str) -> str:
    """Inspect a rendered Portfolio Manager decision and return a governance verdict.

    This is the metered unit for SAIF (PIL-03): every call emits one
    ``saif_assurance`` tool event to Revenium when a metering key is present,
    metered+priced per-call by ``@meter_tool``.

    Parameters
    ----------
    decision_text:
        The rendered markdown from ``render_pm_decision(decision)``, i.e. the
        same string stored in ``AgentState["final_trade_decision"]``.

    Returns
    -------
    A JSON string with the governance verdict::

        {
            "verdict": "PASS" | "FLAG",
            "checks": [{"check": <name>, "status": "PASS"|"FLAG", "note": <str>}, ...],
            "notes": "<summary string>",
            "source": "saif (mock)"
        }

    Design notes
    ------------
    - NOT a LangChain ``@tool`` — do NOT import from ``agent_utils``.
    - Fully local mock — no network, no API key, no external dependency.
    - Metered per-call via ``@meter_tool`` so every call emits a
      ``saif_assurance`` Revenium tool event when a metering key is set.
    - FLAG on ``Sell``/``Underweight`` ratings; PASS otherwise.
    """
    return _saif_mock_verdict(decision_text)


# ---------------------------------------------------------------------------
# Graph node factory (Task 2)
# ---------------------------------------------------------------------------


def create_saif_gate_node() -> Any:
    """Return a LangGraph node function that runs the SAIF assurance gate.

    The returned node is wired into the graph AFTER the Portfolio Manager
    ONLY when ``saif_tool_enabled=True`` in config (build-time in
    ``setup.py``).  It reads ``state["final_trade_decision"]``, calls the
    metered ``run_saif_assurance`` gate, and returns a state delta with the
    ``saif_verdict`` field.

    The node is fail-open (T-07-09): any exception from the gate is caught
    and a fail-open verdict is stored in ``saif_verdict`` so the graph run
    always terminates cleanly.  The node NEVER modifies ``final_trade_decision``
    (T-07-07).

    Returns
    -------
    A callable ``saif_gate_node(state: dict) -> dict`` suitable for use as a
    LangGraph node.
    """

    def saif_gate_node(state: dict) -> dict:
        # D-12: set per-agent Revenium attribution so tool events carry the
        # correct agent name in the Revenium cost view.
        try:
            from tradingagents.revenium.context import current_agent_name  # noqa: PLC0415

            current_agent_name.set("saif_assurance")
        except Exception:  # noqa: BLE001 — attribution is best-effort; never block the run
            pass

        decision_text: str = state.get("final_trade_decision", "")
        try:
            verdict = run_saif_assurance(decision_text)
        except Exception as exc:  # noqa: BLE001 — fail-open (T-07-09)
            logger.debug(
                "SAIF gate: run_saif_assurance raised %s — returning fail-open verdict",
                type(exc).__name__,
            )
            verdict = _FAIL_OPEN_VERDICT

        return {"saif_verdict": verdict}

    return saif_gate_node
