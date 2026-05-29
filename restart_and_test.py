#!/usr/bin/env python
"""Restart API server with auth routes and test login."""
import subprocess
import os
import sys
import time
import httpx

os.chdir(r"C:\Users\User\Desktop\aetherdesk_scaffold")
os.environ["ENCRYPTION_KEY"] = "SkYXQ9OlgNAkCoikdZW9NQLYhRbdgQSrV7vfrnCjxLA="
os.environ["JWT_SECRET"] = "test-websocket-secret"
os.environ["WEBSOCKET_SECRET_KEY"] = "test-websocket-secret"
os.environ["USE_POSTGRES"] = "false"
os.environ["DEEPGRAM_API_KEY"] = os.getenv("DEEPGRAM_API_KEY", "REPLACE_WITH_DEEPGRAM_API_KEY")
os.environ["GROQ_API_KEY"] = os.getenv("GROQ_API_KEY", "REPLACE_WITH_GROQ_API_KEY")

# Kill old API server
os.system('taskkill /F /IM "python.exe" 2>nul')
time.sleep(2)

# Start API server
print("Starting API server with auth routes...")
proc = subprocess.Popen(
    [sys.executable, "-m", "uvicorn", "apps.api.main:app",
     "--host", "127.0.0.1", "--port", "8000", "--log-level", "info"],
    stdout=subprocess.DEVNULL,
    stderr=open(r"C:\Users\User\AppData\Local\Temp\opencode\api_err.log", "w"),
)
print(f"API PID: {proc.pid}")
time.sleep(6)

# Test health
try:
    r = httpx.get("http://127.0.0.1:8000/health", timeout=5)
    print(f"Health: {r.status_code} -> {r.json().get('status')}")
except Exception as e:
    print(f"Health failed: {e}")

# Test login endpoint
try:
    r = httpx.post("http://127.0.0.1:8000/auth/login", json={
        "email": "admin@aetherdesk.com",
        "password": "admin123"
    }, timeout=5)
    print(f"Login: {r.status_code}")
    if r.status_code == 200:
        data = r.json()
        print(f"  Token: {data['token'][:40]}...")
        print(f"  Tenant: {data['tenantId']}")
        print(f"  User: {data['userId']}")
        print(f"  Role: {data['role']}")
        print(f"  Name: {data['name']}")
    else:
        print(f"  Error: {r.text[:200]}")
except Exception as e:
    print(f"Login failed: {e}")

# Check error log
with open(r"C:\Users\User\AppData\Local\Temp\opencode\api_err.log") as f:
    err = f.read()
    if err:
        print(f"\nAPI Errors:\n{err[-1500:]}")

print("\nDone!")