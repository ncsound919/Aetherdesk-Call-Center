import asyncio
import time
import httpx
from datetime import datetime

API_URL = "http://localhost:8000/api/v1"
HEADERS = {"Authorization": "Bearer dev-token"} # Need to ensure this token is valid or use an API key

async def benchmark_endpoint(client, method, endpoint, payload=None):
    start = time.perf_counter()
    if method == "POST":
        res = await client.post(f"{API_URL}{endpoint}", json=payload, headers=HEADERS)
    else:
        res = await client.get(f"{API_URL}{endpoint}", headers=HEADERS)
    end = time.perf_counter()
    return end - start, res.status_code

async def main():
    async with httpx.AsyncClient() as client:
        print(f"Starting performance benchmark at {datetime.now()}")
        
        # Benchmark 1: Health Check (Readiness)
        t, code = await benchmark_endpoint(client, "GET", "/health/ready")
        print(f"GET /health/ready: {t:.4f}s (Status: {code})")

        # Benchmark 2: Intent Classification (AI)
        t, code = await benchmark_endpoint(client, "POST", "/ai-assist/validate", {"output": '{"intent": "billing"}', "schema_name": "intent_classification"})
        print(f"POST /ai-assist/validate: {t:.4f}s (Status: {code})")
        
        # Benchmark 3: Call Queue List
        t, code = await benchmark_endpoint(client, "GET", "/calls")
        print(f"GET /calls: {t:.4f}s (Status: {code})")

if __name__ == "__main__":
    asyncio.run(main())
