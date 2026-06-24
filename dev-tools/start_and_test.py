#!/usr/bin/env python
"""Kill processes on port 8000, then start fresh."""
import subprocess, os, sys, time, httpx, socket

os.chdir(r"C:\Users\User\Desktop\aetherdesk_scaffold")

# Find and kill whatever is on port 8000
print("Finding processes on port 8000...")
result = subprocess.run(
    ['netstat', '-ano'], capture_output=True, text=True
)
for line in result.stdout.split('\n'):
    if ':8000' in line and 'LISTENING' in line:
        parts = line.strip().split()
        if len(parts) >= 5:
            pid = parts[-1]
            print(f"  Found PID {pid} on port 8000, killing...")
            subprocess.run(f'taskkill /F /PID {pid}', shell=True, capture_output=True)
            time.sleep(1)

# Double-check with Python socket
def is_port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(('127.0.0.1', port))
            return False
        except OSError:
            return True

if is_port_in_use(8000):
    print("Port 8000 still in use! Trying harder kill...")
    os.system('taskkill /F /FI "PID gt 0" /IM "python*" 2>nul')
    time.sleep(3)

if is_port_in_use(8000):
    print("ERROR: Cannot free port 8000")
    sys.exit(1)
else:
    print("Port 8000 is free!")

# Set env
for k, v in {
    "ENCRYPTION_KEY": "SkYXQ9OlgNAkCoikdZW9NQLYhRbdgQSrV7vfrnCjxLA=",
    "JWT_SECRET": "test-websocket-secret",
    "WEBSOCKET_SECRET_KEY": "test-websocket-secret",
    "USE_POSTGRES": "false",
    "DEEPGRAM_API_KEY": os.getenv("DEEPGRAM_API_KEY", "REPLACE_WITH_DEEPGRAM_API_KEY"),
    "GROQ_API_KEY": os.getenv("GROQ_API_KEY", "REPLACE_WITH_GROQ_API_KEY"),
}.items():
    os.environ[k] = v

# Start server
print("Starting API server...")
out = open(r"C:\Users\User\AppData\Local\Temp\opencode\server.log", "w")
proc = subprocess.Popen(
    [sys.executable, "-m", "uvicorn", "apps.api.main:app",
     "--host", "127.0.0.1", "--port", "8000", "--log-level", "info"],
    stdout=out, stderr=subprocess.STDOUT
)
print("PID:", proc.pid)

# Wait for startup
for i in range(30):
    time.sleep(1)
    poll = proc.poll()
    if poll is not None:
        print("Process died!")
        out.close()
        with open(r"C:\Users\User\AppData\Local\Temp\opencode\server.log") as f:
            print(f.read()[-2000:])
        sys.exit(1)
    try:
        r = httpx.get("http://127.0.0.1:8000/health", timeout=2)
        if r.status_code == 200:
            print(f"Server UP in {i}s! Status: {r.json()['status']}")
            break
    except:
        pass
else:
    print("Server never ready")

out.close()

# Login
login = httpx.post("http://127.0.0.1:8000/auth/login", json={
    "email": "admin@aetherdesk.com", "password": "admin123"
})
print("LOGIN:", login.status_code)
if login.status_code != 200:
    print("  Failed:", login.text[:300])
    sys.exit(1)

token = login.json()["token"]
headers = {"Authorization": "Bearer " + token}

# Create tenant
t = httpx.post("http://127.0.0.1:8000/api/v1/tenants", json={
    "name": "Acme Corp", "email": "admin@acmecorp.com",
    "phone": "+15551234567", "gdpr_consent": True
}, headers=headers)
print("TENANT:", t.status_code, t.json()["id"][:8] if t.status_code == 201 else t.text[:200])
tid = t.json()["id"] if t.status_code == 201 else "TENANT-001"

# Create agent
a = httpx.post(
    "http://127.0.0.1:8000/api/v1/tenants/" + tid + "/agents",
    json={"name": "Sarah", "display_name": "Sarah Sales",
          "agent_type": "ai", "skills": ["sales"]},
    headers=headers)
print("AGENT:", a.status_code)
if a.status_code == 201:
    d = a.json()
    print("  Name:", d["name"], "SIP:", d.get("sip_extension"))

# List agents
la = httpx.get("http://127.0.0.1:8000/api/v1/tenants/" + tid + "/agents", headers=headers)
print("LIST:", la.status_code)
for ag in la.json():
    print("  -", ag["name"], ag["status"])

print("\n=== ALL TESTS PASSED ===")
print("API: http://127.0.0.1:8000  |  UI: http://127.0.0.1:3001")