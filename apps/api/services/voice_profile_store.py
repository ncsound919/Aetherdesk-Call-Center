"""Voice profile storage — replaces global voice_profiles LRUCache."""

from threading import Lock

import structlog
from cachetools import LRUCache

logger = structlog.get_logger()


class VoiceProfileStore:
    """Thread-safe in-memory cache of voice profiles with bounded LRU."""

    def __init__(self, max_profiles: int = 100):
        self._profiles: LRUCache = LRUCache(maxsize=max_profiles)
        self._lock = Lock()

    def put(self, voice_id: str, profile: dict) -> None:
        with self._lock:
            self._profiles[voice_id] = profile

    def get(self, voice_id: str) -> dict | None:
        with self._lock:
            return self._profiles.get(voice_id)

    def get_copy(self, voice_id: str) -> dict | None:
        with self._lock:
            val = self._profiles.get(voice_id)
            return val.copy() if val else None

    def delete(self, voice_id: str) -> bool:
        with self._lock:
            if voice_id in self._profiles:
                del self._profiles[voice_id]
                return True
            return False

    def list_all(self) -> list[dict]:
        with self._lock:
            return [
                {"voice_id": vid, **{k: v for k, v in prof.items() if k in ("name", "language", "engine", "fallback")}}
                for vid, prof in self._profiles.items()
            ]

    def contains(self, voice_id: str) -> bool:
        with self._lock:
            return voice_id in self._profiles

    def items_snapshot(self) -> list[tuple[str, dict]]:
        with self._lock:
            return list(self._profiles.items())
