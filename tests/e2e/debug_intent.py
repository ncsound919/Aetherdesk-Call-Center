"""Debug intent classifier timing."""
import time, httpx
t0 = time.time()
r = httpx.post("http://localhost:8000/api/v1/voice/intent",
               json={"text": "I need a refill"},
               headers={"x-api-key": "dev-api-key"}, timeout=120)
elapsed = time.time() - t0
print(f"Total: {elapsed:.1f}s, Status: {r.status_code}")
print(r.text[:300])
