"""Idempotent Revenium attribution-hierarchy provisioning script.

Creates or verifies the Org → Subscriber → Product → Subscription chain
in Revenium before any metered trading-agent call.  Re-running the script
is safe: each entity is looked up by its natural key (name / email /
product name) before creation, and existing entities are reported as
"exists" rather than creating duplicates (D-08).

SCOPING NOTE — tenantId vs teamId:
    - Organizations are TENANT-scoped (tenantId on GET query + POST body).
    - Products are TEAM-scoped (teamId in POST body; GET ?teamId=...).
    - Subscribers and Subscriptions use neither as a scope param.
    Passing a teamId where tenantId is expected returns 404.

Attribution values (org/product/subscriber names) are read from
tradingagents.revenium.config (D-01..D-03).  Credentials and platform IDs
are read from environment variables:

    REVENIUM_SK_API_KEY         — rev_sk_* write/management key (required;
                                   D-10 least-privilege split)
    REVENIUM_TENANT_ID          — tenant scope for organizations (required)
    REVENIUM_TEAM_ID            — team scope for products (required)
    REVENIUM_OWNER_ID           — owner id for product creation (required)
    REVENIUM_PLATFORM_BASE_URL  — optional; defaults to
                                   https://api.prod.ai.hcapp.io/profitstream/v2/api

NOTE on host/path split:
    The Revenium **management** API (org/subscriber/product/subscription CRUD)
    is served at a different host and path than the metering hot-path:

        Management host:  https://api.prod.ai.hcapp.io/profitstream/v2/api
        Metering host:    https://api.revenium.ai  (used by Plan 02, untouched here)

    Auth for the management API uses the ``x-api-key`` header, NOT Bearer.

Usage:
    # Dry run — print intended actions, exit 0, no writes:
    REVENIUM_SK_API_KEY=rev_sk_... REVENIUM_TENANT_ID=... REVENIUM_TEAM_ID=... \\
    REVENIUM_OWNER_ID=... .venv/bin/python scripts/setup_revenium.py --dry-run

    # Live run — create/verify hierarchy in Revenium account:
    REVENIUM_SK_API_KEY=rev_sk_... REVENIUM_TENANT_ID=... REVENIUM_TEAM_ID=... \\
    REVENIUM_OWNER_ID=... .venv/bin/python scripts/setup_revenium.py

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
    email / product name).
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
    subscriber_id: str | None,
    product_id: str | None,
    dry_run: bool,
) -> bool:
    """Create or verify the Subscription (Subscriber → Product link).

    Idempotency check: GET /users/<subscriber_id>/subscriptions?productId=<product_id>
    If the returned list is non-empty, subscription already exists.

    Create POST body is BEST-EFFORT — the official create-subscription doc is
    broken/404 at time of writing; field names may be "userId"/"productId" or
    "subscriberId"/"productId".  On any 4xx the raw response body is printed
    verbatim so the field names can be corrected in a follow-up run.

    Returns True on success / exists, False on error.
    """
    print(f"  Subscription: '{SUBSCRIBER_EMAIL}' → '{PRODUCT_NAME}'")
    if dry_run:
        print("    [dry-run] Would GET /users/<subscriber_id>/subscriptions?productId=<product_id>")
        print("    [dry-run] Would POST /subscriptions {name, subscriberId, productId} if not found")
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

    # Create — UNVERIFIED schema; "subscriberId"/"productId" field names are best-effort
    # (official create-subscription API doc returns 404).  On any 4xx, raw response
    # body is printed so the caller can correct the field names.
    url = f"{base_url.rstrip('/')}/subscriptions"
    payload = {
        # UNVERIFIED schema — official create-subscription doc is 404 at time of writing.
        # "name" was discovered as required via live HTTP 400 validation error.
        # Further required fields may surface on the next run; the raw body below shows them.
        "name": f"{PRODUCT_NAME} - {SUBSCRIBER_EMAIL}",
        # UNVERIFIED: may need "userId" instead of "subscriberId" — check raw error body below
        "subscriberId": subscriber_id,
        "productId": product_id,
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
    args = parser.parse_args()

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
    ok = _setup_subscription(base_url, sk_key, subscriber_id, product_id, args.dry_run)
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
