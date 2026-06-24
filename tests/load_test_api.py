"""AetherDesk Call Center — HTTP API Load Test

Tests key REST endpoints under concurrent load with throughput,
latency percentiles, error-rate tracking, and resource-usage
observations.

Usage:
    python tests/load_test_api.py                          # quick smoke (10 req/s)
    python tests/load_test_api.py -c 50 -n 1000            # moderate load
    python tests/load_test_api.py -c 200 -n 5000 -u https://staging.example.com/api/v1
    python tests/load_test_api.py --ramp 30                # ramp-up over 30 s
    python tests/load_test_api.py --endpoints health,agents,billing
    python tests/load_test_api.py --format csv > report.csv
"""

import argparse
import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass, field
from statistics import median
from typing import Callable

import httpx

TARGET = os.getenv("API_TARGET", "http://localhost:8000")

# ── Standard request headers ────────────────────────────────────
DEFAULT_HEADERS = {
    "X-API-Key": "dev-api-key",
    "Content-Type": "application/json",
    "Accept": "application/json",
}


# ── Data classes ─────────────────────────────────────────────────

@dataclass
class RequestResult:
    endpoint: str
    method: str
    status: int
    duration_ms: float
    error: str = ""
    bytes_received: int = 0


@dataclass
class EndpointStats:
    endpoint: str
    method: str
    total: int = 0
    success: int = 0
    failed: int = 0
    durations_ms: list = field(default_factory=list)
    errors: dict = field(default_factory=dict)

    @property
    def success_rate(self) -> float:
        return (self.success / self.total * 100) if self.total else 0.0

    @property
    def p50(self) -> float:
        if not self.durations_ms:
            return 0.0
        s = sorted(self.durations_ms)
        return s[len(s) // 2]

    @property
    def p95(self) -> float:
        if not self.durations_ms:
            return 0.0
        s = sorted(self.durations_ms)
        return s[int(len(s) * 0.95)]

    @property
    def p99(self) -> float:
        if not self.durations_ms:
            return 0.0
        s = sorted(self.durations_ms)
        return s[int(len(s) * 0.99)]

    @property
    def throughput(self) -> float:
        """Approximate requests/second."""
        if not self.durations_ms:
            return 0.0
        total_sec = sum(self.durations_ms) / 1000
        return self.total / total_sec if total_sec else 0.0


# ── Endpoint definitions ─────────────────────────────────────────

ENDPOINT_DEFS: list[dict] = [
    {"method": "GET", "path": "/api/v1/health"},
    {"method": "GET", "path": "/api/v1/health/ready"},
    {"method": "GET", "path": "/api/v1/health/live"},
    {"method": "GET", "path": "/api/v1/tenants/TENANT-001", "headers": {"X-API-Key": "dev-api-key"}},
    {"method": "GET", "path": "/api/v1/tenants/TENANT-001/agents", "headers": {"X-API-Key": "dev-api-key"}},
    {"method": "GET", "path": "/api/v1/calls", "params": {"tenant_id": "TENANT-001"}, "headers": {"X-API-Key": "dev-api-key"}},
    {"method": "GET", "path": "/api/v1/usage", "params": {"tenant_id": "TENANT-001"}, "headers": {"X-API-Key": "dev-api-key"}},
    {"method": "GET", "path": "/api/v1/billing", "params": {"tenant_id": "TENANT-001"}, "headers": {"X-API-Key": "dev-api-key"}},
]

POST_ENDPOINTS: list[dict] = [
    {"method": "POST", "path": "/api/v1/tenants", "json": {"name": "LoadTest", "email": f"loadtest@test.com", "gdpr_consent": True}},
    {"method": "POST", "path": "/api/v1/tenants/TENANT-001/agents", "json": {"name": "load-agent", "agent_type": "ai", "skills": ["support"]}},
]


# ── HTTP Load Generator ──────────────────────────────────────────

async def fire_request(
    client: httpx.AsyncClient,
    endpoint: dict,
) -> RequestResult:
    method = endpoint["method"]
    path = endpoint["path"]
    url = f"{TARGET}{path}"
    params = endpoint.get("params", {})
    headers = {**DEFAULT_HEADERS, **endpoint.get("headers", {})}
    body = endpoint.get("json")

    start = time.monotonic()
    try:
        if method == "GET":
            resp = await client.get(url, params=params, headers=headers)
        elif method == "POST":
            resp = await client.post(url, json=body, headers=headers)
        elif method == "PUT":
            resp = await client.put(url, json=body, headers=headers)
        elif method == "DELETE":
            resp = await client.delete(url, headers=headers)
        else:
            return RequestResult(endpoint=path, method=method, status=0, duration_ms=0, error="unsupported method")

        duration = (time.monotonic() - start) * 1000
        body_bytes = len(resp.content)
        if resp.status_code >= 400:
            return RequestResult(endpoint=path, method=method, status=resp.status_code, duration_ms=duration, error=f"HTTP {resp.status_code}", bytes_received=body_bytes)
        return RequestResult(endpoint=path, method=method, status=resp.status_code, duration_ms=duration, bytes_received=body_bytes)
    except Exception as e:
        duration = (time.monotonic() - start) * 1000
        return RequestResult(endpoint=path, method=method, status=0, duration_ms=duration, error=str(e)[:120])


async def worker(
    worker_id: int,
    endpoints: list,
    requests_per_worker: int,
    results: asyncio.Queue,
    ramp_delay: float = 0,
):
    if ramp_delay:
        await asyncio.sleep(worker_id * ramp_delay)

    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0), limits=httpx.Limits(max_connections=50)) as client:
        for _ in range(requests_per_worker):
            ep = endpoints[_ % len(endpoints)]
            result = await fire_request(client, ep)
            await results.put(result)


