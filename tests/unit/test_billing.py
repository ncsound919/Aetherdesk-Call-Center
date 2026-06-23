import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


@pytest.fixture
def auth_bearer():
    """Mock HTTPBearer credentials."""
    cred = MagicMock()
    cred.credentials = "valid_test_token"
    return cred


class TestCheckout:
    @pytest.mark.asyncio
    async def test_checkout_creates_session(self, auth_bearer):
        from apps.api.routers.billing import create_checkout, CheckoutRequest

        with patch("apps.api.services.stripe_service.get_price_id", return_value="price_test"), \
             patch("apps.api.services.stripe_service.create_checkout_session") as mock_session, \
             patch("apps.api.services.auth.verify_access_token", new_callable=AsyncMock) as mock_verify, \
             patch("apps.api.services.db_tenants.get_tenant_db", new_callable=AsyncMock) as mock_get_tenant, \
             patch("apps.api.services.db_tenants.update_tenant_subscription_db", new_callable=AsyncMock):

            mock_verify.return_value = {"tenant_id": "tenant-1", "email": "user@test.com"}
            mock_get_tenant.return_value = {}
            mock_session.return_value = {"id": "cs_test", "url": "https://checkout.stripe.com/test", "mock": True}

            result = await create_checkout(CheckoutRequest(plan="pro"), credentials=auth_bearer)
            assert result["checkout_url"] == "https://checkout.stripe.com/test"
            assert result["mock"] is True
            mock_session.assert_called_once()

    @pytest.mark.asyncio
    async def test_checkout_rejects_unknown_plan(self, auth_bearer):
        from apps.api.routers.billing import create_checkout, CheckoutRequest
        from fastapi import HTTPException

        with patch("apps.api.services.stripe_service.get_price_id", return_value=None), \
             patch("apps.api.services.auth.verify_access_token", new_callable=AsyncMock) as mock_verify:
            mock_verify.return_value = {"tenant_id": "tenant-1", "email": "user@test.com"}

            with pytest.raises(HTTPException) as exc:
                await create_checkout(CheckoutRequest(plan="bogus"), credentials=auth_bearer)
            assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_checkout_requires_auth(self):
        from apps.api.routers.billing import create_checkout, CheckoutRequest
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            await create_checkout(CheckoutRequest(plan="pro"), credentials=None)
        assert exc.value.status_code == 401


class TestPortal:
    @pytest.mark.asyncio
    async def test_portal_creates_session(self, auth_bearer):
        from apps.api.routers.billing import create_portal

        with patch("apps.api.services.stripe_service.create_portal_session") as mock_portal, \
             patch("apps.api.services.auth.verify_access_token", new_callable=AsyncMock) as mock_verify, \
             patch("apps.api.services.db_tenants.get_tenant_db", new_callable=AsyncMock) as mock_get_tenant:

            mock_verify.return_value = {"tenant_id": "tenant-1"}
            mock_get_tenant.return_value = {"stripe_customer_id": "cus_test"}
            mock_portal.return_value = {"url": "https://billing.stripe.com/test", "mock": True}

            result = await create_portal(credentials=auth_bearer)
            assert result["portal_url"] == "https://billing.stripe.com/test"
            assert result["mock"] is True

    @pytest.mark.asyncio
    async def test_portal_requires_stripe_customer(self, auth_bearer):
        from apps.api.routers.billing import create_portal
        from fastapi import HTTPException

        with patch("apps.api.services.auth.verify_access_token", new_callable=AsyncMock) as mock_verify, \
             patch("apps.api.services.db_tenants.get_tenant_db", new_callable=AsyncMock) as mock_get_tenant:
            mock_verify.return_value = {"tenant_id": "tenant-1"}
            mock_get_tenant.return_value = {}

            with pytest.raises(HTTPException) as exc:
                await create_portal(credentials=auth_bearer)
            assert exc.value.status_code == 400


class TestWebhook:
    @pytest.fixture
    def mock_request(self):
        req = MagicMock()
        req.body = AsyncMock(return_value=b'{"type":"webhook"}')
        return req

    @pytest.mark.asyncio
    async def test_webhook_handles_checkout_completed(self, mock_request):
        from apps.api.routers.billing import stripe_webhook

        with patch("apps.api.services.stripe_service.verify_webhook_signature") as mock_verify, \
             patch("apps.api.services.db_tenants.get_tenant_by_stripe_customer_db", new_callable=AsyncMock) as mock_lookup, \
             patch("apps.api.services.db_tenants.update_tenant_subscription_db", new_callable=AsyncMock) as mock_update:

            mock_verify.return_value = {
                "type": "checkout.session.completed",
                "data": {"object": {"customer": "cus_test", "subscription": "sub_test"}}
            }
            mock_lookup.return_value = {"id": "tenant-1"}

            result = await stripe_webhook(mock_request, stripe_signature="t=123,v1=abc")
            assert result["received"] is True
            assert result["event_type"] == "checkout.session.completed"
            mock_update.assert_called_once()

    @pytest.mark.asyncio
    async def test_webhook_handles_subscription_deleted(self, mock_request):
        from apps.api.routers.billing import stripe_webhook

        with patch("apps.api.services.stripe_service.verify_webhook_signature") as mock_verify, \
             patch("apps.api.services.db_tenants.get_tenant_by_stripe_customer_db", new_callable=AsyncMock) as mock_lookup, \
             patch("apps.api.services.db_tenants.update_tenant_subscription_db", new_callable=AsyncMock) as mock_update:

            mock_verify.return_value = {
                "type": "customer.subscription.deleted",
                "data": {"object": {"customer": "cus_test"}}
            }
            mock_lookup.return_value = {"id": "tenant-1"}

            result = await stripe_webhook(mock_request, stripe_signature="t=123,v1=abc")
            assert result["received"] is True
            assert result["event_type"] == "customer.subscription.deleted"
            mock_update.assert_called_once()

    @pytest.mark.asyncio
    async def test_webhook_rejects_invalid_signature(self, mock_request):
        from apps.api.routers.billing import stripe_webhook
        from fastapi import HTTPException

        with patch("apps.api.services.stripe_service.verify_webhook_signature", return_value=None):
            with pytest.raises(HTTPException) as exc:
                await stripe_webhook(mock_request, stripe_signature="invalid")
            assert exc.value.status_code == 400


