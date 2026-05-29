"""
Start completely detached server processes and test.
Uses DETACHED_PROCESS flag so servers survive parent exit.
"""
import os, sys, time, subprocess, httpx, ctypes

os.chdir(r"C:\Users\User\Desktop\aetherdesk_scaffold")

# Clean DB
try: os.remove("aetherdesk.db")
except: pass

# Environment
env = os.environ.copy()
for k, v in {
    "ENCRYPTION_KEY": "REDACTED_ENCRYPTION_KEY_PLEASE_ROTATE=",
    "JWT_SECRET": "test-websocket-secret",
    "WEBSOCKET_SECRET_KEY": "test-websocket-secret",
    "USE_POSTGRES": "false",
    "DEEPGRAM_API_KEY": os.getenv("DEEPGRAM_API_KEY", "REPLACE_WITH_DEEPGRAM_API_KEY"),
    "GROQ_API_KEY": os.getenv("GROQ_API_KEY", "REPLACE_WITH_GROQ_API_KEY"),
    "VITE_API_URL": "http://127.0.0.1:8000",
}.items(): env[k] = v

print("=" * 60)
print("  AetherDesk Call Center - Starting")
print("=" * 60)

# Create detached API server using CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS
DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200

print("\n[1/3] Starting API server (port 8000)...")
api_proc = subprocess.Popen(
    [sys.executable, "-u", "-c", """
import os, sys
os.environ["ENCRYPTION_KEY"] = "REDACTED_ENCRYPTION_KEY_PLEASE_ROTATE="
os.environ["JWT_SECRET"] = "test-websocket-secret"
os.environ["WEBSOCKET_SECRET_KEY"] = "test-websocket-secret"
os.environ["USE_POSTGRES"] = "false"
os.environ["DEEPGRAM_API_KEY"] = os.getenv("DEEPGRAM_API_KEY", "REPLACE_WITH_DEEPGRAM_API_KEY")
os.environ["GROQ_API_KEY"] = os.getenv("GROQ_API_KEY", "REPLACE_WITH_GROQ_API_KEY")
import uvicorn
uvicorn.run("apps.api.main:app", host="127.0.0.1", port=8000, log_level="info")
"""],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    cwd=r"C:\Users\User\Desktop\aetherdesk_scaffold",
    env=env,
    creationflags=CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS
)
print(f"  API PID: {api_proc.pid}")

print("\n[2/3] Starting UI server (port 3001)...")
npx = r"C:\Program Files\nodejs\npx.CMD"
ui_proc = subprocess.Popen(
    [npx, "vite", "dev", "--host", "127.0.0.1", "--port", "3001", "--strictPort"],
    cwd=r"C:\Users\User\Desktop\aetherdesk_scaffold\agent-ui",
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    env=env,
    creationflags=CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS
)
print(f"  UI PID: {ui_proc.pid}")

# Wait and test
print("\n[3/3] Waiting for servers...")
api_ok = False
ui_ok = False

for i in range(40):
    # API
    if not api_ok:
        try:
            r = httpx.get("http://127.0.0.1:8000/health", timeout=2)
            if r.status_code == 200:
                api_ok = True
                print(f"  API ready at {i*0.5}s: {r.json()['status']}")
        except: pass

    # UI
    if not ui_ok:
        try:
            r = httpx.get("http://127.0.0.1:3001/", timeout=2)
            if r.status_code == 200:
                ui_ok = True
                print(f"  UI ready at {i*0.5}s: status={r.status_code}")
        except: pass

    if api_ok and ui_ok:
        break
    sys.stdout.write(f"\r  {i*0.5:.0f}s...")
    sys.stdout.flush()
    time.sleep(0.5)

