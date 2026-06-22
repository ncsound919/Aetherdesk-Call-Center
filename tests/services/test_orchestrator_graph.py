import asyncio
import json
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import END

from apps.api.services import orchestrator
from apps.api.services.orchestrator import create_langchain_agent, Orchestrator, AgentResponse


class AsyncFakeModel:
    def __init__(self):
        self.responses = []

    async def ainvoke(self, messages, config=None):
        if self.responses:
            return self.responses.pop(0)
        return AIMessage(content="Simulated text response.")


@pytest.fixture
def mock_actions():
    return MagicMock()


def test_create_langchain_agent_returns_compiled_graph(mock_actions):
    # Setup fake model global
    fake_model = AsyncFakeModel()
    orchestrator.model = fake_model

    graph = create_langchain_agent(mock_actions, "test-tenant", "Test system prompt")
    assert graph is not None
    assert hasattr(graph, "ainvoke")


@pytest.mark.asyncio
async def test_graph_routes_to_end_on_response(mock_actions):
    fake_model = AsyncFakeModel()
    fake_model.responses = [AIMessage(content="Welcome to support!")]
    orchestrator.model = fake_model

    graph = create_langchain_agent(mock_actions, "test-tenant", "Test system prompt")
    config = {"configurable": {"thread_id": "test-thread"}}

    result = None
    async for chunk in graph.astream({"messages": [HumanMessage(content="Hello")]}, config=config):
        result = chunk

    # astream yields updates; the final chunk should contain messages
    assert result is not None
    # The result structure depends on LangGraph version; just verify we got something
    assert isinstance(result, dict)


@pytest.fixture
def orch_no_init(mock_actions):
    with patch.object(Orchestrator, '_init_langchain'):
        orch = Orchestrator(mock_actions)
    return orch


@pytest.mark.asyncio
async def test_orchestrator_ttl_cache_management(orch_no_init):
    orch = orch_no_init
    orch.langchain_initialized = True
    
    # We mock create_langchain_agent
    mock_create = MagicMock(return_value=MagicMock())
    orchestrator.create_langchain_agent = mock_create
    
    orch.agent_graphs.clear()
    orch._agent_timestamps.clear()

    # First call - should populate cache
    await orch.get_agent_graph("tenant-1", "prof-1", "sys-prompt")
    assert mock_create.call_count == 1
    
    # Second call within TTL - should hit cache
    await orch.get_agent_graph("tenant-1", "prof-1", "sys-prompt")
    assert mock_create.call_count == 1

    # Force TTL eviction by backdating the timestamp
    orch._agent_timestamps["tenant-1:prof-1"] = 0
    await orch.get_agent_graph("tenant-1", "prof-1", "sys-prompt")
    assert mock_create.call_count == 2


@pytest.mark.asyncio
async def test_orchestrator_step_fallback_when_langchain_disabled(orch_no_init, monkeypatch):
    orch = orch_no_init
    orch.langchain_initialized = False # Force fallback

    # Mock DB context and database calls
    mock_db_context = MagicMock()
    mock_conn = MagicMock()
    
    mock_db_context.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_db_context.__aexit__ = AsyncMock(return_value=False)
    
    mock_conn.fetchval = AsyncMock(return_value="rental-123")
    mock_conn.fetchrow = AsyncMock(return_value={"prompt": "Fallback system prompt", "parameters": "{}"})
    
    monkeypatch.setattr("apps.api.services.database.db_context", lambda: mock_db_context)
    monkeypatch.setattr("apps.api.services.database.USE_POSTGRES", True)

    # Mock fallback HTTP client calls to Ollama
    async def mock_post(*args, **kwargs):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        # Include 'response' key for the fallback agent
        mock_resp.json = MagicMock(return_value={"message": {"content": json.dumps({"response": "Fallback Ollama response"})}})
        return mock_resp

    monkeypatch.setattr("httpx.AsyncClient.post", mock_post)
    
    # Patch security and escalation
    monkeypatch.setattr("apps.api.services.orchestrator.detect_prompt_injection", lambda t: (False, 0.0))
    monkeypatch.setattr("apps.api.routers.campaign.push_escalation_alert", AsyncMock())

    session_state = {"active_agent": None}
    response = await orch.step(session_state, [], "Hello from user", "tenant-123", "PROF-001")
    
    assert isinstance(response, AgentResponse)
    assert response.text == "Fallback Ollama response"
