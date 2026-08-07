"""Unit tests for api.services.agent_assist."""

import random
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import api.services.agent_assist as agent_assist_module
from api.services.agent_assist import (
    SCRIPT_SNIPPETS,
    AgentAssistService,
    _KB_STORE,
    _NEXT_ID,
)

service = AgentAssistService()


@pytest.fixture(autouse=True)
def _reset_global_state():
    saved_store = dict(_KB_STORE)
    saved_next = _NEXT_ID
    _KB_STORE.clear()
    agent_assist_module._NEXT_ID = 1
    service._call_stats.clear()
    yield
    _KB_STORE.clear()
    _KB_STORE.update(saved_store)
    agent_assist_module._NEXT_ID = saved_next


class TestGetSuggestions:
    async def _suggest(self, transcript=None, context=None, classifier_intent=None, valid=True):
        with (
            patch(
                "api.services.agent_assist.validator.validate_intent_result",
                return_value={"valid": valid},
            ),
            patch(
                "api.services.agent_assist.search_knowledge_snippets_db",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "api.services.intent_classifier.classifier", new=MagicMock()
            ) as mock_classifier,
        ):
            if classifier_intent is not None:
                mock_classifier.classify = AsyncMock(
                    return_value=MagicMock(intent=classifier_intent, confidence=0.95)
                )
            return await service.get_suggestions(
                "call-1", transcript, context or {"tenant_id": "tenant-1"}
            )

    @pytest.mark.asyncio
    async def test_no_transcript_uses_default_intent(self):
        suggestions = await self._suggest(transcript=None)

        actions = [s for s in suggestions if s["type"] == "action"]
        assert len(actions) == 6
        assert all(a["confidence"] == 0.5 for a in actions)
        intent = next(s for s in suggestions if s["type"] == "detected_intent")
        assert intent["intent"] == "generalInquiry"
        script = next(s for s in suggestions if s["type"] == "script")
        assert script["key"] == "greeting"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "intent,expected_preferred,expected_script",
        [
            ("generalInquiry", None, "greeting"),
            ("pharmacy_refill", None, None),
            ("pharmacy_refill_doc", None, None),
            ("billing_invoice", "transfer_to_billing", "apology"),
            ("billing_refund", "transfer_to_billing", "apology"),
            ("tech_support_password", "transfer_to_support", "apology"),
            ("order_status", "transfer_to_support", "greeting"),
            ("agent_handoff", "transfer_to_support", "transfer"),
        ],
    )
    async def test_intent_detection(self, intent, expected_preferred, expected_script):
        suggestions = await self._suggest(
            transcript="some utterance", classifier_intent=intent
        )

        detected = next(s for s in suggestions if s["type"] == "detected_intent")
        assert detected["intent"] == intent

        actions = [s for s in suggestions if s["type"] == "action"]
        for action in actions:
            if action["action"] == expected_preferred:
                assert action["confidence"] == 0.9
            elif expected_preferred and "transfer" in action["action"]:
                assert action["confidence"] == 0.3
            else:
                assert action["confidence"] == 0.5

        scripts = [s for s in suggestions if s["type"] == "script"]
        if expected_script:
            assert scripts[0]["key"] == expected_script
            assert scripts[0]["text"] == SCRIPT_SNIPPETS[expected_script]
        else:
            assert scripts == []

    @pytest.mark.asyncio
    async def test_classifier_raises_falls_back_to_default(self):
        with (
            patch(
                "api.services.agent_assist.validator.validate_intent_result",
                return_value={"valid": True},
            ),
            patch(
                "api.services.agent_assist.search_knowledge_snippets_db",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "api.services.intent_classifier.classifier",
                new=MagicMock(),
            ) as mock_classifier,
            patch("api.services.agent_assist.logger.warning") as mock_warn,
        ):
            mock_classifier.classify = AsyncMock(side_effect=RuntimeError("nope"))
            suggestions = await service.get_suggestions(
                "call-1", "hi there", {"tenant_id": "tenant-1"}
            )

        mock_warn.assert_called_once()
        detected = next(s for s in suggestions if s["type"] == "detected_intent")
        assert detected["intent"] == "generalInquiry"

    @pytest.mark.asyncio
    async def test_invalid_intent_result_keeps_default(self):
        suggestions = await self._suggest(
            transcript="hello", classifier_intent="billing_invoice", valid=False
        )
        detected = next(s for s in suggestions if s["type"] == "detected_intent")
        assert detected["intent"] == "generalInquiry"

    @pytest.mark.asyncio
    async def test_knowledge_snippets_appended(self):
        snippets = [
            {"id": "kb1", "title": "Refund policy", "content": "Details here"}
        ]
        with (
            patch(
                "api.services.agent_assist.validator.validate_intent_result",
                return_value={"valid": False},
            ),
            patch(
                "api.services.agent_assist.search_knowledge_snippets_db",
                new=AsyncMock(return_value=snippets),
            ),
        ):
            suggestions = await service.get_suggestions(
                "call-1", "refund?", {"tenant_id": "tenant-1"}
            )

        kb = [s for s in suggestions if s["type"] == "knowledge_article"]
        assert len(kb) == 1
        assert kb[0]["title"] == "Refund policy"
        assert kb[0]["content"] == "Details here"
        assert kb[0]["id"] == "kb1"
        assert kb[0]["confidence"] == 0.85

    @pytest.mark.asyncio
    async def test_kb_search_raises_is_caught(self):
        with (
            patch(
                "api.services.agent_assist.validator.validate_intent_result",
                return_value={"valid": True},
            ),
            patch.object(
                agent_assist_module.AgentAssistService,
                "get_knowledge_snippets",
                new=AsyncMock(side_effect=RuntimeError("db down")),
            ),
            patch(
                "api.services.intent_classifier.classifier",
                new=MagicMock(),
            ) as mock_classifier,
            patch("api.services.agent_assist.logger.warning") as mock_warn,
        ):
            mock_classifier.classify = AsyncMock(
                return_value=MagicMock(intent="generalInquiry", confidence=0.9)
            )
            suggestions = await service.get_suggestions(
                "call-1", "refund?", {"tenant_id": "tenant-1"}
            )

        mock_warn.assert_called_once()
        assert all(s["type"] != "knowledge_article" for s in suggestions)


