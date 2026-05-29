#!/usr/bin/env python
"""Full clean restart and test - fixed process killing order."""
import subprocess, os, sys, time, json, httpx, signal

os.makedirs(r"C:\Users\User\AppData\Local\Temp\opencode", exist_ok=True)
os.chdir(r"C:\Users\User\Desktop\aetherdesk_scaffold")

# Set all env vars FIRST
for k, v in {
    "ENCRYPTION_KEY": "REDACTED_ENCRYPTION_KEY_PLEASE_ROTATE=",
    "JWT_SECRET": "test-websocket-secret",
    "WEBSOCKET_SECRET_KEY": "test-websocket-secret",
    "USE_POSTGRES": "false",
    "DEEPGRAM_API_KEY": os.getenv("DEEPGRAM_API_KEY", "REPLACE_WITH_DEEPGRAM_API_KEY"),
    "GROQ_API_KEY": os.getenv("GROQ_API_KEY", "REPLACE_WITH_GROQ_API_KEY"),
}.items():
    os.environ[k] = v

# Kill old processes FIRST (before starting anything)
print("Step 1: Killing old processes...")
os.system('taskkill /F /IM "python.exe" 2>nul')
os.system('taskkill /F /IM "node.exe" 2>nul')
time.sleep(5)

# Remove old SQLite DB
db_path = r"C:\Users\User\Desktop\aetherdesk_scaffold\aetherdesk.db"
if os.path.exists(db_path):
    os.remove(db_path)
    print("Removed old SQLite DB")

# Start API server
print("Step 2: Starting API server...")
outfile = open(r"C:\Users\User\AppData\Local\Temp\opencode\api_out.log", "w")
errfile = open(r"C:\Users\User\AppData\Local\Temp\opencode\api_err.log", "w")
proc = subprocess.Popen(
    [sys.executable, "-m", "uvicorn", "apps.api.main:app",
     "--host", "127.0.0.1", "--port", "8000", "--log-level", "info"],
    stdout=outfile, stderr=errfile
)
print("API started with PID:", proc.pid)

# Wait for startup
print("Step 3: Waiting for server startup (12s)...")
time.sleep(12)

# Check if process is still alive
poll = proc.poll()
if poll is not None:
    print("ERROR: API process died! Exit code:", poll)
    outfile.close()
    errfile.close()
    with open(r"C:\Users\User\AppData\Local\Temp\opencode\api_err.log") as f:
        print("STDERR:", f.read()[-1000:])
    sys.exit(1)
else:
    print("API process is running")

# Check logs
with open(r"C:\Users\User\AppData\Local\Temp\opencode\api_err.log") as f:
    err = f.read()
    if err:
        print("API stderr (last 500 chars):", err[-500:])

# Now test
print("\nStep 4: Testing endpoints...")
try:
    r = httpx.get("http://127.0.0.1:8000/health", timeout=10)
    print("HEALTH:", r.status_code, r.json()["status"])
except Exception as e:
    print("HEALTH FAILED:", e)

# Login
r = httpx.post("http://127.0.0.1:8000/auth/login", json={
    "email": "admin@aetherdesk.com", "password": "admin123"
}, timeout=10)
print("LOGIN:", r.status_code)
if r.status_code == 200:
    token = r.json()["token"]
    headers = {"Authorization": "Bearer " + token}
    print("  Got JWT token:", token[:40] + "...")
else:
    print("  Error:", r.text[:300])
    headers = {}

# Create tenant
if headers:
    r = httpx.post("http://127.0.0.1:8000/api/v1/tenants", json={
        "name": "Acme Corp", "email": "admin@acmecorp.com",
        "phone": "+15551234567", "gdpr_consent": True
    }, headers=headers, timeout=15)
    print("CREATE TENANT:", r.status_code)
    if r.status_code == 201:
        tenant_id = r.json()["id"]
        print("  Tenant:", tenant_id[:8])
    else:
        print("  Error:", r.text[:300])
        tenant_id = "TENANT-001"

    # Create agent
    r = httpx.post(
        "http://127.0.0.1:8000/api/v1/tenants/" + tenant_id + "/agents",
        json={"name": "Sarah", "display_name": "Sarah Sales",
              "agent_type": "ai", "skills": ["sales"]},
        headers=headers, timeout=15)
    print("CREATE AGENT:", r.status_code)
    if r.status_code == 201:
        d = r.json()
        print("  Agent:", d["name"], "SIP:", d.get("sip_extension"))
    else:
        print("  Error:", r.text[:300])

    # Create call
    r = httpx.post("http://127.0.0.1:8000/api/v1/calls", json={
        "caller_number": "+15559876543",
        "called_number": "+15551234567",
        "call_direction": "inbound",
        "agent_id": "fake-agent-id",
        "intent": "sales"
    }, headers=headers, timeout=15)
    print("CREATE CALL:", r.status_code)
    if r.status_code == 201:
        print("  Call:", r.json()["id"][:8])

print("\n=== DONE ===")
print("API:", "http://127.0.0.1:8000")
print("To start UI, run: cd agent-ui && npx vite dev --host 127.0.0.1 --port 3001")