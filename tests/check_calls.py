"""Verify calls routes and test call creation."""
import httpx

BASE = "http://localhost:8000"

# Login
r = httpx.post(f"{BASE}/api/v1/auth/login",
    json={"email": "admin@aetherdesk.com", "password": "admin123"}, timeout=10)
t = r.json()["token"]
tid = r.json()["tenantId"]

# Check call route via direct GET
for path in ["/api/v1/calls", "/api/v1/calls/calls"]:
    r = httpx.get(f"{BASE}{path}?tenant_id={tid}",
        headers={"x-api-key": "dev-api-key"}, timeout=10)
    print(f"GET {path}: {r.status_code}")

# Get agent
r = httpx.get(f"{BASE}/api/v1/tenants/{tid}/agents",
    headers={"Authorization": f"Bearer {t}"}, timeout=10)
agents = r.json()
aid = agents[0]["id"] if agents else None
print(f"Using agent: {aid}")

# Create call
r = httpx.post(f"{BASE}/api/v1/calls?tenant_id={tid}",
    json={"agent_id": aid, "caller_number": "+19843656059", "call_direction": "inbound"},
    headers={"x-api-key": "dev-api-key"}, timeout=10)
print(f"POST /api/v1/calls: {r.status_code}")
if r.status_code == 201:
    print(f"  OK: {r.json()}")
else:
    print(f"  Error: {r.text[:300]}")
