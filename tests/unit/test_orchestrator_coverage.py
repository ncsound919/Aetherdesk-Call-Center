"""Extended coverage for src/api/services/orchestrator.py.

Targets branches not exercised by the pre-existing orchestrator tests:
ReActAgent.step error/fallback/streaming/tool/approval paths, langfuse +
agentops session handling, record_session SQLite paths, TenantAgent MCP
initialization, Orchestrator langfuse spans + escalation branch, the
LangChain graph call_model / should_continue / tool-node paths, and the
LangChain import-fallback branch of _init_langchain.
"""

import asyncio
import json
import sys

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from api.services import orchestrator as orch_mod
from api.services.llm_client import LlmResult
from api.services.orchestrator import (
    AgentResponse,
    Orchestrator,
    ReActAgent,
    TenantAgent,
    _build_langchain_tools,
    create_langchain_agent,
)


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_actions():
    return MagicMock()


@pytest.fixture
def orch(mock_actions):
    with patch.object(Orchestrator, "_init_langchain"):
        return Orchestrator(mock_actions)


def _db_ctx(conn):
    db = MagicMock()
    db.__aenter__ = AsyncMock(return_value=conn)
    db.__aexit__ = AsyncMock(return_value=False)
    return db


class AsyncFakeModel:
    def __init__(self):
        self.responses = []

    async def ainvoke(self, messages, config=None):
        if self.responses:
            return self.responses.pop(0)
        return MagicMock()


@pytest.fixture
def _restore_model():
    saved = orch_mod.model
    yield
    orch_mod.model = saved


def _capture_tasks():
    """Context manager that runs _safe_create_task coroutines as tracked tasks."""
    created = []

    def _create(coro):
        task = asyncio.create_task(coro)
        created.append(task)
        return task

    return patch("api.services.orchestrator._safe_create_task", side_effect=_create), created


def _chat_ok(text, provider="deepseek"):
    return LlmResult(text=text, provider=provider, model="deepseek-v4-flash")


# ---------------------------------------------------------------------------
# ReActAgent.step — happy paths
# ---------------------------------------------------------------------------


class TestReActAgentStepHappy:
    @pytest.mark.asyncio
    async def test_success_response(self, mock_actions):
        conn = MagicMock()
        conn.fetchrow = AsyncMock(return_value={"parameters": "{}"})
        db = _db_ctx(conn)
        agent = ReActAgent("TestAgent", "You are helpful", ["lookup_invoice"], mock_actions)

        async def fake_chat(messages, temperature=0.1, json_mode=True, tenant_id=None):
            return _chat_ok(json.dumps({"response": "Hello!"}))

        with patch("api.services.orchestrator._ensure_agentops"), \
             patch("api.services.database.db_context", return_value=db), \
             patch("api.services.database.USE_POSTGRES", True), \
             patch("api.services.orchestrator.get_langfuse", return_value=None), \
             patch("api.services.memory_service.memory_service") as mem, \
             patch("api.services.llm_client.llm_client.chat", new=fake_chat):
            mem.get_memories = AsyncMock(return_value=[])
            resp = await agent.step([], "hello", "tenant-1")

        assert resp.text == "Hello!"
        assert resp.needs_agent is False
        assert resp.action_taken is None
        assert resp.latency_ms >= 0

    @pytest.mark.asyncio
    async def test_injects_memories_and_builds_history(self, mock_actions):
        conn = MagicMock()
        conn.fetchrow = AsyncMock(return_value={"parameters": "{}"})
        db = _db_ctx(conn)
        agent = ReActAgent("TestAgent", "base prompt", [], mock_actions)

        captured = {}

        async def fake_chat(messages, temperature=0.1, json_mode=True, tenant_id=None):
            captured["messages"] = messages
            return _chat_ok(json.dumps({"response": "ok"}))

        history = [
            {"from": "customer", "text": "hi", "customer_id": "CUST-1"},
            {"from": "assistant", "text": "welcome"},
        ]

        with patch("api.services.orchestrator._ensure_agentops"), \
             patch("api.services.database.db_context", return_value=db), \
             patch("api.services.database.USE_POSTGRES", True), \
             patch("api.services.orchestrator.get_langfuse", return_value=None), \
             patch("api.services.memory_service.memory_service") as mem, \
             patch("api.services.llm_client.llm_client.chat", new=fake_chat):
            mem.get_memories = AsyncMock(return_value=["loves discounts", "prefers email"])
            await agent.step(history, "need help", "tenant-1")

        mem.get_memories.assert_awaited_once_with("tenant-1", "CUST-1")
        msgs = captured["messages"]
        system = msgs[0]["content"]
        assert "LONG-TERM CUSTOMER MEMORIES" in system
        assert "loves discounts" in system
        assert msgs[1] == {"role": "user", "content": "hi"}
        assert msgs[2]["role"] == "assistant"
        assert msgs[2]["content"].startswith("{")
        assert msgs[-1] == {"role": "user", "content": "need help"}


# ---------------------------------------------------------------------------
# ReActAgent.step — self-healing / tool / approval paths
# ---------------------------------------------------------------------------


