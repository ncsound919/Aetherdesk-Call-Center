import pytest
from pydantic import ValidationError
from api.services.agent import (
    LookupInvoiceInput,
    GetOrderStatusInput,
    SearchKnowledgeBaseInput,
    HandoffToHumanInput,
    ToolCallResponse,
    ToolCallAction,
)


class TestToolInputSchemas:
    def test_lookup_invoice_valid(self):
        m = LookupInvoiceInput(invoice_id="INV-123")
        assert m.invoice_id == "INV-123"

    def test_lookup_invoice_empty_rejected(self):
        with pytest.raises(ValidationError):
            LookupInvoiceInput(invoice_id="")

    def test_get_order_status_valid(self):
        m = GetOrderStatusInput(order_id="ORD-456")
        assert m.order_id == "ORD-456"

    def test_get_order_status_empty_rejected(self):
        with pytest.raises(ValidationError):
            GetOrderStatusInput(order_id="")

    def test_search_knowledge_base_valid(self):
        m = SearchKnowledgeBaseInput(query="refund policy")
        assert m.query == "refund policy"

    def test_search_knowledge_base_empty_rejected(self):
        with pytest.raises(ValidationError):
            SearchKnowledgeBaseInput(query="")

    def test_handoff_to_human_valid(self):
        m = HandoffToHumanInput(reason="customer escalation")
        assert m.reason == "customer escalation"

    def test_handoff_to_human_empty_rejected(self):
        with pytest.raises(ValidationError):
            HandoffToHumanInput(reason="")


class TestToolCallSchemas:
    def test_tool_call_response_valid(self):
        m = ToolCallResponse(response="Hello, how can I help?")
        assert m.response == "Hello, how can I help?"
        assert m.thought == ""

    def test_tool_call_response_with_thought(self):
        m = ToolCallResponse(thought="analyzing query", response="Let me check")
        assert m.thought == "analyzing query"
        assert m.response == "Let me check"

    def test_tool_call_response_empty_rejected(self):
        with pytest.raises(ValidationError):
            ToolCallResponse(response="")

    def test_tool_call_action_valid(self):
        m = ToolCallAction(tool="lookup_invoice", tool_input="INV-001")
        assert m.tool == "lookup_invoice"
        assert m.tool_input == "INV-001"

    def test_tool_call_action_defaults(self):
        m = ToolCallAction(tool="handoff_to_human")
        assert m.tool_input == ""
        assert m.thought == ""

    def test_tool_call_action_empty_tool_rejected(self):
        with pytest.raises(ValidationError):
            ToolCallAction(tool="")

    def test_tool_call_action_unknown_tool_valid(self):
        m = ToolCallAction(tool="custom_action")
        assert m.tool == "custom_action"


class TestHandoffConfirmationGate:
    @pytest.mark.asyncio
    async def test_handoff_confirmation_flow(self):
        from unittest.mock import MagicMock, AsyncMock, patch
        from api.services.agent import DynamicAgent

        mock_actions = MagicMock()
        mock_actions.run.return_value = {"success": True}
        agent = DynamicAgent(mock_actions)

        history = [{"from": "customer", "text": "I want to speak to a manager"}]

        mock_client = AsyncMock()
        mock_client.is_closed = False

        handoff_response = MagicMock()
        handoff_response.raise_for_status = MagicMock()
        handoff_response.json.return_value = {
            "message": {
                "content": '{"thought": "customer wants manager", "tool": "handoff_to_human", "tool_input": "customer requested manager"}'
            }
        }

        response_response = MagicMock()
        response_response.raise_for_status = MagicMock()
        response_response.json.return_value = {
            "message": {
                "content": '{"thought": "confirmation pending", "response": "Let me check with my supervisor."}'
            }
        }

        mock_client.post.side_effect = [handoff_response, response_response]

        with patch.object(agent, "_get_client", return_value=mock_client):
            from api.services.agent import AgentResponse
            result = await agent.step(history, "Connect me to a manager")
            assert isinstance(result, AgentResponse)
            assert result.action_taken == "confirmation_pending"
            assert "Let me check with my supervisor" in result.text

    @pytest.mark.asyncio
    async def test_handoff_second_call_confirms(self):
        from unittest.mock import MagicMock, AsyncMock, patch
        from api.services.agent import DynamicAgent

        mock_actions = MagicMock()
        mock_actions.run.return_value = {"success": True}
        agent = DynamicAgent(mock_actions)
        agent._pending_handoff = "customer requested manager"

        history = [{"from": "customer", "text": "Yes, transfer me"}]

        mock_client = AsyncMock()
        mock_client.is_closed = False

        handoff_response = MagicMock()
        handoff_response.raise_for_status = MagicMock()
        handoff_response.json.return_value = {
            "message": {
                "content": '{"thought": "confirmed", "tool": "handoff_to_human", "tool_input": "customer requested manager"}'
            }
        }

        response_response = MagicMock()
        response_response.raise_for_status = MagicMock()
        response_response.json.return_value = {
            "message": {
                "content": '{"thought": "confirmed", "response": "Transferring you now."}'
            }
        }

        mock_client.post.side_effect = [handoff_response, response_response]

        with patch.object(agent, "_get_client", return_value=mock_client):
            from api.services.agent import AgentResponse
            result = await agent.step(history, "Yes, transfer me")
            assert isinstance(result, AgentResponse)
            assert result.needs_agent is True
