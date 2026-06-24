"""Check which voice client is active on the running server."""
import httpx

BASE = "http://localhost:8000"

# The health check calls fonster_client.health_check()
# Let's see what it returns
r = httpx.get(f"{BASE}/health", timeout=15)
data = r.json()
print(f"Health: {data['status']}")
print(f"Services: {data['services']}")
print(f"fonster_connected: {data.get('fonster_connected')}")

# Make a call and check if Twilio receives it
r = httpx.post(f"{BASE}/api/v1/auth/login",
    json={"email": "admin@aetherdesk.com", "password": "admin123"}, timeout=10)
t = r.json()["token"]
tid = r.json()["tenantId"]

r = httpx.get(f"{BASE}/api/v1/tenants/{tid}/agents",
    headers={"Authorization": f"Bearer {t}"}, timeout=10)
aid = r.json()[0]["id"]

r = httpx.post(f"{BASE}/api/v1/calls?tenant_id={tid}",
    json={"agent_id": aid, "caller_number": "+19843656059", "call_direction": "outbound"},
    headers={"x-api-key": "dev-api-key"}, timeout=30)
print(f"Call: {r.status_code}")
if r.status_code == 201:
    print(f"  ID: {r.json()['id']}")
    print(f"  Status: {r.json()['call_status']}")
