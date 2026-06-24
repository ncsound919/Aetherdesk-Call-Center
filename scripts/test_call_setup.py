"""AetherDesk Test Call Provisioning Script

Provisions the system to make a test outbound call to a phone number.

Usage:
    python scripts/test_call_setup.py +19843656059
    python scripts/test_call_setup.py +19843656059 --profile PROF-META-SALES

Requires:
    - Redis running
    - API server running at $API_URL (default http://localhost:8000)
    - Docker stack deployed with FreeSWITCH + Fonoster + SIP trunk configured
"""

import argparse
import json
import os
import sys
import time
from urllib.parse import urljoin

import httpx

API_URL = os.getenv("API_URL", "http://localhost:8000")
API_KEY = os.getenv("API_KEY", "dev-api-key")


def step(label: str):
    print(f"  >> {label}...", end=" ", flush=True)


def ok():
    print("OK")


def fail(msg: str):
    print(f"FAILED: {msg}")


def check_prerequisites(client: httpx.Client) -> bool:
    all_ok = True

    # 1. Redis
    step("Redis reachable")
    try:
        r = client.get(f"{API_URL}/api/v1/health/ready", timeout=5)
        if r.status_code == 200:
            ok()
        else:
            fail(f"health/ready returned {r.status_code}")
            all_ok = False
    except Exception as e:
        fail(str(e))
        all_ok = False

    # 2. API server
    step("API server reachable")
    try:
        r = client.get(f"{API_URL}/api/v1/health", timeout=5)
        if r.status_code == 200:
            ok()
        else:
            fail(f"health returned {r.status_code}")
            all_ok = False
    except Exception as e:
        fail(str(e))
        all_ok = False

    # 3. Database
    step("Alembic migrations up to date")
    try:
        r = client.get(f"{API_URL}/api/v1/health/ready", timeout=5)
        if r.status_code == 200:
            ok()
        else:
            fail("health/ready indicates DB issue")
            all_ok = False
    except Exception as e:
        fail(str(e))
        all_ok = False

    return all_ok


def ensure_test_tenant(client: httpx.Client) -> str | None:
    """Create TENANT-TEST if it doesn't exist. Return tenant_id."""
    step("TENANT-TEST exists")
    try:
        r = client.get(f"{API_URL}/api/v1/tenants/TENANT-TEST", headers={"X-API-Key": API_KEY}, timeout=5)
        if r.status_code == 200:
            ok()
            return "TENANT-TEST"
        r = client.post(f"{API_URL}/api/v1/tenants", json={"name": "Test Tenant", "email": "test@aetherdesk.io", "gdpr_consent": True}, headers={"X-API-Key": API_KEY}, timeout=5)
        if r.status_code in (200, 201):
            ok()
            return r.json().get("id", "TENANT-TEST")
        fail(f"create tenant returned {r.status_code}: {r.text[:120]}")
        return None
    except Exception as e:
        fail(str(e))
        return None


def ensure_test_agent(client: httpx.Client, tenant_id: str) -> str | None:
    """Create a test AI agent. Return agent_id."""
    step("Test AI agent exists")
    try:
        r = client.get(f"{API_URL}/api/v1/tenants/{tenant_id}/agents", headers={"X-API-Key": API_KEY}, timeout=5)
        if r.status_code == 200:
            agents = r.json()
            if isinstance(agents, list) and agents:
                ok()
                return agents[0].get("id", agents[0].get("agent_id", "unknown"))
        r = client.post(f"{API_URL}/api/v1/tenants/{tenant_id}/agents", json={"name": "TestCallAgent", "agent_type": "ai", "skills": ["support", "sales"]}, headers={"X-API-Key": API_KEY}, timeout=5)
        if r.status_code in (200, 201):
            ok()
            return r.json().get("id", r.json().get("agent_id"))
        fail(f"create agent returned {r.status_code}: {r.text[:120]}")
        return None
    except Exception as e:
        fail(str(e))
        return None


def trigger_outbound_call(client: httpx.Client, phone: str, profile_id: str) -> dict | None:
    """Trigger an outbound call via the voice outbound endpoint."""
    step(f"Initiating outbound call to {phone}")
    try:
        r = client.post(f"{API_URL}/api/v1/voice/outbound", json={"to_phone": phone, "profile_id": profile_id}, headers={"X-API-Key": API_KEY}, timeout=15)
        if r.status_code in (200, 201):
            result = r.json()
            ok()
            return result
        fail(f"outbound call returned {r.status_code}: {r.text[:200]}")
        return None
    except Exception as e:
        fail(str(e))
        return None


def main():
    parser = argparse.ArgumentParser(description="AetherDesk Test Call Provisioning")
    parser.add_argument("phone", help="Phone number to call (e.g., +19843656059)")
    parser.add_argument("--profile", default="PROF-META-SALES", help="Agent profile ID (default: PROF-META-SALES)")
    parser.add_argument("--url", default=API_URL, help=f"API base URL (default: {API_URL})")
    parser.add_argument("--api-key", default=API_KEY, help="API key")
    args = parser.parse_args()

    global API_URL, API_KEY
    API_URL = args.url.rstrip("/")
    API_KEY = args.api_key

    print(f"\n{'=' * 60}")
    print(f"  AetherDesk Test Call Provisioning")
    print(f"  Target: {args.phone}")
    print(f"  API:    {API_URL}")
    print(f"{'=' * 60}\n")

    with httpx.Client(timeout=10) as client:
        print("[1/5] Checking prerequisites")
        if not check_prerequisites(client):
            print("\n  Prerequisites not met. Fix the issues above and retry.")
            print("  Ensure Docker stack is running: docker compose up -d")
            sys.exit(1)

        print("\n[2/5] Provisioning test tenant")
        tenant_id = ensure_test_tenant(client)
        if not tenant_id:
            print("\n  Tenant provisioning failed.")
            sys.exit(1)

        print("\n[3/5] Provisioning test agent")
        agent_id = ensure_test_agent(client, tenant_id)
        if not agent_id:
            print("\n  Agent provisioning failed.")
            sys.exit(1)

        print("\n[4/5] Checking Fonoster connectivity")
        step("Fonoster health check")
        try:
            r = client.get(f"{API_URL}/api/v1/health/live", timeout=5)
            if r.status_code == 200:
                ok()
            else:
                fail(f"health/live returned {r.status_code}")
        except Exception as e:
            fail(str(e))

        print("\n[5/5] Triggering outbound call")
        result = trigger_outbound_call(client, args.phone, args.profile)
        if result:
            print(f"\n  Call initiated successfully!")
            print(f"  Call ref: {result.get('call_ref', 'unknown')}")
            print(f"  Status:   {result.get('status', 'queued')}")
            print(f"\n  Expect a call at {args.phone} within 30 seconds.")
        else:
            print(f"\n  Call initiation failed.")
            print("  Ensure the Docker stack is running with a configured SIP trunk.")
            sys.exit(1)

    print(f"\n{'=' * 60}\n")


if __name__ == "__main__":
    main()
