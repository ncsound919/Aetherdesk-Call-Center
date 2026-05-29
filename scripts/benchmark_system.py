#!/usr/bin/env python3
"""
AetherDesk Call Center - System Benchmark Suite
=================================================
Runs comprehensive benchmarks against the running API and reports results.

Usage:
    python scripts/benchmark_system.py

Environment Variables:
    API_URL  - Base URL for the API (default: http://localhost:8000)
    ITERATIONS - Number of iterations per test (default: 100)
"""
import asyncio
import httpx
import time
import json
import os
import sys
from datetime import datetime
from typing import List, Dict, Any
from dataclasses import dataclass

API_URL = os.getenv("API_URL", "http://localhost:8000")
ITERATIONS = int(os.getenv("ITERATIONS", "100"))
API_KEY = os.getenv("INTERNAL_API_KEY", "dev-api-key")


@dataclass
class BenchmarkResult:
    name: str
    iterations: int
    total_time_ms: float
    avg_time_ms: float
    min_time_ms: float
    max_time_ms: float
    p95_time_ms: float
    p99_time_ms: float
    errors: int
    success: bool


class BenchmarkRunner:
    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.results: List[BenchmarkResult] = []

    async def run_get_benchmark(self, name: str, path: str, iterations: int = ITERATIONS) -> BenchmarkResult:
        """Benchmark GET endpoint"""
        async with httpx.AsyncClient(timeout=30.0) as client:
            times = []
            errors = 0

            for _ in range(iterations):
                start = time.perf_counter()
                try:
                    response = await client.get(f"{self.base_url}{path}")
                    elapsed = (time.perf_counter() - start) * 1000

                    if response.status_code >= 400:
                        errors += 1
                        times.append(elapsed)
                    else:
                        times.append(elapsed)
                except Exception as e:
                    errors += 1
                    elapsed = (time.perf_counter() - start) * 1000
                    times.append(elapsed)

        total = sum(times)
        avg = total / len(times)
        sorted_times = sorted(times)
        p95_idx = int(len(sorted_times) * 0.95)
        p99_idx = int(len(sorted_times) * 0.99)

        return BenchmarkResult(
            name=name,
            iterations=iterations,
            total_time_ms=total,
            avg_time_ms=avg,
            min_time_ms=min(times),
            max_time_ms=max(times),
            p95_time_ms=sorted_times[p95_idx],
            p99_time_ms=sorted_times[p99_idx],
            errors=errors,
            success=errors < iterations * 0.1  # < 10% errors
        )

    async def run_post_benchmark(self, name: str, path: str, json_body: dict, iterations: int = ITERATIONS) -> BenchmarkResult:
        """Benchmark POST endpoint"""
        async with httpx.AsyncClient(timeout=30.0) as client:
            times = []
            errors = 0

            for _ in range(iterations):
                start = time.perf_counter()
                try:
                    response = await client.post(
                        f"{self.base_url}{path}",
                        json=json_body,
                        headers={"X-API-Key": self.api_key}
                    )
                    elapsed = (time.perf_counter() - start) * 1000

                    if response.status_code >= 400:
                        errors += 1
                    times.append(elapsed)
                except Exception as e:
                    errors += 1
                    elapsed = (time.perf_counter() - start) * 1000
                    times.append(elapsed)

        total = sum(times)
        avg = total / len(times)
        sorted_times = sorted(times)
        p95_idx = int(len(sorted_times) * 0.95)
        p99_idx = int(len(sorted_times) * 0.99)

        return BenchmarkResult(
            name=name,
            iterations=iterations,
            total_time_ms=total,
            avg_time_ms=avg,
            min_time_ms=min(times),
            max_time_ms=max(times),
            p95_time_ms=sorted_times[p95_idx],
            p99_time_ms=sorted_times[p99_idx],
            errors=errors,
            success=errors < iterations * 0.1
        )

    def print_results(self):
        """Print formatted results"""
        print("\n" + "=" * 80)
        print("AETHERDESK SYSTEM BENCHMARK RESULTS")
        print("=" * 80)
        print(f"Timestamp: {datetime.now().isoformat()}")
        print(f"API URL: {self.base_url}")
        print(f"Iterations per test: {ITERATIONS}")
        print("=" * 80)

        for result in self.results:
            status = "✅ PASS" if result.success else "❌ FAIL"
            print(f"\n{status} {result.name}")
            print(f"  Total: {result.total_time_ms:.2f}ms")
            print(f"  Avg:   {result.avg_time_ms:.2f}ms")
            print(f"  Min:   {result.min_time_ms:.2f}ms")
            print(f"  Max:   {result.max_time_ms:.2f}ms")
            print(f"  P95:   {result.p95_time_ms:.2f}ms")
            print(f"  P99:   {result.p99_time_ms:.2f}ms")
            print(f"  Errors: {result.errors}/{result.iterations}")

        # Summary
        total_tests = len(self.results)
        passed = sum(1 for r in self.results if r.success)
        failed = total_tests - passed

        print("\n" + "=" * 80)
        print("SUMMARY")
        print("=" * 80)
        print(f"Total Tests: {total_tests}")
        print(f"Passed: {passed}")
        print(f"Failed: {failed}")

        if failed > 0:
            print("\n⚠️  FAILED TESTS:")
            for result in self.results:
                if not result.success:
                    print(f"  - {result.name}: {result.errors} errors")

        print("=" * 80)

        # Performance grades
        print("\n📊 PERFORMANCE GRADES:")
        for result in self.results:
            if result.avg_time_ms < 50:
                grade = "A+"
            elif result.avg_time_ms < 100:
                grade = "A"
            elif result.avg_time_ms < 200:
                grade = "B"
            elif result.avg_time_ms < 500:
                grade = "C"
            elif result.avg_time_ms < 1000:
                grade = "D"
            else:
                grade = "F"

            print(f"  {result.name}: {grade} ({result.avg_time_ms:.1f}ms)")

        print("=" * 80)


