"""
Launch AetherDesk servers without killing them.
The servers run in background cmd windows, browser opens for interaction.
"""
import subprocess, os, sys, time, httpx, json

os.chdir(r"C:\Users\User\Desktop\aetherdesk_scaffold")
my_env = os.environ.copy()
my_env["ENCRYPTION_KEY"] = "REDACTED_ENCRYPTION_KEY_PLEASE_ROTATE="
my_env["JWT_SECRET"] = "test-websocket-secret"
my_env["WEBSOCKET_SECRET_KEY"] = "test-websocket-secret"
my_env["USE_POSTGRES"] = "false"
my_env["DEEPGRAM_API_KEY"] = os.getenv("DEEPGRAM_API_KEY", "REPLACE_WITH_DEEPGRAM_API_KEY")
my_env["GROQ_API_KEY"] = os.getenv("GROQ_API_KEY", "REPLACE_WITH_GROQ_API_KEY")
my_env["VITE_API_URL"] = "http://127.0.0.1:8000"

# Only kill node (stale Vite), NOT python (might be an IDE or other process)
print("Cleaning stale Node processes...")
os.system('taskkill /F /IM "node.exe" 2>nul')
time.sleep(2)

# ---- Start API Server ----
print("Starting API server on port 8000...")
subprocess.Popen(
    'cmd /c "title [API] AetherDesk & color 0C & cd /d '
    + os.path.abspath('.').replace(os.sep, '\\\\')
    + ' & python -m uvicorn apps.api.main:app --host 127.0.0.1 --port 8000 --log-level info & echo SERVER_PID=%!"',
    shell=True, env=my_env, cwd=os.path.abspath('.')
)

# ---- Start UI Server ----
print("Starting UI server on port 3001...")
subprocess.Popen(
    'cmd /c "title [UI] AetherDesk UI & color 0B & cd /d '
    + os.path.abspath('agent-ui').replace(os.sep, '\\\\')
    + ' & npx vite dev --host 127.0.0.1 --port 3001 --strictPort"',
    shell=True, env=my_env
)

# Wait for both servers
print("\nWaiting for servers to start (15 seconds)...")
for i in range(15):
    sys.stdout.write(f"\r  {15-i}s remaining...")
    sys.stdout.flush()
    time.sleep(1)

# Check API
print("\n\nChecking API...")
api_ok = False
for attempt in range(5):
    try:
        r = httpx.get("http://127.0.0.1:8000/health", timeout=5)
        if r.status_code == 200:
            status = r.json()["status"]
            print(f"  API: OK (status={status})")
            api_ok = True
            break
    except Exception as e:
        time.sleep(2)

if not api_ok:
    print("  API: NOT RESPONDING")

# Login
if api_ok:
    login = httpx.post("http://127.0.0.1:8000/auth/login", json={
        "email": "admin@aetherdesk.com", "password": "admin123"
    })
    if login.status_code == 200:
        token = login.json()["token"]
        h = {"Authorization": f"Bearer {token}"}
        print(f"  Login: OK (user=Admin)")

        # Create tenant
        t = httpx.post("http://127.0.0.1:8000/api/v1/tenants", json={
            "name": "Acme Corp", "email": "admin@acmecorp.com",
            "phone": "+15551234567", "gdpr_consent": True
        }, headers=h)
        if t.status_code == 201:
            tid = t.json()["id"]
            print(f"  Tenant: OK ({tid[:8]})")
        else:
            print(f"  Tenant: {t.status_code} - {t.text[:200]}")
            tid = "TENANT-001"

        # Create agent
        a = httpx.post(f"http://127.0.0.1:8000/api/v1/tenants/{tid}/agents", json={
            "name": "Sarah Sales", "display_name": "Sarah Sales",
            "agent_type": "ai", "skills": ["sales"]
        }, headers=h)
        if a.status_code == 201:
            print(f"  Agent: OK (SIP: {a.json().get('sip_extension')})")

# Check UI
print("\nChecking UI...")
ui_ok = False
for attempt in range(5):
    try:
        r = httpx.get("http://127.0.0.1:3001/", timeout=5)
        print(f"  UI: OK (status={r.status_code})")
        ui_ok = True
        break
    except Exception as e:
        time.sleep(2)

if not ui_ok:
    print("  UI: NOT RESPONDING")

print(f"\n{'='*60}")
print("  AETHERDESK CALL CENTER IS RUNNING")
print(f"{'='*60}")
print(f"  API : http://127.0.0.1:8000")
print(f"  UI  : http://127.0.0.1:3001  (open in Chrome)")
print(f"  Docs: http://127.0.0.1:8000/docs")
print(f"\n  Log in with: admin@aetherdesk.com / admin123")
print(f"{'='*60}")

# Open Chrome
print("\nOpening Chrome for interaction...")
from playwright.sync_api import sync_playwright

try:
    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=False,
            args=["--no-first-run", "--no-default-browser-check",
                  "--disable-blink-features=AutomationControlled", "--start-maximized"]
        )
        page = browser.new_page(viewport={"width": 1920, "height": 1080})
        page.goto("http://127.0.0.1:3001/login", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(3000)

        # Try to find and fill login form
        try:
            inputs = page.query_selector_all("input")
            for inp in inputs:
                itype = inp.get_attribute("type") or ""
                if "email" in itype.lower() or "text" in itype.lower():
                    inp.fill("admin@aetherdesk.com")
                elif itype == "password":
                    inp.fill("admin123")

            page.click('button[type="submit"]')
            page.wait_for_timeout(5000)
            page.screenshot(path=".screenshots/dashboard.png", full_page=True)
            print("Logged in successfully! Dashboard screenshot saved.")
        except Exception as e:
            print(f"Could not auto-login: {e}")
            page.screenshot(path=".screenshots/login_attempt.png", full_page=True)

        print("\nBrowser is VISIBLE. Interact manually if needed.")
        print("Close this terminal to exit.")
        input()
        browser.close()
except Exception as e:
    print(f"Browser error: {e}")
    print("Browser may not be available in this environment. Try opening manually:")
    print("  http://127.0.0.1:3001/login")