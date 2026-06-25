import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestExponentialBackoff:
    @pytest.mark.asyncio
    async def test_success_on_first_attempt(self):
        from api.services.retry import exponential_backoff

        @exponential_backoff(max_retries=3, base_delay=0.1)
        async def my_func():
            return "success"

        result = await my_func()
        assert result == "success"

    @pytest.mark.asyncio
    async def test_retry_then_success(self):
        from api.services.retry import exponential_backoff

        call_count = 0

        @exponential_backoff(max_retries=3, base_delay=0.05)
        async def my_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("not ready yet")
            return "success"

        result = await my_func()
        assert result == "success"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_max_retries_exceeded(self):
        from api.services.retry import exponential_backoff, RetryError

        @exponential_backoff(max_retries=2, base_delay=0.05)
        async def my_func():
            raise ValueError("always fails")

        with pytest.raises(RetryError) as exc_info:
            await my_func()

        assert exc_info.value.attempts == 3
        assert isinstance(exc_info.value.last_exception, ValueError)

    @pytest.mark.asyncio
    async def test_cancelled_error_propagates(self):
        from api.services.retry import exponential_backoff

        @exponential_backoff(max_retries=3, base_delay=0.05)
        async def my_func():
            raise asyncio.CancelledError()

        with pytest.raises(asyncio.CancelledError):
            await my_func()

    @pytest.mark.asyncio
    async def test_jitter_applied(self):
        from api.services.retry import exponential_backoff

        delays = []

        @exponential_backoff(max_retries=2, base_delay=1.0, jitter=True)
        async def my_func():
            raise ValueError("fail")

        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep, \
             pytest.raises(Exception):
            await my_func()

        assert mock_sleep.call_count == 2

    @pytest.mark.asyncio
    async def test_no_jitter(self):
        from api.services.retry import exponential_backoff

        @exponential_backoff(max_retries=1, base_delay=0.5, jitter=False)
        async def my_func():
            raise ValueError("fail")

        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep, \
             pytest.raises(Exception):
            await my_func()

        mock_sleep.assert_called_once_with(0.5)

    @pytest.mark.asyncio
    async def test_delay_capped_by_max_delay(self):
        from api.services.retry import exponential_backoff

        @exponential_backoff(max_retries=5, base_delay=1.0, max_delay=2.0, jitter=False)
        async def my_func():
            raise ValueError("fail")

        delays = []

        original_sleep = asyncio.sleep

        async def tracking_sleep(delay):
            delays.append(delay)
            await original_sleep(0)

        with patch("asyncio.sleep", tracking_sleep), \
             pytest.raises(Exception):
            await my_func()

        for d in delays:
            assert d <= 2.0


class TestRetryConfig:
    def test_default_config(self):
        from api.services.retry import RetryConfig

        config = RetryConfig()
        assert config.max_retries == 3
        assert config.base_delay == 1.0
        assert config.max_delay == 30.0
        assert config.exponential_base == 2.0
        assert config.retry_on == (Exception,)

    def test_custom_config(self):
        from api.services.retry import RetryConfig

        config = RetryConfig(max_retries=5, base_delay=0.5, max_delay=15.0, exponential_base=3.0)
        assert config.max_retries == 5
        assert config.base_delay == 0.5
        assert config.max_delay == 15.0
        assert config.exponential_base == 3.0


class TestAsyncRetry:
    @pytest.mark.asyncio
    async def test_execute_async_success(self):
        from api.services.retry import AsyncRetry, RetryConfig

        retrier = AsyncRetry(RetryConfig(max_retries=2, base_delay=0.05))

        async def my_async_func():
            return "done"

        result = await retrier.execute(my_async_func)
        assert result == "done"

    @pytest.mark.asyncio
    async def test_execute_sync_success(self):
        from api.services.retry import AsyncRetry, RetryConfig

        retrier = AsyncRetry(RetryConfig(max_retries=2, base_delay=0.05))

        def my_sync_func():
            return "sync done"

        result = await retrier.execute(my_sync_func)
        assert result == "sync done"

    @pytest.mark.asyncio
    async def test_execute_retry_then_success(self):
        from api.services.retry import AsyncRetry, RetryConfig

        retrier = AsyncRetry(RetryConfig(max_retries=3, base_delay=0.05))
        call_count = 0

        async def my_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("retry")
            return "ok"

        result = await retrier.execute(my_func)
        assert result == "ok"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_execute_max_retries_exceeded(self):
        from api.services.retry import AsyncRetry, RetryConfig, RetryError

        retrier = AsyncRetry(RetryConfig(max_retries=2, base_delay=0.05))

        async def my_func():
            raise ValueError("always fails")

        with pytest.raises(RetryError) as exc_info:
            await retrier.execute(my_func)

        assert exc_info.value.attempts == 3
        assert isinstance(exc_info.value.last_exception, ValueError)

    @pytest.mark.asyncio
    async def test_execute_specific_exception_only(self):
        from api.services.retry import AsyncRetry, RetryConfig, RetryError

        retrier = AsyncRetry(RetryConfig(max_retries=2, base_delay=0.05, retry_on=(ValueError,)))

        async def my_func():
            raise TypeError("wrong exception type")

        with pytest.raises(TypeError):
            await retrier.execute(my_func)

    @pytest.mark.asyncio
    async def test_execute_with_args(self):
        from api.services.retry import AsyncRetry, RetryConfig

        retrier = AsyncRetry(RetryConfig(max_retries=2, base_delay=0.05))

        async def my_func(a, b=None):
            return f"{a}-{b}"

        result = await retrier.execute(my_func, "hello", b="world")
        assert result == "hello-world"


class TestPreconfiguredRetryers:
    def test_retry_default_exists(self):
        from api.services.retry import retry_default

        assert retry_default.config.max_retries == 3
        assert retry_default.config.base_delay == 1.0

    def test_retry_ollama_exists(self):
        from api.services.retry import retry_ollama

        assert retry_ollama.config.max_retries == 2
        assert retry_ollama.config.max_delay == 10.0

    def test_retry_rag_exists(self):
        from api.services.retry import retry_rag

        assert retry_rag.config.max_retries == 2
        assert retry_rag.config.base_delay == 0.5
        assert retry_rag.config.max_delay == 10.0


class TestRetryError:
    def test_retry_error_attributes(self):
        from api.services.retry import RetryError

        inner = ValueError("original")
        err = RetryError("Failed after 3 attempts", inner, 3)

        assert str(err) == "Failed after 3 attempts"
        assert err.last_exception is inner
        assert err.attempts == 3
