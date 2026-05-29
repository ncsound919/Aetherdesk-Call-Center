"""Verify servers and open browser."""
import subprocess, time, httpx, os, sys

os.chdir(r"C:\Users\User\Desktop\aetherdesk_scaffold")
time.sleep(5)

# Check API
print("Checking API...")
api_ok = False
for i in range(5):
    try:
        r = httpx.get("http://127.0.0.1:8000/health", timeout=5)
        print(f"  API: {r.status_code} -> {r.json()['status']}")
        api_ok = True
        break
    except Exception as e:
        print(f"  API attempt {i+1}: {e}")
        time.sleep(2)

# Login
if api_ok:
    login = httpx.post("http://127.0.0.1:8000/auth/login", json={
        "email": "admin@aetherdesk.com", "password": "admin123"
    })
    print(f"  Login: {login.status_code}")
    if login.status_code == 200:
        token = login.json()["token"]
        h = {"Authorization": f"Bearer {token}"}

        t = httpx.post("http://127.0.0.1:8000/api/v1/tenants", json={
            "name": "Acme Corp", "email": "admin@acmecorp.com",
            "phone": "+15551234567", "gdpr_consent": True
        }, headers=h)
        print(f"  Tenant: {t.status_code}", end="")
        if t.status_code == 201:
            tid = t.json()["id"]
            print(f" ({tid[:8]})")

            a = httpx.post(f"http://127.0.0.1:8000/api/v1/tenants/{tid}/agents", json={
                "name": "Sarah Sales", "display_name": "Sarah Sales Agent",
                "agent_type": "ai", "skills": ["sales"]
            }, headers=h)
            print(f"  Agent: {a.status_code}", end="")
            if a.status_code == 201:
                d = a.json()
                print(f" ({d['name']}, SIP: {d.get('sip_extension')})")

                c = httpx.post("http://127.0.0.1:8000/api/v1/calls", json={
                    "caller_number": "+15559876543", "called_number": "+15551234567",
                    "call_direction": "inbound", "intent": "sales"
                }, headers=h)
                print(f"  Call: {c.status_code}", end="")
                if c.status_code == 201:
                    print(f" ({c.json()['id'][:8]})")
        else:
            print(f" - {t.text[:200]}")
else:
    print("  API not available")

# Check UI
print("Checking UI...")
ui_ok = False
for i in range(5):
    try:
        r = httpx.get("http://127.0.0.1:3001/", timeout=5)
        print(f"  UI: {r.status_code}")
        ui_ok = True
        break
    except Exception as e:
        print(f"  UI attempt {i+1}: {e}")
        time.sleep(2)

# Open Chrome
if ui_ok:
    print("\nOpening Chrome...")
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
        page.screenshot(path=".screenshots/login_page.png")
        print("Login page loaded - screenshot saved")

        # Fill form
        try:
            inputs = page.query_selector_all("input")
            for inp in inputs:
                itype = (inp.get_attribute("type") or "").lower()
                if itype in ("email", "text"):
                    inp.fill("admin@aetherdesk.com")
                elif itype == "password":
                    inp.fill("admin123")
            sbtn = page.query_selector('button[type="submit"]')
            if sbtn:
                with page.expect_navigation(wait_until="networkidle", timeout=15000):
                    sbtn.click()
                page.wait_for_timeout(3000)
                page.screenshot(path=".screenshots/dashboard.png")
                print("Logged in! Dashboard screenshot saved.")
        except Exception as e:
            print(f"Form interaction: {e}")

        print("\n=== AETHERDESK IS LIVE ===")
        print("  Chrome is VISIBLE - interact directly!")
        input("Press Enter to close browser and servers...")
        browser.close()