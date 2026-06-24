import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestAgentServiceInit:
    def test_default_init(self):
        from apps.api.services.agent import AgentService

        svc = AgentService()
        assert svc.model == "llama3.2:1b"
        assert svc.host == "http://localhost:11434"

    def test_custom_init(self):
        from apps.api.services.agent import AgentService

        svc = AgentService(model="custom-model", host="http://custom:8080")
        assert svc.model == "custom-model"
        assert svc.host == "http://custom:8080"


class TestAgentServiceGetClient:
    def test_get_client_creates_new(self):
        from apps.api.services.agent import AgentService

        svc = AgentService()
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client
            client = svc._get_client()
            assert client == mock_client
            mock_client_cls.assert_called_once()

    def test_get_client_reuses_existing(self):
        from apps.api.services.agent import AgentService

        svc = AgentService()
        mock_client = MagicMock()
        mock_client.is_closed = False
        svc._client = mock_client

        with patch("httpx.AsyncClient") as mock_client_cls:
            client = svc._get_client()
            assert client == mock_client
            mock_client_cls.assert_not_called()

    def test_get_client_recreates_closed(self):
        from apps.api.services.agent import AgentService

        svc = AgentService()
        mock_client = MagicMock()
        mock_client.is_closed = True
        svc._client = mock_client

        with patch("httpx.AsyncClient") as mock_client_cls:
            new_mock = MagicMock()
            mock_client_cls.return_value = new_mock
            client = svc._get_client()
            assert client == new_mock

    @pytest.mark.asyncio
    async def test_close_client(self):
        from apps.api.services.agent import AgentService

        svc = AgentService()
        mock_client = AsyncMock()
        mock_client.is_closed = False
        svc._client = mock_client

        await svc.close()
        mock_client.aclose.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_no_client(self):
        from apps.api.services.agent import AgentService

        svc = AgentService()
        svc._client = None

        await svc.close()


class TestAgentServiceAnswer:
    @pytest.mark.asyncio
    async def test_answer_with_context(self):
        from apps.api.services.agent import AgentService

        svc = AgentService()
        svc._get_client = MagicMock()
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {"message": {"content": "The refund takes 5-7 business days."}}
        mock_response.status_code = 200
        mock_client.post = AsyncMock(return_value=mock_response)
        svc._get_client.return_value = mock_client

        result = await svc.answer("How long for refund?", [
            {"content": "Refunds process within 5-7 business days.", "metadata": {"source": "billing_faq"}}
        ])

        assert result.text == "The refund takes 5-7 business days."
        assert result.sources == ["billing_faq"]
        assert result.needs_agent is False

    @pytest.mark.asyncio
    async def test_answer_no_context(self):
        from apps.api.services.agent import AgentService

        svc = AgentService()

        result = await svc.answer("How long for refund?", [])

        assert "don't have enough information" in result.text
        assert result.needs_agent is True
        assert result.sources == []

    @pytest.mark.asyncio
    async def test_answer_with_history(self):
        from apps.api.services.agent import AgentService

        svc = AgentService()
        svc._get_client = MagicMock()
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {"message": {"content": "Yes, I can help with that."}}
        mock_response.status_code = 200
        mock_client.post = AsyncMock(return_value=mock_response)
        svc._get_client.return_value = mock_client

        result = await svc.answer("What about discounts?", [
            {"content": "Discounts available for bulk orders.", "metadata": {"source": "pricing"}}
        ], history=[
            {"customer": "Hi", "agent": "Hello, how can I help?"}
        ])

        assert result.text == "Yes, I can help with that."

    @pytest.mark.asyncio
    async def test_answer_detects_need_agent_keyword(self):
        from apps.api.services.agent import AgentService

        svc = AgentService()
        svc._get_client = MagicMock()
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {"message": {"content": "I don't know the answer to that."}}
        mock_response.status_code = 200
        mock_client.post = AsyncMock(return_value=mock_response)
        svc._get_client.return_value = mock_client

        result = await svc.answer("Complex question?", [
            {"content": "Some info.", "metadata": {"source": "faq"}}
        ])

        assert result.needs_agent is True

    @pytest.mark.asyncio
    async def test_answer_http_error(self):
        from apps.api.services.agent import AgentService

        svc = AgentService()
        svc._get_client = MagicMock()
        mock_client = MagicMock()
        mock_client.post = AsyncMock(side_effect=Exception("HTTP 500"))
        svc._get_client.return_value = mock_client

        result = await svc.answer("Question?", [
            {"content": "Info.", "metadata": {"source": "faq"}}
        ])

        assert "having trouble processing" in result.text
        assert result.needs_agent is True

    @pytest.mark.asyncio
    async def test_answer_no_context_results_sources_empty(self):
        from apps.api.services.agent import AgentService

        svc = AgentService()

        result = await svc.answer("Question?", [])

        assert result.sources == []


