#!/usr/bin/env python
"""
Start AetherDesk Call Center with visible servers
Runs both API and UI servers in visible windows
"""
import subprocess
import os
import time
import webbrowser
import sys

print("=" * 60)
print("  AetherDesk Call Center - Starting")
print("=" * 60)
print()

# Set env vars
os.environ["ENCRYPTION_KEY"] = "REDACTED_ENCRYPTION_KEY_PLEASE_ROTATE="
os.environ["WEBSOCKET_SECRET_KEY"] = "test-websocket-secret"

base = r"C:\Users\User\Desktop\aetherdesk_scaffold"
ui_base = r"C:\Users\User\Desktop\aetherdesk_scaffold\agent-ui"

print("[1/3] Starting API Server on port 8000...")
api_proc = subprocess.Popen(
    ['python', '-m', 'uvicorn', 'apps.api.main:app', '--host', '127.0.0.1', '--port', '8000'],
    cwd=base,
    creationflags=subprocess.CREATE_NEW_CONSOLE
)
print(f"    PID: {api_proc.pid}")

time.sleep(5)

print("[2/3] Starting UI Server on port 3001...")
env = os.environ.copy()
env["ENCRYPTION_KEY"] = "REDACTED_ENCRYPTION_KEY_PLEASE_ROTATE="
env["WEBSOCKET_SECRET_KEY"] = "test-websocket-secret"
# npm is a .cmd on Windows, need to run via cmd
ui_proc = subprocess.Popen(
    ['cmd', '/c', 'npm', 'run', 'dev', '--', '--host', '127.0.0.1', '--port', '3001'],
    cwd=ui_base,
    env=env,
    creationflags=subprocess.CREATE_NEW_CONSOLE
)
print(f"    Started UI server")

time.sleep(8)

print("[3/3] Opening browser to http://127.0.0.1:3001/ ...")
webbrowser.open("http://127.0.0.1:3001/")

print()
print("=" * 60)
print("  All started! Your browser should show the AetherDesk UI")
print("=" * 60)
print()
print("  Close this window to stop all servers.")
print("=" * 60)

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("\nStopping servers...")
    api_proc.terminate()
    ui_proc.terminate()
    print("Done.")