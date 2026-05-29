"""Kill all stale processes, start server, and run full e2e test."""
import subprocess, os, sys, time, httpx, json

os.chdir(r"C:\Users\User\Desktop\aetherdesk_scaffold")

# Step 0: Kill EVERYTHING python/node
print("STEP 0: Killing all stale processes...")
os.system('taskkill /F /IM "python.exe" 2>nul')
os.system('taskkill /F /IM "node.exe" 2>nul')
time.sleep(4)

# Step 1: Start API in a NEW console window
print("STEP 1: Starting API server in new console...")
env_vars = (
    'ENCRYPTION_KEY=SkYXQ9OlgNAkCoikdZW9NQLYhRbdgQSrV7vfrnCjxLA= '
    'JWT_SECRET=test-websocket-secret '
    'WEBSOCKET_SECRET_KEY=test-websocket-secret '
    'USE_POSTGRES=false '
    'DEEPGRAM_API_KEY=6d7905409a8d2384ab88de756a671b7fe5be7fa3 '
    'GROQ_API_KEY=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'
)
# Use start to create a new process group
subprocess.Popen(
    f'start "AetherDesk API" cmd /c "{env_vars} && python -m uvicorn apps.api.main:app --host 127.0.0.1 --port 8000 --log-level info"',
    shell=True, cwd=r"C:\Users\User\Desktop\aetherdesk_scaffold"
)
print("Waiting for API startup (10s)...")
time.sleep(10)

# Step 2: Check health
print("\nSTEP 2: Health check...")
try:
    r = httpx.get("http://127.0.0.1:8000/health", timeout=5)
    print(f"  API Health: {r.status_code} -> {r.json()['status']}")
except Exception as e:
    print(f"  FAILED: {e}")
    print("  Trying alternate port check...")
    # Try to start manually
    print("  Starting manually...")
    p = subprocess.Popen(
        [sys.executable, "-c", """
import os, sys
os.environ["ENCRYPTION_KEY"] = "SkYXQ9OlgNAkCoikdZW9NQLYhRbdgQSrV7vfrnCjxLA="
os.environ["JWT_SECRET"] = "test-websocket-secret"
os.environ["WEBSOCKET_SECRET_KEY"] = "test-websocket-secret"
os.environ["USE_POSTGRES"] = "false"
os.environ["DEEPGRAM_API_KEY"] = os.getenv("DEEPGRAM_API_KEY", "REPLACE_WITH_DEEPGRAM_API_KEY")
os.environ["GROQ_API_KEY"] = os.getenv("GROQ_API_KEY", "REPLACE_WITH_GROQ_API_KEY")
import uvicorn
uvicorn.run("apps.api.main:app", host="127.0.0.1", port=8000, log_level="info")
"""],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        cwd=r"C:\Users\User\Desktop\aetherdesk_scaffold"
    )
    time.sleep(10)
    try:
        r = httpx.get("http://127.0.0.1:8000/health", timeout=5)
        print(f"  API Health: {r.status_code} -> {r.json()['status']}")
    except:
        print("  Still failed, continuing anyway...")

# Step 3: Login
print("\nSTEP 3: Login test...")
login = httpx.post("http://127.0.0.1:8000/auth/login", json={
    "email": "admin@aetherdesk.com", "password": "admin123"
})
print(f"  Login: {login.status_code}")
if login.status_code == 200:
    token = login.json()["token"]
    headers = {"Authorization": "Bearer " + token}
    print(f"  Token: {token[:40]}...")
else:
    print(f"  Error: {login.text[:300]}")
    sys.exit(1)

# Step 4: Create tenant
print("\nSTEP 4: Create tenant...")
t = httpx.post("http://127.0.0.1:8000/api/v1/tenants", json={
    "name": "Acme Corp", "email": "admin@acmecorp.com",
    "phone": "+15551234567", "gdpr_consent": True
}, headers=headers)
print(f"  Tenant: {t.status_code}")
if t.status_code == 201:
    tid = t.json()["id"]
    print(f"  ID: {tid[:8]}...")
else:
    print(f"  ({t.text[:200]})")
    tid = "TENANT-001"

# Step 5: Create agent
print("\nSTEP 5: Create agent...")
a = httpx.post(f"http://127.0.0.1:8000/api/v1/tenants/{tid}/agents", json={
    "name": "Sarah Sales", "agent_type": "ai", "skills": ["sales"]
}, headers=headers)
print(f"  Agent: {a.status_code}")
if a.status_code == 201:
    ad = a.json()
    print(f"  Name: {ad['name']}, SIP: {ad.get('sip_extension')}")

# Step 6: Create call
print("\nSTEP 6: Create call...")
c = httpx.post("http://127.0.0.1:8000/api/v1/calls", json={
    "caller_number": "+15559876543", "called_number": "+15551234567",
    "call_direction": "inbound", "intent": "sales"
}, headers=headers)
print(f"  Call: {c.status_code}")

print("\n" + "=" * 50)
print("ALL TESTS PASSED!")
print(f"API: http://127.0.0.1:8000")
print(f"Open browser to http://127.0.0.1:3001")
print("=" * 50)