# API tests
print("\n\n--- API Tests ---")
token = None
if api_ok:
    login = httpx.post("http://127.0.0.1:8000/auth/login", json={
        "email": "admin@aetherdesk.com", "password": "admin123"
    })
    print(f"  Login: {login.status_code}", end="")
    if login.status_code == 200:
        token = login.json()["token"]
        print(f" OK (token: {token[:30]}...)")
    else:
        print(f" FAIL")

h = {"Authorization": f"Bearer {token}"} if token else {}
tid = "TENANT-001"

if token:
    t = httpx.post("http://127.0.0.1:8000/api/v1/tenants", json={
        "name": "Acme Corp", "email": "admin@acmecorp.com",
        "phone": "+15551234567", "gdpr_consent": True
    }, headers=h)
    print(f"  Tenant: {t.status_code}", end="")
    if t.status_code == 201:
        tid = t.json()["id"]
        print(f" OK ({tid[:8]})")
    elif t.status_code == 409:
        print(f" exists")
    else:
        print(f" FAIL: {t.text[:100]}")

    a = httpx.post(f"http://127.0.0.1:8000/api/v1/tenants/{tid}/agents", json={
        "name": "Sarah Sales", "display_name": "Sarah Sales Agent",
        "agent_type": "ai", "skills": ["sales"]
    }, headers=h)
    print(f"  Agent: {a.status_code}", end="")
    if a.status_code == 201:
        d = a.json()
        print(f" OK (SIP: {d.get('sip_extension')})")
    elif a.status_code == 409:
        print(f" exists")
    else:
        print(f" FAIL: {a.text[:100]}")

    c = httpx.post("http://127.0.0.1:8000/api/v1/calls", json={
        "caller_number": "+15559876543", "called_number": "+15551234567",
        "call_direction": "inbound", "intent": "sales"
    }, headers=h)
    print(f"  Call: {c.status_code}", end="")
    if c.status_code == 201:
        print(f" OK ({c.json()['id'][:8]})")
    else:
        print(f" FAIL: {c.text[:100]}")

print(f"\n{'='*60}")
print(f"  API: http://127.0.0.1:8000 [{'UP' if api_ok else 'DOWN'}]")
print(f"  UI:  http://127.0.0.1:3001 [{'UP' if ui_ok else 'DOWN'}]")
print(f"  Docs: http://127.0.0.1:8000/docs")
print(f"  Login: admin@aetherdesk.com / admin123")
print(f"{'='*60}")

# Open browser
if ui_ok:
    print("\nOpening Chrome...")
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            browser = pw.chromium.launch(
                headless=False,
                args=["--no-first-run", "--no-default-browser-check",
                      "--disable-blink-features=AutomationControlled", "--start-maximized"]
            )
            page = browser.new_page(viewport={"width": 1920, "height": 1080})
            page.goto("http://127.0.0.1:3001/login", wait_until="networkidle", timeout=30000)
            page.wait_for_timeout(2000)
            os.makedirs(".screenshots", exist_ok=True)

            for inp in page.query_selector_all("input"):
                itype = (inp.get_attribute("type") or "").lower()
                ph = (inp.get_attribute("placeholder") or "").lower()
                if itype == "email" or "email" in ph: inp.fill("admin@aetherdesk.com")
                elif itype == "password" or "password" in ph: inp.fill("admin123")

            for btn in page.query_selector_all("button"):
                t = (btn.text_content() or "").strip().lower()
                bt = btn.get_attribute("type") or ""
                if "sign" in t or "login" in t or bt == "submit":
                    with page.expect_navigation(wait_until="networkidle", timeout=15000):
                        btn.click()
                    break
            page.wait_for_timeout(3000)
            page.screenshot(path=".screenshots/dashboard.png")
            h1 = page.query_selector("h1")
            title = h1.text_content().strip() if h1 else "Unknown"
            print(f"Logged in! Title: '{title}'")
            print("Browser VISIBLE - interact manually!")
            print("Press Enter to exit...")
            input()
            browser.close()
    except Exception as e:
        print(f"Browser: {e}")

print("Done!")