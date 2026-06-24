"""
Simplest possible AetherDesk launcher.
Starts API in thread (no subprocess issues), UI via subprocess, then opens Chrome.
"""
import os, sys, time, threading, subprocess, httpx

os.chdir(r"C:\Users\User\Desktop\aetherdesk_scaffold")
for k, v in {
    "ENCRYPTION_KEY": "SkYXQ9OlgNAkCoikdZW9NQLYhRbdgQSrV7vfrnCjxLA=",
    "JWT_SECRET": "test-websocket-secret",
    "WEBSOCKET_SECRET_KEY": "test-websocket-secret",
    "USE_POSTGRES": "false",
    "DEEPGRAM_API_KEY": os.getenv("DEEPGRAM_API_KEY", "REPLACE_WITH_DEEPGRAM_API_KEY"),
    "GROQ_API_KEY": os.getenv("GROQ_API_KEY", "REPLACE_WITH_GROQ_API_KEY"),
}.items(): os.environ[k] = v

try: os.remove("aetherdesk.db")
except: pass

print("=" * 60)
print("  AetherDesk Call Center - Starting")
print("=" * 60)

# ---- API Server in thread ----
def api_server():
    import uvicorn
    uvicorn.run("apps.api.main:app", host="127.0.0.1", port=8000, log_level="info")

t = threading.Thread(target=api_server, daemon=True)
t.start()
time.sleep(10)

import httpx
try:
    r = httpx.get("http://127.0.0.1:8000/health", timeout=3)
    print(f"API: {r.status_code} -> {r.json()['status']}")
except:
    print("API not ready, waiting more...")
    time.sleep(5)
    r = httpx.get("http://127.0.0.1:8000/health", timeout=3)
    print(f"API: {r.status_code} -> {r.json()['status']}")

# Login
login = httpx.post("http://127.0.0.1:8000/auth/login", json={
    "email": "admin@aetherdesk.com", "password": "admin123"
})
print(f"Login: {login.status_code}")
token = login.json()["token"] if login.status_code == 200 else ""
h = {"Authorization": f"Bearer {token}"} if token else {}
tid = "TENANT-001"

if token:
    t = httpx.post("http://127.0.0.1:8000/api/v1/tenants", json={
        "name": "Acme Corp", "email": "admin@acmecorp.com",
        "phone": "+15551234567", "gdpr_consent": True
    }, headers=h)
    tid = t.json()["id"] if t.status_code == 201 else tid
    print(f"Tenant: {t.status_code}")

    a = httpx.post(f"http://127.0.0.1:8000/api/v1/tenants/{tid}/agents", json={
        "name": "Sarah Sales", "display_name": "Sarah Sales",
        "agent_type": "ai", "skills": ["sales"]
    }, headers=h)
    print(f"Agent: {a.status_code}", end="")
    if a.status_code == 201:
        print(f" SIP: {a.json().get('sip_extension')}")
    else:
        print(f" ({a.text[:100]})")

    c = httpx.post("http://127.0.0.1:8000/api/v1/calls", json={
        "caller_number": "+15559876543", "called_number": "+15551234567",
        "call_direction": "inbound", "intent": "sales"
    }, headers=h)
    print(f"Call: {c.status_code}")

# ---- UI ----
print("\nStarting UI server...")
my_env = os.environ.copy()
my_env["VITE_API_URL"] = "http://127.0.0.1:8000"
ui = subprocess.Popen(
    [r"C:\Program Files\nodejs\npx.CMD", "vite", "dev",
     "--host", "127.0.0.1", "--port", "3001", "--strictPort"],
    cwd=r"C:\Users\User\Desktop\aetherdesk_scaffold\agent-ui",
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=my_env
)
time.sleep(12)

try:
    r = httpx.get("http://127.0.0.1:3001/", timeout=3)
    print(f"UI: {r.status_code}")
except Exception as e:
    print(f"UI: {e}")
    try:
        r = httpx.get("http://127.0.0.1:3002/", timeout=3)
        print(f"UI (alt port): {r.status_code}")
    except:
        print("UI not available")

print(f"\n{'='*60}")
print("  Browsing to UI now...")
print(f"{'='*60}")

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
        page.screenshot(path=".screenshots/login.png")
        for inp in page.query_selector_all("input"):
            it = (inp.get_attribute("type") or "").lower()
            ph = (inp.get_attribute("placeholder") or "").lower()
            if it in ("email", "text") or "email" in ph: inp.fill("admin@aetherdesk.com")
            elif it == "password" or "password" in ph: inp.fill("admin123")
        for btn in page.query_selector_all("button"):
            tx = (btn.text_content() or "").strip().lower()
            bt = btn.get_attribute("type") or ""
            if "sign" in tx or "login" in tx or bt == "submit":
                with page.expect_navigation(wait_until="networkidle", timeout=15000):
                    btn.click()
                break
        page.wait_for_timeout(3000)
        page.screenshot(path=".screenshots/dashboard.png")
        h1 = page.query_selector("h1")
        title = h1.text_content().strip() if h1 else "Unknown"
        print(f"Page title: {title}")
        print("Browser VISIBLE! Interact directly.")
        print("Press Enter to close...")
        input()
        browser.close()
except Exception as e:
    print(f"Browser error: {e}")

print("Done!")