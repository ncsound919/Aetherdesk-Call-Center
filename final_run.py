import subprocess, os, sys, time, httpx

os.chdir(r"C:\Users\User\Desktop\aetherdesk_scaffold")

# Run the batch launcher
print("Launching AetherDesk via batch file...")
proc = subprocess.Popen(
    ['cmd', '/c', 'C:\\Users\\User\\Desktop\\aetherdesk_scaffold\\launch.bat'],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
)

# Wait for servers
print("Waiting 18s for servers to start...")
time.sleep(18)

# Check
print("\nChecking services...")
try:
    r = httpx.get("http://127.0.0.1:8000/health", timeout=5)
    print(f"  API: {r.status_code} -> {r.json()['status']}")
except Exception as e:
    print(f"  API: {e}")

try:
    r = httpx.get("http://127.0.0.1:3001/", timeout=5)
    print(f"  UI:  {r.status_code}")
except Exception as e:
    print(f"  UI:  {e}")

# Login
login = httpx.post("http://127.0.0.1:8000/auth/login", json={
    "email": "admin@aetherdesk.com", "password": "admin123"
})
print(f"  Login: {login.status_code}")
if login.status_code == 200:
    token = login.json()["token"]
    h = {"Authorization": f"Bearer {token}"}

    # Tenant
    t = httpx.post("http://127.0.0.1:8000/api/v1/tenants", json={
        "name": "Acme Corp", "email": "admin@acmecorp.com",
        "phone": "+15551234567", "gdpr_consent": True
    }, headers=h)
    print(f"  Tenant: {t.status_code}")
    tid = t.json()["id"] if t.status_code == 201 else "TENANT-001"

    # Agent
    a = httpx.post(f"http://127.0.0.1:8000/api/v1/tenants/{tid}/agents", json={
        "name": "Sarah Sales", "display_name": "Sarah Sales Agent",
        "agent_type": "ai", "skills": ["sales"]
    }, headers=h)
    print(f"  Agent: {a.status_code}")
    if a.status_code == 201:
        print(f"    SIP: {a.json().get('sip_extension')}")

    # Call
    c = httpx.post("http://127.0.0.1:8000/api/v1/calls", json={
        "caller_number": "+15559876543", "called_number": "+15551234567",
        "call_direction": "inbound", "intent": "sales"
    }, headers=h)
    print(f"  Call: {c.status_code}")

    # List agents
    la = httpx.get(f"http://127.0.0.1:8000/api/v1/tenants/{tid}/agents", headers=h)
    if la.status_code == 200:
        print(f"  Listed {len(la.json())} agent(s)")

print(f"\n{'='*50}")
print("  API: http://127.0.0.1:8000")
print("  UI:  http://127.0.0.1:3001")
print("  Docs: http://127.0.0.1:8000/docs")
print(f"{'='*50}")

# Open browser
print("\nOpening Chrome for interaction...")
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

        # Fill login
        for inp in page.query_selector_all("input"):
            itype = (inp.get_attribute("type") or "").lower()
            ph = (inp.get_attribute("placeholder") or "").lower()
            if itype == "email" or "email" in ph:
                inp.fill("admin@aetherdesk.com")
            elif itype == "password" or "password" in ph:
                inp.fill("admin123")

        # Submit
        for btn in page.query_selector_all("button"):
            text = (btn.text_content() or "").strip().lower()
            btype = btn.get_attribute("type") or ""
            if ("sign" in text or "login" in text or btype == "submit"):
                with page.expect_navigation(wait_until="networkidle", timeout=15000):
                    btn.click()
                break
        page.wait_for_timeout(3000)
        page.screenshot(path=".screenshots/login_result.png")
        h1 = page.query_selector("h1")
        title = h1.text_content().strip() if h1 else "Unknown"
        print(f"Logged in! Title: '{title}'")
        print("Browser VISIBLE - interact directly!")
        input("\nPress Enter to exit...")
        browser.close()
except Exception as e:
    print(f"Browser: {e}")
    import traceback
    traceback.print_exc()

print("Done!")