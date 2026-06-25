import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestTwoQuestionRouter:
    def test_route_hit(self):
        from api.services.router import TwoQuestionRouter

        table = {
            "refill:id_lookup": {
                "protocol_id": "refill_protocol",
                "queue": "rx",
                "fields": ["rx_number"]
            }
        }
        router = TwoQuestionRouter(table)
        result = router.route("refill", "id_lookup")

        assert result["protocol_id"] == "refill_protocol"
        assert result["queue"] == "rx"
        assert result["fields"] == ["rx_number"]

    def test_route_miss_returns_fallback(self):
        from api.services.router import TwoQuestionRouter

        router = TwoQuestionRouter({})
        result = router.route("unknown", "missing")

        assert result["protocol_id"] == "fallback_handoff_v1"
        assert result["queue"] == "general"
        assert result["fields"] == []

    def test_route_empty_table(self):
        from api.services.router import TwoQuestionRouter

        router = TwoQuestionRouter({})
        result = router.route("refill", "id_lookup")

        assert result["protocol_id"] == "fallback_handoff_v1"


class TestLLMIntentRouter:
    def test_route_known_intent(self):
        from api.services.router import LLMIntentRouter

        router = LLMIntentRouter()
        result = router.route("pharmacy_refill", {"rx_number": "12345"})

        assert result["protocol_id"] == "pharmacy_refill_v1"
        assert result["queue"] == "rx"
        assert result["fields"] == ["rx_number"]
        assert result["entities"] == {"rx_number": "12345"}
        assert result["intent"] == "pharmacy_refill"

    def test_route_unknown_intent_fallback(self):
        from api.services.router import LLMIntentRouter

        router = LLMIntentRouter()
        result = router.route("unknown_intent", {})

        assert result["protocol_id"] == "fallback_handoff_v1"
        assert result["queue"] == "general"
        assert result["fields"] == []

    def test_route_billing_invoice(self):
        from api.services.router import LLMIntentRouter

        router = LLMIntentRouter()
        result = router.route("billing_invoice", {"invoice_id": "INV-001"})

        assert result["protocol_id"] == "billing_invoice_v1"
        assert result["queue"] == "billing"

    def test_route_tech_support_password(self):
        from api.services.router import LLMIntentRouter

        router = LLMIntentRouter()
        result = router.route("tech_support_password", {"customer_id": "CUST-001"})

        assert result["protocol_id"] == "reset_v1"
        assert result["queue"] == "support"

    @pytest.mark.asyncio
    async def test_route_from_transcript(self):
        from api.services.router import LLMIntentRouter

        router = LLMIntentRouter()
        mock_classifier = MagicMock()
        mock_result = MagicMock()
        mock_result.intent = "order_status"
        mock_result.entities = {"order_id": "ORD-001"}
        mock_classifier.classify_with_fallback = AsyncMock(return_value=mock_result)

        with patch.object(router, "_get_classifier", return_value=mock_classifier):
            result = await router.route_from_transcript("Where is my order?")

        assert result["protocol_id"] == "order_status_v1"
        assert result["queue"] == "ops"
        assert result["entities"] == {"order_id": "ORD-001"}
        assert result["intent"] == "order_status"
        mock_classifier.classify_with_fallback.assert_called_once_with("Where is my order?")

    def test_get_classifier_returns_global_classifier(self):
        from api.services.router import LLMIntentRouter
        from api.services.intent_classifier import classifier

        router = LLMIntentRouter()
        cls = router._get_classifier()
        assert cls is classifier


class TestGetRouter:
    @patch.dict(os.environ, {}, clear=True)
    def test_default_returns_two_question_router(self):
        from api.services.router import get_router
        from api.services.router import TwoQuestionRouter

        router = get_router()
        assert isinstance(router, TwoQuestionRouter)

    @patch.dict(os.environ, {"USE_LLM_ROUTING": "true"}, clear=True)
    def test_llm_routing_enabled(self):
        from api.services.router import get_router
        from api.services.router import LLMIntentRouter

        router = get_router()
        assert isinstance(router, LLMIntentRouter)


class TestRouterModuleConstants:
    def test_intent_to_protocol_mapping(self):
        from api.services.router import INTENT_TO_PROTOCOL

        assert "pharmacy_refill" in INTENT_TO_PROTOCOL
        assert "pharmacy_refill_doc" in INTENT_TO_PROTOCOL
        assert "billing_invoice" in INTENT_TO_PROTOCOL
        assert "billing_refund" in INTENT_TO_PROTOCOL
        assert "order_status" in INTENT_TO_PROTOCOL
        assert "tech_support_password" in INTENT_TO_PROTOCOL
        assert "generalInquiry" in INTENT_TO_PROTOCOL
        assert "agent_handoff" in INTENT_TO_PROTOCOL
        assert "retry" in INTENT_TO_PROTOCOL

    def test_two_question_router_instantiated(self):
        from api.services.router import two_question_router, route_table
        assert two_question_router is not None

    def test_llm_router_instantiated(self):
        from api.services.router import llm_router
        assert llm_router is not None

    def test_module_router_instantiation(self):
        from api.services.router import router
        assert router is not None
