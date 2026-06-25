import asyncio
import time
from enum import Enum

import structlog

from api.services.db_reliability import log_circuit_breaker_event_db

logger = structlog.get_logger()


class CircuitState(Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitBreaker:
    def __init__(self, name: str, failure_threshold: int = 5, recovery_timeout: float = 30.0, half_open_max_calls: int = 3):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time = 0.0
        self._half_open_calls = 0
        self._total_calls = 0
        self._total_failures = 0
        self._total_successes = 0
        self._last_state_change = time.time()

    async def call(self, func, *args, **kwargs):
        self._total_calls += 1

        if self._state == CircuitState.OPEN:
            if time.time() - self._last_failure_time >= self.recovery_timeout:
                await self._transition_to(CircuitState.HALF_OPEN)
            else:
                raise CircuitBreakerOpenError(f"Circuit breaker '{self.name}' is OPEN")

        if self._state == CircuitState.HALF_OPEN:
            if self._half_open_calls >= self.half_open_max_calls:
                raise CircuitBreakerOpenError(f"Circuit breaker '{self.name}' is HALF_OPEN and at max probe calls")

            self._half_open_calls += 1

        try:
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)

            self.record_success()
            return result
        except Exception:
            self.record_failure()
            raise

    def record_success(self):
        self._total_successes += 1
        self._success_count += 1
        self._half_open_calls = 0

        if self._state == CircuitState.HALF_OPEN:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._last_state_change = time.time()
            logger.info("circuit_breaker_closed", name=self.name)

    def record_failure(self):
        self._total_failures += 1
        self._failure_count += 1
        self._last_failure_time = time.time()
        self._half_open_calls = 0

        if self._state == CircuitState.CLOSED and self._failure_count >= self.failure_threshold:
            self._state = CircuitState.OPEN
            self._last_state_change = time.time()
            logger.warning("circuit_breaker_opened", name=self.name, failure_count=self._failure_count)

        elif self._state == CircuitState.HALF_OPEN:
            self._state = CircuitState.OPEN
            self._last_state_change = time.time()
            logger.warning("circuit_breaker_reopened", name=self.name)

    async def _transition_to(self, new_state: CircuitState):
        old_state = self._state
        self._state = new_state
        self._last_state_change = time.time()
        logger.info("circuit_breaker_state_change", name=self.name, from_state=old_state.value, to_state=new_state.value)
        try:
            await log_circuit_breaker_event_db(self.name, old_state.value, new_state.value, self._failure_count)
        except Exception as e:
            logger.warning("circuit_breaker_event_log_failed", name=self.name, error=str(e))

    def get_state(self) -> dict:
        return {
            "name": self.name,
            "state": self._state.value,
            "failure_count": self._failure_count,
            "success_count": self._success_count,
            "threshold": self.failure_threshold,
            "recovery_timeout": self.recovery_timeout,
            "half_open_max_calls": self.half_open_max_calls,
            "total_calls": self._total_calls,
            "total_failures": self._total_failures,
            "total_successes": self._total_successes,
            "last_failure_time": self._last_failure_time,
            "last_state_change": self._last_state_change,
            "is_open": self._state == CircuitState.OPEN,
        }

    async def reset(self):
        old_state = self._state
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._half_open_calls = 0
        self._last_state_change = time.time()
        logger.info("circuit_breaker_manually_reset", name=self.name)
        try:
            await log_circuit_breaker_event_db(self.name, old_state.value, "RESET", self._failure_count)
        except Exception as e:
            logger.warning("circuit_breaker_event_log_failed", name=self.name, error=str(e))


class CircuitBreakerOpenError(Exception):
    pass


class CircuitBreakerRegistry:
    _instance = None
    _breakers: dict[str, CircuitBreaker] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def get(self, name: str, failure_threshold: int = 5, recovery_timeout: float = 30.0, half_open_max_calls: int = 3) -> CircuitBreaker:
        if name not in self._breakers:
            self._breakers[name] = CircuitBreaker(name, failure_threshold, recovery_timeout, half_open_max_calls)
            logger.info("circuit_breaker_created", name=name)
        return self._breakers[name]

    def list_state(self) -> list[dict]:
        return [cb.get_state() for cb in self._breakers.values()]

    async def reset(self, name: str) -> bool:
        if name in self._breakers:
            await self._breakers[name].reset()
            return True
        return False


circuit_breaker_registry = CircuitBreakerRegistry()
