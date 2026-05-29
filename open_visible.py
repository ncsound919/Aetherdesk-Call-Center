#!/usr/bin/env python
"""Open AetherDesk UI in a VISIBLE Chrome browser for human interaction."""
import subprocess
import os
import sys
import time

os.chdir(r"C:\Users\User\Desktop\aetherdesk_scaffold")

# Ensure servers are running
print("=" * 60)
print("  AetherDesk Call Center - VISIBLE Browser Mode")
print("=" * 60)
print()

# Start API server if not running
import httpx
try:
    r = httpx.get("http://127.0.0.1:8000/health", timeout=3)
    print(f"API server: RUNNING (port 8000, status={r.json().get('status')})")
except:
    print("Starting API server...")
    subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "apps.api.main:app",
         "--host", "127.0.0.1", "--port", "8000"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    time.sleep(6)
    print("API server started.")

# Start UI server if not running
try:
    r = httpx.get("http://127.0.0.1:3001/", timeout=3)
    print(f"UI server: RUNNING (port 3001)")
except:
    print("Starting UI server...")
    env = os.environ.copy()
    env["ENCRYPTION_KEY"] = "REDACTED_ENCRYPTION_KEY_PLEASE_ROTATE="
    env["WEBSOCKET_SECRET_KEY"] = "test-websocket-secret"
    subprocess.Popen(
        [r"C:\Program Files\nodejs\npx.CMD", "vite", "dev", "--host", "127.0.0.1", "--port", "3001"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        env=env, cwd=r"C:\Users\User\Desktop\aetherdesk_scaffold\agent-ui"
    )
    time.sleep(10)
    print("UI server started.")

time.sleep(2)

# Now open a VISIBLE Chrome browser via Playwright
print()
print("Opening VISIBLE Chrome browser...")
print("  -> http://127.0.0.1:3001/")
print()

from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(
        headless=False,  # VISIBLE!
        args=[
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-blink-features=AutomationControlled",
            "--start-maximized"
        ]
    )
    context = browser.new_context(
        viewport={"width": 1920, "height": 1080}
    )
    page = context.new_page()

    print("Navigating to AetherDesk UI...")
    page.goto("http://127.0.0.1:3001/", wait_until="networkidle", timeout=30000)
    print(f"Page title: {page.title()}")
    print(f"URL: {page.url}")

    # Save screenshot so we can see it
    os.makedirs(".screenshots", exist_ok=True)
    page.screenshot(path=".screenshots/aetherdesk_ui.png", full_page=True)
    print("Screenshot saved to .screenshots/aetherdesk_ui.png")

    print()
    print("=" * 60)
    print("  BROWSER IS VISIBLE! You can interact with the UI now.")
    print("=" * 60)
    print()
    print("  API  : http://127.0.0.1:8000")
    print("  UI   : http://127.0.0.1:3001")
    print("  Docs : http://127.0.0.1:8000/docs")
    print()
    print("  Press Enter in this console to close browser...")
    print()

    input()

    browser.close()
    print("Browser closed.")