"""Idempotent Revenium attribution-hierarchy provisioning script.

Creates or verifies the Org → Subscriber → Product → Subscription chain
in Revenium before any metered trading-agent call.  Re-running the script
is safe: each entity is looked up by its natural key (name / email /
product name) before creation, and existing entities are reported as
"exists" rather than creating duplicates (D-08).

Attribution values are read from tradingagents.revenium.config (D-01..D-03),
not duplicated here.  Credentials are read from environment variables:

    REVENIUM_METERING_API_KEY  — rev_mk_* metering key (for validation only;
                                  not used for write operations)
    REVENIUM_SK_API_KEY        — rev_sk_* write/management key (required for
                                  create/verify; D-10 least-privilege split)
    REVENIUM_METERING_BASE_URL — optional; defaults to https://api.revenium.ai

Usage:
    # Dry run — print intended actions, exit 0, no writes:
    REVENIUM_SK_API_KEY=rev_sk_... \\
        .venv/bin/python scripts/setup_revenium.py --dry-run

    # Live run — create/verify hierarchy in Revenium account:
    REVENIUM_SK_API_KEY=rev_sk_... \\
        .venv/bin/python scripts/setup_revenium.py

    # With an override base URL (staging):
    REVENIUM_SK_API_KEY=rev_sk_... REVENIUM_METERING_BASE_URL=https://staging.revenium.ai \\
        .venv/bin/python scripts/setup_revenium.py

Security:
    - Key material is never printed or logged (repo convention: log symbolic names only).
    - The rev_sk_ key is validated for prefix format before any API call (Pitfall 8).
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
    DEFAULT_API_URL = _attr["api_url"]
except ImportError as _exc:
    # Fail early with a clear message if the package is not installed.
    print(f"FAIL: could not import tradingagents package — {_exc}")
    print("      Run: pip install -e . (or uv pip install -e .)")
    sys.exit(1)

# Product pricing (D-03: $2.00 per trading signal)
PRODUCT_PRICE_USD = 2.00


# ---------------------------------------------------------------------------
# Key validation helpers
# ---------------------------------------------------------------------------

_VALID_SK_PREFIXES = ("rev_sk_",)
_VALID_MK_PREFIXES = ("rev_mk_", "hak_")  # hak_ is legacy but still accepted


def _validate_sk_key(key: str) -> None:
    """Validate the write/management key prefix; exit 1 with a human-readable message on mismatch."""
    if not any(key.startswith(p) for p in _VALID_SK_PREFIXES):
        # Don't print the key; print only the prefix shape (Pitfall 8)
        print("FAIL: REVENIUM_SK_API_KEY has an unexpected prefix.")
        print(f"      Expected prefix(es): {', '.join(_VALID_SK_PREFIXES)}")
        print("      Example correct format: rev_sk_xxxxxxxx...")
        print("      Get this key from: Revenium dashboard -> Settings -> API Keys")
        sys.exit(1)


# ---------------------------------------------------------------------------
# REST client helpers
# ---------------------------------------------------------------------------

def _headers(sk_key: str) -> dict[str, str]:
    """Build auth headers for the Revenium management API."""
    return {
        "Authorization": f"Bearer {sk_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _get(base_url: str, path: str, sk_key: str, params: dict | None = None) -> dict[str, Any]:
    """GET from Revenium management REST API; return parsed JSON."""
    url = f"{base_url.rstrip('/')}{path}"
    resp = requests.get(url, headers=_headers(sk_key), params=params, timeout=15)
    resp.raise_for_status()
    return resp.json()


def _post(base_url: str, path: str, sk_key: str, payload: dict) -> dict[str, Any]:
    """POST to Revenium management REST API; return parsed JSON."""
    url = f"{base_url.rstrip('/')}{path}"
    resp = requests.post(url, headers=_headers(sk_key), json=payload, timeout=15)
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Entity create-or-verify helpers
# ---------------------------------------------------------------------------

def _setup_organization(base_url: str, sk_key: str, dry_run: bool) -> str | None:
    """Create or verify the Revenium Organization.

    Returns the organization ID on success, None on dry-run.
    """
    print(f"  Organization: '{ORG_NAME}'")
    if dry_run:
        print("    [dry-run] Would create/verify Organization")
        return None

    try:
        # Look up by name first (idempotency)
        data = _get(base_url, "/api/v2/organizations", sk_key, params={"name": ORG_NAME})
        orgs = data.get("items", data) if isinstance(data, dict) else data
        for org in (orgs if isinstance(orgs, list) else []):
            if org.get("name") == ORG_NAME:
                print(f"    exists (id={org.get('id', 'n/a')})")
                return str(org.get("id", ""))
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 404:
            pass  # List endpoint may not exist; fall through to create
        else:
            _handle_http_error("Organization lookup", exc)
            return None

    # Create
    try:
        result = _post(base_url, "/api/v2/organizations", sk_key, {"name": ORG_NAME})
        print(f"    created (id={result.get('id', 'n/a')})")
        return str(result.get("id", ""))
    except requests.HTTPError as exc:
        _handle_http_error("Organization create", exc)
        return None


def _setup_subscriber(base_url: str, sk_key: str, dry_run: bool) -> str | None:
    """Create or verify the Revenium Subscriber.

    Returns the subscriber ID on success, None on dry-run or error.
    """
    print(f"  Subscriber: '{SUBSCRIBER_EMAIL}'")
    if dry_run:
        print("    [dry-run] Would create/verify Subscriber")
        return None

    try:
        data = _get(base_url, "/api/v2/subscribers", sk_key, params={"email": SUBSCRIBER_EMAIL})
        subs = data.get("items", data) if isinstance(data, dict) else data
        for sub in (subs if isinstance(subs, list) else []):
            if sub.get("email") == SUBSCRIBER_EMAIL or sub.get("id") == SUBSCRIBER_EMAIL:
                print(f"    exists (id={sub.get('id', 'n/a')})")
                return str(sub.get("id", ""))
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 404:
            pass
        else:
            _handle_http_error("Subscriber lookup", exc)
            return None

    try:
        result = _post(
            base_url,
            "/api/v2/subscribers",
            sk_key,
            {"id": SUBSCRIBER_EMAIL, "email": SUBSCRIBER_EMAIL},
        )
        print(f"    created (id={result.get('id', 'n/a')})")
        return str(result.get("id", ""))
    except requests.HTTPError as exc:
        _handle_http_error("Subscriber create", exc)
        return None


def _setup_product(base_url: str, sk_key: str, dry_run: bool) -> str | None:
    """Create or verify the Revenium Product (trading-signal, $2.00/signal).

    Returns the product ID on success, None on dry-run or error.
    """
    print(f"  Product: '{PRODUCT_NAME}' @ ${PRODUCT_PRICE_USD:.2f}/signal")
    if dry_run:
        print("    [dry-run] Would create/verify Product")
        return None

    try:
        data = _get(base_url, "/api/v2/products", sk_key, params={"name": PRODUCT_NAME})
        products = data.get("items", data) if isinstance(data, dict) else data
        for prod in (products if isinstance(products, list) else []):
            if prod.get("name") == PRODUCT_NAME:
                print(f"    exists (id={prod.get('id', 'n/a')})")
                return str(prod.get("id", ""))
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 404:
            pass
        else:
            _handle_http_error("Product lookup", exc)
            return None

    try:
        result = _post(
            base_url,
            "/api/v2/products",
            sk_key,
            {
                "name": PRODUCT_NAME,
                "pricePerUnit": PRODUCT_PRICE_USD,
                "unit": "signal",
                "description": "One complete TradingAgents trading-signal analysis run",
            },
        )
        print(f"    created (id={result.get('id', 'n/a')})")
        return str(result.get("id", ""))
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

    Returns True on success / exists, False on error.
    """
    print(f"  Subscription: '{SUBSCRIBER_EMAIL}' → '{PRODUCT_NAME}'")
    if dry_run:
        print("    [dry-run] Would create/verify Subscription")
        return True

    if not subscriber_id or not product_id:
        print("    SKIP: subscriber or product ID unavailable; cannot create subscription")
        return False

    try:
        data = _get(
            base_url,
            "/api/v2/subscriptions",
            sk_key,
            params={"subscriberId": subscriber_id, "productId": product_id},
        )
        subs = data.get("items", data) if isinstance(data, dict) else data
        if subs and isinstance(subs, list) and len(subs) > 0:
            print(f"    exists (id={subs[0].get('id', 'n/a')})")
            return True
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 404:
            pass
        else:
            _handle_http_error("Subscription lookup", exc)
            return False

    try:
        result = _post(
            base_url,
            "/api/v2/subscriptions",
            sk_key,
            {"subscriberId": subscriber_id, "productId": product_id},
        )
        print(f"    created (id={result.get('id', 'n/a')})")
        return True
    except requests.HTTPError as exc:
        _handle_http_error("Subscription create", exc)
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
    """Provision Revenium attribution hierarchy; return 0 on success, 1 on first error."""
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

    # Resolve base URL from env (may be overridden in .env)
    base_url = os.getenv("REVENIUM_METERING_BASE_URL", DEFAULT_API_URL)

    # Validate the write key (skip validation in dry-run mode — key may be absent)
    sk_key: str = os.getenv("REVENIUM_SK_API_KEY", "")
    if not args.dry_run:
        if not sk_key:
            print("FAIL: REVENIUM_SK_API_KEY is not set.")
            print("      Set this variable to your rev_sk_* write/management key.")
            print("      Get it from: Revenium dashboard -> Settings -> API Keys")
            print("")
            print("      For a dry run (no writes, no key required):")
            print("        python scripts/setup_revenium.py --dry-run")
            return 1
        _validate_sk_key(sk_key)  # exits 1 on wrong prefix

    mode = "[DRY-RUN]" if args.dry_run else "[LIVE]"
    print(f"Revenium attribution-hierarchy setup  {mode}")
    print(f"  Base URL:   {base_url}")
    print(f"  Org:        {ORG_NAME}")
    print(f"  Subscriber: {SUBSCRIBER_EMAIL}")
    print(f"  Product:    {PRODUCT_NAME}")
    print("")
    print("Provisioning entities:")

    failures = 0

    # 1. Organization
    org_id = _setup_organization(base_url, sk_key, args.dry_run)
    if not args.dry_run and org_id is None:
        failures += 1

    # 2. Subscriber
    subscriber_id = _setup_subscriber(base_url, sk_key, args.dry_run)
    if not args.dry_run and subscriber_id is None:
        failures += 1

    # 3. Product
    product_id = _setup_product(base_url, sk_key, args.dry_run)
    if not args.dry_run and product_id is None:
        failures += 1

    # 4. Subscription (Subscriber → Product)
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
