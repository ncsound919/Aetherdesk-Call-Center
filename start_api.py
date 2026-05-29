import subprocess
import os
import time

os.environ["ENCRYPTION_KEY"] = "REDACTED_ENCRYPTION_KEY_PLEASE_ROTATE="
os.environ["WEBSOCKET_SECRET_KEY"] = "test-websocket-secret"

print("Starting API server on port 8000...")
proc = subprocess.Popen(
    ['python', '-m', 'uvicorn', 'apps.api.main:app', '--host', '127.0.0.1', '--port', '8000'],
    cwd=r'C:\Users\User\Desktop\aetherdesk_scaffold',
    creationflags=subprocess.CREATE_NEW_CONSOLE
)
print(f"API server started (PID: {proc.pid})")

time.sleep(6)

import httpx
try:
    r = httpx.get('http://127.0.0.1:8000/health')
    print(f"API is running! Status: {r.status_code}")
    print(f"Response: {r.text[:200]}")
except Exception as e:
    print(f"API failed: {e}")

print("\nNow open http://127.0.0.1:3001 in your Chrome browser!")
print("Both servers should be working.")