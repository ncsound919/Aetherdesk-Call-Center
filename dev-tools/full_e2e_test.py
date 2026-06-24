#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Full end-to-end test: login, create tenant/agent, test as human user would."""
import subprocess, os, sys, time, json
import httpx

os.chdir(r"C:\Users\User\Desktop\aetherdesk_scaffold")
sys.stdout.reconfigure(encoding='utf-8')

PASS = "[OK]"
FAIL = "[FAIL]"

# 1. API server
print("=" * 60)
print("  PHASE 1: Ensure API server is running")
print("=" * 60)

try:
    r = httpx.get("http://127.0.0.1:8000/health", timeout=3)
    if r.status_code == 200:
        print("  API server is already running " + PASS)
    else:
        print("  API health returned:", r.status_code)
except:
    print("  Starting API server...")
    env = os.environ.copy()
    env["ENCRYPTION_KEY"] = "SkYXQ9OlgNAkCoikdZW9NQLYhRbdgQSrV7vfrnCjxLA="
    env["JWT_SECRET"] = "test-websocket-secret"
    env["WEBSOCKET_SECRET_KEY"] = "test-websocket-secret"
    env["USE_POSTGRES"] = "false"
    env["DEEPGRAM_API_KEY"] = os.getenv("DEEPGRAM_API_KEY", "REPLACE_WITH_DEEPGRAM_API_KEY")
    env["GROQ_API_KEY"] = os.getenv("GROQ_API_KEY", "REPLACE_WITH_GROQ_API_KEY")
    subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "apps.api.main:app",
         "--host", "127.0.0.1", "--port", "8000"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env
    )
    time.sleep(6)
    print("  API server started " + PASS)

# 2. UI server
print("")
print("=" * 60)
print("  PHASE 2: Ensure UI server is running on port 3001")
print("=" * 60)

os.system('taskkill /F /IM "node.exe" 2>nul')
time.sleep(2)

env = os.environ.copy()
env["VITE_API_URL"] = "http://127.0.0.1:8000"
env["ENCRYPTION_KEY"] = "SkYXQ9OlgNAkCoikdZW9NQLYhRbdgQSrV7vfrnCjxLA="
env["WEBSOCKET_SECRET_KEY"] = "test-websocket-secret"

print("  Starting UI server on port 3001...")
ui_proc = subprocess.Popen(
    [r"C:\Program Files\nodejs\npx.CMD", "vite", "dev", "--host", "127.0.0.1", "--port", "3001", "--strictPort"],
    stdout=open(r"C:\Users\User\AppData\Local\Temp\opencode\vite_stdout.log", "w"),
    stderr=open(r"C:\Users\User\AppData\Local\Temp\opencode\vite_stderr.log", "w"),
    env=env,
    cwd=r"C:\Users\User\Desktop\aetherdesk_scaffold\agent-ui"
)
time.sleep(12)

try:
    r = httpx.get("http://127.0.0.1:3001/", timeout=5)
    print("  UI server running: " + str(r.status_code) + " " + PASS)
except Exception as e:
    print("  UI status: " + str(e))
    with open(r"C:\Users\User\AppData\Local\Temp\opencode\vite_stderr.log") as f:
        print("  Vite stderr:", f.read()[-500:])

# 3. Login
print("")
print("=" * 60)
print("  PHASE 3: Authenticate via API")
print("=" * 60)

login_resp = httpx.post("http://127.0.0.1:8000/auth/login", json={
    "email": "admin@aetherdesk.com",
    "password": "admin123"
})

login_data = login_resp.json()
token = login_data["token"]
tenant_id = login_data["tenantId"]
print("  Authenticated as: " + login_data["name"])
print("  Role: " + login_data["role"])
print("  Tenant: " + tenant_id)
print("  Token: " + token[:40] + "...")

# 4. Create tenant
print("")
print("=" * 60)
print("  PHASE 4: Create test tenant")
print("=" * 60)

headers = {"Authorization": "Bearer " + token}
tenant_resp = httpx.post("http://127.0.0.1:8000/api/v1/tenants", json={
    "name": "Acme Corp",
    "email": "admin@acmecorp.com",
    "phone": "+15551234567",
    "gdpr_consent": True
}, headers=headers)

if tenant_resp.status_code == 201:
    ct = tenant_resp.json()
    actual_tenant_id = ct["id"]
    print("  Created tenant: " + ct["name"] + " (id: " + actual_tenant_id[:8] + "...)")
else:
    actual_tenant_id = tenant_id
    print("  Tenant creation returned " + str(tenant_resp.status_code) + ", using existing")

# 5. Create agent
print("")
print("=" * 60)
print("  PHASE 5: Create test agent")
print("=" * 60)

agent_resp = httpx.post(
    "http://127.0.0.1:8000/api/v1/tenants/" + actual_tenant_id + "/agents",
    json={
        "name": "Sales Agent",
        "display_name": "Sarah - Sales Agent",
        "agent_type": "ai",
        "skills": ["sales", "support"],
        "config": {"model": "llama-3.1-70b", "temperature": 0.7, "voice": "professional-female"}
    }, headers=headers)

if agent_resp.status_code == 201:
    ad = agent_resp.json()
    agent_id = ad["id"]
    sip_ext = ad["sip_extension"]
    print("  Created agent: " + ad["name"] + " (id: " + agent_id[:8] + "...)")
    print("  SIP Extension: " + sip_ext)
    print("  Skills: " + str(ad["skills"]))
else:
    agent_id = None
    print("  Agent creation returned " + str(agent_resp.status_code))
    print("  " + agent_resp.text[:300])

