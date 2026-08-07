"""Unit tests for api.services.failover_testing."""

from unittest.mock import patch

import pytest

import api.services.failover_testing as ft
from api.services.failover_testing import failover_service


@pytest.fixture(autouse=True)
def _reset_globals():
    ft._in_memory_history.clear()
    ft._in_memory_config.update(
        {
            "primary_provider": "twilio",
            "secondary_provider": "fonster",
            "auto_test_interval_hours": 24,
            "notifications_enabled": True,
            "last_test_at": None,
        }
    )
    yield


@pytest.mark.asyncio
async def test_test_telephony_failover_success():
    with patch("api.services.failover_testing.random.random", return_value=0.9):
        with patch(
            "api.services.failover_testing.random.uniform", return_value=1234.56
        ):
            result = await failover_service.test_telephony_failover()
    assert result["primary"] == "twilio"
    assert result["secondary"] == "fonster"
    assert result["failover_success"] is True
    assert result["fallback_success"] is True
    assert result["failover_time_ms"] == 1234.56
    assert isinstance(result["total_test_time_ms"], float)
    assert result["id"]
    assert result["timestamp"]


@pytest.mark.asyncio
async def test_test_telephony_failover_failure_branch():
    with patch("api.services.failover_testing.random.random", side_effect=[0.01, 0.99]):
        result = await failover_service.test_telephony_failover()
    assert result["failover_success"] is False
    assert result["fallback_success"] is True


@pytest.mark.asyncio
async def test_failover_test_updates_state():
    with patch("api.services.failover_testing.random.random", return_value=0.5):
        result = await failover_service.test_telephony_failover()
    assert ft._in_memory_history[0]["id"] == result["id"]
    assert ft._in_memory_config["last_test_at"] == result["timestamp"]
    assert len(ft._in_memory_history) == 1


@pytest.mark.asyncio
async def test_get_failover_status_initial():
    result = await failover_service.get_failover_status()
    assert result["primary_provider"] == "twilio"
    assert result["secondary_provider"] == "fonster"
    assert result["primary_healthy"] is True
    assert result["secondary_healthy"] is True
    assert result["last_test_at"] is None
    assert result["auto_test_enabled"] is True


@pytest.mark.asyncio
async def test_get_failover_status_after_test():
    ft._in_memory_config["last_test_at"] = "2026-01-01T00:00:00Z"
    ft._in_memory_config["auto_test_interval_hours"] = 0
    result = await failover_service.get_failover_status()
    assert result["last_test_at"] == "2026-01-01T00:00:00Z"
    assert result["auto_test_enabled"] is False


@pytest.mark.asyncio
async def test_schedule_failover_test():
    result = await failover_service.schedule_failover_test(48)
    assert result["scheduled"] is True
    assert result["interval_hours"] == 48
    assert "next_test_at" in result
    assert ft._in_memory_config["auto_test_interval_hours"] == 48


@pytest.mark.asyncio
async def test_schedule_failover_test_zero_interval():
    result = await failover_service.schedule_failover_test(0)
    assert result["interval_hours"] == 0
    assert "next_test_at" in result


@pytest.mark.asyncio
async def test_get_failover_history_empty():
    result = await failover_service.get_failover_history()
    assert result == []


@pytest.mark.asyncio
async def test_get_failover_history_respects_limit():
    for _ in range(5):
        ft._in_memory_history.insert(0, {"id": f"r{_}"})
    result = await failover_service.get_failover_history(limit=3)
    assert len(result) == 3


@pytest.mark.asyncio
async def test_get_failover_config_returns_copy():
    ft._in_memory_config["last_test_at"] = "2026-01-01T00:00:00Z"
    result = await failover_service.get_failover_config()
    assert result["primary_provider"] == "twilio"
    assert result["last_test_at"] == "2026-01-01T00:00:00Z"
    result["primary_provider"] = "mutated"
    assert ft._in_memory_config["primary_provider"] == "twilio"