class TestAgentServiceAnswerWithRag:
    @pytest.mark.asyncio
    async def test_answer_with_rag_enabled(self):
        from apps.api.services.agent import AgentService

        svc = AgentService()
        mock_context = [{"content": "RAG result", "metadata": {"source": "kb"}}]

        with patch("apps.api.services.rag.rag_service") as mock_rag, \
             patch.object(svc, "answer", new_callable=AsyncMock) as mock_answer:
            mock_rag.query = AsyncMock(return_value=mock_context)
            mock_answer.return_value = MagicMock(text="RAG answer", sources=["kb"], needs_agent=False)

            result = await svc.answer_with_rag("Question?")

            mock_rag.query.assert_called_once_with("Question?", k=3)
            mock_answer.assert_called_once_with("Question?", mock_context, None)
            assert result.text == "RAG answer"

    @pytest.mark.asyncio
    async def test_answer_with_rag_disabled(self):
        from apps.api.services.agent import AgentService

        svc = AgentService()

        with patch.object(svc, "answer", new_callable=AsyncMock) as mock_answer:
            mock_answer.return_value = MagicMock(text="No RAG", sources=[], needs_agent=False)

            result = await svc.answer_with_rag("Question?", use_rag=False)

            mock_answer.assert_called_once_with("Question?", [], None)
            assert result.text == "No RAG"

    @pytest.mark.asyncio
    async def test_answer_with_rag_and_history(self):
        from apps.api.services.agent import AgentService

        svc = AgentService()
        history = [{"customer": "Hi", "agent": "Hello"}]

        with patch("apps.api.services.rag.rag_service") as mock_rag, \
             patch.object(svc, "answer", new_callable=AsyncMock) as mock_answer:
            mock_rag.query = AsyncMock(return_value=[])
            mock_answer.return_value = MagicMock(text="With history", sources=[], needs_agent=False)

            result = await svc.answer_with_rag("Question?", history=history)

            mock_answer.assert_called_once_with("Question?", [], history)
            assert result.text == "With history"


