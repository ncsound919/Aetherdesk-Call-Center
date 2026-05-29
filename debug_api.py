#!/usr/bin/env python
"""Debug the API errors."""
import httpx, json, time

time.sleep(2)

# Test health
print("=== HEALTH CHECK ===")
r = httpx.get("http://127.0.0.1:8000/health", timeout=5)
print("Status:", r.status_code)
print(json.dumps(r.json(), indent=2))

# Test login
print("\n=== LOGIN ===")
r = httpx.post("http://127.0.0.1:8000/auth/login", json={
    "email": "admin@aetherdesk.com",
    "password": "admin123"
})
print("Status:", r.status_code)
if r.status_code == 200:
    data = r.json()
    token = data["token"]
    print("Token:", token[:60] + "...")

    # Use this token for subsequent requests
    headers = {"Authorization": "Bearer " + token}

    # Try creating tenant
    print("\n=== CREATE TENANT ===")
    r2 = httpx.post("http://127.0.0.1:8000/api/v1/tenants", json={
        "name": "Acme Corp",
        "email": "admin@acmecorp.com",
        "phone": "+15551234567",
        "gdpr_consent": True
    }, headers=headers)
    print("Status:", r2.status_code)
    print("Body:", r2.text[:500])

    # Try creating agent
    print("\n=== CREATE AGENT ===")
    tenant_id = "TENANT-001"
    r3 = httpx.post(
        "http://127.0.0.1:8000/api/v1/tenants/" + tenant_id + "/agents",
        json={"name": "Test Agent", "display_name": "Test Agent",
              "agent_type": "ai", "skills": ["sales"]},
        headers=headers)
    print("Status:", r3.status_code)
    print("Body:", r3.text[:500])

    # Try listing agents
    print("\n=== LIST AGENTS ===")
    r4 = httpx.get(
        "http://127.0.0.1:8000/api/v1/tenants/" + tenant_id + "/agents",
        headers=headers)
    print("Status:", r4.status_code)
    print("Body:", r4.text[:500])
else:
    print("Login response:", r.text[:500])