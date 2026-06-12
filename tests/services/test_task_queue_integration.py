import os
import pytest
from unittest.mock import MagicMock, patch

from apps.api.services.task_queue import AsyncTaskQueue, BackgroundTask, TaskStatus
from apps.api.services.celery_app import celery_app


@pytest.fixture
def celery_config():
    return {
        "broker_url": "redis://localhost:6379/15",
        "result_backend": "redis://localhost:6379/15",
        "task_always_eager": False,
        "task_store_eager_result": True,
    }


@pytest.fixture(autouse=True)
def enable_celery():
    os.environ["CELERY_ENABLED"] = "true"
    yield
    os.environ.pop("CELERY_ENABLED", None)


class TestAsyncTaskQueueWithCelery:
    @pytest.mark.asyncio
    async def test_submit_rag_query_via_celery(self, monkeypatch):
        queue = AsyncTaskQueue()
        
        # Mock the celery delay method
        mock_delay = MagicMock()
        mock_delay.id = "celery-task-123"
        monkeypatch.setattr(
            "apps.api.services.celery_tasks.process_rag_query.delay", 
            mock_delay
        )
        
        task_id = await queue.submit("rag_query", {"query": "refund policy", "k": 3, "tenant_id": "tenant-1"})
        
        assert task_id == "celery-task-123"
        mock_delay.assert_called_once_with("refund policy", 3, "tenant-1")

    @pytest.mark.asyncio
    async def test_submit_intent_classify_via_celery(self, monkeypatch):
        queue = AsyncTaskQueue()
        
        mock_delay = MagicMock()
        mock_delay.id = "celery-task-456"
        monkeypatch.setattr(
            "apps.api.services.celery_tasks.process_intent_classify.delay", 
            mock_delay
        )
        
        task_id = await queue.submit("intent_classify", {"transcript": "I need help with billing", "tenant_id": "tenant-1"})
        
        assert task_id == "celery-task-456"
        mock_delay.assert_called_once_with("I need help with billing", "tenant-1")

    @pytest.mark.asyncio
    async def test_submit_agent_response_via_celery(self, monkeypatch):
        queue = AsyncTaskQueue()
        
        mock_delay = MagicMock()
        mock_delay.id = "celery-task-789"
        monkeypatch.setattr(
            "apps.api.services.celery_tasks.process_agent_response.delay", 
            mock_delay
        )
        
        task_id = await queue.submit("agent_response", {
            "question": "When is my delivery?",
            "context": [{"content": "Delivery by Friday"}],
            "history": [],
            "tenant_id": "tenant-1"
        })
        
        assert task_id == "celery-task-789"
        mock_delay.assert_called_once_with(
            "When is my delivery?",
            [{"content": "Delivery by Friday"}],
            [],
            "tenant-1"
        )

    @pytest.mark.asyncio
    async def test_get_task_status_from_celery(self, monkeypatch):
        queue = AsyncTaskQueue()
        
        mock_async_result = MagicMock()
        mock_async_result.state = "SUCCESS"
        mock_async_result.successful.return_value = True
        mock_async_result.result = {"status": "completed"}
        mock_async_result.failed.return_value = False
        mock_async_result.info = None
        
        monkeypatch.setattr("apps.api.services.task_queue.AsyncResult", lambda tid, app: mock_async_result)
        
        task = queue.get_task("celery-task-123")
        
        assert task is not None
        assert task.status == TaskStatus.COMPLETED
        assert task.result == {"status": "completed"}

    @pytest.mark.asyncio
    async def test_get_status_returns_celery_backend_info(self, monkeypatch):
        queue = AsyncTaskQueue()
        
        mock_inspector = MagicMock()
        mock_inspector.active.return_value = {"worker1@host": [{"id": "t1"}]}
        mock_inspector.reserved.return_value = {"worker1@host": [{"id": "t2"}]}
        monkeypatch.setattr(celery_app, "control", MagicMock(inspect=lambda: mock_inspector))
        
        status = queue.get_status()
        
        assert status["active"] == 1
        assert status["reserved"] == 1
        assert status["backend"] == "celery"

    @pytest.mark.asyncio
    async def test_unknown_task_type_raises(self):
        queue = AsyncTaskQueue()
        
        # Unknown task type will still try to submit via celery but fail
        with pytest.raises(Exception):
            await queue.submit("unknown_type", {})


class TestAsyncTaskQueueEagerMode:
    """Test async queue with celery disabled (local execution)"""
    
    @pytest.fixture(autouse=True)
    def disable_celery(self):
        os.environ["CELERY_ENABLED"] = "false"
        yield
        os.environ.pop("CELERY_ENABLED", None)
    
    @pytest.mark.asyncio
    async def test_submit_and_process_locally(self, monkeypatch):
        queue = AsyncTaskQueue()
        
        mock_rag = MagicMock()
        mock_rag.query = AsyncMock(return_value=[{"content": "local result"}])
        monkeypatch.setattr("apps.api.services.rag.rag_service", mock_rag)
        
        task_id = await queue.submit("rag_query", {"query": "test", "k": 2})
        
        assert task_id is not None
        task = queue.get_task(task_id)
        assert task is not None
        
        # Start workers to process
        await queue.start(num_workers=1)
        import asyncio
        await asyncio.sleep(0.2)
        
        task = queue.get_task(task_id)
        assert task.status == TaskStatus.COMPLETED
        assert task.result == [{"content": "local result"}]
        
        await queue.stop()


class TestTaskQueueRedisFallback:
    """Test that queue works when redis is unavailable (local mode)"""
    
    @pytest.mark.asyncio
    async def test_enqueue_works_in_memory(self, monkeypatch):
        queue = AsyncTaskQueue()
        
        # Test internal queue operations
        await queue._queue.put(("test-1", None))
        assert queue._queue.qsize() == 1
        
        item = await queue._queue.get()
        assert item[0] == "test-1"
