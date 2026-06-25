import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from celery.exceptions import Retry
from api.services import celery_tasks


class TestProcessRagQueryTask:
    def test_apply_returns_result(self, monkeypatch):
        mock_rag = MagicMock()
        mock_rag.query = AsyncMock(return_value=[{"content": "RAG result"}])
        monkeypatch.setattr("api.services.rag.rag_service", mock_rag)

        result = celery_tasks.process_rag_query.apply(args=("test query", 3, "tenant-1"))

        assert result.successful()
        assert result.result == [{"content": "RAG result"}]

    def test_retry_on_failure(self, monkeypatch):
        mock_rag = MagicMock()
        mock_rag.query = AsyncMock(side_effect=Exception("RAG down"))
        monkeypatch.setattr("api.services.rag.rag_service", mock_rag)

        with pytest.raises(Retry):
            celery_tasks.process_rag_query.apply(args=("test query", 3, "tenant-1"), throw=True)


class TestProcessIntentClassifyTask:
    def test_apply_returns_classification(self, monkeypatch):
        mock_classifier = MagicMock()
        mock_classifier.classify = AsyncMock(return_value={"intent": "billing", "confidence": 0.95})
        monkeypatch.setattr("api.services.intent_classifier.classifier", mock_classifier)

        result = celery_tasks.process_intent_classify.apply(args=("Where is my refund?", "tenant-1"))

        assert result.successful()
        assert result.result["intent"] == "billing"

    def test_retry_on_failure(self, monkeypatch):
        mock_classifier = MagicMock()
        mock_classifier.classify = AsyncMock(side_effect=Exception("Classifier down"))
        monkeypatch.setattr("api.services.intent_classifier.classifier", mock_classifier)

        with pytest.raises(Retry):
            celery_tasks.process_intent_classify.apply(args=("query", "tenant-1"), throw=True)


class TestProcessAgentResponseTask:
    def test_apply_returns_answer(self, monkeypatch):
        mock_agent = MagicMock()
        mock_agent.answer = AsyncMock(return_value="Your refund is being processed.")
        monkeypatch.setattr("api.services.agent.agent_service", mock_agent)

        result = celery_tasks.process_agent_response.apply(args=(
            "When will I get my refund?",
            [{"type": "doc", "content": "policy..."}],
            [],
            "tenant-1"
        ))

        assert result.successful()
        assert "refund" in result.result.lower()

    def test_retry_on_failure(self, monkeypatch):
        mock_agent = MagicMock()
        mock_agent.answer = AsyncMock(side_effect=Exception("Agent down"))
        monkeypatch.setattr("api.services.agent.agent_service", mock_agent)

        with pytest.raises(Retry):
            celery_tasks.process_agent_response.apply(args=("query", [], [], "tenant-1"), throw=True)


class TestEnqueueItemTask:
    def test_enqueue_item(self, monkeypatch):
        mock_redis_mod = MagicMock()
        mock_client = MagicMock()
        mock_redis_mod.from_url.return_value = mock_client
        monkeypatch.setattr("builtins.__import__", lambda name, *a, **kw: mock_redis_mod if name == "redis" else __import__(name, *a, **kw))

        celery_tasks.enqueue_item("test-queue", '{"session_id": "sess-1", "data": "test"}')

        mock_client.lpush.assert_called_once()


class TestLogSessionEventTask:
    def test_log_session_event(self, monkeypatch):
        mock_redis_mod = MagicMock()
        mock_client = MagicMock()
        mock_redis_mod.from_url.return_value = mock_client
        monkeypatch.setattr("builtins.__import__", lambda name, *a, **kw: mock_redis_mod if name == "redis" else __import__(name, *a, **kw))

        celery_tasks.log_session_event("sess-1", '{"event": "claimed", "agent_id": "agent-1"}')

        mock_client.rpush.assert_called_once()


class TestProcessHandoffTask:
    def test_handoff_logging(self, monkeypatch):
        with patch.object(celery_tasks, "logger") as mock_logger:
            celery_tasks.process_handoff(
                "handoff-queue",
                '{"session_id": "sess-1", "claimed_by": "agent-1", "claimed_ts": 12345.0}',
                "agent-1"
            )
            mock_logger.info.assert_called_once()
            call_args = mock_logger.info.call_args
            assert call_args[0][0] == "handoff_processed"
            assert call_args[1]["session"] == "sess-1"


class TestCeleryTaskErrorHandling:
    def test_task_raises_for_invalid_args(self):
        result = celery_tasks.process_rag_query.apply(args=())
        assert result.failed()

    def test_all_tasks_return_none_on_ignore_result(self):
        enqueue = celery_tasks.enqueue_item.apply(args=("q", '{}'))
        log = celery_tasks.log_session_event.apply(args=("s", '{}'))
        handoff = celery_tasks.process_handoff.apply(args=("q", '{}', "a"))

        for r in [enqueue, log, handoff]:
            assert r.successful()
            assert r.result is None