# ── Ramp-up mode ─────────────────────────────────────────────────

async def ramp_up_worker(
    worker_id: int,
    endpoint: dict,
    results: asyncio.Queue,
    ramp_duration: float,
    calls_per_worker: int,
):
    """Gradually increase request rate over ramp_duration."""
    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
        base_delay = ramp_duration / calls_per_worker
        for i in range(calls_per_worker):
            await asyncio.sleep(base_delay * (1 - i / calls_per_worker))
            result = await fire_request(client, endpoint)
            await results.put(result)


# ── Main runner ──────────────────────────────────────────────────

async def run_load_test(
    concurrent: int = 10,
    total_requests: int = 100,
    endpoints: list | None = None,
    ramp_seconds: float = 0,
    ramp_endpoint: str = "/api/v1/health",
    max_failure_rate: float = 100.0,
) -> dict[str, EndpointStats]:
    results_queue: asyncio.Queue = asyncio.Queue()
    endpoints = endpoints or ENDPOINT_DEFS

    requests_per_worker = max(1, total_requests // concurrent)

    start = time.monotonic()

    if ramp_seconds > 0:
        ep = next((e for e in endpoints if e["path"] == ramp_endpoint), endpoints[0])
        workers = [ramp_up_worker(i, ep, results_queue, ramp_seconds, requests_per_worker) for i in range(concurrent)]
    else:
        workers = [worker(i, endpoints, requests_per_worker, results_queue) for i in range(concurrent)]

    await asyncio.gather(*workers)

    elapsed = time.monotonic() - start
    total_results = []
    while not results_queue.empty():
        total_results.append(await results_queue.get())

    # Aggregate per-endpoint
    stats: dict[str, EndpointStats] = {}
    for r in total_results:
        key = f"{r.method} {r.endpoint}"
        if key not in stats:
            stats[key] = EndpointStats(endpoint=r.endpoint, method=r.method)
        s = stats[key]
        s.total += 1
        if r.status and 200 <= r.status < 400:
            s.success += 1
            s.durations_ms.append(r.duration_ms)
        else:
            s.failed += 1
            s.errors[r.error] = s.errors.get(r.error, 0) + 1

    _print_report(stats, elapsed, total_results)

    total = len(total_results)
    failed = sum(1 for r in total_results if not (r.status and 200 <= r.status < 400))
    failure_rate = (failed / total * 100) if total else 0
    if failure_rate > max_failure_rate:
        print(f"  FAILURE RATE {failure_rate:.1f}% exceeds threshold {max_failure_rate:.1f}% — aborting")
        raise SystemExit(1)

    return stats


def _print_report(stats: dict[str, EndpointStats], elapsed: float, all_results: list):
    total = len(all_results)
    success = sum(1 for r in all_results if r.status and 200 <= r.status < 400)
    failed = total - success

    print(f"\n{'=' * 70}")
    print(f"  HTTP LOAD TEST REPORT")
    print(f"{'=' * 70}")
    print(f"  Total requests:   {total}")
    print(f"  Successful:       {success} ({success/total*100:.1f}%)" if total else "  Successful:       0")
    print(f"  Failed:           {failed}")
    print(f"  Duration:         {elapsed:.2f}s")
    print(f"  Throughput:       {total/elapsed:.1f} req/s" if elapsed else "  Throughput:       N/A")

    # All non-2xx statuses
    status_counts = {}
    for r in all_results:
        status_counts[r.status] = status_counts.get(r.status, 0) + 1
    if any(k != 200 for k in status_counts):
        print(f"\n  Status codes:")
        for code, count in sorted(status_counts.items()):
            marker = "" if code == 200 or (200 <= code < 400) else "  ERR"
            print(f"    HTTP {code}: {count}{marker}")

    print(f"\n  Per-endpoint breakdown:")
    print(f"  {'Endpoint':30s} {'Method':6s} {'Total':6s} {'OK':6s} {'Fail':6s} {'p50(ms)':8s} {'p95(ms)':8s} {'p99(ms)':8s}")
    print(f"  {'-'*30} {'-'*6} {'-'*6} {'-'*6} {'-'*6} {'-'*8} {'-'*8} {'-'*8}")
    for key in sorted(stats.keys()):
        s = stats[key]
        print(f"  {s.endpoint:30s} {s.method:6s} {s.total:6d} {s.success:6d} {s.failed:6d} {s.p50:8.0f} {s.p95:8.0f} {s.p99:8.0f}")
        if s.errors:
            for err, count in sorted(s.errors.items(), key=lambda x: -x[1]):
                print(f"    +-- [{count}x] {err}")

    print(f"{'=' * 70}\n")

    if failed > 0:
        print(f"  !! {failed}/{total} requests failed. Review endpoint errors above.")
    elif total > 0:
        print(f"  ++ All {total} requests succeeded.")
    print()


# ── CLI ──────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="AetherDesk Call Center — HTTP API Load Test",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  python tests/load_test_api.py
  python tests/load_test_api.py -c 50 -n 1000
  python tests/load_test_api.py -c 200 -n 5000 -u https://staging.example.com
  python tests/load_test_api.py --ramp 30
  python tests/load_test_api.py --endpoints health,agents
""",
    )
    parser.add_argument("-c", "--concurrent", type=int, default=10, help="Concurrent workers (default: 10)")
    parser.add_argument("-n", "--requests", type=int, default=100, help="Total requests (default: 100)")
    parser.add_argument("-u", "--url", default=None, help="Base URL (default: $API_TARGET or http://localhost:8000)")
    parser.add_argument("--ramp", type=float, default=0, help="Ramp-up duration in seconds (default: 0 = immediate)")
    parser.add_argument("--endpoints", default=None, help="Comma-separated endpoint paths to test (e.g. health,agents,billing)")
    parser.add_argument("--max-failure-rate", type=float, default=100.0, help="Max allowed failure %% before exit 1 (default: 100)")
    parser.add_argument("--format", choices=["text", "json", "csv"], default="text", help="Output format (default: text)")

    args = parser.parse_args()

    global TARGET
    if args.url:
        TARGET = args.url

    endpoints = list(ENDPOINT_DEFS)
    if args.endpoints:
        requested = set(args.endpoints.split(","))
        endpoints = [e for e in ENDPOINT_DEFS + POST_ENDPOINTS if e["path"].split("/")[-1] in requested]

    asyncio.run(run_load_test(
        concurrent=args.concurrent,
        total_requests=args.requests,
        endpoints=endpoints,
        ramp_seconds=args.ramp,
        max_failure_rate=args.max_failure_rate,
    ))


if __name__ == "__main__":
    main()
