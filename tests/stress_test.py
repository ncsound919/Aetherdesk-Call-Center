import argparse
import asyncio
import base64
import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

try:
    import websockets
except ImportError:
    print("websockets not installed. Run: pip install websockets")
    sys.exit(1)


@dataclass
class CallResult:
    call_id: int
    success: bool
    duration_ms: float = 0.0
    error: str = ""


@dataclass
class TestResults:
    results: list[CallResult] = field(default_factory=list)
    start_time: float = 0.0
    end_time: float = 0.0

    @property
    def successful(self):
        return [r for r in self.results if r.success]

    @property
    def failed(self):
        return [r for r in self.results if not r.success]

    @property
    def success_rate(self):
        total = len(self.results)
        return len(self.successful) / total * 100 if total > 0 else 0

    @property
    def latencies(self):
        return sorted([r.duration_ms for r in self.successful])

    def percentile(self, p):
        if not self.latencies:
            return 0
        idx = int(len(self.latencies) * p / 100)
        return self.latencies[min(idx, len(self.latencies) - 1)]

    def print_summary(self):
        total = len(self.results)
        if total == 0:
            print("No results to report.")
            return
        ok = len(self.successful)
        fail = len(self.failed)
        elapsed = self.end_time - self.start_time

        print("\n" + "=" * 60)
        print("  LOAD TEST RESULTS")
        print("=" * 60)
        print(f"  Total calls:    {total}")
        print(f"  Successful:     {ok} ({self.success_rate:.1f}%)")
        print(f"  Failed:         {fail}")
        print(f"  Duration:       {elapsed:.2f}s")
        print(f"  Throughput:     {ok / elapsed:.1f} calls/sec" if elapsed > 0 else "  Throughput:     N/A")
        if self.latencies:
            print(f"  Latency (p50):  {self.percentile(50):.0f}ms")
            print(f"  Latency (p95):  {self.percentile(95):.0f}ms")
            print(f"  Latency (p99):  {self.percentile(99):.0f}ms")
            print(f"  Latency (min):  {min(self.latencies):.0f}ms")
            print(f"  Latency (max):  {max(self.latencies):.0f}ms")
        if self.failed:
            print(f"\n  Failure reasons:")
            error_counts = {}
            for r in self.failed:
                key = r.error[:60]
                error_counts[key] = error_counts.get(key, 0) + 1
            for err, count in sorted(error_counts.items(), key=lambda x: -x[1]):
                print(f"    [{count}x] {err}")
        print("=" * 60)


def load_audio_sample(path: str) -> bytes:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Audio file not found: {path}")
    return p.read_bytes()


