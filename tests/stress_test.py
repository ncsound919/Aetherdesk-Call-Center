import asyncio
import base64
import json
import sys
import time

import websockets


async def simulate_call(call_id):
    uri = "ws://localhost:8000/api/v1/voice/media-stream"
    try:
        async with websockets.connect(uri) as websocket:
            # 1. Start event
            await websocket.send(json.dumps({
                "event": "start",
                "start": {
                    "streamSid": f"stream_{call_id}",
                    "callSid": f"call_{call_id}"
                }
            }))

            # 2. Simulate 5 seconds of audio chunks
            for _i in range(50): # 100ms * 50 = 5s
                # Send dummy mulaw silence
                dummy_audio = b"\xff" * 160
                await websocket.send(json.dumps({
                    "event": "media",
                    "media": {
                        "payload": base64.b64encode(dummy_audio).decode("utf-8")
                    }
                }))
                await asyncio.sleep(0.1)

            print(f"Call {call_id} completed successfully.")
    except Exception as e:
        print(f"Call {call_id} failed: {e}")

async def run_stress_test(n=10):
    print(f"Starting stress test with {n} concurrent calls...")
    start_time = time.time()
    tasks = [simulate_call(i) for i in range(n)]
    await asyncio.gather(*tasks)
    duration = time.time() - start_time
    print(f"Stress test finished in {duration:.2f} seconds.")

if __name__ == "__main__":
    # Ensure a server is running or this will fail
    count = 10
    if len(sys.argv) > 1:
        count = int(sys.argv[1])
    asyncio.run(run_stress_test(count))
