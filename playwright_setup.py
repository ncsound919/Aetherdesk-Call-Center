#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
AetherDesk Playwright Setup Script
Starts servers and verifies everything works
"""
import subprocess
import time
import httpx
import os
import sys
import signal

# Set environment variables
os.environ["ENCRYPTION_KEY"] = "REDACTED_ENCRYPTION_KEY_PLEASE_ROTATE="
os.environ["WEBSOCKET_SECRET_KEY"] = "test-websocket-secret"

def kill_port(port):
    try:
        result = subprocess.run(
            f'for /f "tokens=5" %i in (\'netstat -ano ^| findstr :{port}\') do @echo %i',
            shell=True, capture_output=True, text=True
        )
        pids = [p.strip() for p in result.stdout.strip().split('\n') if p.strip()]
        for pid in pids:
            if pid.isdigit():
                subprocess.run(f'taskkill /PID {pid} /F 2>nul', shell=True, capture_output=True)
                print(f"  Killed old process on port {port} (PID: {pid})")
    except:
        pass

# Kill old processes
print("Cleaning up old processes...")
kill_port(8000)
kill_port(3001)
time.sleep(2)

# Start API server
print("Starting API server on port 8000...")
api_proc = subprocess.Popen(
    [sys.executable, '-m', 'uvicorn', 'apps.api.main:app',
     '--host', '127.0.0.1', '--port', '8000', '--log-level', 'warning'],
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
    cwd=r'C:\Users\User\Desktop\aetherdesk_scaffold'
)

# Wait for API
print("Waiting for API to start (max 30s)...")
api_ready = False
for i in range(30):
    try:
        with httpx.Client(timeout=2.0) as client:
            r = client.get('http://127.0.0.1:8000/health')
            if r.status_code == 200:
                api_ready = True
                print("  API is ready!")
                break
    except:
        pass
    time.sleep(1)

if not api_ready:
    print("  WARNING: API may not be ready")

# Start UI server
print("Starting UI server on port 3001...")
ui_proc = subprocess.Popen(
    [sys.executable, '-m', 'vite', '--host', '0.0.0.0', '--port', '3001'],
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
    cwd=r'C:\Users\User\Desktop\aetherdesk_scaffold\agent-ui'
)

# Wait for UI
print("Waiting for UI to start (max 30s)...")
ui_ready = False
for i in range(30):
    try:
        with httpx.Client(timeout=2.0) as client:
            r = client.get('http://127.0.0.1:3001/')
            if r.status_code in [200, 404]:
                ui_ready = True
                print("  UI is ready!")
                break
    except:
        pass
    time.sleep(1)

if not ui_ready:
    print("  WARNING: UI may not be ready")

# Now use Playwright to interact
print("\n" + "="*60)
print("Starting Playwright browser session...")
print("="*60)

from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(
        headless=False,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-first-run",
            "--window-size=1920,1080"
        ]
    )
    context = browser.new_context()
    page = context.new_page()

    print("\n1. Opening UI...")
    try:
        page.goto("http://127.0.0.1:3001/", wait_until="domcontentloaded", timeout=15000)
        print("   DONE - Title:", page.title()[:50])
        page.screenshot(path=".screenshots/ui_landing.png", full_page=True)
    except Exception as e:
        print("   ERROR:", str(e)[:100])

    print("\n2. Checking API health...")
    try:
        page.goto("http://127.0.0.1:8000/health", timeout=10000)
        content = page.text_content("body")
        print("   API health response:", content[:200])
        page.screenshot(path=".screenshots/api_health.png")
    except Exception as e:
        print("   ERROR:", str(e)[:100])

    print("\n3. Taking full screenshot...")
    try:
        page.goto("http://127.0.0.1:3001/", wait_until="networkidle", timeout=15000)
        page.wait_for_timeout(2000)
        page.screenshot(path=".screenshots/call_center_full.png", full_page=True)
        print("   Screenshot saved!")
    except Exception as e:
        print("   ERROR:", str(e)[:100])

    print("\n" + "="*60)
    print("Browser session complete!")
    print("Servers are still running in background.")
    print("Close browser window when done.")
    print("="*60)

    browser.close()

# Keep servers alive after browser closes
print("\nServers still running. Press Enter to stop...")
input()

api_proc.terminate()
ui_proc.terminate()
print("Stopped.")