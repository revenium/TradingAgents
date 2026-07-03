"""Idempotent Revenium attribution-hierarchy provisioning script.

Creates or verifies the Org → Subscriber → Product → Subscription chain
in Revenium before any metered trading-agent call.  Re-running the script
is safe: each entity is looked up by its natural key (name / email /
product name) before creation, and existing entities are reported as
"exists" rather than creating duplicates (D-08).

Also supports registering per-call Revenium ToolResource pricing for the
Jentic-backed news tool (JEN-02).  Run with ``--jentic-tool`` to register
the ToolResource independently of the attribution hierarchy.

SCOPING NOTE — tenantId vs teamId:
    - Organizations are TENANT-scoped (tenantId on GET query + POST body).
    - Products are TEAM-scoped (teamId in POST body; GET ?teamId=...).
    - Subscribers and Subscriptions use neither as a scope param.
    Passing a teamId where tenantId is expected returns 404.

Attribution values (org/product/subscriber names) are read from
tradingagents.revenium.config (D-01..D-03).  Credentials and platform IDs
are read from environment variables:

    REVENIUM_SK_API_KEY            — rev_sk_* write/management key (required;
                                      D-10 least-privilege split)
    REVENIUM_TENANT_ID             — tenant scope for organizations (required)
    REVENIUM_TEAM_ID               — team scope for products (required)
    REVENIUM_OWNER_ID              — owner id for product creation (required)
    REVENIUM_PLATFORM_BASE_URL     — optional; defaults to
                                      https://api.prod.ai.hcapp.io/profitstream/v2/api
    REVENIUM_PROFITSTREAM_BASE_URL — optional; HOST-ONLY form used for tool pricing;
                                      defaults to the revenium_profitstream_url config
                                      key (https://api.revenium.io by default).
                                      For live runs use: https://api.prod.ai.hcapp.io

NOTE on host/path split:
    The Revenium **management** API (org/subscriber/product/subscription CRUD)
    is served at a different host and path than the metering hot-path:

        Management host:  https://api.prod.ai.hcapp.io/profitstream/v2/api
        Metering host:    https://api.revenium.ai  (used by Plan 02, untouched here)

    The Tools API for ToolResource pricing uses the profitstream host (host-only):
        Tools host:       https://api.prod.ai.hcapp.io → /profitstream/v2/api/tools

    Auth for all management/tools APIs uses the ``x-api-key`` header, NOT Bearer.

Usage:
    # Dry run — print intended actions, exit 0, no writes:
    REVENIUM_SK_API_KEY=rev_sk_... REVENIUM_TENANT_ID=... REVENIUM_TEAM_ID=... \\
    REVENIUM_OWNER_ID=... .venv/bin/python scripts/setup_revenium.py --dry-run

    # Live run — create/verify hierarchy in Revenium account:
    REVENIUM_SK_API_KEY=rev_sk_... REVENIUM_TENANT_ID=... REVENIUM_TEAM_ID=... \\
    REVENIUM_OWNER_ID=... .venv/bin/python scripts/setup_revenium.py

    # Register Jentic tool pricing (standalone — TENANT_ID and OWNER_ID not needed):
    REVENIUM_SK_API_KEY=rev_sk_... REVENIUM_TEAM_ID=... \\
    REVENIUM_PROFITSTREAM_BASE_URL=https://api.prod.ai.hcapp.io \\
        .venv/bin/python scripts/setup_revenium.py --jentic-tool

    # With an override base URL (staging):
    REVENIUM_PLATFORM_BASE_URL=https://staging.hcapp.io/profitstream/v2/api \\
        .venv/bin/python scripts/setup_revenium.py --dry-run

Security:
    - Key material is never printed or logged (repo convention: log symbolic names only).
    - The rev_sk_ key is validated for prefix format before any API call (Pitfall 8).
    - tenant/team/owner IDs are platform identifiers, not secrets; they may be printed.
    - This script intentionally WRITES to Revenium (provisioning exception to fail-open).
      The fail-open convention applies to the metering hot path (Plan 02), not here.

Idempotency invariant:
    Re-running the live script reports each entity as "exists" rather than
    creating duplicates.  Lookup is by natural key (org name / subscriber
    email / product name / toolId).
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Any

import requests

# ---------------------------------------------------------------------------
# Attribution values — read from config helper (single source of truth, D-01..D-03)
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from tradingagents.default_config import DEFAULT_CONFIG
    from tradingagents.revenium.config import attribution_from_config

    _attr = attribution_from_config(DEFAULT_CONFIG)
    ORG_NAME = _attr["organizationName"]
    PRODUCT_NAME = _attr["productName"]
    SUBSCRIBER_EMAIL = _attr["subscriber_id"]
except ImportError as _exc:
    # Fail early with a clear message if the package is not installed.
    print(f"FAIL: could not import tradingagents package — {_exc}")
    print("      Run: pip install -e . (or uv pip install -e .)")
    sys.exit(1)

# Management API base URL — separate from the metering host (revenium_api_url / Plan 02).
# Override via REVENIUM_PLATFORM_BASE_URL without touching the metering config.
_DEFAULT_PLATFORM_BASE_URL = "https://api.prod.ai.hcapp.io/profitstream/v2/api"

# ---------------------------------------------------------------------------
# Cost-rule provisioning constants (CTL-04, D-06/D-07)
# ---------------------------------------------------------------------------
DEMO_RULE_NAME = "TradingAgents Demo Budget"
DEMO_RULE_HARD_LIMIT = 1.00    # $1.00 DAILY — tune per timing dry-run
DEMO_RULE_WARN_THRESHOLD = 0.50


# ---------------------------------------------------------------------------
# Key / env-var validation helpers
# ---------------------------------------------------------------------------

_VALID_SK_PREFIXES = ("rev_sk_",)


def _validate_sk_key(key: str) -> None:
    """Validate the write/management key prefix; exit 1 with a human-readable message on mismatch."""
    if not any(key.startswith(p) for p in _VALID_SK_PREFIXES):
        # Don't print the key; print only the prefix shape (Pitfall 8)
        print("FAIL: REVENIUM_SK_API_KEY has an unexpected prefix.")
        print(f"      Expected prefix(es): {', '.join(_VALID_SK_PREFIXES)}")
        print("      Example correct format: rev_sk_xxxxxxxx...")
        print("      Get this key from: Revenium dashboard -> Settings -> API Keys")
        sys.exit(1)


def _require_env(name: str, description: str) -> str:
    """Return the env var value; print a human-readable error and exit 1 if missing."""
    value = os.getenv(name, "")
    if not value:
        print(f"FAIL: {name} is not set.")
        print(f"      {description}")
        return ""
    return value


# ---------------------------------------------------------------------------
# REST client helpers
# ---------------------------------------------------------------------------

def _headers(sk_key: str) -> dict[str, str]:
    """Build auth headers for the Revenium management API.

    The platform management API authenticates via ``x-api-key``, NOT Bearer.
    """
    return {
        "x-api-key": sk_key,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _get(
    base_url: str,
    path: str,
    sk_key: str,
    params: dict | None = None,
) -> Any:
    """GET from Revenium management REST API; return parsed JSON.

    Each caller is responsible for supplying the correct scope params
    (tenantId for org endpoints, teamId for product endpoints, neither for
    subscriber/subscription endpoints).  This helper does NOT inject teamId
    automatically — the old blanket-injection was the source of 404s.
    """
    url = f"{base_url.rstrip('/')}{path}"
    resp = requests.get(url, headers=_headers(sk_key), params=params or {}, timeout=15)
    resp.raise_for_status()
    return resp.json()


def _post(
    base_url: str,
    path: str,
    sk_key: str,
    payload: dict,
) -> Any:
    """POST to Revenium management REST API; return parsed JSON.

    Scope identifiers (tenantId / teamId / ownerId) must be included by the
    caller in ``payload`` where the API requires them in the request body.
    """
    url = f"{base_url.rstrip('/')}{path}"
    resp = requests.post(
        url,
        headers=_headers(sk_key),
        json=payload,
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def _patch(
    base_url: str,
    path: str,
    sk_key: str,
    payload: dict,
) -> Any:
    """PATCH to Revenium management REST API; return parsed JSON.

    Used by the cost-rule idempotency path to update an existing rule's
    shadowMode/enabled state without recreating it.
    """
    url = f"{base_url.rstrip('/')}{path}"
    resp = requests.patch(
        url,
        headers=_headers(sk_key),
        json=payload,
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Defensive list-extraction helper
# ---------------------------------------------------------------------------

def _extract_list(data: Any) -> list:
    """Extract a list from a response that may be a bare array or a paginated envelope.

    Revenium list endpoints may return:
    - A bare JSON array: [...]
    - Spring-style pagination: {"content": [...], "totalElements": N, ...}
    - HAL-style: {"_embedded": {"<type>List": [...]}}
    - A dict with an "items" key: {"items": [...]}

    Returns an empty list if none of the above match.
    """
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        if "content" in data and isinstance(data["content"], list):
            return data["content"]
        if "_embedded" in data and isinstance(data["_embedded"], dict):
            for val in data["_embedded"].values():
                if isinstance(val, list):
                    return val
        if "items" in data and isinstance(data["items"], list):
            return data["items"]
    return []


# ---------------------------------------------------------------------------
# Entity create-or-verify helpers
# ---------------------------------------------------------------------------

def _setup_organization(base_url: str, sk_key: str, tenant_id: str, dry_run: bool) -> str | None:
    """Create or verify the Revenium Organization (tenant-scoped).

    Organizations use tenantId (NOT teamId) on both the GET query and the
    POST body.  Passing teamId here returns 404.

    Returns the organization ID on success, None on dry-run or error.
    """
    print(f"  Organization: '{ORG_NAME}'")
    if dry_run:
        print(f"    [dry-run] Would GET /organizations?tenantId={tenant_id} (find by name)")
        print("    [dry-run] Would POST /organizations {name, tenantId} if not found")
        return None

    # Lookup by tenantId; match by exact name client-side
    try:
        data = _get(base_url, "/organizations", sk_key, params={"tenantId": tenant_id})
        for org in _extract_list(data):
            if org.get("name") == ORG_NAME:
                org_id = str(org.get("id", ""))
                print(f"    exists (id={org_id or 'n/a'})")
                return org_id or None
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 404:
            pass  # No orgs yet — fall through to create
        else:
            _handle_http_error("Organization lookup", exc)
            return None

    # Create — tenantId is a REQUIRED body field
    try:
        result = _post(base_url, "/organizations", sk_key, {"name": ORG_NAME, "tenantId": tenant_id})
        org_id = str(result.get("id", ""))
        print(f"    created (id={org_id or 'n/a'})")
        return org_id or None
    except requests.HTTPError as exc:
        _handle_http_error("Organization create", exc)
        return None


def _setup_subscriber(
    base_url: str, sk_key: str, org_id: str | None, dry_run: bool
) -> str | None:
    """Create or verify the Revenium Subscriber.

    Lookup uses the dedicated /subscribers/lookup-by-email?email= endpoint
    (NOT /subscribers?email=).  A 404 on the lookup means "not found" —
    treat it as a signal to create, not a fatal error.

    Create sends organizationIds as a REQUIRED array (org must exist first).

    Returns the subscriber ID on success, None on dry-run or error.
    """
    print(f"  Subscriber: '{SUBSCRIBER_EMAIL}'")
    if dry_run:
        print(f"    [dry-run] Would GET /subscribers/lookup-by-email?email={SUBSCRIBER_EMAIL}")
        print("    [dry-run] Would POST /subscribers {email, firstName, lastName, organizationIds} if not found")
        return None

    # Lookup by dedicated email-lookup endpoint; 404 = not found (not fatal)
    subscriber_id: str | None = None
    try:
        data = _get(
            base_url,
            "/subscribers/lookup-by-email",
            sk_key,
            params={"email": SUBSCRIBER_EMAIL},
        )
        # Response is a single subscriber object (not a list)
        if isinstance(data, dict) and data.get("id"):
            subscriber_id = str(data["id"])
            print(f"    exists (id={subscriber_id})")
            return subscriber_id
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 404:
            pass  # "not found" — proceed to create
        else:
            _handle_http_error("Subscriber lookup", exc)
            return None

    # Create — organizationIds is REQUIRED; org must exist first
    org_ids: list[str] = [org_id] if org_id else []
    try:
        result = _post(
            base_url,
            "/subscribers",
            sk_key,
            {
                "email": SUBSCRIBER_EMAIL,
                "firstName": "Trading",
                "lastName": "Agent",
                "organizationIds": org_ids,
            },
        )
        subscriber_id = str(result.get("id", ""))
        print(f"    created (id={subscriber_id or 'n/a'})")
        return subscriber_id or None
    except requests.HTTPError as exc:
        _handle_http_error("Subscriber create", exc)
        return None


def _setup_product(
    base_url: str, sk_key: str, team_id: str, owner_id: str, dry_run: bool
) -> str | None:
    """Create or verify the Revenium Product (team-scoped).

    Products use teamId in the POST body and as a GET query param.
    ownerId is also a required body field for create.

    Pricing note: exact $2.00/signal metered pricing (D-03) is intentionally
    DEFERRED to the Phase 4 monetize pillar.  The minimal plan here only
    needs the product to EXIST for attribution — the plan type must be
    "SUBSCRIPTION" with the four required fields (type/name/currency/graduated).

    Returns the product ID on success, None on dry-run or error.
    """
    print(f"  Product: '{PRODUCT_NAME}'")
    if dry_run:
        print(f"    [dry-run] Would GET /products?teamId={team_id} (find by name)")
        print("    [dry-run] Would POST /products {teamId, ownerId, name, version, plan} if not found")
        print("    [dry-run] Note: $2.00/signal metered pricing (D-03) deferred to Phase 4")
        return None

    # Lookup by teamId; match by exact name client-side
    try:
        data = _get(base_url, "/products", sk_key, params={"teamId": team_id})
        for prod in _extract_list(data):
            if prod.get("name") == PRODUCT_NAME:
                product_id = str(prod.get("id", ""))
                print(f"    exists (id={product_id or 'n/a'})")
                return product_id or None
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 404:
            pass  # No products yet — fall through to create
        else:
            _handle_http_error("Product lookup", exc)
            return None

    # Create — teamId + ownerId in body; plan is minimal (pricing deferred to Phase 4)
    try:
        result = _post(
            base_url,
            "/products",
            sk_key,
            {
                "teamId": team_id,
                "ownerId": owner_id,
                "name": PRODUCT_NAME,
                "version": "1.0.0",
                "comingSoon": False,
                # Minimal valid plan — type must be "SUBSCRIPTION"; API requires a billing
                # period for SUBSCRIPTION plans (period/periodCount are NOT optional).
                # MONTH/1 is the smallest standard billing cycle; it is NOT the demo pricing.
                # Exact $2.00/signal metered pricing (D-03) is DEFERRED to Phase 4
                # monetize pillar — only the product's EXISTENCE is needed for attribution now.
                "plan": {
                    "type": "SUBSCRIPTION",
                    "name": "Basic Plan",
                    "currency": "USD",
                    "graduated": False,
                    "period": "MONTH",
                    "periodCount": 1,
                },
            },
        )
        product_id = str(result.get("id", ""))
        print(f"    created (id={product_id or 'n/a'})")
        return product_id or None
    except requests.HTTPError as exc:
        _handle_http_error("Product create", exc)
        return None


def _setup_subscription(
    base_url: str,
    sk_key: str,
    owner_id: str,
    team_id: str,
    subscriber_id: str | None,
    product_id: str | None,
    dry_run: bool,
) -> bool:
    """Create or verify the Subscription (Subscriber → Product link).

    Idempotency check: GET /users/<subscriber_id>/subscriptions?productId=<product_id>
    If the returned list is non-empty, subscription already exists.

    Create POST body is BEST-EFFORT — the official create-subscription doc is
    broken/404 at time of writing.  Fields ownerId, clientEmailAddress, and teamId
    were discovered as required via live HTTP 400 batch validation; further required
    fields may still surface.  On any 4xx the raw response body is printed verbatim
    so the field names can be corrected in a follow-up run.

    Returns True on success / exists, False on error.
    """
    print(f"  Subscription: '{SUBSCRIBER_EMAIL}' → '{PRODUCT_NAME}'")
    if dry_run:
        print("    [dry-run] Would GET /users/<subscriber_id>/subscriptions?productId=<product_id>")
        print(
            "    [dry-run] Would POST /subscriptions"
            " {name, subscriberId, productId, ownerId, clientEmailAddress, teamId} if not found"
        )
        print("    [dry-run] Note: subscription create schema is unverified/best-effort")
        return True

    if not subscriber_id or not product_id:
        print("    SKIP: subscriber or product ID unavailable; cannot create subscription")
        return False

    # Idempotency lookup: check existing subscriptions for this user + product
    try:
        data = _get(
            base_url,
            f"/users/{subscriber_id}/subscriptions",
            sk_key,
            params={"productId": product_id},
        )
        existing = _extract_list(data)
        if existing:
            sub_id = existing[0].get("id", "n/a") if isinstance(existing[0], dict) else "n/a"
            print(f"    exists (id={sub_id})")
            return True
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 404:
            pass  # No subscriptions yet — fall through to create
        else:
            _handle_http_error("Subscription lookup", exc)
            return False

    # Create — UNVERIFIED schema; field names are best-effort (official create-subscription
    # API doc returns 404).  "name" was discovered as required first; ownerId,
    # clientEmailAddress, and teamId were subsequently discovered via live HTTP 400
    # batch validation.  Further required fields may still surface on the next run;
    # the raw body below shows them.  On any 4xx, raw response body is printed so
    # the caller can correct the field names.
    url = f"{base_url.rstrip('/')}/subscriptions"
    payload = {
        # UNVERIFIED schema — official create-subscription doc is 404 at time of writing.
        # "name" discovered as required via live HTTP 400; ownerId/clientEmailAddress/teamId
        # discovered in a subsequent live 400 batch-validation response.
        # Further required fields may surface on the next run; see raw body below.
        "name": f"{PRODUCT_NAME} - {SUBSCRIBER_EMAIL}",
        # UNVERIFIED: may need "userId" instead of "subscriberId" — check raw error body below
        "subscriberId": subscriber_id,
        "productId": product_id,
        "ownerId": owner_id,
        "clientEmailAddress": SUBSCRIBER_EMAIL,
        "teamId": team_id,
    }
    try:
        resp = requests.post(url, headers=_headers(sk_key), json=payload, timeout=15)
        if not resp.ok:
            raw_body = resp.text[:1000]
            print(f"    FAIL [Subscription create] HTTP {resp.status_code}")
            print(f"    Raw response body (verbatim — use to correct field names):\n    {raw_body}")
            if resp.status_code == 401:
                print("    Check that REVENIUM_SK_API_KEY is a valid rev_sk_* management key.")
            elif resp.status_code == 403:
                print("    The key may lack write permissions for subscriptions.")
            return False
        result = resp.json()
        print(f"    created (id={result.get('id', 'n/a') if isinstance(result, dict) else 'n/a'})")
        return True
    except Exception as exc:  # noqa: BLE001 — fail open on unexpected errors; report verbatim
        print(f"    FAIL [Subscription create] unexpected error: {exc}")
        return False


def _handle_http_error(context: str, exc: requests.HTTPError) -> None:
    """Print a human-readable error message for an HTTP failure.

    Never prints the API key; only the HTTP status and response body.
    """
    status = exc.response.status_code if exc.response is not None else "unknown"
    body = exc.response.text[:500] if exc.response is not None else ""
    print(f"    ERROR [{context}] HTTP {status}: {body}")
    if status == 401:
        print("    Check that REVENIUM_SK_API_KEY is a valid rev_sk_* management key.")
    elif status == 403:
        print("    The key may lack the required write permissions for this resource.")


def _setup_cost_rule(base_url: str, sk_key: str, team_id: str, dry_run: bool) -> bool:
    """Create or verify the enforce-mode cost rule (CTL-04, D-06).

    Idempotency: look up by name, create if missing, PATCH to enforce mode
    if found in shadow mode.  Returns True on success or dry-run.

    Host note: uses the management base URL (api.prod.ai.hcapp.io), NOT the
    enforcement polling host (api.revenium.ai).  The existing ``base_url``
    variable in main() is correct — do not substitute the metering host here
    (Pitfall #4 from 03-RESEARCH.md).

    Body note: ``teamId`` MUST be in the POST body for correct rule scoping
    (Pitfall #6).  ``shadowMode: False`` MUST be explicit — observe-only rules
    never produce the dashboard ENFORCEMENT_VIOLATION event (D-07).
    """
    print(f"  Cost rule: '{DEMO_RULE_NAME}' (TOTAL_COST DAILY ${DEMO_RULE_HARD_LIMIT})")
    if dry_run:
        print(f"    [dry-run] Would GET /ai/cost-controls?teamId={team_id} (find by name)")
        print("    [dry-run] Would POST /ai/cost-controls {name, metricType, DAILY, BLOCK,"
              " hardLimit, shadowMode:false, ORGANIZATION filter} if not found")
        print("    [dry-run] Would PATCH /ai/cost-controls/{id} {shadowMode:false, enabled:true}"
              " if found in shadow mode")
        return True

    # Lookup existing rules for this team; match by name client-side
    try:
        data = _get(base_url, "/ai/cost-controls", sk_key, params={"teamId": team_id})
        for rule in _extract_list(data):
            if rule.get("name") == DEMO_RULE_NAME or rule.get("label") == DEMO_RULE_NAME:
                rule_id = str(rule.get("id", ""))
                shadow = rule.get("shadowMode", True)
                enabled = rule.get("enabled", False)
                if not shadow and enabled:
                    print(f"    exists in enforce mode (id={rule_id}) — OK")
                    return True
                # Found but in wrong state — PATCH to enforce mode (D-07)
                try:
                    _patch(base_url, f"/ai/cost-controls/{rule_id}", sk_key,
                           {"shadowMode": False, "enabled": True})
                    print(f"    updated to enforce mode (id={rule_id})")
                    return True
                except requests.HTTPError as exc:
                    _handle_http_error("Cost rule PATCH", exc)
                    return False
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 404:
            pass  # No rules yet — fall through to create
        else:
            _handle_http_error("Cost rule lookup", exc)
            return False

    # Create in enforce mode — shadowMode:false is the demo-critical field (D-07)
    try:
        result = _post(base_url, "/ai/cost-controls", sk_key, {
            "name": DEMO_RULE_NAME,
            "description": (
                "Demo cost gate for FCAT — enforce mode. "
                "Scoped to Revenium-Research-Desk org. "
                "Halts the run mid-debate for the control pillar demo."
            ),
            "metricType": "TOTAL_COST",
            "windowType": "DAILY",
            "action": "BLOCK",
            "groupBy": "AGENT",
            "hardLimit": DEMO_RULE_HARD_LIMIT,
            "warnThreshold": DEMO_RULE_WARN_THRESHOLD,
            "shadowMode": False,    # D-07: MUST be false; shadow mode silently skips enforcement
            "enabled": True,
            "filters": [
                {
                    "dimension": "ORGANIZATION",
                    "operator": "IS",
                    "value": ORG_NAME,  # "Revenium-Research-Desk" — D-04: org-scoped filter
                },
            ],
            "teamId": team_id,           # Pitfall #6: teamId MUST be in the POST body
            "notificationChannelIds": [],
        })
        rule_id = str(result.get("id", ""))
        print(f"    created in enforce mode (id={rule_id or 'n/a'})")
        return True
    except requests.HTTPError as exc:
        _handle_http_error("Cost rule create", exc)
        return False


# ---------------------------------------------------------------------------
# Jentic tool-pricing registration (JEN-02)
# ---------------------------------------------------------------------------

# Default per-call price for the Jentic news tool (USD); override via JENTIC_TOOL_PRICE env var.
_DEFAULT_JENTIC_UNIT_PRICE = "0.05"


def _update_tool_pricing(
    profitstream_host: str,
    sk_key: str,
    team_id: str,
    tool_id: str,
    payload: dict,
) -> bool:
    """Upsert pricing on an already-existing ToolResource (GET id -> PUT payload).

    Works around a Revenium backend gap: ``POST /v2/api/tools`` on an existing
    ``toolId`` returns 409 WITHOUT applying the pricing element, so re-running a
    POST alone leaves an unpriced tool unpriced.  This looks the tool up by
    ``toolId`` and PUTs the full payload to ``/v2/api/tools/{id}`` so pricing is
    applied in place.  (Backend ticket filed for the FE/BE gap.)
    """
    base = f"{profitstream_host.rstrip('/')}/profitstream/v2/api/tools"
    quoted = requests.utils.quote(tool_id, safe="")
    try:
        get_resp = requests.get(
            f"{base}/by-tool-id/{quoted}",
            headers=_headers(sk_key),
            params={"teamId": team_id},
            timeout=15,
        )
        if get_resp.status_code != 200:
            print(f"    FAIL [Jentic tool upsert] fetch existing tool HTTP "
                  f"{get_resp.status_code}: {get_resp.text[:200]}")
            return False
        resource_id = (get_resp.json() or {}).get("id")
        if not resource_id:
            print("    FAIL [Jentic tool upsert] existing tool has no id")
            return False
        put_resp = requests.put(
            f"{base}/{resource_id}",
            headers=_headers(sk_key),
            json=payload,
            timeout=15,
        )
        if put_resp.status_code in (200, 201):
            unit = payload["pricing"]["elements"][0]["unitPrice"]
            print(f"    updated pricing (id={resource_id}, toolId={tool_id}, ${unit}/call)")
            return True
        print(f"    FAIL [Jentic tool upsert] PUT HTTP {put_resp.status_code}: {put_resp.text[:200]}")
        return False
    except Exception as exc:  # noqa: BLE001 — fail open; report verbatim
        print(f"    FAIL [Jentic tool upsert] unexpected error: {exc}")
        return False


def register_jentic_tool(
    profitstream_host: str,
    sk_key: str,
    team_id: str,
    tool_id: str,
    unit_price: str,
    dry_run: bool,
) -> bool:
    """Register a per-call priced ToolResource for the Jentic news tool (JEN-02).

    POSTs to ``{profitstream_host}/profitstream/v2/api/tools`` with a COUNT
    pricing element so every emitted ``jentic_news`` tool event accrues a per-call
    cost in Revenium.  The ``toolId`` MUST exactly match the string emitted by
    ``@meter_tool`` in ``jentic_news_tools.py`` (``jentic_tool_id`` config key, L6).

    Host note: ``profitstream_host`` must be the HOST-ONLY form, e.g.
    ``https://api.prod.ai.hcapp.io``.  The path ``/profitstream/v2/api/tools``
    is appended by this function.  This is the same host confirmed for billing
    (Pitfall 6 — do not pass a host that already includes ``/profitstream``).
    If the primary host 401/404s, the printed hint suggests the OAS server
    ``https://api.revenium.ai`` as an alternative (T-06-05).

    Idempotency: 409 Conflict (or a response body containing "already exists")
    is treated as success — re-running is safe.

    Arguments:
        profitstream_host  HOST-ONLY URL (e.g. https://api.prod.ai.hcapp.io)
                           from ``REVENIUM_PROFITSTREAM_BASE_URL`` /
                           ``revenium_profitstream_url`` config key.
        sk_key             ``rev_sk_*`` write-scope key.  If empty, print skip
                           and return True (keyless-CI-safe, DMO-04 discipline).
        team_id            Revenium team UUID for ToolResource scoping.
        tool_id            ``ToolResource.toolId`` — must equal the ``@meter_tool``
                           string, sourced from ``jentic_tool_id`` config key.
        unit_price         Per-call price as decimal string, e.g. ``"0.05"`` = $0.05/call.
        dry_run            If True, print intended action and return True without
                           making any network call.
    """
    print(f"  Jentic tool resource: toolId='{tool_id}' (COUNT ${unit_price}/call)")

    if not sk_key:
        # Keyless mode — skip gracefully, never error (DMO-04).
        print("    SKIP: REVENIUM_SK_API_KEY not set — skipping Jentic tool registration (keyless mode).")
        return True

    tools_url = f"{profitstream_host.rstrip('/')}/profitstream/v2/api/tools"

    if dry_run:
        print(f"    [dry-run] Would POST {tools_url}")
        print(f"    [dry-run] toolId={tool_id}, teamId={team_id[:8]}..., "
              f"aggregationType=COUNT, unitPrice={unit_price}")
        print("    [dry-run] toolType=CUSTOM, toolProvider=jentic, enabled=true")
        return True

    payload: dict = {
        "teamId": team_id,
        "toolId": tool_id,               # must equal @meter_tool string (L6)
        "name": "Jentic News Tool",
        "description": (
            "External news data via Jentic tool-execution SDK. "
            "Metered per-call by Revenium (Phase 6, JEN-02). "
            "toolId must match the @meter_tool decorator string."
        ),
        "toolType": "CUSTOM",            # enum: MCP_SERVER | MULTIMODAL | TOOL_CALL | CUSTOM
        "toolProvider": "jentic",
        "enabled": True,
        "pricing": {
            "currency": "USD",
            "elements": [
                {
                    "name": "requests",
                    "unitPrice": unit_price,        # per-call flat fee (string decimal)
                    "aggregationType": "COUNT",     # counts events, not SUM/AVERAGE
                }
            ],
        },
    }

    try:
        resp = requests.post(
            tools_url,
            headers=_headers(sk_key),
            json=payload,
            timeout=15,
        )

        if resp.status_code in (200, 201):
            result: dict = resp.json() if resp.text.strip() else {}
            resource_id = result.get("id", "n/a") if isinstance(result, dict) else "n/a"
            print(f"    created (id={resource_id}, toolId={tool_id})")
            return True

        body_lower = resp.text[:500].lower()
        _is_duplicate = resp.status_code == 409 or (
            resp.status_code in (400, 422)
            and any(w in body_lower for w in ("already", "exists", "duplicate", "conflict"))
        )
        if _is_duplicate:
            # Already exists — UPSERT pricing in place. A bare POST-on-existing
            # (409) does NOT apply pricing server-side (backend gap), so an
            # unpriced tool would stay unpriced on re-run. Look up + PUT instead.
            print(f"    already exists (toolId={tool_id}) — updating pricing via PUT")
            return _update_tool_pricing(profitstream_host, sk_key, team_id, tool_id, payload)

        # 401 / 404 — likely a host mismatch; provide the alternate-host hint (T-06-05).
        if resp.status_code in (401, 403, 404):
            print(f"    FAIL [Jentic tool register] HTTP {resp.status_code}: {resp.text[:200]}")
            if resp.status_code in (401, 403):
                print("    Check that REVENIUM_SK_API_KEY is a valid rev_sk_* write-scope key.")
            print(f"    Host tried: {tools_url}")
            print("    Hint (T-06-05): if the primary host 401/404s, try the OAS server:")
            print("      export REVENIUM_PROFITSTREAM_BASE_URL=https://api.revenium.ai")
            print("      Which builds: https://api.revenium.ai/profitstream/v2/api/tools")
            print("    Or confirm via Revenium dashboard -> Tools -> Add Tool (manual fallback).")
            return False

        resp.raise_for_status()
        return True  # should not reach here; raise_for_status handles remaining 4xx/5xx

    except requests.HTTPError as exc:
        _handle_http_error("Jentic tool register", exc)
        if exc.response is not None and exc.response.status_code in (401, 403, 404):
            print(f"    Host tried: {tools_url}")
            print("    Hint (T-06-05): try REVENIUM_PROFITSTREAM_BASE_URL=https://api.revenium.ai")
        return False
    except Exception as exc:  # noqa: BLE001 — fail open; report verbatim
        print(f"    FAIL [Jentic tool register] unexpected error: {exc}")
        return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    """Provision Revenium attribution hierarchy; return 0 on success, 1 on any step error."""
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print intended actions without making any writes to Revenium",
    )
    parser.add_argument(
        "--jentic-tool",
        action="store_true",
        help=(
            "Register the Jentic news tool with per-call COUNT pricing in Revenium "
            "(POST /v2/api/tools).  Runs independently of the attribution-hierarchy "
            "steps — only REVENIUM_SK_API_KEY and REVENIUM_TEAM_ID are required.  "
            "If REVENIUM_SK_API_KEY is absent, prints a skip message and exits 0 "
            "(keyless-CI-safe, DMO-04).  Use REVENIUM_PROFITSTREAM_BASE_URL to "
            "select the host (HOST-ONLY form, e.g. https://api.prod.ai.hcapp.io)."
        ),
    )
    args = parser.parse_args()

    # ------------------------------------------------------------------
    # --jentic-tool standalone mode (JEN-02)
    # ------------------------------------------------------------------
    if args.jentic_tool:
        sk_key: str = os.getenv("REVENIUM_SK_API_KEY", "")
        if not sk_key:
            print("SKIP: REVENIUM_SK_API_KEY not set — jentic tool registration skipped (keyless mode).")
            print("      To register: REVENIUM_SK_API_KEY=rev_sk_... REVENIUM_TEAM_ID=<id> \\")
            print("        REVENIUM_PROFITSTREAM_BASE_URL=https://api.prod.ai.hcapp.io \\")
            print("        .venv/bin/python scripts/setup_revenium.py --jentic-tool")
            return 0

        _validate_sk_key(sk_key)  # exits 1 on wrong prefix (never prints key value)

        team_id: str = os.getenv("REVENIUM_TEAM_ID", "")
        if not team_id:
            print("FAIL: REVENIUM_TEAM_ID is not set.")
            print("      Required as teamId in the ToolResource POST body.")
            print("      Find it in: Revenium dashboard -> Settings -> Team.")
            return 1

        # Profitstream host — HOST-ONLY (path is appended by register_jentic_tool).
        # Prefer REVENIUM_PROFITSTREAM_BASE_URL; fall back to DEFAULT_CONFIG key.
        profitstream_host: str = (
            os.getenv("REVENIUM_PROFITSTREAM_BASE_URL", "")
            or DEFAULT_CONFIG.get("revenium_profitstream_url", "https://api.revenium.io")
        ).rstrip("/")

        tool_id: str = DEFAULT_CONFIG.get("jentic_tool_id", "jentic_news")
        unit_price: str = os.getenv("JENTIC_TOOL_PRICE", _DEFAULT_JENTIC_UNIT_PRICE)

        mode = "[DRY-RUN]" if args.dry_run else "[LIVE]"
        print(f"Registering Jentic tool price model  {mode}")
        print(f"  Profitstream host : {profitstream_host}")
        print(f"  Team ID           : {team_id}")
        print(f"  SK API Key        : {'(set)' if sk_key else '(MISSING)'}")
        print(f"  Tool ID           : {tool_id}")
        print(f"  Unit price        : ${unit_price}/call (COUNT)")
        print()
        print("Provisioning tool resource:")

        ok = register_jentic_tool(
            profitstream_host=profitstream_host,
            sk_key=sk_key,
            team_id=team_id,
            tool_id=tool_id,
            unit_price=unit_price,
            dry_run=args.dry_run,
        )
        print()
        if args.dry_run:
            print("Dry-run PASS: intended actions printed; no writes made.")
            return 0
        if ok:
            print("Jentic tool PASS: ToolResource registered (or already exists).")
            print("Next step: run validate_jentic.py to confirm metered+priced events appear.")
            return 0
        print("Jentic tool FAIL: see error above.")
        return 1

    # Resolve platform management base URL — NOT the metering URL (revenium_api_url).
    # The two hosts are intentionally separate; this script never touches the metering host.
    base_url = os.getenv("REVENIUM_PLATFORM_BASE_URL", _DEFAULT_PLATFORM_BASE_URL)

    # --- Required env vars ---
    # Validate all required vars up front; collect errors so the user sees them all at once.
    missing: list[str] = []

    sk_key: str = os.getenv("REVENIUM_SK_API_KEY", "")
    if not args.dry_run:
        if not sk_key:
            print("FAIL: REVENIUM_SK_API_KEY is not set.")
            print("      Set this variable to your rev_sk_* write/management key.")
            print("      Get it from: Revenium dashboard -> Settings -> API Keys")
            missing.append("REVENIUM_SK_API_KEY")
        else:
            _validate_sk_key(sk_key)  # exits 1 on wrong prefix

    tenant_id: str = os.getenv("REVENIUM_TENANT_ID", "")
    if not tenant_id:
        print("FAIL: REVENIUM_TENANT_ID is not set.")
        print("      Required for organization scoping (tenantId on GET + POST).")
        print("      Find it in: Revenium dashboard -> Settings -> Tenant / Organization.")
        missing.append("REVENIUM_TENANT_ID")

    team_id: str = os.getenv("REVENIUM_TEAM_ID", "")
    if not team_id:
        print("FAIL: REVENIUM_TEAM_ID is not set.")
        print("      Required for product scoping (teamId in product body + GET query).")
        print("      Find it in: Revenium dashboard URL or Settings -> Team.")
        missing.append("REVENIUM_TEAM_ID")

    owner_id: str = os.getenv("REVENIUM_OWNER_ID", "")
    if not owner_id:
        print("FAIL: REVENIUM_OWNER_ID is not set.")
        print("      Required as ownerId in the product create body.")
        print("      Find it in: Revenium dashboard -> Settings -> Team / Owner.")
        missing.append("REVENIUM_OWNER_ID")

    if missing:
        print("")
        print(f"      Missing required variable(s): {', '.join(missing)}")
        print("")
        print("      For a dry run set all four vars to placeholder values:")
        print("        REVENIUM_SK_API_KEY=rev_sk_placeholder REVENIUM_TENANT_ID=t1 \\")
        print("        REVENIUM_TEAM_ID=t2 REVENIUM_OWNER_ID=o1 \\")
        print("        python scripts/setup_revenium.py --dry-run")
        return 1

    mode = "[DRY-RUN]" if args.dry_run else "[LIVE]"
    print(f"Revenium attribution-hierarchy setup  {mode}")
    print(f"  Platform URL: {base_url}")
    print(f"  SK API Key:   {'(set)' if sk_key else '(MISSING — dry-run only)'}")
    print(f"  Tenant ID:    {tenant_id}")
    print(f"  Team ID:      {team_id}")
    print(f"  Owner ID:     {owner_id}")
    print(f"  Org:          {ORG_NAME}")
    print(f"  Subscriber:   {SUBSCRIBER_EMAIL}")
    print(f"  Product:      {PRODUCT_NAME}")
    print("")
    print("Provisioning entities:")

    failures = 0

    # 1. Organization (tenant-scoped — tenantId on GET query + POST body)
    org_id = _setup_organization(base_url, sk_key, tenant_id, args.dry_run)
    if not args.dry_run and org_id is None:
        failures += 1

    # 2. Subscriber (org must exist first so organizationIds can be populated)
    subscriber_id = _setup_subscriber(base_url, sk_key, org_id, args.dry_run)
    if not args.dry_run and subscriber_id is None:
        failures += 1

    # 3. Product (team-scoped — teamId + ownerId in body)
    product_id = _setup_product(base_url, sk_key, team_id, owner_id, args.dry_run)
    if not args.dry_run and product_id is None:
        failures += 1

    # 4. Subscription (Subscriber → Product; best-effort create with raw-body error reporting)
    ok = _setup_subscription(base_url, sk_key, owner_id, team_id, subscriber_id, product_id, args.dry_run)
    if not args.dry_run and not ok:
        failures += 1

    # 5. Cost rule (enforce-mode, TOTAL_COST DAILY $1.00 — CTL-04, D-06)
    ok = _setup_cost_rule(base_url, sk_key, team_id, args.dry_run)
    if not args.dry_run and not ok:
        failures += 1

    print("")
    if args.dry_run:
        print("Dry-run PASS: all intended actions printed; no writes made.")
        return 0

    if failures:
        print(f"Setup FAIL: {failures} step(s) encountered errors (see above).")
        return 1

    print("Setup PASS: Org → Subscriber → Product → Subscription provisioned (or already exists).")
    print("Next step: run the live TradingAgents analysis to confirm metering events appear.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
