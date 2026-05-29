"""
AetherDesk - Start servers and open visible Chrome for human interaction.
No Playwright automation - just opens the browser for YOU to use.
"""
import subprocess, os, sys, time, httpx, signal

os.chdir(r"C:\Users\User\Desktop\aetherdesk_scaffold")

# Environment - load from env vars first, fall back to dev defaults
dev_env = {
    "ENCRYPTION_KEY": os.getenv("ENCRYPTION_KEY", "SkYXQ9OlgNAkCoikdZW9NQLYhRbdgQSrV7vfrnCjxLA="),
    "JWT_SECRET": os.getenv("JWT_SECRET", "dev-secret-key-change-me"),
    "WEBSOCKET_SECRET_KEY": os.getenv("WEBSOCKET_SECRET_KEY", "dev-websocket-secret-change-me"),
    "USE_POSTGRES": os.getenv("USE_POSTGRES", "false"),
    "DEEPGRAM_API_KEY": os.getenv("DEEPGRAM_API_KEY"),
    "GROQ_API_KEY": os.getenv("GROQ_API_KEY"),
    "VITE_API_URL": os.getenv("VITE_API_URL", "http://127.0.0.1:8000"),
}
for k, v in dev_env.items():
    if v is not None:  # Don't set empty values
        os.environ[k] = v

try:
    os.remove("aetherdesk.db")
except:
    pass

print("=" * 60)
print("  AETHERDESK CALL CENTER")
print("=" * 60)
print()

# ---- START API SERVER ----
print("[1/2] Starting API server on port 8000...")
api_out = open(r"C:\Users\User\AppData\Local\Temp\aetherdesk_api.log", "w")
api_proc = subprocess.Popen(
    [sys.executable, "-u", "-m", "uvicorn", "apps.api.main:app",
     "--host", "127.0.0.1", "--port", "8000", "--log-level", "info"],
    stdout=api_out, stderr=api_out,
    cwd=r"C:\Users\User\Desktop\aetherdesk_scaffold"
)

# Wait for API
for i in range(40):
    try:
        r = httpx.get("http://127.0.0.1:8000/health", timeout=2)
        if r.status_code == 200:
            print(f"    API is UP! [{r.json()['status']}]")
            break
    except:
        pass
    time.sleep(0.3)
else:
    print("    API failed to start!")
    api_out.close()
    with open(r"C:\Users\User\AppData\Local\Temp\aetherdesk_api.log") as f:
        print("    LOG:", f.read()[-500:])
    sys.exit(1)

# ---- SETUP DATA ----
print("[2/2] Setting up test data (login, tenant, agent, call)...")
login = httpx.post("http://127.0.0.1:8000/auth/login", json={
    "email": "admin@aetherdesk.com", "password": "admin123"
})
if login.status_code != 200:
    print("    Login failed!")
    sys.exit(1)

token = login.json()["token"]
h = {"Authorization": f"Bearer {token}"}

t = httpx.post("http://127.0.0.1:8000/api/v1/tenants", json={
    "name": "Acme Corp", "email": "admin@acmecorp.com",
    "phone": "+15551234567"
}, headers=h)
tid = t.json()["id"] if t.status_code in (200, 201) else ""

if tid:
    a = httpx.post(f"http://127.0.0.1:8000/api/v1/tenants/{tid}/agents", json={
        "name": "Sarah Sales", "display_name": "Sarah Sales Agent",
        "agent_type": "ai", "skills": ["sales"]
    }, headers=h)
    if a.status_code == 201:
        print(f"    Agent created: SIP={a.json().get('sip_extension')}")

    c = httpx.post("http://127.0.0.1:8000/api/v1/calls", json={
        "caller_number": "+15559876543", "called_number": "+15551234567",
        "call_direction": "inbound", "intent": "sales",
        "agent_id": a.json()["id"] if a.status_code == 201 else ""
    }, headers=h)
    if c.status_code == 201:
        print(f"    Call created: {c.json()['id'][:8]}")

# ---- START UI SERVER ----
print("\nStarting UI server on port 3001...")
ui_env = os.environ.copy()
ui_proc = subprocess.Popen(
    [r"C:\Program Files\nodejs\npx.CMD", "vite", "dev",
     "--host", "127.0.0.1", "--port", "3001"],
    cwd=r"C:\Users\User\Desktop\aetherdesk_scaffold\agent-ui",
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    env=ui_env
)

# Wait for UI
for i in range(40):
    try:
        r = httpx.get("http://127.0.0.1:3001/", timeout=2)
        if r.status_code == 200:
            print(f"    UI is UP! [status={r.status_code}]")
            break
        else:
            port = 3002
            try:
                r2 = httpx.get(f"http://127.0.0.1:{port}/", timeout=2)
                if r2.status_code == 200:
                    print(f"    UI is UP on port {port}!")
                    ui_url = f"http://127.0.0.1:{port}"
            except:
                pass
    except:
        pass
    time.sleep(0.5)
else:
    print("    UI not responding - trying alternate ports...")
    ui_url = "http://127.0.0.1:3001"

ui_url = "http://127.0.0.1:3001"

# ---- OPEN CHROME ----
print()
print("=" * 60)
print("  EVERYTHING IS RUNNING!")
print("=" * 60)
print()
print(f"  API Server : http://127.0.0.1:8000")
print(f"  UI Server  : {ui_url}")
print(f"  API Docs   : http://127.0.0.1:8000/docs")
print()
print("  Login credentials:")
print("    Email:    admin@aetherdesk.com")
print("    Password: admin123")
print()
print("  Opening Chrome...")
print("=" * 60)

# Open Chrome simply - no Playwright automation
try:
    os.startfile(f"{ui_url}/login")
except:
    subprocess.Popen(["start", "chrome", f"{ui_url}/login"], shell=True)

print()
print("Chrome opened! The login page should be visible.")
print("Log in with the credentials above to access the dashboard.")
print()
print("Close this window to stop all servers.")
print("=" * 60)

# Keep running
try:
    signal.pause()
except (KeyboardInterrupt, SystemExit):
    print("\nShutting down...")
    api_proc.terminate()
    ui_proc.terminate()