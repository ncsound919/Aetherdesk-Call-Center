#!/usr/bin/env python
"""
AetherDesk - Visible Browser Test
Opens Chrome visibly so user can see and interact with the UI
"""
import subprocess
import os
import time
import sys

# Set env vars
os.environ["ENCRYPTION_KEY"] = "SkYXQ9OlgNAkCoikdZW9NQLYhRbdgQSrV7vfrnCjxLA="
os.environ["WEBSOCKET_SECRET_KEY"] = "test-websocket-secret"

base = r"C:\Users\User\Desktop\aetherdesk_scaffold"
ui_base = r"C:\Users\User\Desktop\aetherdesk_scaffold\agent-ui"

print("=" * 60)
print("  AetherDesk Call Center - VISIBLE MODE")
print("=" * 60)
print()

# Kill any old processes
print("[1/4] Cleaning old processes...")
subprocess.run('taskkill /F /IM "python.exe" /T 2>nul', shell=True, capture_output=True)
subprocess.run('taskkill /F /IM "node.exe" /T 2>nul', shell=True, capture_output=True)
subprocess.run('taskkill /F /IM "chrome.exe" /T 2>nul', shell=True, capture_output=True)
time.sleep(2)

# Start API server
print("[2/4] Starting API Server (port 8000)...")
api_proc = subprocess.Popen(
    ['python', '-m', 'uvicorn', 'apps.api.main:app', '--host', '127.0.0.1', '--port', '8000'],
    cwd=base,
    creationflags=subprocess.CREATE_NEW_CONSOLE
)
print(f"    API PID: {api_proc.pid}")
time.sleep(5)

# Start UI server
print("[3/4] Starting UI Server (port 3001)...")
env = os.environ.copy()
env["ENCRYPTION_KEY"] = "SkYXQ9OlgNAkCoikdZW9NQLYhRbdgQSrV7vfrnCjxLA="
env["WEBSOCKET_SECRET_KEY"] = "test-websocket-secret"
ui_proc = subprocess.Popen(
    ['cmd', '/c', 'npm', 'run', 'dev', '--', '--host', '127.0.0.1', '--port', '3001'],
    cwd=ui_base,
    env=env,
    creationflags=subprocess.CREATE_NEW_CONSOLE
)
print(f"    UI started")
time.sleep(8)

# Open browser VISIBLE
print("[4/4] Opening Chrome browser (VISIBLE)...")

from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    print("Launching browser...")
    browser = p.chromium.launch(
        headless=False,  # VISIBLE MODE!
        args=[
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-blink-features=AutomationControlled"
        ]
    )
    context = browser.new_context(
        viewport={"width": 1920, "height": 1080}
    )
    page = context.new_page()

    print("Opening http://127.0.0.1:3001/ ...")
    page.goto("http://127.0.0.1:3001/", wait_until="networkidle", timeout=30000)
    print(f"Page title: {page.title()}")

    # Take screenshot so we can see what's displayed
    page.screenshot(path=".screenshots/call_center_visible.png", full_page=True)
    print("Screenshot saved!")

    # Click the Login button if it exists
    print("\nLooking for Login button...")
    try:
        login_btn = page.query_selector("text='Login'")
        if login_btn:
            print("Found Login! Clicking...")
            login_btn.click()
            page.wait_for_timeout(3000)
            page.screenshot(path=".screenshots/call_center_login.png", full_page=True)
            print("Login page screenshot saved!")
        else:
            print("No Login button found - checking page content...")
            content = page.text_content("body")
            print(f"Page text: {content[:500]}")
    except Exception as e:
        print(f"Error: {e}")

    print("\n" + "=" * 60)
    print("  BROWSER IS VISIBLE! You can now interact with it.")
    print("  The call center UI should be displayed above.")
    print("=" * 60)
    print("\n  - API running on: http://127.0.0.1:8000")
    print("  - UI running on:  http://127.0.0.1:3001")
    print("  - API docs:       http://127.0.0.1:8000/docs")
    print("\n  Press Enter in this window to close everything...")
    input()

    browser.close()

api_proc.terminate()
ui_proc.terminate()
print("\nAll servers stopped. Goodbye!")