#!/usr/bin/env python
"""
AetherDesk Call Center - Complete Visible Setup
This script starts both servers and opens Chrome visibly
"""
import subprocess
import os
import time
import sys

print("=" * 60)
print("  AETHERDESK CALL CENTER")
print("  Starting everything visibly...")
print("=" * 60)
print()

# Change to project directory
base = r"C:\Users\User\Desktop\aetherdesk_scaffold"
ui_base = r"C:\Users\User\Desktop\aetherdesk_scaffold\agent-ui"

# Set environment variables
os.environ["ENCRYPTION_KEY"] = "REDACTED_ENCRYPTION_KEY_PLEASE_ROTATE="
os.environ["WEBSOCKET_SECRET_KEY"] = "test-websocket-secret"

# Clean up old processes
print("[1/4] Cleaning up old processes...")
os.system('taskkill /F /IM "python.exe" 2>nul')
os.system('taskkill /F /IM "node.exe" 2>nul')
os.system('taskkill /F /IM "chrome.exe" 2>nul')
time.sleep(2)

# Start API server in a visible console window
print("[2/4] Starting API Server (visible console)...")
api_cmd = 'python -m uvicorn apps.api.main:app --host 127.0.0.1 --port 8000'
subprocess.Popen(
    ['cmd', '/c', api_cmd],
    cwd=base,
    creationflags=subprocess.CREATE_NEW_CONSOLE
)
print("    API server starting in a new window...")
time.sleep(6)

# Start UI server in a visible console window
print("[3/4] Starting UI Server (visible console)...")
ui_env_cmd = 'set ENCRYPTION_KEY=REDACTED_ENCRYPTION_KEY_PLEASE_ROTATE= && set WEBSOCKET_SECRET_KEY=test-websocket-secret && npm run dev -- --host 127.0.0.1 --port 3001'
subprocess.Popen(
    ['cmd', '/c', ui_env_cmd],
    cwd=ui_base,
    creationflags=subprocess.CREATE_NEW_CONSOLE
)
print("    UI server starting in a new window...")
time.sleep(8)

# Open Chrome browser pointing to UI
print("[4/4] Opening Chrome browser...")
os.system('start chrome http://127.0.0.1:3001/')
time.sleep(3)

print()
print("=" * 60)
print("  ALL STARTED SUCCESSFULLY!")
print("=" * 60)
print()
print("  You should see:")
print("    - An API server window (port 8000)")
print("    - A UI dev server window (port 3001)")
print("    - Chrome browser opened to the AetherDesk UI")
print()
print("  If Chrome shows an error, wait 5 seconds and refresh.")
print("  Keep all windows open to use the call center.")
print()
print("  When done, close all windows.")
print("=" * 60)

# Wait for user to finish
input("\nPress Enter to exit setup (servers keep running)...")