class TestReActAgentStepRetryAndTools:
    @pytest.mark.asyncio
    async def test_self_heals_on_invalid_json(self, mock_actions):
        conn = MagicMock()
        conn.fetchrow = AsyncMock(return_value={"parameters": "{}"})
        db = _db_ctx(conn)
        agent = ReActAgent("TestAgent", "p", [], mock_actions)

        responses = ["this is not json", json.dumps({"response": "recovered"})]
        calls = []

        async def fake_chat(messages, temperature=0.1, json_mode=True, tenant_id=None):
            calls.append(messages)
            return _chat_ok(responses.pop(0))

        with patch("api.services.orchestrator._ensure_agentops"), \
             patch("api.services.database.db_context", return_value=db), \
             patch("api.services.database.USE_POSTGRES", True), \
             patch("api.services.orchestrator.get_langfuse", return_value=None), \
             patch("api.services.memory_service.memory_service") as mem, \
             patch("api.services.llm_client.llm_client.chat", new=fake_chat):
            mem.get_memories = AsyncMock(return_value=[])
            resp = await agent.step([], "hello", "t")

        assert resp.text == "recovered"
        assert len(calls) == 2
        assert "not valid JSON" in calls[1][-1]["content"]

    @pytest.mark.asyncio
    async def test_executes_tool_and_continues(self, mock_actions):
        mock_actions.run = AsyncMock(
            return_value={"success": True, "data": {"status": "paid", "amount": "$10", "due_date": "2025-01-01"}}
        )
        conn = MagicMock()
        conn.fetchrow = AsyncMock(return_value={"parameters": "{}"})
        db = _db_ctx(conn)
        agent = ReActAgent("TestAgent", "p", ["lookup_invoice"], mock_actions)

        responses = [
            json.dumps({"tool": "lookup_invoice", "tool_input": "INV-1"}),
            json.dumps({"response": "invoice handled"}),
        ]

        async def fake_chat(messages, temperature=0.1, json_mode=True, tenant_id=None):
            return _chat_ok(responses.pop(0))

        with patch("api.services.orchestrator._ensure_agentops"), \
             patch("api.services.orchestrator.agentops.ToolEvent"), \
             patch("api.services.orchestrator.agentops.record"), \
             patch("api.services.database.db_context", return_value=db), \
             patch("api.services.database.USE_POSTGRES", True), \
             patch("api.services.orchestrator.get_langfuse", return_value=None), \
             patch("api.services.memory_service.memory_service") as mem, \
             patch("api.services.llm_client.llm_client.chat", new=fake_chat):
            mem.get_memories = AsyncMock(return_value=[])
            resp = await agent.step([], "check my invoice", "t")

        assert resp.text == "invoice handled"
        assert resp.action_taken == "lookup_invoice"
        mock_actions.run.assert_awaited_with(
            "lookup_invoice", {"invoice_id": "INV-1"}, tenant_id="t"
        )

    @pytest.mark.asyncio
    async def test_handoff_tool_pushes_escalation_alert(self, mock_actions):
        mock_actions.run = AsyncMock(return_value={"success": True})
        conn = MagicMock()
        conn.fetchrow = AsyncMock(return_value={"parameters": "{}"})
        db = _db_ctx(conn)
        agent = ReActAgent("TestAgent", "p", ["handoff_to_human"], mock_actions)

        responses = [
            json.dumps({"tool": "handoff_to_human", "tool_input": "customer angry"}),
            json.dumps({"response": "transferred"}),
        ]

        async def fake_chat(messages, temperature=0.1, json_mode=True, tenant_id=None):
            return _chat_ok(responses.pop(0))

        ctx, tasks = _capture_tasks()
        with ctx, \
             patch("api.services.orchestrator._ensure_agentops"), \
             patch("api.services.orchestrator.agentops.ToolEvent"), \
             patch("api.services.orchestrator.agentops.record"), \
             patch("api.services.database.db_context", return_value=db), \
             patch("api.services.database.USE_POSTGRES", True), \
             patch("api.services.orchestrator.get_langfuse", return_value=None), \
             patch("api.services.memory_service.memory_service") as mem, \
             patch("api.routers.campaign.push_escalation_alert") as push, \
             patch("api.services.llm_client.llm_client.chat", new=fake_chat):
            mem.get_memories = AsyncMock(return_value=[])
            resp = await agent.step([], "please transfer me", "t")
            await asyncio.gather(*tasks, return_exceptions=True)

        assert resp.text == "transferred"
        assert resp.action_taken == "handoff_to_human"
        assert push.awaited

    @pytest.mark.asyncio
    async def test_supervision_requires_approval(self, mock_actions):
        conn = MagicMock()
        conn.fetchrow = AsyncMock(
            return_value={"parameters": json.dumps({"require_approval_on": ["escalate_to_supervisor"]})}
        )
        conn.execute = AsyncMock()
        db = _db_ctx(conn)
        agent = ReActAgent("TestAgent", "p", ["escalate_to_supervisor"], mock_actions)

        async def fake_chat(messages, temperature=0.1, json_mode=True, tenant_id=None):
            return _chat_ok(json.dumps({"tool": "escalate_to_supervisor", "tool_input": "refund $5000"}))

        with patch("api.services.orchestrator._ensure_agentops"), \
             patch("api.services.database.db_context", return_value=db), \
             patch("api.services.database.USE_POSTGRES", True), \
             patch("api.services.orchestrator.get_langfuse", return_value=None), \
             patch("api.services.memory_service.memory_service") as mem, \
             patch("api.services.llm_client.llm_client.chat", new=fake_chat):
            mem.get_memories = AsyncMock(return_value=[])
            resp = await agent.step([], "approve the refund", "t")

        assert resp.action_taken == "pending_approval"
        assert "approval" in resp.text.lower()
        conn.execute.assert_awaited()

    @pytest.mark.asyncio
    async def test_supervision_sqlite_path(self, mock_actions):
        cursor = MagicMock()
        cursor.fetchone = MagicMock(
            return_value={"parameters": json.dumps({"require_approval_on": ["escalate_to_supervisor"]})}
        )
        conn = MagicMock()
        conn.cursor = MagicMock(return_value=cursor)
        db = _db_ctx(conn)
        agent = ReActAgent("TestAgent", "p", ["escalate_to_supervisor"], mock_actions)

        async def fake_chat(messages, temperature=0.1, json_mode=True, tenant_id=None):
            return _chat_ok(json.dumps({"tool": "escalate_to_supervisor", "tool_input": "x"}))

        with patch("api.services.orchestrator._ensure_agentops"), \
             patch("api.services.database.db_context", return_value=db), \
             patch("api.services.database.USE_POSTGRES", False), \
             patch("api.services.orchestrator.get_langfuse", return_value=None), \
             patch("api.services.memory_service.memory_service") as mem, \
             patch("api.services.llm_client.llm_client.chat", new=fake_chat):
            mem.get_memories = AsyncMock(return_value=[])
            resp = await agent.step([], "go", "t")

        assert resp.action_taken == "pending_approval"
        cursor.execute.assert_called()
        conn.commit.assert_called()


