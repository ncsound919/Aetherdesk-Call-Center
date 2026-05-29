#!/usr/bin/env python
"""Test API server login endpoint."""
import subprocess
import os
import sys
import time
import httpx

os.chdir(r"C:\Users\User\Desktop\Aetherdesk-Call-Center-main")

# Start API server
print("Starting API server...")
proc = subprocess.Popen(
    [sys.executable, "-m", "uvicorn", "apps.api.main:app",
     "--host", "127.0.0.1", "--port", "8000", "--log-level", "info"],
    stdout=open(r"C:\Users\User\AppData\Local\Temp\opencode\api_stdout.log", "w"),
    stderr=open(r"C:\Users\User\AppData\Local\Temp\opencode\api_stderr.log", "w"),
)
print(f"API PID: {proc.pid}")
time.sleep(8)

poll = proc.poll()
print(f"Process poll: {poll}")

# Check logs
with open(r"C:\Users\User\AppData\Local\Temp\opencode\api_stderr.log") as f:
    err = f.read()
    if err:
        print("=== STDERR ===")
        print(err[-2000:])

with open(r"C:\Users\User\AppData\Local\Temp\opencode\api_stdout.log") as f:
    out = f.read()
    if out:
        print("=== STDOUT ===")
        print(out[-2000:])

# Test health
try:
    r = httpx.get("http://127.0.0.1:8000/health", timeout=5)
    print(f"\nHealth: {r.status_code}")
    print(r.json())
except Exception as e:
    print(f"Health failed: {e}")

    # Test auth login
    try:
        r = httpx.post("http://127.0.0.1:8000/api/v1/auth/login", json={
            "email": "admin@aetherdesk.com",
            "password": "admin123"
        }, timeout=5)
        print(f"\nLogin: {r.status_code}")
        print(r.text[:500])
    except Exception as e:
        print(f"Login failed: {e}")