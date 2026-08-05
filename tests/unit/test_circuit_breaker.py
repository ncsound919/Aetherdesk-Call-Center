"""Unit tests for the circuit breaker (reliability)."""

from unittest.mock import patch

import pytest

from api.services.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerOpenError,
    CircuitBreakerRegistry,
)


@pytest.mark.asyncio
async def test_closed_breaker_allows_calls_and_records_success():
    cb = CircuitBreaker("test", failure_threshold=3, recovery_timeout=1.0)
    result = await cb.call(lambda: 42)
    assert result == 42
    state = cb.get_state()
    assert state["state"] == "CLOSED"
    assert state["total_successes"] == 1
    assert state["is_open"] is False


@pytest.mark.asyncio
async def test_async_function_supported():
    async def worker():
        return "ok"

    cb = CircuitBreaker("async")
    assert await cb.call(worker) == "ok"


@pytest.mark.asyncio
async def test_opens_after_failure_threshold():
    cb = CircuitBreaker("fail", failure_threshold=2, recovery_timeout=10.0)

    def boom():
        raise ValueError("downstream failed")

    with pytest.raises(ValueError):
        await cb.call(boom)
    assert cb.get_state()["state"] == "CLOSED"

    with pytest.raises(ValueError):
        await cb.call(boom)
    # Threshold reached -> OPEN
    state = cb.get_state()
    assert state["state"] == "OPEN"
    assert state["is_open"] is True

    # Now calls are rejected immediately
    with pytest.raises(CircuitBreakerOpenError):
        await cb.call(lambda: 1)


@pytest.mark.asyncio
async def test_recovery_to_half_open_after_timeout():
    cb = CircuitBreaker("recover", failure_threshold=1, recovery_timeout=0.05)

    with pytest.raises(ValueError):
        await cb.call(_boom)
    assert cb.get_state()["state"] == "OPEN"

    # Wait past recovery timeout
    await _sleep_ms(80)

    # Next call transitions to HALF_OPEN and runs the probe
    result = await cb.call(lambda: "probe-ok")
    assert result == "probe-ok"
    # Success in HALF_OPEN closes the breaker
    assert cb.get_state()["state"] == "CLOSED"


@pytest.mark.asyncio
async def test_half_open_failure_reopens():
    cb = CircuitBreaker("reopen", failure_threshold=2, recovery_timeout=0.05)

    with pytest.raises(ValueError):
        await cb.call(_boom)
    with pytest.raises(ValueError):
        await cb.call(_boom)
    assert cb.get_state()["state"] == "OPEN"

    await _sleep_ms(80)
    # Probe fails -> back to OPEN
    with pytest.raises(ValueError):
        await cb.call(_boom)
    assert cb.get_state()["state"] == "OPEN"


@pytest.mark.asyncio
async def test_half_open_limits_probe_calls():
    cb = CircuitBreaker("half", failure_threshold=1, recovery_timeout=0.05)
    cb._state = cb._state.__class__.HALF_OPEN  # force half-open
    cb._half_open_calls = cb.half_open_max_calls
    with pytest.raises(CircuitBreakerOpenError):
        await cb.call(lambda: 1)


@pytest.mark.asyncio
async def test_reset_returns_to_closed():
    cb = CircuitBreaker("reset", failure_threshold=1, recovery_timeout=1.0)
    with pytest.raises(ValueError):
        await cb.call(_boom)
    assert cb.get_state()["state"] == "OPEN"

    with patch("api.services.circuit_breaker.log_circuit_breaker_event_db", new_callable=pytest_asyncio_mock) as mock_log:
        await cb.reset()
    assert cb.get_state()["state"] == "CLOSED"
    assert cb.get_state()["failure_count"] == 0


def test_registry_singleton_and_get():
    reg1 = CircuitBreakerRegistry()
    reg2 = CircuitBreakerRegistry()
    assert reg1 is reg2

    cb = reg1.get("db", failure_threshold=2)
    assert cb.name == "db"
    # Second get returns same instance
    assert reg1.get("db") is cb


@pytest.mark.asyncio
async def test_registry_list_and_reset():
    reg = CircuitBreakerRegistry()
    reg.get("svc-a")
    reg.get("svc-b")
    states = reg.list_state()
    assert len(states) >= 2

    assert await reg.reset("svc-a") is True
    assert await reg.reset("nonexistent") is False


def _boom():
    raise ValueError("boom")


async def _sleep_ms(ms):
    import asyncio
    await asyncio.sleep(ms / 1000)


def pytest_asyncio_mock():
    from unittest.mock import AsyncMock
    return AsyncMock(return_value=None)