# ---------------------------------------------------------------------------
# ReActAgent.step — error / crash / max-steps paths
# ---------------------------------------------------------------------------


class TestReActAgentStepErrors:
    @pytest.mark.asyncio
    async def test_retries_on_first_error(self, mock_actions):
        conn = MagicMock()
        conn.fetchrow = AsyncMock(return_value={"parameters": "{}"})
        db = _db_ctx(conn)
        agent = ReActAgent("TestAgent", "p", [], mock_actions)

        calls = []

        async def fake_chat(messages, temperature=0.1, json_mode=True, tenant_id=None):
            calls.append(1)
            if len(calls) == 1:
                raise RuntimeError("provider timeout")
            return _chat_ok(json.dumps({"response": "ok after retry"}))

        with patch("api.services.orchestrator._ensure_agentops"), \
             patch("api.services.database.db_context", return_value=db), \
             patch("api.services.database.USE_POSTGRES", True), \
             patch("api.services.orchestrator.get_langfuse", return_value=None), \
             patch("api.services.memory_service.memory_service") as mem, \
             patch("api.services.llm_client.llm_client.chat", new=fake_chat):
            mem.get_memories = AsyncMock(return_value=[])
            resp = await agent.step([], "hello", "t")

        assert resp.text == "ok after retry"
        assert len(calls) == 2

    @pytest.mark.asyncio
    async def test_crash_recovery_pushes_escalation(self, mock_actions):
        conn = MagicMock()
        conn.fetchrow = AsyncMock(return_value={"parameters": "{}"})
        db = _db_ctx(conn)
        agent = ReActAgent("TestAgent", "p", [], mock_actions)

        async def fake_chat(messages, temperature=0.1, json_mode=True, tenant_id=None):
            raise RuntimeError("fatal failure")

        ctx, tasks = _capture_tasks()
        with ctx, \
             patch("api.services.orchestrator._ensure_agentops"), \
             patch("api.services.database.db_context", return_value=db), \
             patch("api.services.database.USE_POSTGRES", True), \
             patch("api.services.orchestrator.get_langfuse", return_value=None), \
             patch("api.services.memory_service.memory_service") as mem, \
             patch("api.routers.campaign.push_escalation_alert") as push, \
             patch("api.services.llm_client.llm_client.chat", new=fake_chat):
            mem.get_memories = AsyncMock(return_value=[])
            resp = await agent.step([], "hello", "t")
            await asyncio.gather(*tasks, return_exceptions=True)

        assert "having trouble" in resp.text
        assert resp.needs_agent is True
        assert push.awaited

    @pytest.mark.asyncio
    async def test_max_steps_exhausted(self, mock_actions):
        conn = MagicMock()
        conn.fetchrow = AsyncMock(return_value={"parameters": "{}"})
        db = _db_ctx(conn)
        agent = ReActAgent("TestAgent", "p", ["search_knowledge_base"], mock_actions)

        responses = [
            json.dumps({"tool": "search_knowledge_base", "tool_input": "q1"}),
            json.dumps({"tool": "search_knowledge_base", "tool_input": "q2"}),
        ]

        async def fake_chat(messages, temperature=0.1, json_mode=True, tenant_id=None):
            return _chat_ok(responses.pop(0))

        ctx, tasks = _capture_tasks()
        with ctx, \
             patch("api.services.orchestrator._ensure_agentops"), \
             patch("api.services.orchestrator.agentops.ToolEvent"), \
             patch("api.services.orchestrator.agentops.record"), \
             patch("api.services.rag.rag_service") as rag, \
             patch("api.services.database.db_context", return_value=db), \
             patch("api.services.database.USE_POSTGRES", True), \
             patch("api.services.orchestrator.get_langfuse", return_value=None), \
             patch("api.services.memory_service.memory_service") as mem, \
             patch("api.routers.campaign.push_escalation_alert") as push, \
             patch("api.services.llm_client.llm_client.chat", new=fake_chat):
            mem.get_memories = AsyncMock(return_value=[])
            rag.query = AsyncMock(return_value=[])
            resp = await agent.step([], "hello", "t")
            await asyncio.gather(*tasks, return_exceptions=True)

        assert "transfer" in resp.text
        assert resp.needs_agent is True
        assert push.awaited


