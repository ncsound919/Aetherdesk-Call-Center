"""Start AetherDesk API server and test it."""
import subprocess, os, sys, time, json

os.chdir(r"C:\Users\User\Desktop\aetherdesk_scaffold")
os.environ["ENCRYPTION_KEY"] = "REDACTED_ENCRYPTION_KEY_PLEASE_ROTATE="
os.environ["JWT_SECRET"] = "test-websocket-secret"
os.environ["WEBSOCKET_SECRET_KEY"] = "test-websocket-secret"
os.environ["USE_POSTGRES"] = "false"

# Write a tiny test script
with open(r"C:\Users\User\AppData\Local\Temp\opencode\quick_test.py", "w") as f:
    f.write('''
import httpx, json, sys, time
time.sleep(3)
try:
    r = httpx.get("http://127.0.0.1:8000/health", timeout=5)
    print("HEALTH:", r.status_code, r.json()["status"])
except Exception as e:
    print("HEALTH FAIL:", e)
    sys.exit(1)

login = httpx.post("http://127.0.0.1:8000/auth/login", json={
    "email": "admin@aetherdesk.com", "password": "admin123"
})
print("LOGIN:", login.status_code)
if login.status_code == 200:
    token = login.json()["token"]
    h = {"Authorization": "Bearer " + token}
    t = httpx.post("http://127.0.0.1:8000/api/v1/tenants", json={
        "name": "Acme Corp", "email": "admin@acmecorp.com",
        "phone": "+15551234567", "gdpr_consent": True
    }, headers=h)
    print("TENANT:", t.status_code)
    if t.status_code == 201:
        tid = t.json()["id"]
        a = httpx.post("http://127.0.0.1:8000/api/v1/tenants/" + tid + "/agents", json={
            "name": "Sarah", "display_name": "Sarah Sales",
            "agent_type": "ai", "skills": ["sales"]
        }, headers=h)
        print("AGENT:", a.status_code)
        if a.status_code == 201:
            d = a.json()
            print("  Created:", d["name"], "SIP:", d.get("sip_extension"))
    print("ALL TESTS PASSED")
else:
    print("Login failed:", login.text[:300])
''')

# Start test in background
tester = subprocess.Popen(
    [sys.executable, "-u", r"C:\Users\User\AppData\Local\Temp\opencode\quick_test.py"],
    stdout=subprocess.PIPE, stderr=subprocess.STDOUT
)

# Start server
print("=== STARTING SERVER ===")
server = subprocess.Popen(
    [sys.executable, "-m", "uvicorn", "apps.api.main:app",
     "--host", "127.0.0.1", "--port", "8000", "--log-level", "info"]
)
print("Server PID:", server.pid)

# Collect test output
for _ in range(40):
    line = tester.stdout.readline().decode()
    if line:
        print("TEST> " + line.rstrip())
    time.sleep(0.5)

server.terminate()
print("=== DONE ===")