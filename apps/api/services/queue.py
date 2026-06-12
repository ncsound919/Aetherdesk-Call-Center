import json
import time
from threading import Lock

import structlog

logger = structlog.get_logger()

QUEUE_KEY = "queue:{name}"
SESSION_KEY = "session:{sid}"


class InMemoryQueue:
    def __init__(self):
        self._queues: dict[str, list[dict]] = {}
        self._sessions: dict[str, dict] = {}
        self._lock = Lock()

    def lpush(self, key: str, value: str):
        with self._lock:
            if key not in self._queues:
                self._queues[key] = []
            self._queues[key].insert(0, value)

    def rpop(self, key: str) -> str | None:
        with self._lock:
            if key not in self._queues or not self._queues[key]:
                return None
            return self._queues[key].pop()

    def lrange(self, key: str, start: int, stop: int) -> list[str]:
        with self._lock:
            if key not in self._queues:
                return []
            # Redis lrange stop is inclusive, Python slice stop is exclusive
            return self._queues[key][start:stop + 1 if stop >= 0 else None]

    def rpush(self, key: str, value: str):
        with self._lock:
            if key not in self._queues:
                self._queues[key] = []
            self._queues[key].append(value)

    def get(self, key: str) -> str | None:
        with self._lock:
            return self._sessions.get(key)

    def setex(self, key: str, ttl: int, value: str):
        with self._lock:
            self._sessions[key] = value

    def exists(self, key: str) -> bool:
        with self._lock:
            return key in self._sessions

    def delete(self, key: str) -> int:
        with self._lock:
            removed = 0
            if key in self._sessions:
                del self._sessions[key]
                removed += 1
            if key in self._queues:
                del self._queues[key]
                removed += 1
            return removed

    def ping(self) -> bool:
        return True


class QueueManager:
    def __init__(self, redis_client, use_fallback: bool = True, in_memory_queue: InMemoryQueue | None = None):
        self.r = redis_client
        self._use_fallback = use_fallback
        self._in_memory = in_memory_queue or InMemoryQueue()
        self._last_health_check = 0
        self._redis_ok = False

    def _is_redis_available(self) -> bool:
        now = time.time()
        if now - self._last_health_check < 5:
            return self._redis_ok

        self._last_health_check = now
        try:
            if hasattr(self.r, 'ping'):
                self._redis_ok = self.r.ping()
                return self._redis_ok
        except Exception as e:
            logger.warning("redis_unavailable", error=str(e))
            self._redis_ok = False
        return False

    def _get_backend(self):
        if self._use_fallback and not self._is_redis_available():
            return self._in_memory
        return self.r

    def enqueue(self, queue: str, item: dict) -> None:
        backend = self._get_backend()
        entry = dict(item)
        entry.setdefault("created_ts", time.time())
        backend.lpush(QUEUE_KEY.format(name=queue), json.dumps(entry))

    def peek(self, queue: str, n: int = 50):
        backend = self._get_backend()
        vals = backend.lrange(QUEUE_KEY.format(name=queue), 0, n-1)
        return [json.loads(v) for v in vals]

    def claim(self, queue: str, agent_id: str):
        backend = self._get_backend()
        v = backend.rpop(QUEUE_KEY.format(name=queue))
        if not v:
            return None
        item = json.loads(v)
        item["claimed_by"] = agent_id
        item["claimed_ts"] = time.time()
        backend.rpush(f"log:{item['session_id']}", json.dumps({"event":"claimed","agent_id":agent_id,"ts":item["claimed_ts"]}))
        return item

    def session_set(self, sid: str, data: dict, ttl: int = 1800):
        backend = self._get_backend()
        backend.setex(SESSION_KEY.format(sid=sid), ttl, json.dumps(data))

    def session_get(self, sid: str):
        backend = self._get_backend()
        v = backend.get(SESSION_KEY.format(sid=sid))
        return json.loads(v) if v else None

    def session_delete(self, sid: str):
        backend = self._get_backend()
        backend.delete(SESSION_KEY.format(sid=sid))