class TestDynamicAgent:
    @pytest.mark.asyncio
    async def test_step_returns_response(self):
        from apps.api.services.agent import DynamicAgent

        mock_actions = MagicMock()
        agent = DynamicAgent(mock_actions)

        agent._get_client = MagicMock()
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "message": {"content": json.dumps({"thought": "answering", "response": "Hello, how can I help?"})}
        }
        mock_response.status_code = 200
        mock_client.post = AsyncMock(return_value=mock_response)
        agent._get_client.return_value = mock_client

        result = await agent.step([], "Hi there")

        assert result.text == "Hello, how can I help?"
        assert result.needs_agent is False

    @pytest.mark.asyncio
    async def test_step_tool_call_then_response(self):
        from apps.api.services.agent import DynamicAgent

        mock_actions = MagicMock()
        agent = DynamicAgent(mock_actions)

        agent._get_client = MagicMock()
        mock_client = MagicMock()

        tool_response = MagicMock()
        tool_response.json.return_value = {
            "message": {"content": json.dumps({"thought": "looking up", "tool": "lookup_invoice", "tool_input": "INV-001"})}
        }
        tool_response.status_code = 200

        final_response = MagicMock()
        final_response.json.return_value = {
            "message": {"content": json.dumps({"thought": "done", "response": "Invoice INV-001 is paid."})}
        }
        final_response.status_code = 200

        mock_client.post = AsyncMock(side_effect=[tool_response, final_response])
        agent._get_client.return_value = mock_client

        with patch.object(agent, "_execute_tool", new_callable=AsyncMock, return_value="Invoice found"):
            result = await agent.step([], "Check invoice INV-001")

        assert result.text == "Invoice INV-001 is paid."
        assert mock_client.post.call_count == 2

    @pytest.mark.asyncio
    async def test_step_handoff_sets_needs_agent(self):
        from apps.api.services.agent import DynamicAgent

        mock_actions = MagicMock()
        agent = DynamicAgent(mock_actions)

        agent._get_client = MagicMock()
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "message": {"content": json.dumps({"thought": "handing off", "tool": "handoff_to_human", "tool_input": "customer upset"})}
        }
        mock_response.status_code = 200
        mock_client.post = AsyncMock(return_value=mock_response)
        agent._get_client.return_value = mock_client

        with patch.object(agent, "_execute_tool", new_callable=AsyncMock, return_value="Handoff initiated."):
            result = await agent.step([], "Speak to a human")

        assert result.needs_agent is True

    @pytest.mark.asyncio
    async def test_step_max_steps_exceeded(self):
        from apps.api.services.agent import DynamicAgent

        mock_actions = MagicMock()
        agent = DynamicAgent(mock_actions)
        agent._max_steps = 1

        agent._get_client = MagicMock()
        mock_client = MagicMock()
        tool_response = MagicMock()
        tool_response.json.return_value = {
            "message": {"content": json.dumps({"thought": "using tool", "tool": "search_knowledge_base", "tool_input": "policy"})}
        }
        tool_response.status_code = 200
        mock_client.post = AsyncMock(return_value=tool_response)
        agent._get_client.return_value = mock_client

        with patch.object(agent, "_execute_tool", new_callable=AsyncMock, return_value="Policy info"):
            result = await agent.step([], "Check policy")

        assert "taking too long" in result.text
        assert result.needs_agent is True

    @pytest.mark.asyncio
    async def test_step_json_decode_error_retry(self):
        from apps.api.services.agent import DynamicAgent

        mock_actions = MagicMock()
        agent = DynamicAgent(mock_actions)

        agent._get_client = MagicMock()
        mock_client = MagicMock()
        bad_response = MagicMock()
        bad_response.json.return_value = {"message": {"content": "not valid json"}}
        bad_response.status_code = 200
        good_response = MagicMock()
        good_response.json.return_value = {
            "message": {"content": json.dumps({"thought": "fixed", "response": "Here you go."})}
        }
        good_response.status_code = 200
        mock_client.post = AsyncMock(side_effect=[bad_response, good_response])
        agent._get_client.return_value = mock_client

        result = await agent.step([], "Hello")

        assert result.text == "Here you go."
        assert mock_client.post.call_count == 2

    @pytest.mark.asyncio
    async def test_step_json_decode_error_fails_after_retry(self):
        from apps.api.services.agent import DynamicAgent

        mock_actions = MagicMock()
        agent = DynamicAgent(mock_actions)

        agent._get_client = MagicMock()
        mock_client = MagicMock()
        bad_response = MagicMock()
        bad_response.json.return_value = {"message": {"content": "not valid json and still bad on retry"}}
        bad_response.status_code = 200
        mock_client.post = AsyncMock(return_value=bad_response)
        agent._get_client.return_value = mock_client

        result = await agent.step([], "Hello")

        assert "error processing" in result.text
        assert result.needs_agent is True

    @pytest.mark.asyncio
    async def test_step_http_error(self):
        from apps.api.services.agent import DynamicAgent

        mock_actions = MagicMock()
        agent = DynamicAgent(mock_actions)

        agent._get_client = MagicMock()
        mock_client = MagicMock()
        mock_client.post = AsyncMock(side_effect=Exception("Connection refused"))
        agent._get_client.return_value = mock_client

        result = await agent.step([], "Hello")

        assert "having trouble processing" in result.text
        assert result.needs_agent is True

    @pytest.mark.asyncio
    async def test_step_uses_history(self):
        from apps.api.services.agent import DynamicAgent

        mock_actions = MagicMock()
        agent = DynamicAgent(mock_actions)

        agent._get_client = MagicMock()
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "message": {"content": json.dumps({"thought": "responding", "response": "I remember our chat."})}
        }
        mock_response.status_code = 200
        mock_client.post = AsyncMock(return_value=mock_response)
        agent._get_client.return_value = mock_client

        result = await agent.step([
            {"from": "customer", "text": "My order is late"},
            {"from": "agent", "text": "Let me check"}
        ], "Where is it?")

        assert result.text == "I remember our chat."


