"""Revenium attribution config helpers.

This module is the single source of truth for translating TradingAgents'
process-global config dict into the Revenium attribution fields used by
the callback handler (Plan 02), setup script (Plan 01), and billing emitter
(Plan 04).

Design rationale:
- Centralising here avoids duplicating the D-01..D-03 string literals across
  the setup script, callback handler, and billing emitter.  Every consumer
  calls attribution_from_config() instead of hard-coding names.
- Config values are read at call time (get_config() deepcopy) to honour the
  existing project convention of not reading config at import time.
- The task-type map (D-11) is provided as a helper so callback and context
  modules share the same lookup without reaching back into DEFAULT_CONFIG.

Key invariants:
- Returned dicts use the exact field names expected by ReveniumCallbackHandler
  and the Revenium metering REST payload (camelCase for API surface, snake_case
  for internal config keys).
- The setup script (scripts/setup_revenium.py) reads from this module; any
  changes to attribution values must be made in DEFAULT_CONFIG only.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def attribution_from_config(config: dict) -> dict:
    """Return Revenium attribution fields derived from the TradingAgents config.

    Pulls ``revenium_organization_name``, ``revenium_product_name``, and
    ``revenium_subscriber_id`` from the passed config dict (a deep copy of
    DEFAULT_CONFIG after env-var overrides).

    Returns a dict with the camelCase field names expected by Revenium's
    metering API and callback handler:
        {
            "organizationName": str,
            "productName":      str,
            "subscriber_id":    str,   # used as subscriber.id in the API
            "api_key":          str,   # rev_mk_* metering key (may be empty)
            "api_url":          str,
        }

    When the api_key is empty the caller (callback handler, setup script)
    should treat metering as disabled (D-05).
    """
    return {
        "organizationName": config.get("revenium_organization_name", "Revenium-Research-Desk"),
        "productName":      config.get("revenium_product_name", "trading-signal"),
        "subscriber_id":    config.get("revenium_subscriber_id", ""),
        "api_key":          config.get("revenium_api_key", ""),
        "api_url":          config.get("revenium_api_url", "https://api.revenium.ai"),
    }


def task_type_for_node(node_name: str, config: dict) -> str:
    """Return the Revenium task_type label (D-11) for a given LangGraph node name.

    Falls back to ``"unknown"`` for node names not in the taxonomy so that
    new agents added to the graph do not cause a KeyError in the callback handler.
    """
    task_type_map: dict[str, str] = config.get("revenium_task_type_map", {})
    result = task_type_map.get(node_name, "unknown")
    if result == "unknown":
        logger.debug("No task_type mapping for node %r — using 'unknown'", node_name)
    return result