# ---------------------------------------------------------------------------
# ReActAgent.step — langfuse + agentops session handling
# ---------------------------------------------------------------------------


class TestReActAgentStepObservability:
    @pytest.mark.asyncio
    async def test_langfuse_trace_generation_and_score(self, mock_actions):
        conn = MagicMock()
        conn.fetchrow = AsyncMock(return_value={"parameters": "{}"})
        db = _db_ctx(conn)
        agent = ReActAgent("TestAgent", "p", [], mock_actions)

        lf = MagicMock()
        trace = MagicMock()
        trace.id = "TRACE-1"
        lf.trace.return_value = trace
        generation = MagicMock()
        lf.generation.return_value = generation
        ao_session = MagicMock()

        async def fake_chat(messages, temperature=0.1, json_mode=True, tenant_id=None):
            return _chat_ok(json.dumps({"response": "hi"}))

        with patch("api.services.orchestrator._ensure_agentops"), \
             patch("api.services.orchestrator._agentops_initialized", True), \
             patch("api.services.orchestrator.agentops.start_session", return_value=ao_session), \
             patch("api.services.orchestrator.get_langfuse", return_value=lf), \
             patch("api.services.orchestrator.score_call") as mock_score, \
             patch("api.services.database.db_context", return_value=db), \
             patch("api.services.database.USE_POSTGRES", True), \
             patch("api.services.memory_service.memory_service") as mem, \
             patch("api.services.llm_client.llm_client.chat", new=fake_chat):
            mem.get_memories = AsyncMock(return_value=[])
            resp = await agent.step([], "hello", "t")

        assert resp.text == "hi"
        lf.trace.assert_called_once()
        lf.generation.assert_called_once()
        generation.update.assert_called()
        mock_score.assert_called_once()
        ao_session.end_session.assert_called_once()

    @pytest.mark.asyncio
    async def test_generation_update_error_swallowed(self, mock_actions):
        conn = MagicMock()
        conn.fetchrow = AsyncMock(return_value={"parameters": "{}"})
        db = _db_ctx(conn)
        agent = ReActAgent("TestAgent", "p", [], mock_actions)

        lf = MagicMock()
        trace = MagicMock()
        trace.id = "TRACE-1"
        lf.trace.return_value = trace
        generation = MagicMock()
        generation.update.side_effect = Exception("update failed")
        lf.generation.return_value = generation

        async def fake_chat(messages, temperature=0.1, json_mode=True, tenant_id=None):
            return _chat_ok(json.dumps({"response": "hi"}))

        with patch("api.services.orchestrator._ensure_agentops"), \
             patch("api.services.orchestrator.get_langfuse", return_value=lf), \
             patch("api.services.orchestrator.score_call"), \
             patch("api.services.database.db_context", return_value=db), \
             patch("api.services.database.USE_POSTGRES", True), \
             patch("api.services.memory_service.memory_service") as mem, \
             patch("api.services.llm_client.llm_client.chat", new=fake_chat):
            mem.get_memories = AsyncMock(return_value=[])
            resp = await agent.step([], "hello", "t")

        assert resp.text == "hi"

    @pytest.mark.asyncio
    async def test_agentops_start_session_exception_swallowed(self, mock_actions):
        conn = MagicMock()
        conn.fetchrow = AsyncMock(return_value={"parameters": "{}"})
        db = _db_ctx(conn)
        agent = ReActAgent("TestAgent", "p", [], mock_actions)

        async def fake_chat(messages, temperature=0.1, json_mode=True, tenant_id=None):
            return _chat_ok(json.dumps({"response": "hi"}))

        with patch("api.services.orchestrator._ensure_agentops"), \
             patch("api.services.orchestrator._agentops_initialized", True), \
             patch("api.services.orchestrator.agentops.start_session", side_effect=Exception("boom")), \
             patch("api.services.orchestrator.get_langfuse", return_value=None), \
             patch("api.services.database.db_context", return_value=db), \
             patch("api.services.database.USE_POSTGRES", True), \
             patch("api.services.memory_service.memory_service") as mem, \
             patch("api.services.llm_client.llm_client.chat", new=fake_chat):
            mem.get_memories = AsyncMock(return_value=[])
            resp = await agent.step([], "hello", "t")

        assert resp.text == "hi"

    @pytest.mark.asyncio
    async def test_finally_ends_session_on_crash(self, mock_actions):
        conn = MagicMock()
        conn.fetchrow = AsyncMock(return_value={"parameters": "{}"})
        db = _db_ctx(conn)
        agent = ReActAgent("TestAgent", "p", [], mock_actions)

        ao_session = MagicMock()

        async def fake_chat(messages, temperature=0.1, json_mode=True, tenant_id=None):
            raise RuntimeError("boom")

        with patch("api.services.orchestrator._ensure_agentops"), \
             patch("api.services.orchestrator._agentops_initialized", True), \
             patch("api.services.orchestrator.agentops.start_session", return_value=ao_session), \
             patch("api.services.orchestrator.get_langfuse", return_value=None), \
             patch("api.services.database.db_context", return_value=db), \
             patch("api.services.database.USE_POSTGRES", True), \
             patch("api.services.memory_service.memory_service") as mem, \
             patch("api.routers.campaign.push_escalation_alert"), \
             patch("api.services.llm_client.llm_client.chat", new=fake_chat):
            mem.get_memories = AsyncMock(return_value=[])
            resp = await agent.step([], "hello", "t")

        assert resp.needs_agent is True
        ao_session.end_session.assert_called_once()

    @pytest.mark.asyncio
    async def test_end_session_error_swallowed_in_response_branch(self, mock_actions):
        conn = MagicMock()
        conn.fetchrow = AsyncMock(return_value={"parameters": "{}"})
        db = _db_ctx(conn)
        agent = ReActAgent("TestAgent", "p", [], mock_actions)

        ao_session = MagicMock()
        ao_session.end_session.side_effect = Exception("end failed")

        async def fake_chat(messages, temperature=0.1, json_mode=True, tenant_id=None):
            return _chat_ok(json.dumps({"response": "hi"}))

        with patch("api.services.orchestrator._ensure_agentops"), \
             patch("api.services.orchestrator._agentops_initialized", True), \
             patch("api.services.orchestrator.agentops.start_session", return_value=ao_session), \
             patch("api.services.orchestrator.get_langfuse", return_value=None), \
             patch("api.services.database.db_context", return_value=db), \
             patch("api.services.database.USE_POSTGRES", True), \
             patch("api.services.memory_service.memory_service") as mem, \
             patch("api.services.llm_client.llm_client.chat", new=fake_chat):
            mem.get_memories = AsyncMock(return_value=[])
            resp = await agent.step([], "hello", "t")

        assert resp.text == "hi"
        ao_session.end_session.assert_called_once()

    @pytest.mark.asyncio
    async def test_finally_end_session_error_swallowed(self, mock_actions):
        conn = MagicMock()
        conn.fetchrow = AsyncMock(return_value={"parameters": "{}"})
        db = _db_ctx(conn)
        agent = ReActAgent("TestAgent", "p", [], mock_actions)

        ao_session = MagicMock()
        ao_session.end_session.side_effect = Exception("end failed")

        async def fake_chat(messages, temperature=0.1, json_mode=True, tenant_id=None):
            raise RuntimeError("boom")

        with patch("api.services.orchestrator._ensure_agentops"), \
             patch("api.services.orchestrator._agentops_initialized", True), \
             patch("api.services.orchestrator.agentops.start_session", return_value=ao_session), \
             patch("api.services.orchestrator.get_langfuse", return_value=None), \
             patch("api.services.database.db_context", return_value=db), \
             patch("api.services.database.USE_POSTGRES", True), \
             patch("api.services.memory_service.memory_service") as mem, \
             patch("api.routers.campaign.push_escalation_alert"), \
             patch("api.services.llm_client.llm_client.chat", new=fake_chat):
            mem.get_memories = AsyncMock(return_value=[])
            resp = await agent.step([], "hello", "t")

        assert resp.needs_agent is True


    @pytest.mark.asyncio
    async def test_unknown_tool_allowed_but_unknown(self, mock_actions):
        agent = ReActAgent(name="TestAgent", system_prompt="", tools=["mystery_tool"], actions=mock_actions)
        with patch("api.services.orchestrator._ensure_agentops"), \
             patch("api.services.orchestrator.agentops.ToolEvent"), \
             patch("api.services.orchestrator.agentops.record"):
            result = await agent._execute_tool("mystery_tool", "data", "tenant-1")
        assert "Unknown tool" in result

    @pytest.mark.asyncio
    async def test_get_order_status_not_found(self, mock_actions):
        agent = ReActAgent(name="TestAgent", system_prompt="", tools=["get_order_status"], actions=mock_actions)
        mock_actions.run = AsyncMock(return_value={"success": False})
        with patch("api.services.orchestrator._ensure_agentops"), \
             patch("api.services.orchestrator.agentops.ToolEvent"), \
             patch("api.services.orchestrator.agentops.record"):
            result = await agent._execute_tool("get_order_status", "ORD-X", "tenant-1")
        assert "Could not find order" in result