class TestDynamicAgentExecuteTool:
    @pytest.mark.asyncio
    async def test_execute_tool_lookup_invoice(self):
        from apps.api.services.agent import DynamicAgent

        mock_actions = MagicMock()
        mock_actions.run.return_value = {"success": True, "data": {"status": "paid"}}
        agent = DynamicAgent(mock_actions)

        result = await agent._execute_tool("lookup_invoice", "INV-001")
        assert "Invoice INV-001 found" in result

    @pytest.mark.asyncio
    async def test_execute_tool_lookup_invoice_not_found(self):
        from apps.api.services.agent import DynamicAgent

        mock_actions = MagicMock()
        mock_actions.run.return_value = {"success": False}
        agent = DynamicAgent(mock_actions)

        result = await agent._execute_tool("lookup_invoice", "INV-999")
        assert "Could not find" in result

    @pytest.mark.asyncio
    async def test_execute_tool_get_order_status(self):
        from apps.api.services.agent import DynamicAgent

        mock_actions = MagicMock()
        agent = DynamicAgent(mock_actions)

        result = await agent._execute_tool("get_order_status", "ORD-001")
        assert "processing" in result

    @pytest.mark.asyncio
    async def test_execute_tool_search_kb(self):
        from apps.api.services.agent import DynamicAgent

        mock_actions = MagicMock()
        agent = DynamicAgent(mock_actions)

        with patch("apps.api.services.rag.rag_service") as mock_rag:
            mock_rag.query = AsyncMock(return_value=[{"content": "Return policy is 30 days."}])
            result = await agent._execute_tool("search_knowledge_base", "return policy")

        assert "Return policy" in result

    @pytest.mark.asyncio
    async def test_execute_tool_search_kb_no_results(self):
        from apps.api.services.agent import DynamicAgent

        mock_actions = MagicMock()
        agent = DynamicAgent(mock_actions)

        with patch("apps.api.services.rag.rag_service") as mock_rag:
            mock_rag.query = AsyncMock(return_value=[])
            result = await agent._execute_tool("search_knowledge_base", "unknown")

        assert "No information found" in result

    @pytest.mark.asyncio
    async def test_execute_tool_handoff(self):
        from apps.api.services.agent import DynamicAgent

        mock_actions = MagicMock()
        agent = DynamicAgent(mock_actions)

        result = await agent._execute_tool("handoff_to_human", "customer escalation")
        assert "Handoff initiated" in result

    @pytest.mark.asyncio
    async def test_execute_tool_unknown(self):
        from apps.api.services.agent import DynamicAgent

        mock_actions = MagicMock()
        agent = DynamicAgent(mock_actions)

        result = await agent._execute_tool("nonexistent_tool", "")
        assert "Unknown tool" in result
