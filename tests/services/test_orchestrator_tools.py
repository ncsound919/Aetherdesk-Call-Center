import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from apps.api.services import orchestrator


@pytest.fixture
def mock_actions():
    actions = MagicMock()
    actions.run = AsyncMock()
    return actions


class TestLookupInvoiceTool:
    @pytest.mark.asyncio
    async def test_invoice_found(self, mock_actions):
        mock_actions.run.return_value = {
            "success": True,
            "data": {"status": "paid", "amount": "$100.00", "due_date": "2024-12-31"}
        }

        result = await orchestrator.lookup_invoice(
            invoice_id="INV-123",
            tenant_id="tenant-1",
            actions_instance=mock_actions
        )

        assert "INV-123" in result
        assert "paid" in result
        assert "$100.00" in result
        mock_actions.run.assert_called_once_with(
            "lookup_invoice",
            {"invoice_id": "INV-123"},
            tenant_id="tenant-1"
        )

    @pytest.mark.asyncio
    async def test_invoice_not_found(self, mock_actions):
        mock_actions.run.return_value = {"success": False}

        result = await orchestrator.lookup_invoice(
            invoice_id="INV-999",
            tenant_id="tenant-1",
            actions_instance=mock_actions
        )

        assert "Could not find invoice INV-999" in result


class TestGetOrderStatusTool:
    @pytest.mark.asyncio
    async def test_order_found(self, mock_actions):
        mock_actions.run.return_value = {
            "success": True,
            "data": {"status": "shipped", "expected_delivery": "2024-07-15"}
        }

        result = await orchestrator.get_order_status(
            order_id="ORD-456",
            tenant_id="tenant-1",
            actions_instance=mock_actions
        )

        assert "ORD-456" in result
        assert "shipped" in result
        assert "2024-07-15" in result

    @pytest.mark.asyncio
    async def test_order_not_found(self, mock_actions):
        mock_actions.run.return_value = {"success": False}

        result = await orchestrator.get_order_status(
            order_id="ORD-999",
            tenant_id="tenant-1",
            actions_instance=mock_actions
        )

        assert "Could not find order ORD-999" in result


class TestSearchKnowledgeBaseTool:
    @pytest.mark.asyncio
    async def test_knowledge_results(self, mock_actions):
        with patch("apps.api.services.rag.rag_service") as mock_rag:
            mock_rag.query = AsyncMock(return_value=[
                {"content": "Refunds are processed within 5-7 business days."},
                {"content": "Contact support@company.com for expedited processing."}
            ])

            result = await orchestrator.search_knowledge_base(
                query="refund policy",
                tenant_id="tenant-1"
            )

            assert "Refunds are processed" in result
            assert "support@company.com" in result
            mock_rag.query.assert_called_once_with("refund policy", k=2)

    @pytest.mark.asyncio
    async def test_no_knowledge_results(self, mock_actions):
        with patch("apps.api.services.rag.rag_service") as mock_rag:
            mock_rag.query = AsyncMock(return_value=[])

            result = await orchestrator.search_knowledge_base(
                query="unknown topic",
                tenant_id="tenant-1"
            )

            assert result == "No information found."


class TestHandoffToHumanTool:
    @pytest.mark.asyncio
    async def test_handoff_initiated(self, mock_actions):
        mock_actions.run.return_value = {"success": True}

        result = await orchestrator.handoff_to_human(
            reason="Customer requested supervisor",
            tenant_id="tenant-1",
            actions_instance=mock_actions
        )

        assert result == "Handoff initiated."
        mock_actions.run.assert_called_once_with(
            "handoff",
            {"queue": "general", "reason": "Customer requested supervisor"},
            tenant_id="tenant-1"
        )


class TestEscalateToSupervisorTool:
    @pytest.mark.asyncio
    async def test_escalation_returns_message(self, mock_actions):
        result = await orchestrator.escalate_to_supervisor(
            reason="Complex billing issue requiring approval"
        )

        assert result == "Escalated back to supervisor."