# ---------------------------------------------------------------------------
# ReActAgent.record_session — SQLite paths
# ---------------------------------------------------------------------------


class TestReActAgentRecordSessionSqlite:
    @pytest.mark.asyncio
    async def test_sqlite_without_redaction(self, mock_actions):
        agent = ReActAgent("TestAgent", "p", [], mock_actions)
        cursor = MagicMock()
        cursor.fetchone = MagicMock(return_value={"redact_pii": False})
        conn = MagicMock()
        conn.cursor = MagicMock(return_value=cursor)
        db = _db_ctx(conn)

        ctx, tasks = _capture_tasks()
        with ctx, \
             patch("api.services.database.db_context", return_value=db), \
             patch("api.services.database.USE_POSTGRES", False), \
             patch("api.services.orchestrator.redact_pii") as mock_redact, \
             patch("api.services.memory_service.memory_service") as mem:
            mem.add_memories = AsyncMock()
            await agent.record_session("SES-1", [{"from": "customer", "text": "plain text"}], "t")
            await asyncio.gather(*tasks, return_exceptions=True)

        mock_redact.assert_not_called()
        cursor.execute.assert_called()
        conn.commit.assert_called()

    @pytest.mark.asyncio
    async def test_sqlite_default_redact_when_no_settings(self, mock_actions):
        agent = ReActAgent("TestAgent", "p", [], mock_actions)
        cursor = MagicMock()
        cursor.fetchone = MagicMock(return_value=None)
        conn = MagicMock()
        conn.cursor = MagicMock(return_value=cursor)
        db = _db_ctx(conn)

        ctx, tasks = _capture_tasks()
        with ctx, \
             patch("api.services.database.db_context", return_value=db), \
             patch("api.services.database.USE_POSTGRES", False), \
             patch("api.services.orchestrator.redact_pii", return_value="REDACTED") as mock_redact, \
             patch("api.services.memory_service.memory_service") as mem:
            mem.add_memories = AsyncMock()
            await agent.record_session("SES-2", [{"from": "customer", "text": "my number is 555"}], "t")
            await asyncio.gather(*tasks, return_exceptions=True)

        mock_redact.assert_called_once()