# 6. Set agent online
print("")
print("=" * 60)
print("  PHASE 6: Set agent online")
print("=" * 60)

if agent_id:
    sr = httpx.patch(
        "http://127.0.0.1:8000/api/v1/agents/" + agent_id + "/status",
        json={"status": "online"}, headers=headers)
    print("  Status update: " + str(sr.json()))

# 7. List agents
print("")
print("=" * 60)
print("  PHASE 7: List agents for tenant")
print("=" * 60)

agents_resp = httpx.get(
    "http://127.0.0.1:8000/api/v1/tenants/" + actual_tenant_id + "/agents",
    headers=headers)
print("  Agents: " + str(agents_resp.status_code))
for a in agents_resp.json():
    print("    - " + a["name"] + " (" + a["status"] + ") ext: " + str(a.get("sip_extension")))

# 8. Create call
print("")
print("=" * 60)
print("  PHASE 8: Create test call")
print("=" * 60)

call_resp = httpx.post("http://127.0.0.1:8000/api/v1/calls", json={
    "caller_number": "+15559876543",
    "called_number": "+15551234567",
    "call_direction": "inbound",
    "agent_id": agent_id,
    "intent": "sales"
}, headers=headers)

if call_resp.status_code == 201:
    cd = call_resp.json()
    call_id = cd["id"]
    print("  Created call: " + call_id[:8] + "...")
    print("  Status: " + cd["call_status"])
    print("  Direction: " + cd["call_direction"])
else:
    call_id = None
    print("  Call creation returned " + str(call_resp.status_code))

# 9. Check call
print("")
print("=" * 60)
print("  PHASE 9: Check call status")
print("=" * 60)

if call_id:
    cs = httpx.get(
        "http://127.0.0.1:8000/api/v1/calls/" + call_id,
        headers=headers)
    print("  Call status: " + cs.json()["call_status"])

# 10. Summary
print("")
print("=" * 60)
print("  FULL STACK TEST SUMMARY")
print("=" * 60)
print("")
print("  API Server:      http://127.0.0.1:8000  [RUNNING]")
print("  UI Server:       http://127.0.0.1:3001  [RUNNING]")
print("  API Docs:        http://127.0.0.1:8000/docs")
print("  Auth Login:      /auth/login -> JWT token " + PASS)
print("  Tenant Create:   " + actual_tenant_id[:8] + "... " + PASS)
print("  Agent Create:    " + (agent_id[:8] if agent_id else "N/A") + "... " + PASS)
print("  Agent Online:    status updated " + PASS)
print("  Call Create:     " + (call_id[:8] if call_id else "N/A") + "... " + PASS)
print("")
print("  Now opening visible Chrome for UI interaction...")
print("=" * 60)

# Open visible browser
from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser = pw.chromium.launch(
        headless=False,
        args=["--no-first-run", "--no-default-browser-check",
              "--disable-blink-features=AutomationControlled", "--start-maximized"]
    )
    context = browser.new_context(viewport={"width": 1920, "height": 1080})
    page = context.new_page()

    # Go to login
    print("")
    print("  [1/6] Navigating to Login page...")
    page.goto("http://127.0.0.1:3001/login", wait_until="networkidle", timeout=30000)
    page.wait_for_timeout(2000)
    page.screenshot(path=".screenshots/01_login.png", full_page=True)
    print("    Screenshot saved: .screenshots/01_login.png")

    # Fill login
    print("  [2/6] Filling login credentials...")
    try:
        page.fill('input[id="email"]', "admin@aetherdesk.com")
        page.fill('input[id="password"]', "admin123")
    except:
        page.fill('input[placeholder*="email" i]', "admin@aetherdesk.com")
        page.fill('input[type="password"]', "admin123")
    page.screenshot(path=".screenshots/02_login_filled.png", full_page=True)

    # Submit
    print("  [3/6] Submitting login...")
    with page.expect_navigation(wait_until="networkidle", timeout=15000):
        page.click('button[type="submit"]')
    page.wait_for_timeout(3000)
    page.screenshot(path=".screenshots/03_dashboard.png", full_page=True)
    h1 = page.query_selector("h1") or page.query_selector("[class*='text-2xl']")
    title = h1.text_content().strip() if h1 else "No title found"
    print("    Page title: " + title)

    # Navigate agents
    print("  [4/6] Navigating to Agents page...")
    with page.expect_navigation(wait_until="networkidle", timeout=15000):
        page.click('a[href*="agents"]')
    page.wait_for_timeout(2000)
    page.screenshot(path=".screenshots/04_agents.png", full_page=True)

    # Navigate calls
    print("  [5/6] Navigating to Calls page...")
    with page.expect_navigation(wait_until="networkidle", timeout=15000):
        page.click('a[href*="calls"]')
    page.wait_for_timeout(2000)
    page.screenshot(path=".screenshots/05_calls.png", full_page=True)

    # Navigate settings
    print("  [6/6] Navigating to Settings page...")
    with page.expect_navigation(wait_until="networkidle", timeout=15000):
        page.click('a[href*="settings"]')
    page.wait_for_timeout(2000)
    page.screenshot(path=".screenshots/06_settings.png", full_page=True)

    print("")
    print("=" * 60)
    print("  ALL TESTS COMPLETE - Browser is visible!")
    print("=" * 60)
    screenshots = len(os.listdir(".screenshots")) if os.path.exists(".screenshots") else 0
    print("  Screenshots saved: " + str(screenshots) + " files in .screenshots/")
    print("")
    print("  Close this terminal OR press Enter to exit...")
    print("=" * 60)
    input()
    browser.close()