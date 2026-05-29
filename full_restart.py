#!/usr/bin/env python
"""Full clean restart and test."""
import subprocess, os, sys, time, json, httpx

os.makedirs(r"C:\Users\User\AppData\Local\Temp\opencode", exist_ok=True)
os.chdir(r"C:\Users\User\Desktop\aetherdesk_scaffold")

# Set all env vars
for k, v in {
    "ENCRYPTION_KEY": "SkYXQ9OlgNAkCoikdZW9NQLYhRbdgQSrV7vfrnCjxLA=",
    "JWT_SECRET": "test-websocket-secret",
    "WEBSOCKET_SECRET_KEY": "test-websocket-secret",
    "USE_POSTGRES": "false",
    "DEEPGRAM_API_KEY": os.getenv("DEEPGRAM_API_KEY", "REPLACE_WITH_DEEPGRAM_API_KEY"),
    "GROQ_API_KEY": os.getenv("GROQ_API_KEY", "REPLACE_WITH_GROQ_API_KEY"),
}.items():
    os.environ[k] = v

# Kill ALL old processes
print("Killing old processes...")
os.system('taskkill /F /IM "python.exe" 2>nul')
os.system('taskkill /F /IM "node.exe" 2>nul')
time.sleep(5)

# Remove old SQLite DB to start fresh
db_path = r"C:\Users\User\Desktop\aetherdesk_scaffold\aetherdesk.db"
if os.path.exists(db_path):
    os.remove(db_path)
    print("Removed old SQLite DB")

# Start API using uvicorn directly
print("Starting API server...")
proc = subprocess.Popen(
    [sys.executable, "-m", "uvicorn", "apps.api.main:app",
     "--host", "127.0.0.1", "--port", "8000", "--log-level", "info"],
    stdout=open(r"C:\Users\User\AppData\Local\Temp\opencode\api_out.log", "w"),
    stderr=open(r"C:\Users\User\AppData\Local\Temp\opencode\api_err.log", "w"),
)
print("API PID:", proc.pid)

# Wait and check logs
time.sleep(10)
with open(r"C:\Users\User\AppData\Local\Temp\opencode\api_err.log") as f:
    stderr = f.read()
    if stderr:
        print("API stderr:", stderr[-1000:])

# Test sequentially
print("\n=== Testing endpoints ===")

# Health
try:
    r = httpx.get("http://127.0.0.1:8000/health", timeout=10)
    print("HEALTH:", r.status_code, r.json()["status"])
except Exception as e:
    print("HEALTH FAILED:", e)

# Login
try:
    r = httpx.post("http://127.0.0.1:8000/auth/login", json={
        "email": "admin@aetherdesk.com", "password": "admin123"
    }, timeout=10)
    print("LOGIN:", r.status_code)
    if r.status_code == 200:
        token = r.json()["token"]
        headers = {"Authorization": "Bearer " + token}
        print("  Got token:", token[:40] + "...")
    else:
        print("  Login error:", r.text[:200])
        headers = {}
except Exception as e:
    print("LOGIN FAILED:", e)
    headers = {}

# Create tenant
if headers:
    try:
        r = httpx.post("http://127.0.0.1:8000/api/v1/tenants", json={
            "name": "Acme Corp", "email": "admin@acmecorp.com",
            "phone": "+15551234567", "gdpr_consent": True
        }, headers=headers, timeout=15)
        print("CREATE TENANT:", r.status_code)
        if r.status_code == 201:
            tenant_id = r.json()["id"]
            print("  Tenant ID:", tenant_id[:8])
        else:
            print("  Error:", r.text[:300])
            tenant_id = "TENANT-001"
    except Exception as e:
        print("CREATE TENANT FAILED:", e)
        tenant_id = "TENANT-001"

    # Create agent
    try:
        r = httpx.post(
            "http://127.0.0.1:8000/api/v1/tenants/" + tenant_id + "/agents",
            json={"name": "Sales Agent", "display_name": "Sarah",
                  "agent_type": "ai", "skills": ["sales"]},
            headers=headers, timeout=15)
        print("CREATE AGENT:", r.status_code)
        if r.status_code == 201:
            d = r.json()
            print("  Agent:", d["name"], "SIP:", d.get("sip_extension"))
        else:
            print("  Error:", r.text[:300])
    except Exception as e:
        print("CREATE AGENT FAILED:", e)

print("\nServer is running. Open http://127.0.0.1:3001 in Chrome.")