# ---------------------------------------------------------------------------
# TenantAgent._ensure_initialized — MCP servers
# ---------------------------------------------------------------------------


class TestTenantAgentMcpInit:
    @pytest.mark.asyncio
    async def test_initializes_mcp_tools(self, mock_actions):
        agent = TenantAgent("t", "p", mock_actions)
        conn = MagicMock()
        conn.fetchrow = AsyncMock(side_effect=[
            {"id": "p", "name": "McpAgent", "prompt": "p", "parameters": json.dumps({"tools": ["search_knowledge_base"]})},
            {"mcp_servers": ["server-a"]},
        ])
        db = _db_ctx(conn)

        ctx, tasks = _capture_tasks()
        with ctx, \
             patch("api.services.database.db_context", return_value=db), \
             patch("api.services.database.USE_POSTGRES", True), \
             patch("api.services.mcp_client.mcp_manager") as mcp:
            mcp.initialize_tenant_servers = AsyncMock()
            mcp.get_available_tools.return_value = [
                {"name": "mcp_orders"},
                {"name": "mcp_status"},
            ]
            await agent._ensure_initialized()
            await asyncio.gather(*tasks, return_exceptions=True)

        assert agent._initialized is True
        assert "mcp_orders" in agent.tools
        assert "mcp_status" in agent.tools
        assert "search_knowledge_base" in agent.tools

    @pytest.mark.asyncio
    async def test_mcp_init_error_is_swallowed(self, mock_actions):
        agent = TenantAgent("t", "p", mock_actions)
        conn = MagicMock()
        conn.fetchrow = AsyncMock(side_effect=[
            {"id": "p", "name": "McpAgent", "prompt": "p", "parameters": "{}"},
            {"mcp_servers": ["server-a"]},
        ])
        db = _db_ctx(conn)

        ctx, tasks = _capture_tasks()
        with ctx, \
             patch("api.services.database.db_context", return_value=db), \
             patch("api.services.database.USE_POSTGRES", True), \
             patch("api.services.mcp_client.mcp_manager") as mcp:
            mcp.initialize_tenant_servers = AsyncMock()
            mcp.get_available_tools.side_effect = Exception("mcp down")
            await agent._ensure_initialized()
            await asyncio.gather(*tasks, return_exceptions=True)

        assert agent._initialized is True
        assert agent.tools == ["search_knowledge_base", "handoff_to_human"]


# ---------------------------------------------------------------------------
# Orchestrator._init_langchain — import fallback
# ---------------------------------------------------------------------------


class TestInitLangchainImportError:
    def test_falls_back_when_langchain_openai_missing(self, mock_actions, monkeypatch):
        monkeypatch.setattr(orch_mod, "DEEPSEEK_API_KEY", "test-key")
        monkeypatch.setattr(orch_mod, "DEEPSEEK_MODEL", "deepseek-v4-flash")
        monkeypatch.setattr(orch_mod, "DEEPSEEK_BASE_URL", "https://api.deepseek.com")
        monkeypatch.setitem(sys.modules, "langchain_openai", None)
        orch_mod.model = None
        orch = Orchestrator(mock_actions)
        assert orch.langchain_initialized is False


# ---------------------------------------------------------------------------
# Orchestrator.get_agent_graph
# ---------------------------------------------------------------------------


