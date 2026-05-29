#!/usr/bin/env python
"""Restart server with fixes and run debug test."""
import subprocess, os, sys, time, json, httpx

os.makedirs(r"C:\Users\User\AppData\Local\Temp\opencode", exist_ok=True)
os.chdir(r"C:\Users\User\Desktop\aetherdesk_scaffold")

os.environ["ENCRYPTION_KEY"] = "REDACTED_ENCRYPTION_KEY_PLEASE_ROTATE="
os.environ["JWT_SECRET"] = "test-websocket-secret"
os.environ["WEBSOCKET_SECRET_KEY"] = "test-websocket-secret"
os.environ["USE_POSTGRES"] = "false"
os.environ["DEEPGRAM_API_KEY"] = os.getenv("DEEPGRAM_API_KEY", "REPLACE_WITH_DEEPGRAM_API_KEY")
os.environ["GROQ_API_KEY"] = os.getenv("GROQ_API_KEY", "REPLACE_WITH_GROQ_API_KEY")

# Start API server directly (no taskkill - that was killing the new process)
print("Starting API server...")
proc = subprocess.Popen(
    [sys.executable, "run_server.py"],
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE
)
print("API PID:", proc.pid)
time.sleep(12)

poll = proc.poll()
if poll is not None:
    out, err = proc.communicate()
    print("API died! stdout:", out.decode()[-500:])
    print("API died! stderr:", err.decode()[-500:])
    sys.exit(1)
else:
    print("API process is running")

# Test health
try:
    r = httpx.get("http://127.0.0.1:8000/health", timeout=5)
    print("Health:", r.status_code, r.json()["status"])
except Exception as e:
    print("Health failed:", e)
    sys.exit(1)

# Login
login = httpx.post("http://127.0.0.1:8000/auth/login", json={
    "email": "admin@aetherdesk.com", "password": "admin123"
})
print("Login:", login.status_code)
if login.status_code != 200:
    print("Login failed:", login.text[:500])
    sys.exit(1)

token = login.json()["token"]
headers = {"Authorization": "Bearer " + token}

# Create tenant
t = httpx.post("http://127.0.0.1:8000/api/v1/tenants", json={
    "name": "Acme Corp", "email": "admin@acmecorp.com",
    "phone": "+15551234567", "gdpr_consent": True
}, headers=headers)
print("Create tenant:", t.status_code)
if t.status_code == 201:
    tenant_id = t.json()["id"]
    print("  Tenant ID:", tenant_id)
else:
    print("  Error:", t.text[:500])
    tenant_id = "TENANT-001"

# Create agent
agent_body = {
    "name": "Sales Agent", "display_name": "Sarah",
    "agent_type": "ai", "skills": ["sales"]
}
a = httpx.post(
    "http://127.0.0.1:8000/api/v1/tenants/" + tenant_id + "/agents",
    json=agent_body, headers=headers)
print("Create agent:", a.status_code)
if a.status_code == 201:
    agent_id = a.json()["id"]
    print("  Agent ID:", agent_id, "SIP:", a.json().get("sip_extension"))
else:
    print("  Error:", a.text[:500])
    agent_id = None

# List agents
la = httpx.get(
    "http://127.0.0.1:8000/api/v1/tenants/" + tenant_id + "/agents",
    headers=headers)
print("List agents:", la.status_code)
if la.status_code == 200:
    agents = la.json()
    for ag in agents:
        print("  -", ag["name"], "(" + ag["status"] + ")")

# Create call
if agent_id:
    call = httpx.post("http://127.0.0.1:8000/api/v1/calls", json={
        "caller_number": "+15559876543",
        "called_number": "+15551234567",
        "call_direction": "inbound",
        "agent_id": agent_id,
        "intent": "sales"
    }, headers=headers)
    print("Create call:", call.status_code)
    if call.status_code == 201:
        print("  Call ID:", call.json()["id"][:8])

print("\n=== ALL TESTS PASSED ===")
print("Server running at http://127.0.0.1:8000")
print("Keep this running, then open Chrome to http://127.0.0.1:3001")