import httpx
import time

time.sleep(5)
print("Checking servers...")

try:
    r = httpx.get('http://127.0.0.1:8000/health')
    print(f"API (port 8000): {r.status_code} - {r.text[:100]}")
except Exception as e:
    print(f"API (port 8000): FAILED - {e}")

try:
    r = httpx.get('http://127.0.0.1:3001/')
    print(f"UI (port 3001): {r.status_code}")
except Exception as e:
    print(f"UI (port 3001): FAILED - {e}")