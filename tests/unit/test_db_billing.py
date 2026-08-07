"""Unit tests for rental billing DB access (tenant_rentals, tenant_balances)."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from api.services.db_billing import (
    activate_rental_db,
    credit_minutes_db,
    debit_minutes_db,
    get_active_rental_db,
    get_minute_balance_db,
    has_call_capacity_db,
    settle_call_minutes_db,
    set_tenant_billing_settings_db,
    get_tenant_billing_settings_db,
)


def _fake_tenant_row(settings_json='{"ai_mode":"deepseek"}'):
    return {"settings": settings_json}


class TestMinuteBalance:
    @pytest.mark.asyncio
    async def test_credit_creates_balance(self):
        with patch("api.services.db_billing.USE_POSTGRES", False), \
             patch("api.services.db_billing._get_sqlite_conn") as mock_conn:
            mock_conn.return_value.execute.return_value.fetchone.return_value = {"minute_balance": 500}
            balance = await credit_minutes_db("T-1", 500)
            assert balance == 500

    @pytest.mark.asyncio
    async def test_credit_ignores_non_positive(self):
        with patch("api.services.db_billing.get_minute_balance_db", new_callable=AsyncMock, return_value=100) as m:
            balance = await credit_minutes_db("T-1", 0)
            assert balance == 100
            m.assert_called_once()

    @pytest.mark.asyncio
    async def test_debit_success(self):
        with patch("api.services.db_billing.USE_POSTGRES", False), \
             patch("api.services.db_billing._get_sqlite_conn") as mock_conn:
            mock_conn.return_value.execute.return_value.rowcount = 1
            assert await debit_minutes_db("T-1", 60) is True

    @pytest.mark.asyncio
    async def test_debit_insufficient(self):
        with patch("api.services.db_billing.USE_POSTGRES", False), \
             patch("api.services.db_billing._get_sqlite_conn") as mock_conn:
            mock_conn.return_value.execute.return_value.rowcount = 0
            assert await debit_minutes_db("T-1", 9999) is False

    @pytest.mark.asyncio
    async def test_debit_non_positive_always_ok(self):
        assert await debit_minutes_db("T-1", 0) is True


class TestRentalActivation:
    @pytest.mark.asyncio
    async def test_activate_credits_included_minutes(self):
        with patch("api.services.db_billing.USE_POSTGRES", False), \
             patch("api.services.db_billing._get_sqlite_conn"), \
             patch("api.services.db_billing.credit_minutes_db", new_callable=AsyncMock) as mock_credit, \
             patch("api.services.db_billing.get_active_rental_db", new_callable=AsyncMock,
                   return_value={"period": "hour", "included_minutes": 40}):
            result = await activate_rental_db(
                "T-1", "hour", "deepseek", 2, 80,
                "2026-01-01T00:00:00Z", "2026-01-01T01:00:00Z",
            )
            mock_credit.assert_awaited_once_with("T-1", 80)
            assert result["period"] == "hour"


class TestCapacity:
    @pytest.mark.asyncio
    async def test_ok_with_rental_and_balance(self):
        with patch("api.services.db_billing.get_active_rental_db", new_callable=AsyncMock,
                   return_value={"period": "hour"}), \
             patch("api.services.db_billing.get_minute_balance_db", new_callable=AsyncMock, return_value=100):
            ok, info = await has_call_capacity_db("T-1")
            assert ok is True
            assert info["reason"] is None

    @pytest.mark.asyncio
    async def test_blocked_without_rental(self):
        with patch("api.services.db_billing.get_active_rental_db", new_callable=AsyncMock, return_value=None), \
             patch("api.services.db_billing.get_minute_balance_db", new_callable=AsyncMock, return_value=100):
            ok, info = await has_call_capacity_db("T-1")
            assert ok is False
            assert info["reason"] == "no_active_rental"

    @pytest.mark.asyncio
    async def test_blocked_without_minutes(self):
        with patch("api.services.db_billing.get_active_rental_db", new_callable=AsyncMock,
                   return_value={"period": "hour"}), \
             patch("api.services.db_billing.get_minute_balance_db", new_callable=AsyncMock, return_value=0):
            ok, info = await has_call_capacity_db("T-1")
            assert ok is False
            assert info["reason"] == "insufficient_minutes"


class TestSettlement:
    @pytest.mark.asyncio
    async def test_settle_rounds_up_minutes(self):
        with patch("api.services.db_billing._tenant_id_for_sip_call", new_callable=AsyncMock,
                   return_value="T-1"), \
             patch("api.services.db_billing.debit_minutes_db", new_callable=AsyncMock, return_value=True) as mock_debit:
            result = await settle_call_minutes_db("CA-1", 61)
            assert result["debit"] is True
            assert result["minutes"] == 2
            mock_debit.assert_awaited_once_with("T-1", 2)

    @pytest.mark.asyncio
    async def test_settle_min_one_minute(self):
        with patch("api.services.db_billing._tenant_id_for_sip_call", new_callable=AsyncMock,
                   return_value="T-1"), \
             patch("api.services.db_billing.debit_minutes_db", new_callable=AsyncMock, return_value=True):
            result = await settle_call_minutes_db("CA-1", 5)
            assert result["minutes"] == 1

    @pytest.mark.asyncio
    async def test_settle_no_call_mapping(self):
        with patch("api.services.db_billing._tenant_id_for_sip_call", new_callable=AsyncMock,
                   return_value=None), \
             patch("api.services.db_billing.debit_minutes_db", new_callable=AsyncMock) as mock_debit:
            result = await settle_call_minutes_db("CA-UNKNOWN", 60)
            assert result["debit"] is False
            assert result["reason"] == "call_not_found"
            mock_debit.assert_not_called()


class TestTenantBillingSettings:
    @pytest.mark.asyncio
    async def test_get_defaults_to_deepseek(self):
        with patch("api.services.db_tenants.get_tenant_db", new_callable=AsyncMock,
                   return_value=_fake_tenant_row('{"ai_mode":"byok","byok_keys":{"openai":"x"}}')):
            settings = await get_tenant_billing_settings_db("T-1")
            assert settings["ai_mode"] == "byok"
            assert settings["byok_keys"] == {"openai": "x"}

    @pytest.mark.asyncio
    async def test_get_falls_back_when_no_tenant(self):
        with patch("api.services.db_tenants.get_tenant_db", new_callable=AsyncMock, return_value=None):
            settings = await get_tenant_billing_settings_db("T-1")
            assert settings["ai_mode"] == "deepseek"
            assert settings["byok_keys"] == {}

    @pytest.mark.asyncio
    async def test_set_persists_settings(self):
        with patch("api.services.db_tenants.get_tenant_db", new_callable=AsyncMock,
                   side_effect=[_fake_tenant_row('{}'), _fake_tenant_row('{"ai_mode":"byok"}')]), \
             patch("api.services.db_billing.USE_POSTGRES", False), \
             patch("api.services.db_billing._get_sqlite_conn"):
            result = await set_tenant_billing_settings_db("T-1", {"ai_mode": "byok"})
            assert result["ai_mode"] == "byok"
