"""
Start both AetherDesk servers (API + UI) as detached processes,
then open a visible Chrome browser for human interaction.
"""
import subprocess, os, sys, time, httpx, json

os.chdir(r"C:\Users\User\Desktop\aetherdesk_scaffold")

# Environment for both servers
env = os.environ.copy()
env["ENCRYPTION_KEY"] = "rqSRQd2JssHG3nhORTRC3CBaeUjqOqZ3D2BH2FX0l0k="
env["JWT_SECRET"] = "test-websocket-secret"
env["WEBSOCKET_SECRET_KEY"] = "test-websocket-secret"
env["USE_POSTGRES"] = "false"
env["DEEPGRAM_API_KEY"] = os.getenv("DEEPGRAM_API_KEY", "REPLACE_WITH_DEEPGRAM_API_KEY")
env["GROQ_API_KEY"] = os.getenv("GROQ_API_KEY", "REPLACE_WITH_GROQ_API_KEY")
env["VITE_API_URL"] = "http://127.0.0.1:8000"

# Use start /B to create detached console processes
print("=" * 60)
print("  Starting AetherDesk Servers")
print("=" * 60)

# Start API server as detached process
api_cmd = 'cmd /c "title API Server & color 0C & python -m uvicorn apps.api.main:app --host 127.0.0.1 --port 8000 --log-level info"'
subprocess.Popen(api_cmd, shell=True, creationflags=0x08000000)  # CREATE_NO_WINDOW won't work, use /B
print("[1/4] API server starting...")

time.sleep(10)

# Check API is up
try:
    r = httpx.get("http://127.0.0.1:8000/health", timeout=5)
    print("  API is UP! Status:", r.json()["status"])
except:
    print("  API failed to start")

# Start UI server
ui_cmd = 'cmd /c "title UI Server & color 0B & cd /d C:\\Users\\User\\Desktop\\aetherdesk_scaffold\\agent-ui & npx vite dev --host 127.0.0.1 --port 3001 --strictPort"'
subprocess.Popen(ui_cmd, shell=True, creationflags=0x08000000)
print("[2/4] UI server starting...")

time.sleep(12)

# Check UI is up
try:
    r = httpx.get("http://127.0.0.1:3001/", timeout=5)
    print("  UI is UP! Status:", r.status_code)
except:
    print("  UI failed to start")

# Login and set up data
print("[3/4] Setting up test data...")
login = httpx.post("http://127.0.0.1:8000/auth/login", json={
    "email": "admin@aetherdesk.com", "password": "admin123"
})
if login.status_code == 200:
    token = login.json()["token"]
    h = {"Authorization": "Bearer " + token}

    # Create tenant
    t = httpx.post("http://127.0.0.1:8000/api/v1/tenants", json={
        "name": "Acme Corp", "email": "admin@acmecorp.com",
        "phone": "+15551234567", "gdpr_consent": True
    }, headers=h)
    tid = t.json()["id"] if t.status_code == 201 else "TENANT-001"

    # Create agent
    a = httpx.post(f"http://127.0.0.1:8000/api/v1/tenants/{tid}/agents", json={
        "name": "Sarah Sales", "agent_type": "ai", "skills": ["sales"]
    }, headers=h)

    print("  Login: OK")
    print("  Tenant:", t.status_code)
    print("  Agent:", a.status_code, a.json().get("sip_extension", "") if a.status_code == 201 else "")
else:
    print("  Login failed:", login.text[:200])

# Open browser
print("[4/4] Opening Chrome browser (VISIBLE)...")
from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser = pw.chromium.launch(
        headless=False,
        args=["--no-first-run", "--no-default-browser-check",
              "--disable-blink-features=AutomationControlled", "--start-maximized"]
    )
    page = browser.new_page(viewport={"width": 1920, "height": 1080})

    # Go to login page
    print("  Navigating to login page...")
    page.goto("http://127.0.0.1:3001/login", wait_until="networkidle", timeout=30000)
    page.wait_for_timeout(2000)

    # Fill credentials
    print("  Filling login form...")
    try:
        page.fill('input[id="email"]', "admin@aetherdesk.com")
        page.fill('input[type="password"]', "admin123")
    except:
        page.fill('input[placeholder*="email" i]', "admin@aetherdesk.com")
        page.fill('input[placeholder*="password" i]', "admin123")

    # Submit
    print("  Submitting...")
    with page.expect_navigation(wait_until="networkidle", timeout=15000):
        page.click('button[type="submit"]')
    page.wait_for_timeout(3000)

    # Take screenshot
    os.makedirs(".screenshots", exist_ok=True)
    page.screenshot(path=".screenshots/dashboard.png", full_page=True)

    h1 = page.query_selector("h1,[class*='text-2xl']")
    title = h1.text_content().strip() if h1 else "Unknown"
    print(f"  Logged in! Page title: {title}")

    print("\n" + "=" * 60)
    print("  SUCCESS! AetherDesk is running:")
    print("  API: http://127.0.0.1:8000")
    print("  UI:  http://127.0.0.1:3001")
    print("  Chrome is VISIBLE - interact with the UI directly!")
    print("=" * 60)
    print("\n  Press Enter in this console to close browser...")

    input()
    browser.close()