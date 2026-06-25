import httpx
import time

time.sleep(3)
try:
    r1 = httpx.get('http://127.0.0.1:8000/health')
    print(f'API (port 8000): {r1.status_code}')
    print(f'  Response: {r1.text[:200]}')
except Exception as e:
    print(f'API (port 8000): FAILED - {e}')

try:
    r2 = httpx.get('http://127.0.0.1:3001/')
    print(f'UI (port 3001): {r2.status_code}')
except Exception as e:
    print(f'UI (port 3001): FAILED - {e}')