class TestOrchestratorGetAgentGraph:
    @pytest.mark.asyncio
    async def test_caches_and_evicts_graph(self, orch):
        graph = MagicMock()
        with patch("api.services.orchestrator.create_langchain_agent", return_value=graph) as mock_create:
            g1 = await orch.get_agent_graph("t", "p", "sys")
            g2 = await orch.get_agent_graph("t", "p", "sys")
            assert g1 is graph
            assert g2 is graph
            mock_create.assert_called_once()

            orch._agent_timestamps["t:p"] = 0
            g3 = await orch.get_agent_graph("t", "p", "sys")
            assert g3 is graph
            assert mock_create.call_count == 2


# ---------------------------------------------------------------------------
# Orchestrator.step — langfuse span / escalate / sqlite / span error
# ---------------------------------------------------------------------------


class TestOrchestratorStepExtended:
    @pytest.mark.asyncio
    async def test_step_updates_langfuse_span(self, orch):
        lf = MagicMock()
        span = MagicMock()
        lf.span.return_value = span
        conn = MagicMock()
        conn.fetchval = AsyncMock(return_value="rental-123")
        db = _db_ctx(conn)
        mock_agent = AsyncMock()
        mock_agent.step = AsyncMock(
            return_value=AgentResponse(text="hi", sources=[], needs_agent=False)
        )

        with patch("api.services.orchestrator.get_langfuse", return_value=lf), \
             patch("api.services.database.db_context", return_value=db), \
             patch("api.services.database.USE_POSTGRES", True), \
             patch.object(orch, "get_agent", new_callable=AsyncMock, return_value=mock_agent), \
             patch("api.services.orchestrator.sanitize_user_input", side_effect=lambda s, **kw: s):
            session_state = {"active_agent": None}
            resp = await orch.step(session_state, [], "hello", "t", "PROF-001")

        assert resp.text == "hi"
        span.update.assert_called()
        assert session_state["active_agent"] == "PROF-001"

    @pytest.mark.asyncio
    async def test_step_escalate_action(self, orch):
        conn = MagicMock()
        conn.fetchval = AsyncMock(return_value="rental-123")
        db = _db_ctx(conn)
        mock_agent = AsyncMock()
        mock_agent.step = AsyncMock(
            return_value=AgentResponse(
                text="escalating", sources=[], needs_agent=False, action_taken="escalate"
            )
        )

        with patch("api.services.orchestrator.get_langfuse", return_value=None), \
             patch("api.services.database.db_context", return_value=db), \
             patch("api.services.database.USE_POSTGRES", True), \
             patch.object(orch, "get_agent", new_callable=AsyncMock, return_value=mock_agent), \
             patch("api.services.orchestrator.sanitize_user_input", side_effect=lambda s, **kw: s):
            session_state = {"active_agent": "PROF-001"}
            resp = await orch.step(session_state, [], "hello", "t", "PROF-001")

        assert "another department" in resp.text
        assert session_state["active_agent"] is None

    @pytest.mark.asyncio
    async def test_step_sqlite_rental_path(self, orch):
        cursor = MagicMock()
        cursor.fetchone = MagicMock(return_value={"id": "rental-9"})
        conn = MagicMock()
        conn.cursor = MagicMock(return_value=cursor)
        db = _db_ctx(conn)
        mock_agent = AsyncMock()
        mock_agent.step = AsyncMock(
            return_value=AgentResponse(text="ok", sources=[], needs_agent=False)
        )

        with patch("api.services.orchestrator.get_langfuse", return_value=None), \
             patch("api.services.database.db_context", return_value=db), \
             patch("api.services.database.USE_POSTGRES", False), \
             patch.object(orch, "get_agent", new_callable=AsyncMock, return_value=mock_agent), \
             patch("api.services.orchestrator.sanitize_user_input", side_effect=lambda s, **kw: s):
            resp = await orch.step({"active_agent": None}, [], "hello", "t", "PROF-001")

        assert resp.text == "ok"
        assert resp.needs_agent is False

    @pytest.mark.asyncio
    async def test_step_span_update_output_error_swallowed(self, orch):
        lf = MagicMock()
        span = MagicMock()
        span.update.side_effect = Exception("span error")
        lf.span.return_value = span
        conn = MagicMock()
        conn.fetchval = AsyncMock(return_value="rental-123")
        db = _db_ctx(conn)
        mock_agent = AsyncMock()
        mock_agent.step = AsyncMock(
            return_value=AgentResponse(text="ok", sources=[], needs_agent=False)
        )

        with patch("api.services.orchestrator.get_langfuse", return_value=lf), \
             patch("api.services.database.db_context", return_value=db), \
             patch("api.services.database.USE_POSTGRES", True), \
             patch.object(orch, "get_agent", new_callable=AsyncMock, return_value=mock_agent), \
             patch("api.services.orchestrator.sanitize_user_input", side_effect=lambda s, **kw: s):
            resp = await orch.step({"active_agent": None}, [], "hello", "t", "PROF-001")

        assert resp.text == "ok"

    @pytest.mark.asyncio
    async def test_step_exception_span_update_error_swallowed(self, orch):
        lf = MagicMock()
        span = MagicMock()
        span.update.side_effect = Exception("span error")
        lf.span.return_value = span
        conn = MagicMock()
        conn.fetchval = AsyncMock(return_value="rental-123")
        db = _db_ctx(conn)

        with patch("api.services.orchestrator.get_langfuse", return_value=lf), \
             patch("api.services.database.db_context", return_value=db), \
             patch("api.services.database.USE_POSTGRES", True), \
             patch.object(orch, "get_agent", new_callable=AsyncMock, side_effect=Exception("boom")), \
             patch("api.services.orchestrator.sanitize_user_input", side_effect=lambda s, **kw: s):
            resp = await orch.step({}, [], "hello", "t", "PROF-001")

        assert "having trouble" in resp.text

    @pytest.mark.asyncio
    async def test_step_exception_updates_span_error(self, orch):
        lf = MagicMock()
        span = MagicMock()
        lf.span.return_value = span
        conn = MagicMock()
        conn.fetchval = AsyncMock(return_value="rental-123")
        db = _db_ctx(conn)

        with patch("api.services.orchestrator.get_langfuse", return_value=lf), \
             patch("api.services.database.db_context", return_value=db), \
             patch("api.services.database.USE_POSTGRES", True), \
             patch.object(orch, "get_agent", new_callable=AsyncMock, side_effect=Exception("boom")), \
             patch("api.services.orchestrator.sanitize_user_input", side_effect=lambda s, **kw: s):
            resp = await orch.step({}, [], "hello", "t", "PROF-001")

        assert "having trouble" in resp.text
        assert resp.needs_agent is True
        span.update.assert_called_with(level="ERROR", status_message="boom")


