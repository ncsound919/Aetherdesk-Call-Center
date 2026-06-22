import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from apps.api.services.task_queue import AsyncTaskQueue, BackgroundTask, TaskStatus


class TestAsyncTaskQueueSubmit:
    @pytest.mark.asyncio
    async def test_submit_returns_task_id(self):
        queue = AsyncTaskQueue()
        task_id = await queue.submit("rag_query", {"query": "refund policy", "k": 3})
        assert isinstance(task_id, str)
        assert len(task_id) == 8

    @pytest.mark.asyncio
    async def test_submit_creates_background_task(self):
        queue = AsyncTaskQueue()
        task_id = await queue.submit("intent_classify", {"transcript": "help with billing"})
        task = queue.get_task(task_id)
        assert task is not None
        assert task.task_type == "intent_classify"
        assert task.status == TaskStatus.PENDING

    @pytest.mark.asyncio
    async def test_submit_returns_unique_ids(self):
        queue = AsyncTaskQueue()
        id1 = await queue.submit("rag_query", {"query": "a"})
        id2 = await queue.submit("rag_query", {"query": "b"})
        assert id1 != id2


class TestAsyncTaskQueueExecution:
    @pytest.mark.asyncio
    async def test_worker_executes_rag_query(self, monkeypatch):
        queue = AsyncTaskQueue()
        mock_rag = MagicMock()
        mock_rag.query = AsyncMock(return_value=[{"content": "result"}])
        monkeypatch.setattr("apps.api.services.task_queue.AsyncTaskQueue._execute_task",
                            lambda self, task: AsyncMock(return_value=[{"content": "result"}])())

        task_id = await queue.submit("rag_query", {"query": "test", "k": 2})
        await queue.start(num_workers=1)
        await asyncio.sleep(0.3)
        await queue.stop()

        task = queue.get_task(task_id)
        assert task.status == TaskStatus.COMPLETED
        assert task.result == [{"content": "result"}]

    @pytest.mark.asyncio
    async def test_worker_handles_failure(self, monkeypatch):
        queue = AsyncTaskQueue()
        async def fail_execute(self_arg, task):
            raise ValueError("Task failed")
        monkeypatch.setattr("apps.api.services.task_queue.AsyncTaskQueue._execute_task", fail_execute)

        task_id = await queue.submit("rag_query", {"query": "test"})
        await queue.start(num_workers=1)
        await asyncio.sleep(0.3)
        await queue.stop()

        task = queue.get_task(task_id)
        assert task.status == TaskStatus.FAILED
        assert "Task failed" in task.error

    @pytest.mark.asyncio
    async def test_callback_called_on_completion(self):
        queue = AsyncTaskQueue()
        callback_result = None

        async def my_callback(result):
            nonlocal callback_result
            callback_result = result

        async def fast_execute(task):
            return {"done": True}

        with patch.object(queue, "_execute_task", fast_execute):
            task_id = await queue.submit("rag_query", {"query": "x"}, callback=my_callback)
            await queue.start(num_workers=1)
            await asyncio.sleep(0.3)
            await queue.stop()

        assert callback_result == {"done": True}


class TestAsyncTaskQueueStatus:
    @pytest.mark.asyncio
    async def test_get_status_counts(self):
        queue = AsyncTaskQueue()
        await queue.submit("rag_query", {"query": "a"})
        await queue.submit("rag_query", {"query": "b"})
        await queue.submit("rag_query", {"query": "c"})

        status = queue.get_status()
        assert status["pending"] == 3
        assert status["running"] == 0
        assert status["completed"] == 0
        assert status["failed"] == 0
        assert status["total"] == 3


class TestAsyncTaskQueueUnknownType:
    @pytest.mark.asyncio
    async def test_unknown_type_raises_during_execution(self, monkeypatch):
        queue = AsyncTaskQueue()
        task_id = await queue.submit("unknown_type", {})
        await queue.start(num_workers=1)
        await asyncio.sleep(0.3)
        await queue.stop()

        task = queue.get_task(task_id)
        assert task.status == TaskStatus.FAILED
        assert "Unknown task type" in task.error


class TestAsyncTaskQueueInMemory:
    @pytest.mark.asyncio
    async def test_queue_operations(self):
        queue = AsyncTaskQueue()
        await queue._queue.put(("test-1", None))
        assert queue._queue.qsize() == 1

        item = await queue._queue.get()
        assert item[0] == "test-1"