class TestSubscription:
    @pytest.mark.asyncio
    async def test_subscription_returns_plan(self, auth_bearer):
        from apps.api.routers.billing import get_subscription

        with patch("apps.api.services.auth.verify_access_token", new_callable=AsyncMock) as mock_verify, \
             patch("apps.api.services.db_tenants.get_tenant_db", new_callable=AsyncMock) as mock_get_tenant, \
             patch("apps.api.services.db_tenants.get_tenant_plan_db", new_callable=AsyncMock) as mock_get_plan:

            mock_verify.return_value = {"tenant_id": "tenant-1"}
            mock_get_tenant.return_value = {"stripe_subscription_id": "sub_test"}
            mock_get_plan.return_value = {"plan_name": "pro", "max_concurrent_calls": 10, "max_agents": 10}

            result = await get_subscription(credentials=auth_bearer)
            assert result["plan_name"] == "pro"
            assert result["active"] is True
            assert result["max_agents"] == 10

    @pytest.mark.asyncio
    async def test_subscription_defaults_to_free(self, auth_bearer):
        from apps.api.routers.billing import get_subscription

        with patch("apps.api.services.auth.verify_access_token", new_callable=AsyncMock) as mock_verify, \
             patch("apps.api.services.db_tenants.get_tenant_db", new_callable=AsyncMock) as mock_get_tenant, \
             patch("apps.api.services.db_tenants.get_tenant_plan_db", new_callable=AsyncMock) as mock_get_plan:

            mock_verify.return_value = {"tenant_id": "tenant-1"}
            mock_get_tenant.return_value = None
            mock_get_plan.return_value = None

            result = await get_subscription(credentials=auth_bearer)
            assert result["plan_name"] == "free"
            assert result["active"] is False


class TestUsage:
    @pytest.mark.asyncio
    async def test_usage_recorded(self, auth_bearer):
        from apps.api.routers.billing import report_usage, UsageRequest

        with patch("apps.api.services.auth.verify_access_token", new_callable=AsyncMock) as mock_verify, \
             patch("apps.api.services.db_tenants.record_usage_db", new_callable=AsyncMock) as mock_record:

            mock_verify.return_value = {"tenant_id": "tenant-1"}

            result = await report_usage(UsageRequest(metric="agent_minutes", quantity=42.5), credentials=auth_bearer)
            assert result["recorded"] is True
            assert result["quantity"] == 42.5
            mock_record.assert_called_once()


class TestPlanEnforcement:
    @pytest.mark.asyncio
    async def test_agent_limit_exceeded(self):
        from apps.api.services.plan_enforcement import check_agent_limit

        with patch("apps.api.services.db_tenants.get_tenant_plan_db", new_callable=AsyncMock) as mock_plan, \
             patch("apps.api.services.db_tenants.count_active_agents_db", new_callable=AsyncMock) as mock_count:

            mock_plan.return_value = {"plan_name": "starter", "max_agents": 2}
            mock_count.return_value = 2

            ok, info = await check_agent_limit("tenant-1")
            assert ok is False
            assert info["limit"] == 2
            assert info["plan"] == "starter"

    @pytest.mark.asyncio
    async def test_agent_limit_ok(self):
        from apps.api.services.plan_enforcement import check_agent_limit

        with patch("apps.api.services.db_tenants.get_tenant_plan_db", new_callable=AsyncMock) as mock_plan, \
             patch("apps.api.services.db_tenants.count_active_agents_db", new_callable=AsyncMock) as mock_count:

            mock_plan.return_value = {"plan_name": "pro", "max_agents": 10}
            mock_count.return_value = 5

            ok, info = await check_agent_limit("tenant-1")
            assert ok is True
            assert info["current"] == 5

    @pytest.mark.asyncio
    async def test_call_limit_exceeded(self):
        from apps.api.services.plan_enforcement import check_call_limit

        with patch("apps.api.services.db_tenants.get_tenant_plan_db", new_callable=AsyncMock) as mock_plan, \
             patch("apps.api.services.db_tenants.count_active_calls_db", new_callable=AsyncMock) as mock_count:

            mock_plan.return_value = {"plan_name": "starter", "max_concurrent_calls": 2}
            mock_count.return_value = 2

            ok, info = await check_call_limit("tenant-1")
            assert ok is False
            assert info["resource"] == "concurrent_calls"

    @pytest.mark.asyncio
    async def test_call_limit_ok(self):
        from apps.api.services.plan_enforcement import check_call_limit

        with patch("apps.api.services.db_tenants.get_tenant_plan_db", new_callable=AsyncMock) as mock_plan, \
             patch("apps.api.services.db_tenants.count_active_calls_db", new_callable=AsyncMock) as mock_count:

            mock_plan.return_value = {"plan_name": "enterprise", "max_concurrent_calls": 50}
            mock_count.return_value = 10

            ok, info = await check_call_limit("tenant-1")
            assert ok is True
            assert info["limit"] == 50