# ---------------------------------------------------------------------------
# create_langchain_agent / _build_langchain_tools
# ---------------------------------------------------------------------------


class TestLangchainAgentGraph:
    @pytest.mark.asyncio
    async def test_call_model_raises_without_model(self, mock_actions, _restore_model):
        orch_mod.model = None
        graph = create_langchain_agent(mock_actions, "t", "sys")
        from langchain_core.messages import HumanMessage

        with pytest.raises(RuntimeError):
            await graph.ainvoke({"messages": [HumanMessage(content="hi")]})

    @pytest.mark.asyncio
    async def test_graph_no_tools_branch(self, mock_actions, _restore_model):
        from langchain_core.messages import AIMessage, HumanMessage

        fake = AsyncFakeModel()
        fake.responses = [AIMessage(content="No tools here.")]
        orch_mod.model = fake

        with patch("api.services.orchestrator._build_langchain_tools", return_value=[]):
            graph = create_langchain_agent(mock_actions, "t", "sys")
            chunks = []
            async for chunk in graph.astream({"messages": [HumanMessage(content="hi")]}):
                chunks.append(chunk)

        assert graph is not None
        assert len(chunks) >= 1

    @pytest.mark.asyncio
    async def test_graph_tool_route(self, mock_actions, _restore_model):
        from langchain_core.messages import AIMessage, HumanMessage

        class FakeToolNode:
            calls = 0

            def __init__(self, tools):
                self.tools = tools

            async def __call__(self, state):
                type(self).calls += 1
                return {"messages": [AIMessage(content="tool executed")]}

        fake = AsyncFakeModel()
        fake.responses = [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "lookup_invoice",
                        "args": {"invoice_id": "INV-1"},
                        "id": "call_1",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(content="All done."),
        ]
        orch_mod.model = fake

        with patch("langgraph.prebuilt.ToolNode", FakeToolNode):
            graph = create_langchain_agent(mock_actions, "t", "sys")
            async for _chunk in graph.astream({"messages": [HumanMessage(content="check invoice")]}):
                pass

        assert FakeToolNode.calls == 1


class TestBuildLangchainTools:
    @pytest.mark.asyncio
    async def test_invoke_all_tool_closures(self, mock_actions):
        mock_actions.run = AsyncMock(return_value={"success": True, "data": {}})
        tools = _build_langchain_tools(mock_actions, "t1")

        assert len(tools) == 5

        await tools[0].coroutine(invoice_id="INV-1", actions_instance=mock_actions, tenant_id="t1")
        await tools[1].coroutine(order_id="ORD-1", actions_instance=mock_actions, tenant_id="t1")

        with patch("api.services.rag.rag_service") as rag:
            rag.query = AsyncMock(return_value=[{"content": "kb result"}])
            await tools[2].coroutine(query="refunds", tenant_id="t1")
            rag.query.assert_awaited_once_with("refunds", k=2)

        await tools[3].coroutine(reason="need help", actions_instance=mock_actions, tenant_id="t1")
        result = await tools[4].coroutine(reason="complex issue")
        assert result == "Escalated back to supervisor."

    @pytest.mark.asyncio
    async def test_tool_lookup_invoice_failure(self, mock_actions):
        mock_actions.run = AsyncMock(return_value={"success": False})
        tools = _build_langchain_tools(mock_actions, "t1")
        result = await tools[0].coroutine(invoice_id="INV-X", actions_instance=mock_actions, tenant_id="t1")
        assert "Could not find" in result

    @pytest.mark.asyncio
    async def test_tool_knowledge_base_no_results(self, mock_actions):
        tools = _build_langchain_tools(mock_actions, "t1")
        with patch("api.services.rag.rag_service") as rag:
            rag.query = AsyncMock(return_value=[])
            result = await tools[2].coroutine(query="nothing", tenant_id="t1")
        assert result == "No information found."
