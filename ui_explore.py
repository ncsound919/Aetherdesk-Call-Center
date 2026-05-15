#!/usr/bin/env python
"""Interact with the AetherDesk UI - navigate pages, click buttons, test features."""
import os
import sys
import time
import json

os.chdir(r"C:\Users\User\Desktop\aetherdesk_scaffold")

from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(
        headless=False,
        args=["--no-first-run", "--no-default-browser-check",
              "--disable-blink-features=AutomationControlled", "--start-maximized"]
    )
    context = browser.new_context(viewport={"width": 1920, "height": 1080})
    page = context.new_page()

    # ── 1. Navigate to UI ──────────────────────────────────────────────
    print("[1] Navigating to AetherDesk UI...")
    page.goto("http://127.0.0.1:3001/", wait_until="networkidle", timeout=30000)
    print(f"    Title: {page.title()}")
    os.makedirs(".screenshots", exist_ok=True)
    page.screenshot(path=".screenshots/01_dashboard.png", full_page=True)
    print("    Screenshot: .screenshots/01_dashboard.png")
    time.sleep(1)

    # ── 2. Check what's on the page ────────────────────────────────────
    print("\n[2] Page structure:")
    headings = page.query_selector_all("h1, h2, h3")
    for h in headings[:10]:
        print(f"    {h.tag_name}: {h.text_content().strip()[:80]}")

    buttons = page.query_selector_all("button")
    print(f"\n    Found {len(buttons)} buttons")
    for btn in buttons[:15]:
        text = btn.text_content().strip()
        if text:
            print(f"    Button: {text[:60]}")

    links = page.query_selector_all("a")
    print(f"    Found {len(links)} links (nav items)")
    for link in links[:15]:
        text = link.text_content().strip()
        if text and len(text) > 2:
            print(f"    Nav: {text[:60]}")

    time.sleep(1)

    # ── 3. Try to navigate to Login page if available ──────────────────
    print("\n[3] Looking for Login/Sign In...")
    login_btn = page.query_selector("text='Login'") or page.query_selector("text='Sign In'") or page.query_selector("text='login'")
    if login_btn:
        print("    Found login button, clicking...")
        login_btn.click()
        time.sleep(2)
        page.screenshot(path=".screenshots/02_login.png", full_page=True)
        print("    Screenshot: .screenshots/02_login.png")

        # Check for form fields
        inputs = page.query_selector_all("input")
        print(f"    Found {len(inputs)} input fields on login page")
        for inp in inputs:
            placeholder = inp.get_attribute("placeholder") or ""
            itype = inp.get_attribute("type") or "text"
            print(f"      Input [{itype}]: placeholder='{placeholder}'")

        # Try filling in login form if it exists
        email_input = page.query_selector("input[type='email'], input[name='email'], input[placeholder*='email' i]")
        password_input = page.query_selector("input[type='password'], input[name='password']")

        if email_input and password_input:
            print("    Filling in test credentials...")
            email_input.fill("admin@aetherdesk.com")
            password_input.fill("Test123!")
            page.screenshot(path=".screenshots/03_login_filled.png", full_page=True)
            print("    Screenshot: .screenshots/03_login_filled.png")

            submit_btn = page.query_selector("button[type='submit']") or page.query_selector("text='Login'")
            if submit_btn:
                print("    Submitting login (expecting 401 in dev mode)...")
                try:
                    submit_btn.click()
                    time.sleep(3)
                    page.screenshot(path=".screenshots/04_login_submit.png", full_page=True)
                    print("    Screenshot: .screenshots/04_login_submit.png")
                except Exception as e:
                    print(f"    Click error: {e}")
        else:
            print("    No login form fields found - might be SSO or landing page")
    else:
        print("    No login button found - already on main app")

    time.sleep(2)

    # ── 4. Navigate to different routes ────────────────────────────────
    print("\n[4] Testing navigation to key pages...")
    routes = [
        ("/", "Dashboard"),
        ("/agents", "Agents"),
        ("/calls", "Calls"),
        ("/campaigns", "Campaigns"),
        ("/settings", "Settings"),
        ("/voice-cloning", "Voice Cloning"),
    ]

    for route, name in routes:
        try:
            link = page.query_selector(f"a[href='{route}']") or page.query_selector(f"a[href$='{route}']")
            if link:
                link.click()
                time.sleep(2)
                page.screenshot(path=f".screenshots/05_{name.replace(' ', '_')}.png", full_page=True)
                h1 = page.query_selector("h1")
                title_text = h1.text_content().strip() if h1 else "No h1"
                print(f"    {name}: '{title_text}' - Screenshot saved")
            else:
                # Try direct navigation
                page.goto(f"http://127.0.0.1:3001{route}", wait_until="networkidle", timeout=10000)
                time.sleep(2)
                page.screenshot(path=f".screenshots/05_{name.replace(' ', '_')}.png", full_page=True)
                h1 = page.query_selector("h1")
                title_text = h1.text_content().strip() if h1 else "No h1"
                print(f"    {name}: '{title_text}' - Screenshot saved")
        except Exception as e:
            print(f"    {name}: Error - {e}")

    time.sleep(2)

    # ── 5. Test API interaction from UI ────────────────────────────────
    print("\n[5] Testing API from UI (via browser console)...")
    try:
        api_result = page.evaluate("""
            async () => {
                try {
                    const r = await fetch('http://127.0.0.1:8000/health');
                    const data = await r.json();
                    return { status: r.status, data: data };
                } catch(e) { return { error: e.message }; }
            }
        """)
        print(f"    API health from UI: {json.dumps(api_result, indent=2)[:300]}")
    except Exception as e:
        print(f"    API test error: {e}")

    time.sleep(1)

    # ── 6. Final full-page screenshot ──────────────────────────────────
    print("\n[6] Final dashboard screenshot...")
    page.goto("http://127.0.0.1:3001/", wait_until="networkidle", timeout=15000)
    time.sleep(2)
    page.screenshot(path=".screenshots/final_dashboard.png", full_page=True)
    print("    Screenshot: .screenshots/final_dashboard.png")

    print("\n" + "=" * 60)
    print("  UI EXPLORATION COMPLETE")
    print("=" * 60)
    print("  Screenshots saved to .screenshots/")
    print(f"  Total screenshots: {len(os.listdir('.screenshots'))}")
    print()
    print("  Press Enter to close browser...")

    input()
    browser.close()