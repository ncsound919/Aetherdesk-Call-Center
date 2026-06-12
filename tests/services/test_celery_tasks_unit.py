import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from apps.api.services import celery_tasks


class TestProcessRagQueryTask:
    def test_apply_returns_result(self, monkeypatch):
        mock_rag = MagicMock()
        mock_rag.query = AsyncMock(return_value=[{"content": "RAG result"}])
        monkeypatch.setattr(celery_tasks, "rag_service", mock_rag)
        
        result = celery_tasks.process_rag_query.apply(args=("test query", 3, "tenant-1"))
        
        assert result.successful()
        assert result.result == [{"content": "RAG result"}]

    def test_retry_on_failure(self, monkeypatch):
        mock_rag = MagicMock()
        mock_rag.query = AsyncMock(side_effect=Exception("RAG down"))
        monkeypatch.setattr(celery_tasks, "rag_service", mock_rag)
        
        result = celery_tasks.process_rag_query.apply(args=("test query", 3, "tenant-1"), throw=True)
        
        assert result.failed()


class TestProcessIntentClassifyTask:
    def test_apply_returns_classification(self, monkeypatch):
        mock_classifier = MagicMock()
        mock_classifier.classify = AsyncMock(return_value={"intent": "billing", "confidence": 0.95})
        monkeypatch.setattr(celery_tasks, "classifier", mock_classifier)
        
        result = celery_tasks.process_intent_classify.apply(args=("Where is my refund?", "tenant-1"))
        
        assert result.successful()
        assert result.result["intent"] == "billing"

    def test_retry_on_failure(self, monkeypatch):
        mock_classifier = MagicMock()
        mock_classifier.classify = AsyncMock(side_effect=Exception("Classifier down"))
        monkeypatch.setattr(celery_tasks, "classifier", mock_classifier)
        
        result = celery_tasks.process_intent_classify.apply(args=("query", "tenant-1"), throw=True)
        
        assert result.failed()


class TestProcessAgentResponseTask:
    def test_apply_returns_answer(self, monkeypatch):
        mock_agent = MagicMock()
        mock_agent.answer = AsyncMock(return_value="Your refund is being processed.")
        monkeypatch.setattr(celery_tasks, "agent_service", mock_agent)
        
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
        monkeypatch.setattr(celery_tasks, "agent_service", mock_agent)
        
        result = celery_tasks.process_agent_response.apply(args=("query", [], [], "tenant-1"), throw=True)
        
        assert result.failed()


class TestEnqueueItemTask:
    def test_enqueue_item(self, monkeypatch):
        mock_redis = MagicMock()
        mock_redis.lpush = MagicMock()
        monkeypatch.setattr(celery_tasks, "sync_redis", mock_redis)
        
        celery_tasks.enqueue_item("test-queue", '{"session_id": "sess-1", "data": "test"}')
        
        mock_redis.lpush.assert_called_once()


class TestLogSessionEventTask:
    def test_log_session_event(self, monkeypatch):
        mock_redis = MagicMock()
        mock_redis.rpush = MagicMock()
        monkeypatch.setattr(celery_tasks, "sync_redis", mock_redis)
        
        celery_tasks.log_session_event("sess-1", '{"event": "claimed", "agent_id": "agent-1"}')
        
        mock_redis.rpush.assert_called_once()


class TestProcessHandoffTask:
    def test_handoff_logging(self, monkeypatch, caplog):
        import structlog
        logger = structlog.get_logger()
        
        celery_tasks.process_handoff(
            "handoff-queue", 
            '{"session_id": "sess-1", "claimed_by": "agent-1", "claimed_ts": 12345.0}',
            "agent-1"
        )
        
        # Verify logging happened
        assert any("handoff_processed" in str(r) for r in caplog.records)


class TestCeleryTaskErrorHandling:
    def test_task_raises_for_invalid_args(self):
        result = celery_tasks.process_rag_query.apply(args=())  # Missing required args
        assert result.failed()

    def test_all_tasks_return_none_on_ignore_result(self):
        # These tasks use ignore_result=True
        enqueue = celery_tasks.enqueue_item.apply(args=("q", '{}'))
        log = celery_tasks.log_session_event.apply(args=("s", '{}'))
        handoff = celery_tasks.process_handoff.apply(args=("q", '{}', "a"))
        
        for r in [enqueue, log, handoff]:
            assert r.successful()
            # ignore_result=True means result is None
            assert r.result is None
