#!/usr/bin/env python
"""Test API endpoints - server should already be running."""
import httpx
import time
import json

time.sleep(2)

# Test health
try:
    r = httpx.get("http://127.0.0.1:8000/health", timeout=5)
    print(f"Health: {r.status_code}")
    print(json.dumps(r.json(), indent=2))
except Exception as e:
    print(f"Health failed: {e}")

print()

# Test auth login
try:
    r = httpx.post("http://127.0.0.1:8000/auth/login", json={
        "email": "admin@aetherdesk.com",
        "password": "admin123"
    }, timeout=5)
    print(f"Login: {r.status_code}")
    print(r.text[:500])
except Exception as e:
    print(f"Login failed: {e}")

print()

# Test docs
try:
    r = httpx.get("http://127.0.0.1:8000/docs", timeout=5)
    print(f"Docs: {r.status_code}")
except Exception as e:
    print(f"Docs failed: {e}")