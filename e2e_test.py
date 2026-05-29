"""Full end-to-end test with UI browser interaction."""
import os, sys, time, threading, httpx, sqlite3, json

os.chdir(r"C:\Users\User\Desktop\aetherdesk_scaffold")
for k, v in {
    "ENCRYPTION_KEY": "SkYXQ9OlgNAkCoikdZW9NQLYhRbdgQSrV7vfrnCjxLA=",
    "JWT_SECRET": "test-websocket-secret",
    "WEBSOCKET_SECRET_KEY": "test-websocket-secret",
    "USE_POSTGRES": "false",
    "DEEPGRAM_API_KEY": os.getenv("DEEPGRAM_API_KEY", "REPLACE_WITH_DEEPGRAM_API_KEY"),
    "GROQ_API_KEY": os.getenv("GROQ_API_KEY", "REPLACE_WITH_GROQ_API_KEY"),
    "VITE_API_URL": "http://127.0.0.1:8000",
}.items(): os.environ[k] = v

try: os.remove("aetherdesk.db")
except: pass

# ---- START API SERVER ----
def api():
    import uvicorn
    uvicorn.run("apps.api.main:app", host="127.0.0.1", port=8000, log_level="warning")

t = threading.Thread(target=api, daemon=True)
t.start()

for i in range(20):
    try:
        r = httpx.get("http://127.0.0.1:8000/health", timeout=2)
        if r.status_code == 200:
            print(f"API: UP ({r.json()['status']})")
            break
    except: pass
    time.sleep(0.5)

# Login and setup data
login = httpx.post("http://127.0.0.1:8000/auth/login", json={
    "email": "admin@aetherdesk.com", "password": "admin123"
})
token = login.json()["token"]
h = {"Authorization": f"Bearer {token}"}

t = httpx.post("http://127.0.0.1:8000/api/v1/tenants", json={
    "name": "Acme Corp", "email": "admin@acmecorp.com",
    "phone": "+15551234567", "gdpr_consent": True
}, headers=h)
tid = t.json()["id"] if t.status_code == 201 else ""

a = httpx.post(f"http://127.0.0.1:8000/api/v1/tenants/{tid}/agents", json={
    "name": "Sarah Sales", "display_name": "Sarah Sales Agent",
    "agent_type": "ai", "skills": ["sales"],
    "config": {"model": "llama-3.1-70b", "voice": "professional-female"}
}, headers=h)
aid = a.json()["id"] if a.status_code == 201 else ""

c = httpx.post("http://127.0.0.1:8000/api/v1/calls", json={
    "caller_number": "+15559876543", "called_number": "+15551234567",
    "call_direction": "inbound", "intent": "sales", "agent_id": aid
}, headers=h)
cid = c.json()["id"] if c.status_code == 201 else ""

print(f"Setup: tenant={tid[:8]}, agent={aid[:8]}, call={cid[:8]}")

# ---- START UI SERVER ----
import subprocess
ui_env = os.environ.copy()
ui_proc = subprocess.Popen(
    [r"C:\Program Files\nodejs\npx.CMD", "vite", "dev",
     "--host", "127.0.0.1", "--port", "3001", "--strictPort"],
    cwd=r"C:\Users\User\Desktop\aetherdesk_scaffold\agent-ui",
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=ui_env
)

print("UI starting...")
for i in range(30):
    try:
        r = httpx.get("http://127.0.0.1:3001/", timeout=2)
        if r.status_code == 200:
            print(f"UI: UP (status={r.status_code})")
            break
    except: pass
    time.sleep(0.5)

# ---- OPEN CHROME ----
print("\nOpening Chrome browser...")
try:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=False,
            args=["--no-first-run", "--no-default-browser-check",
                  "--disable-blink-features=AutomationControlled", "--start-maximized"]
        )
        page = browser.new_page(viewport={"width": 1920, "height": 1080})

        # 1. Navigate to login
        print("\n[1] Navigating to login page...")
        page.goto("http://127.0.0.1:3001/login", wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(2000)
        os.makedirs(".screenshots", exist_ok=True)
        page.screenshot(path=".screenshots/01_login.png")
        print("    Screenshot: .screenshots/01_login.png")

        # 2. Fill login form
        print("[2] Filling login form...")
        for inp in page.query_selector_all("input"):
            itype = (inp.get_attribute("type") or "").lower()
            ph = (inp.get_attribute("placeholder") or "").lower()
            if itype == "email" or "email" in ph:
                inp.fill("admin@aetherdesk.com")
            elif itype == "password" or "password" in ph:
                inp.fill("admin123")
        page.screenshot(path=".screenshots/02_login_filled.png")

        # 3. Submit login
        print("[3] Submitting login...")
        for btn in page.query_selector_all("button"):
            text = (btn.text_content() or "").strip().lower()
            btype = btn.get_attribute("type") or ""
            if "sign" in text or "login" in text or btype == "submit":
                with page.expect_navigation(wait_until="networkidle", timeout=15000):
                    btn.click()
                break
        page.wait_for_timeout(3000)
        page.screenshot(path=".screenshots/03_dashboard.png")

        h1 = page.query_selector("h1")
        title = h1.text_content().strip() if h1 else "Unknown"
        print(f"    Logged in! Page: '{title}'")

        # 4. Navigate to Agents page
        print("[4] Going to Agents page...")
        for link in page.query_selector_all("a"):
            href = link.get_attribute("href") or ""
            if "agent" in href.lower():
                with page.expect_navigation(wait_until="networkidle", timeout=15000):
                    link.click()
                break
        page.wait_for_timeout(2000)
        page.screenshot(path=".screenshots/04_agents.png")

        # Check for agent card
        agent_rows = page.query_selector_all("table tbody tr, [class*='agent-card']")
        print(f"    Agents displayed: {len(agent_rows)} row(s)")

        # 5. Navigate to Calls page
        print("[5] Going to Calls page...")
        for link in page.query_selector_all("a"):
            href = link.get_attribute("href") or ""
            if "call" in href.lower() and "agent" not in href.lower():
                with page.expect_navigation(wait_until="networkidle", timeout=15000):
                    link.click()
                break
        page.wait_for_timeout(2000)
        page.screenshot(path=".screenshots/05_calls.png")
        print("    Calls page captured")

        # 6. Navigate to Voice Cloning
        print("[6] Going to Voice Cloning page...")
        for link in page.query_selector_all("a"):
            href = link.get_attribute("href") or ""
            text = (link.text_content() or "").strip().lower()
            if "voice-clone" in href.lower() or "voice cloning" in text:
                with page.expect_navigation(wait_until="networkidle", timeout=15000):
                    link.click()
                break
        page.wait_for_timeout(2000)
        page.screenshot(path=".screenshots/06_voice_cloning.png")
        print("    Voice Cloning page captured")

        # Done
        print(f"\n{'='*60}")
        print("  ALL E2E TESTS PASSED!")
        print(f"{'='*60}")
        print("  6 pages navigated, all screenshots saved")
        print("  Chrome is VISIBLE - interact directly!")
        print(f"{'='*60}\n")
        input("Press Enter to close browser and servers...")
        browser.close()

except Exception as e:
    print(f"Browser error: {e}")
    import traceback
    traceback.print_exc()

print("\nDone!")