class TestPickScript:
    @pytest.mark.parametrize(
        "intent,expected",
        [
            ("billing_invoice", "apology"),
            ("billing_refund", "apology"),
            ("tech_support_password", "apology"),
            ("generalInquiry", "greeting"),
            ("order_status", "greeting"),
            ("agent_handoff", "transfer"),
            ("pharmacy_refill", None),
        ],
    )
    def test_pick_script(self, intent, expected):
        assert service._pick_script(intent) == expected


class TestKnowledgeSnippets:
    @pytest.mark.asyncio
    async def test_db_returns_results(self):
        results = [{"id": "kb1"}]
        with patch(
            "api.services.agent_assist.search_knowledge_snippets_db",
            new=AsyncMock(return_value=results),
        ) as mock_search:
            out = await service.get_knowledge_snippets("tenant-1", "query", limit=5)

        assert out == results
        mock_search.assert_called_once_with("tenant-1", "query", 5)

    @pytest.mark.asyncio
    async def test_db_empty_falls_back_to_memory(self):
        _KB_STORE["kb1"] = {
            "id": "kb1",
            "tenant_id": "tenant-1",
            "title": "Order Status",
            "content": "How to track orders",
        }
        _KB_STORE["kb2"] = {
            "id": "kb2",
            "tenant_id": "other",
            "title": "Order Status",
            "content": "nope",
        }
        with patch(
            "api.services.agent_assist.search_knowledge_snippets_db",
            new=AsyncMock(return_value=[]),
        ):
            out = await service.get_knowledge_snippets("tenant-1", "order", limit=5)

        assert [s["id"] for s in out] == ["kb1"]

    @pytest.mark.asyncio
    async def test_db_raises_falls_back_to_memory(self):
        _KB_STORE["kb1"] = {
            "id": "kb1",
            "tenant_id": "tenant-1",
            "title": "Refunds",
            "content": "Refund process",
        }
        with patch(
            "api.services.agent_assist.search_knowledge_snippets_db",
            new=AsyncMock(side_effect=RuntimeError("db down")),
        ):
            out = await service.get_knowledge_snippets("tenant-1", "refund")

        assert [s["id"] for s in out] == ["kb1"]

    @pytest.mark.asyncio
    async def test_memory_match_by_content_and_limit(self):
        for i in range(5):
            _KB_STORE[str(i)] = {
                "id": str(i),
                "tenant_id": "tenant-1",
                "title": f"T{i}",
                "content": "shared keyword",
            }
        with patch(
            "api.services.agent_assist.search_knowledge_snippets_db",
            new=AsyncMock(return_value=[]),
        ):
            out = await service.get_knowledge_snippets("tenant-1", "shared", limit=3)

        assert len(out) == 3

    @pytest.mark.asyncio
    async def test_create_db_success(self):
        result = {"id": "kb1"}
        with patch(
            "api.services.agent_assist.create_knowledge_snippet_db",
            new=AsyncMock(return_value=result),
        ) as mock_create:
            out = await service.create_knowledge_snippet(
                "tenant-1", "Title", "Body", tags=["a"], category="billing"
            )

        assert out == result
        mock_create.assert_called_once_with("tenant-1", "Title", "Body", ["a"], "billing")

    @pytest.mark.asyncio
    async def test_create_db_none_uses_memory(self):
        with patch(
            "api.services.agent_assist.create_knowledge_snippet_db",
            new=AsyncMock(return_value=None),
        ):
            out = await service.create_knowledge_snippet("tenant-1", "Title", "Body")

        assert out["id"] == "1"
        assert out["tenant_id"] == "tenant-1"
        assert out["tags"] == []
        assert out["category"] == "general"
        assert _KB_STORE["1"] == out

    @pytest.mark.asyncio
    async def test_create_db_raises_uses_memory(self):
        with patch(
            "api.services.agent_assist.create_knowledge_snippet_db",
            new=AsyncMock(side_effect=RuntimeError("db down")),
        ):
            out = await service.create_knowledge_snippet(
                "tenant-1", "Title", "Body", tags=None, category="general"
            )

        assert out["tags"] == []
        assert _KB_STORE[out["id"]] == out

    @pytest.mark.asyncio
    async def test_delete_db_success(self):
        with patch(
            "api.services.agent_assist.delete_knowledge_snippet_db",
            new=AsyncMock(return_value=True),
        ) as mock_delete:
            assert await service.delete_knowledge_snippet("tenant-1", "kb1") is True
        mock_delete.assert_called_once_with("tenant-1", "kb1")

    @pytest.mark.asyncio
    async def test_delete_db_none_uses_memory(self):
        _KB_STORE["kb1"] = {"id": "kb1", "tenant_id": "tenant-1"}
        with patch(
            "api.services.agent_assist.delete_knowledge_snippet_db",
            new=AsyncMock(return_value=False),
        ):
            assert await service.delete_knowledge_snippet("tenant-1", "kb1") is True
        assert "kb1" not in _KB_STORE

    @pytest.mark.asyncio
    async def test_delete_db_raises_uses_memory(self):
        _KB_STORE["kb1"] = {"id": "kb1", "tenant_id": "tenant-1"}
        with patch(
            "api.services.agent_assist.delete_knowledge_snippet_db",
            new=AsyncMock(side_effect=RuntimeError("db down")),
        ):
            assert await service.delete_knowledge_snippet("tenant-1", "kb1") is True
        assert "kb1" not in _KB_STORE

    @pytest.mark.asyncio
    async def test_delete_tenant_mismatch_returns_false(self):
        _KB_STORE["kb1"] = {"id": "kb1", "tenant_id": "other"}
        with patch(
            "api.services.agent_assist.delete_knowledge_snippet_db",
            new=AsyncMock(return_value=False),
        ):
            assert await service.delete_knowledge_snippet("tenant-1", "kb1") is False
        assert "kb1" in _KB_STORE

    @pytest.mark.asyncio
    async def test_delete_missing_returns_false(self):
        with patch(
            "api.services.agent_assist.delete_knowledge_snippet_db",
            new=AsyncMock(return_value=False),
        ):
            assert await service.delete_knowledge_snippet("tenant-1", "ghost") is False