async def main():
    runner = BenchmarkRunner(API_URL, API_KEY)

    print("Starting benchmarks...")

    # Basic Health Endpoints
    runner.results.append(await runner.run_get_benchmark("GET /api/v1/health", "/api/v1/health"))
    runner.results.append(await runner.run_get_benchmark("GET /api/v1/health/ready", "/api/v1/health/ready"))
    runner.results.append(await runner.run_get_benchmark("GET /api/v1/health/live", "/api/v1/health/live"))

    # Auth Endpoints
    runner.results.append(await runner.run_post_benchmark(
        "POST /auth/login",
        "/auth/login",
        {"email": "admin@aetherdesk.com", "password": "admin123"}
    ))

    # Tenant Management
    runner.results.append(await runner.run_post_benchmark(
        "POST /api/v1/tenants",
        "/api/v1/tenants",
        {
            "name": "Benchmark Corp",
            "email": f"bench{int(time.time())}@test.com",
            "slug": f"bench{int(time.time())}",
            "gdpr_consent": True
        }
    ))

    # Agent Management
    runner.results.append(await runner.run_post_benchmark(
        "POST /api/v1/agents",
        "/api/v1/agents",
        {"name": "Benchmark Agent", "skills": ["sales"]}
    ))

    # Call Management
    runner.results.append(await runner.run_post_benchmark(
        "POST /api/v1/calls",
        "/api/v1/calls",
        {"caller_number": "+15551234567", "call_direction": "inbound"}
    ))

    # Intent Classification
    runner.results.append(await runner.run_post_benchmark(
        "POST /voice/intent",
        "/voice/intent",
        {"text": "I need to check my invoice status"}
    ))

    # Queue Operations
    runner.results.append(await runner.run_post_benchmark(
        "POST /campaign/leads",
        "/campaign/leads",
        {"phone": "+15551234567", "company_name": "Test Company", "industry": "tech"}
    ))

    # Campaign Dashboard
    runner.results.append(await runner.run_get_benchmark("GET /campaign/stats", "/campaign/stats"))

    # SaaS Dashboard
    runner.results.append(await runner.run_get_benchmark("GET /saas/dashboard", "/saas/dashboard"))

    # Print results
    runner.print_results()

    # Export JSON results
    results_json = [
        {
            "name": r.name,
            "iterations": r.iterations,
            "total_ms": round(r.total_time_ms, 2),
            "avg_ms": round(r.avg_time_ms, 2),
            "min_ms": round(r.min_time_ms, 2),
            "max_ms": round(r.max_time_ms, 2),
            "p95_ms": round(r.p95_time_ms, 2),
            "p99_ms": round(r.p99_time_ms, 2),
            "errors": r.errors,
            "success": r.success
        }
        for r in runner.results
    ]

    with open("benchmark_results.json", "w") as f:
        json.dump(results_json, f, indent=2)

    print(f"\nBenchmark results saved to benchmark_results.json")

    # Return exit code based on results
    failed = sum(1 for r in runner.results if not r.success)
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    asyncio.run(main())