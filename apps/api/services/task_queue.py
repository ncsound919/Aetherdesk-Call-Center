import asyncio
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any

import structlog

logger = structlog.get_logger()


class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class BackgroundTask:
    task_id: str
    task_type: str
    payload: dict[str, Any]
    status: TaskStatus
    created_at: float
    started_at: float | None = None
    completed_at: float | None = None
    result: Any | None = None
    error: str | None = None


class AsyncTaskQueue:
    def __init__(self, max_concurrent: int = 10):
        self._tasks: dict[str, BackgroundTask] = {}
        self._queue: asyncio.Queue = asyncio.Queue()
        self._max_concurrent = max_concurrent
        self._running = 0
        self._lock = asyncio.Lock()
        self._workers: list = []

    async def start(self, num_workers: int = 3):
        self._workers = [
            asyncio.create_task(self._worker(i))
            for i in range(num_workers)
        ]
        logger.info("async_task_queue_started", workers=num_workers)

    async def stop(self):
        for _ in self._workers:
            await self._queue.put(None)
        await asyncio.gather(*self._workers, return_exceptions=True)
        logger.info("async_task_queue_stopped")

    async def submit(
        self,
        task_type: str,
        payload: dict[str, Any],
        callback: Callable | None = None
    ) -> str:
        task_id = str(uuid.uuid4())[:8]
        task = BackgroundTask(
            task_id=task_id,
            task_type=task_type,
            payload=payload,
            status=TaskStatus.PENDING,
            created_at=time.time()
        )
        self._tasks[task_id] = task

        await self._queue.put((task_id, callback))
        logger.info("task_submitted", task_id=task_id, task_type=task_type)

        return task_id

    async def _worker(self, worker_id: int):
        while True:
            try:
                item = await self._queue.get()
                if item is None:
                    break

                task_id, callback = item
                task = self._tasks.get(task_id)

                if not task:
                    continue

                async with self._lock:
                    if self._running >= self._max_concurrent:
                        await self._queue.put((task_id, callback))
                        await asyncio.sleep(0.1)
                        continue
                    self._running += 1

                try:
                    task.status = TaskStatus.RUNNING
                    task.started_at = time.time()

                    result = await self._execute_task(task)

                    task.status = TaskStatus.COMPLETED
                    task.result = result
                    task.completed_at = time.time()

                    if callback:
                        try:
                            await callback(result)
                        except Exception as e:
                            logger.error("callback_error", task_id=task_id, error=str(e))

                    logger.info(
                        "task_completed",
                        task_id=task_id,
                        duration_ms=int((task.completed_at - task.started_at) * 1000)
                    )

                except Exception as e:
                    task.status = TaskStatus.FAILED
                    task.error = str(e)
                    task.completed_at = time.time()
                    logger.error("task_failed", task_id=task_id, error=str(e))

                finally:
                    async with self._lock:
                        self._running -= 1

            except Exception as e:
                logger.error("worker_error", worker_id=worker_id, error=str(e))

    async def _execute_task(self, task: BackgroundTask) -> Any:
        if task.task_type == "rag_query":
            from apps.api.services.rag import rag_service
            return await rag_service.query(
                task.payload["query"],
                task.payload.get("k", 3)
            )
        elif task.task_type == "intent_classify":
            from apps.api.services.intent_classifier import classifier
            return await classifier.classify(task.payload["transcript"])
        elif task.task_type == "agent_response":
            from apps.api.services.agent import agent_service
            return await agent_service.answer(
                task.payload["question"],
                task.payload.get("context", []),
                task.payload.get("history")
            )
        else:
            raise ValueError(f"Unknown task type: {task.task_type}")

    def get_task(self, task_id: str) -> BackgroundTask | None:
        return self._tasks.get(task_id)

    def get_status(self) -> dict[str, Any]:
        return {
            "pending": sum(1 for t in self._tasks.values() if t.status == TaskStatus.PENDING),
            "running": sum(1 for t in self._tasks.values() if t.status == TaskStatus.RUNNING),
            "completed": sum(1 for t in self._tasks.values() if t.status == TaskStatus.COMPLETED),
            "failed": sum(1 for t in self._tasks.values() if t.status == TaskStatus.FAILED),
            "total": len(self._tasks),
            "concurrent": self._running
        }


task_queue = AsyncTaskQueue(max_concurrent=10)