class TestNextBestAction:
    @pytest.mark.asyncio
    async def test_default(self):
        result = await service.get_next_best_action({"current_intent": "generalInquiry"})
        assert result["action"] == "continue_monitoring"

    @pytest.mark.asyncio
    async def test_negative_long_duration(self):
        result = await service.get_next_best_action(
            {"current_intent": "x", "sentiment": "negative", "call_duration_seconds": 500}
        )
        assert result["action"] == "escalate_to_supervisor"
        assert result["confidence"] == 0.85

    @pytest.mark.asyncio
    async def test_billing_intent(self):
        for intent in ("billing_refund", "billing_invoice"):
            result = await service.get_next_best_action({"current_intent": intent})
            assert result["action"] == "offer_discount"
            assert result["confidence"] == 0.7

    @pytest.mark.asyncio
    async def test_negative_short_duration(self):
        result = await service.get_next_best_action(
            {"current_intent": "x", "sentiment": "negative", "call_duration_seconds": 10}
        )
        assert result["action"] == "send_email_summary"
        assert result["confidence"] == 0.6

    @pytest.mark.asyncio
    async def test_low_performance_negative_overrides(self):
        result = await service.get_next_best_action(
            {"current_intent": "billing_invoice", "sentiment": "negative"},
            agent_performance={"avg_score": 0.4},
        )
        assert result["action"] == "escalate_to_supervisor"
        assert result["confidence"] == 0.9

    @pytest.mark.asyncio
    async def test_high_performance_no_override(self):
        result = await service.get_next_best_action(
            {"current_intent": "billing_invoice", "sentiment": "negative"},
            agent_performance={"avg_score": 0.8},
        )
        assert result["action"] == "offer_discount"

    @pytest.mark.asyncio
    async def test_agent_performance_negative_but_no_negative_sentiment(self):
        result = await service.get_next_best_action(
            {"current_intent": "billing_invoice", "sentiment": "positive"},
            agent_performance={"avg_score": 0.3},
        )
        assert result["action"] == "offer_discount"


