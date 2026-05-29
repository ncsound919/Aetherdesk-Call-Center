
import pytest

from apps.api.services.actions import Actions

# Mocking the Orchestrator and Agent Response to simulate chaos
from apps.api.services.orchestrator import AgentResponse, Orchestrator


class MockRedis:
    def publish(self, *args, **kwargs): pass
    def set(self, *args, **kwargs): pass
    def get(self, *args, **kwargs): return None
    def rpush(self, *args, **kwargs): pass

@pytest.fixture
def orchestrator():
    actions = Actions(MockRedis())
    return Orchestrator(actions)

@pytest.mark.asyncio
async def test_chaos_llm_json_failure_recovery(orchestrator):
    """
    Simulates a chaos event where the underlying LLM returns malformed JSON.
    The system should self-heal rather than crashing the call session.
    """
    # Force a failure state by injecting bad data into history
    bad_history = [
        {"from": "customer", "text": "I need help."},
        {"from": "agent", "text": "{bad_json: "}
    ]

    # The step function should still return a graceful AgentResponse, not raise JSONDecodeError
    response = await orchestrator.step(
        session_state={},
        history=bad_history,
        user_input="Hello?",
        tenant_id="TENANT-001",
        profile_id="PROF-001"
    )

    assert isinstance(response, AgentResponse)
    assert response.needs_agent is True or isinstance(response.text, str)

@pytest.mark.asyncio
async def test_chaos_database_connection_drop():
    """
    Simulates a database connection dropping mid-transaction to ensure
    the db_context manager prevents connection leaks and handles the error gracefully.
    """
    import sqlite3

    from apps.api.services.database import db_context

    error_caught = False
    try:
        async with db_context() as conn:
            cursor = conn.cursor()
            # Force syntax error to simulate a drop/failure
            cursor.execute("SELECT * FROM non_existent_chaos_table")
    except sqlite3.OperationalError:
        error_caught = True

    assert error_caught is True

    # Verify we can still get a new connection immediately (no deadlock or leak)
    async with db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        assert cursor.fetchone()[0] == 1

@pytest.mark.asyncio
async def test_chaos_rapid_websocket_disconnect():
    """
    Simulates rapid connect/disconnect cycles from an unstable network,
    ensuring the ConnectionManager doesn't leak memory or crash.
    """

    from apps.api.routers.realtime import ConnectionManager

    class MockWebsocket:
        async def accept(self): pass
        async def send_json(self, data): pass
        async def receive_text(self): raise Exception("Disconnect")

    manager = ConnectionManager()

    # Rapid connect/disconnect
    for i in range(100):
        ws = MockWebsocket()
        agent_id = f"chaos_agent_{i}"

        await manager.connect(ws, agent_id)
        assert agent_id in manager.active_connections

        manager.disconnect(agent_id, ws)
        assert agent_id not in manager.active_connections

    assert len(manager.active_connections) == 0
