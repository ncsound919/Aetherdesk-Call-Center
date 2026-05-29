import asyncio
import json

import pytest
import websockets

# Note: The server must be running on localhost:8000 for these tests to pass.
WS_URL = "ws://localhost:8000/api/v1/realtime/call"

@pytest.mark.asyncio
async def test_websocket_stress_and_bounds():
    """
    Stress tests the realtime WebSocket endpoints.
    Simulates a high-volume call where hundreds of transcripts are generated rapidly.
    Ensures the server doesn't crash (DoS) and that memory bounding works.
    """
    call_sid = "STRESS_TEST_SID_001"

    try:
        # Connect to the call websocket
        async with websockets.connect(f"{WS_URL}/{call_sid}") as ws:

            # Spam 500 transcript events rapidly
            for i in range(500):
                await ws.send(json.dumps({
                    "type": "transcript",
                    "text": f"This is spam message number {i}",
                    "from": "customer"
                }))

            # Wait a moment for the server to process
            await asyncio.sleep(1)

            # Now we need to verify the server is still alive and bounded the memory.
            # We can check this by subscribing as an agent to the same call_sid.
            # The agent should receive EXACTLY 200 messages (MAX_TRANSCRIPT_PER_CALL).

            agent_received = 0
            async with websockets.connect("ws://localhost:8000/api/v1/realtime/agent/stress_supervisor") as agent_ws:
                # Subscribe to the call
                await agent_ws.send(json.dumps({
                    "type": "subscribe_call",
                    "call_sid": call_sid
                }))

                # First message should be the subscription confirmation
                confirm = await agent_ws.recv()
                assert json.loads(confirm)["type"] == "subscribed"

                # Now we should receive the historical transcripts.
                # It should be capped at 200.
                try:
                    while True:
                        msg = await asyncio.wait_for(agent_ws.recv(), timeout=2.0)
                        data = json.loads(msg)
                        if data.get("type") == "transcript":
                            agent_received += 1
                except TimeoutError:
                    pass # Done receiving history

            assert agent_received == 200, f"Expected exactly 200 bounded transcripts, got {agent_received}. Memory leak or bounding failure!"

    except websockets.exceptions.ConnectionClosed:
        pytest.fail("Server crashed or forcibly closed the connection during stress test.")

@pytest.mark.asyncio
async def test_concurrent_connections_stability():
    """
    Simulates a "thundering herd" of 50 concurrent calls connecting simultaneously.
    """
    async def connect_and_idle(sid):
        try:
            async with websockets.connect(f"{WS_URL}/{sid}") as ws:
                await ws.send(json.dumps({
                    "type": "transcript",
                    "text": "Hello",
                    "from": "customer"
                }))
                await asyncio.sleep(2)
                return True
        except Exception:
            return False

    # Spawn 50 connections at once
    tasks = [connect_and_idle(f"HERD_{i}") for i in range(50)]
    results = await asyncio.gather(*tasks)

    # Verify all 50 connected successfully without overloading the server
    assert all(results) is True, "Some connections failed during the thundering herd test."