async def simulate_call(
    call_id: int,
    uri: str,
    duration_ms: int,
    chunk_ms: int,
    audio_chunk: bytes,
    auth_token: str = "",
    connect_timeout: float = 10.0,
    call_timeout: float = 120.0,
) -> CallResult:
    start = time.monotonic()
    headers = {}
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"

    try:
        async with asyncio.timeout(connect_timeout):
            ws = await websockets.connect(uri, extra_headers=headers)

        await ws.send(json.dumps({
            "event": "start",
            "start": {
                "streamSid": f"stream_{call_id}",
                "callSid": f"call_{call_id}"
            }
        }))

        chunks = max(1, duration_ms // chunk_ms)
        for _ in range(chunks):
            await asyncio.wait_for(
                ws.send(json.dumps({
                    "event": "media",
                    "media": {
                        "payload": base64.b64encode(audio_chunk).decode("utf-8")
                    }
                })),
                timeout=call_timeout
            )
            await asyncio.sleep(chunk_ms / 1000.0)

        await ws.close()
        elapsed = (time.monotonic() - start) * 1000
        return CallResult(call_id=call_id, success=True, duration_ms=elapsed)

    except asyncio.TimeoutError:
        elapsed = (time.monotonic() - start) * 1000
        return CallResult(call_id=call_id, success=False, duration_ms=elapsed,
                          error="Connection timeout")
    except websockets.exceptions.InvalidStatusCode as e:
        elapsed = (time.monotonic() - start) * 1000
        return CallResult(call_id=call_id, success=False, duration_ms=elapsed,
                          error=f"HTTP {e.status_code}")
    except Exception as e:
        elapsed = (time.monotonic() - start) * 1000
        return CallResult(call_id=call_id, success=False, duration_ms=elapsed,
                          error=str(e)[:120])


async def run_stress_test(
    target_url: str,
    concurrent: int,
    call_duration_ms: int,
    chunk_ms: int,
    audio_file: str = "",
    auth_token: str = "",
    connect_timeout: float = 10.0,
    call_timeout: float = 120.0,
):
    if audio_file:
        audio_chunk = load_audio_sample(audio_file)
    else:
        audio_chunk = b"\xff" * 160

    print(f"Target:          {target_url}")
    print(f"Concurrency:     {concurrent}")
    print(f"Call duration:   {call_duration_ms}ms ({call_duration_ms / 1000:.1f}s)")
    print(f"Chunk interval:  {chunk_ms}ms")
    print(f"Audio:           {'real sample' if audio_file else 'dummy silence (\uff\xff)'}")
    if auth_token:
        print(f"Auth:            Bearer token ({len(auth_token)} chars)")
    print()

    results = TestResults()
    results.start_time = time.monotonic()

    tasks = [
        simulate_call(i, target_url, call_duration_ms, chunk_ms, audio_chunk,
                      auth_token, connect_timeout, call_timeout)
        for i in range(concurrent)
    ]

    gathered = await asyncio.gather(*tasks, return_exceptions=True)
    for i, res in enumerate(gathered):
        if isinstance(res, Exception):
            results.results.append(CallResult(call_id=i, success=False, error=str(res)[:120]))
        else:
            results.results.append(res)
            status = "OK" if res.success else "FAIL"
            print(f"  Call {res.call_id:3d}: {status:4s}  {res.duration_ms:8.0f}ms" +
                  (f"  {res.error}" if not res.success else ""))

    results.end_time = time.monotonic()
    results.print_summary()
    return results


def main():
    parser = argparse.ArgumentParser(
        description="AetherDesk Call Center WebSocket Load Test",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # 10 concurrent calls, 5s each, local dev
  python tests/stress_test.py

  # 50 concurrent calls, 10s each, staging
  python tests/stress_test.py -n 50 -d 10000 -u wss://staging.aetherdesk.com/api/v1/voice/media-stream

  # 100 concurrent, 30s duration, with auth and real audio
  python tests/stress_test.py -n 100 -d 30000 -t "$AUTH_TOKEN" -a audio/hello.pcm

  # Production GKE with 200 concurrent
  python tests/stress_test.py -n 200 -d 15000 -u wss://api.aetherdesk.com/api/v1/voice/media-stream -t "$AUTH_TOKEN"
        """
    )
    parser.add_argument("-n", "--concurrent", type=int, default=10,
                        help="Number of concurrent calls (default: 10)")
    parser.add_argument("-d", "--duration", type=int, default=5000,
                        help="Call duration in ms (default: 5000)")
    parser.add_argument("-c", "--chunk", type=int, default=100,
                        help="Audio chunk interval in ms (default: 100)")
    parser.add_argument("-u", "--url",
                        default="ws://localhost:8000/api/v1/voice/media-stream",
                        help="WebSocket URL (default: ws://localhost:8000/api/v1/voice/media-stream)")
    parser.add_argument("-t", "--token",
                        help="Bearer auth token for authenticated endpoints")
    parser.add_argument("-a", "--audio",
                        help="Path to raw audio file (PCM 8kHz mulaw) for real audio instead of dummy silence")
    parser.add_argument("--connect-timeout", type=float, default=10.0,
                        help="WebSocket connect timeout in seconds (default: 10)")
    parser.add_argument("--call-timeout", type=float, default=120.0,
                        help="Per-call timeout in seconds (default: 120)")

    args = parser.parse_args()

    if args.concurrent < 1:
        parser.error("Concurrency must be >= 1")
    if args.duration < 100:
        parser.error("Duration must be >= 100ms")

    if args.concurrent > 50 and "localhost" in args.url:
        print("WARNING: Running >50 concurrent on localhost may cause port exhaustion.")
        print("Consider increasing ephemeral port range or using a remote target.\n")

    asyncio.run(run_stress_test(
        target_url=args.url,
        concurrent=args.concurrent,
        call_duration_ms=args.duration,
        chunk_ms=args.chunk,
        audio_file=args.audio,
        auth_token=args.token,
        connect_timeout=args.connect_timeout,
        call_timeout=args.call_timeout,
    ))


if __name__ == "__main__":
    main()
