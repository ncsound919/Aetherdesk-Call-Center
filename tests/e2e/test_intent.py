"""Quick intent classification test."""
import time
import httpx

scenarios = [
    ("Pharmacy", "I need to refill my blood pressure medication"),
    ("Billing", "You charged me twice this month and I want a refund"),
    ("Tech", "My password is not working and I am locked out"),
]

for label, text in scenarios:
    t0 = time.time()
    try:
        r = httpx.post(
            "http://localhost:8000/api/v1/voice/intent",
            json={"text": text},
            headers={"x-api-key": "dev-api-key"},
            timeout=120,
        )
        elapsed = time.time() - t0
        if r.status_code == 200:
            d = r.json()
            print(f"[{elapsed:5.1f}s] {label:10s} -> intent={d.get('intent','?')}, "
                  f"confidence={d.get('confidence','?')}, "
                  f"reason={d.get('reasoning','')[:60]}")
        else:
            print(f"[{elapsed:5.1f}s] {label:10s} -> HTTP {r.status_code}: {r.text[:100]}")
    except Exception as e:
        print(f"[{time.time()-t0:5.1f}s] {label:10s} -> FAIL: {e}")
