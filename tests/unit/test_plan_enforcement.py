"""Unit tests for plan enforcement helpers."""

from unittest.mock import AsyncMock, patch

import pytest

from api.services.plan_enforcement import PlanLimitExceeded, check_agent_limit, check_call_limit


class TestPlanLimitExceeded:
    def test_stores_attributes(self):
        exc = PlanLimitExceeded("Agent limit reached", current=3, limit=2, plan="free")
        assert exc.message == "Agent limit reached"
        assert exc.current == 3
        assert exc.limit == 2
        assert exc.plan == "free"
        assert "Agent limit reached" in str(exc)


@pytest.mark.asyncio
async def test_check_agent_limit_allows_when_below():
    with patch(
        "api.services.db_tenants.get_tenant_plan_db",
        new_callable=AsyncMock,
        return_value={"max_agents": 5, "plan_name": "pro"},
    ), patch(
        "api.services.db_tenants.count_active_agents_db",
        new_callable=AsyncMock,
        return_value=2,
    ):
        allowed, info = await check_agent_limit("T-1")
    assert allowed is True
    assert info == {"current": 2, "limit": 5}


@pytest.mark.asyncio
async def test_check_agent_limit_blocks_when_at_limit():
    with patch(
        "api.services.db_tenants.get_tenant_plan_db",
        new_callable=AsyncMock,
        return_value={"max_agents": 3, "plan_name": "pro"},
    ), patch(
        "api.services.db_tenants.count_active_agents_db",
        new_callable=AsyncMock,
        return_value=3,
    ):
        allowed, info = await check_agent_limit("T-1")
    assert allowed is False
    assert info["error"] == "plan_limit_reached"
    assert info["resource"] == "agents"


@pytest.mark.asyncio
async def test_check_agent_limit_no_plan_defaults():
    with patch(
        "api.services.db_tenants.get_tenant_plan_db",
        new_callable=AsyncMock,
        return_value=None,
    ), patch(
        "api.services.db_tenants.count_active_agents_db",
        new_callable=AsyncMock,
        return_value=0,
    ):
        allowed, info = await check_agent_limit("T-1")
    assert allowed is True
    assert info["limit"] == 1


@pytest.mark.asyncio
async def test_check_call_limit_allows_when_below():
    with patch(
        "api.services.db_tenants.get_tenant_plan_db",
        new_callable=AsyncMock,
        return_value={"max_concurrent_calls": 10, "plan_name": "pro"},
    ), patch(
        "api.services.db_tenants.count_active_calls_db",
        new_callable=AsyncMock,
        return_value=4,
    ):
        allowed, info = await check_call_limit("T-1")
    assert allowed is True
    assert info == {"current": 4, "limit": 10}


@pytest.mark.asyncio
async def test_check_call_limit_blocks_when_at_limit():
    with patch(
        "api.services.db_tenants.get_tenant_plan_db",
        new_callable=AsyncMock,
        return_value={"max_concurrent_calls": 2, "plan_name": "free"},
    ), patch(
        "api.services.db_tenants.count_active_calls_db",
        new_callable=AsyncMock,
        return_value=2,
    ):
        allowed, info = await check_call_limit("T-1")
    assert allowed is False
    assert info["resource"] == "concurrent_calls"
    assert info["plan"] == "free"