class TestRealtimeStats:
    @pytest.mark.asyncio
    async def test_new_call_initialized(self):
        with patch.object(random, "choice", return_value="neutral"), patch.object(
            random, "random", return_value=0.9
        ):
            stats = await service.get_realtime_stats("call-1")

        assert stats["call_id"] == "call-1"
        assert stats["duration_seconds"] == 15
        assert stats["sentiment_trend"] == ["neutral", "neutral"]

    @pytest.mark.asyncio
    async def test_existing_call_increments_duration(self):
        with patch.object(random, "choice", return_value="neutral"), patch.object(
            random, "random", return_value=0.9
        ):
            await service.get_realtime_stats("call-2")
            await service.get_realtime_stats("call-2")
            stats = await service.get_realtime_stats("call-2")

        assert stats["duration_seconds"] == 45

    @pytest.mark.asyncio
    async def test_sentiment_shift(self):
        with patch.object(random, "choice", return_value="negative"), patch.object(
            random, "random", return_value=0.1
        ):
            stats = await service.get_realtime_stats("call-3")

        assert stats["sentiment"] == "negative"

    @pytest.mark.asyncio
    async def test_sentiment_trend_capped(self):
        service._call_stats["call-4"] = {
            "call_id": "call-4",
            "duration_seconds": 0,
            "sentiment": "neutral",
            "sentiment_trend": ["neutral"] * 25,
            "keywords": [],
            "talk_ratio": 0.5,
            "interruptions": 0,
        }
        with patch.object(random, "choice", return_value="neutral"), patch.object(
            random, "random", return_value=0.9
        ):
            stats = await service.get_realtime_stats("call-4")

        assert len(stats["sentiment_trend"]) <= 20
