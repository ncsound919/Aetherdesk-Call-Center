import asyncio
from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar

import structlog

logger = structlog.get_logger()

T = TypeVar('T')

DEFAULT_MAX_RETRIES = 3
DEFAULT_BASE_DELAY = 1.0
DEFAULT_MAX_DELAY = 30.0


class RetryError(Exception):
    def __init__(self, message: str, last_exception: Exception, attempts: int):
        super().__init__(message)
        self.last_exception = last_exception
        self.attempts = attempts


def exponential_backoff(
    max_retries: int = DEFAULT_MAX_RETRIES,
    base_delay: float = DEFAULT_BASE_DELAY,
    max_delay: float = DEFAULT_MAX_DELAY,
    exponential_base: float = 2.0,
    jitter: bool = True
):
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None

            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    last_exception = e

                    if attempt >= max_retries:
                        break

                    delay = min(base_delay * (exponential_base ** attempt), max_delay)
                    if jitter:
                        import random
                        delay = delay * (0.5 + random.random())  # nosec B311 — jitter for retry timing, not cryptographic

                    logger.warning(
                        "retry_attempt",
                        function=func.__name__,
                        attempt=attempt + 1,
                        max_retries=max_retries,
                        delay_sec=delay,
                        error=str(e)
                    )
                    await asyncio.sleep(delay)

            raise RetryError(
                f"Failed after {max_retries + 1} attempts",
                last_exception,
                max_retries + 1
            )
        return wrapper
    return decorator


class RetryConfig:
    def __init__(
        self,
        max_retries: int = DEFAULT_MAX_RETRIES,
        base_delay: float = DEFAULT_BASE_DELAY,
        max_delay: float = DEFAULT_MAX_DELAY,
        exponential_base: float = 2.0,
        retry_on: tuple = (Exception,)
    ):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.retry_on = retry_on


class AsyncRetry:
    def __init__(self, config: RetryConfig | None = None):
        self.config = config or RetryConfig()

    async def execute(self, func: Callable, *args, **kwargs) -> Any:
        last_exception = None

        for attempt in range(self.config.max_retries + 1):
            try:
                if asyncio.iscoroutinefunction(func):
                    return await func(*args, **kwargs)
                else:
                    return func(*args, **kwargs)
            except self.config.retry_on as e:
                last_exception = e

                if attempt >= self.config.max_retries:
                    break

                delay = min(
                    self.config.base_delay * (self.config.exponential_base ** attempt),
                    self.config.max_delay
                )

                logger.warning(
                    "retry_execute_attempt",
                    function=func.__name__,
                    attempt=attempt + 1,
                    delay_sec=delay,
                    error=str(e)
                )
                await asyncio.sleep(delay)

        raise RetryError(
            f"Failed after {self.config.max_retries + 1} attempts",
            last_exception,
            self.config.max_retries + 1
        )


retry_default = AsyncRetry(RetryConfig(max_retries=3, base_delay=1.0))
retry_ollama = AsyncRetry(RetryConfig(max_retries=2, base_delay=1.0, max_delay=10.0))
retry_rag = AsyncRetry(RetryConfig(max_retries=2, base_delay=0.5, max_delay=10.0))


