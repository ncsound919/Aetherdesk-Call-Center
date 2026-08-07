import os
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def auth_bearer():
    """Mock HTTPBearer credentials."""
    cred = MagicMock()
    cred.credentials = "valid_test_token"
    cred.__getitem__ = MagicMock(return_value="TENANT-001")
    return cred


@pytest.fixture
def app():
    from api.routers.billing import router
    from api.services.auth import verify_tenant_access

    application = FastAPI()
    application.include_router(router, prefix="/api/v1")
    application.dependency_overrides[verify_tenant_access] = lambda: "TENANT-001"
    return application


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c


def _valid_tenant():
    return {"id": "TENANT-001", "email": "owner@acme.com", "stripe_customer_id": "cus_test"}


class TestPlans:
    def test_plans_returns_catalog(self, client):
        resp = client.get("/api/v1/billing/plans")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["rental_periods"]) == 8
        hour = next(p for p in body["rental_periods"] if p["key"] == "hour")
        assert hour["price"] == 2.0
        assert hour["included_minutes"] == 40
        assert body["rates_per_minute"] == {"byok": 0.03, "deepseek": 0.05}


class TestCheckoutRental:
    @pytest.mark.asyncio
    async def test_rental_checkout_creates_session(self, auth_bearer):
        from api.routers.billing import CheckoutRequest, create_checkout

        with patch.dict(os.environ, {"STRIPE_PRICE_RENTAL_HOUR": "price_hour"}), \
             patch("api.routers.billing.get_tenant_db", new_callable=AsyncMock, return_value=_valid_tenant()), \
             patch("api.routers.billing.create_one_time_checkout") as mock_session:

            mock_session.return_value = {"id": "cs_test", "url": "https://checkout.stripe.com/test", "mock": True}

            result = await create_checkout(
                CheckoutRequest(type="rental", period="hour", mode="deepseek", quantity=5),
                credentials=auth_bearer,
            )
            assert result["checkout_url"] == "https://checkout.stripe.com/test"
            kwargs = mock_session.call_args.kwargs
            assert kwargs["price_id"] == "price_hour"
            assert kwargs["quantity"] == 5
            assert kwargs["metadata"]["type"] == "rental"
            assert kwargs["metadata"]["period"] == "hour"

    @pytest.mark.asyncio
    async def test_rental_checkout_rejects_invalid_period(self, auth_bearer):
        from api.routers.billing import CheckoutRequest, create_checkout
        from fastapi import HTTPException

        with patch("api.routers.billing.get_tenant_db", new_callable=AsyncMock, return_value=_valid_tenant()):
            with pytest.raises(HTTPException) as exc:
                await create_checkout(CheckoutRequest(type="rental", period="bogus"), credentials=auth_bearer)
            assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_rental_checkout_unconfigured_price(self, auth_bearer):
        from api.routers.billing import CheckoutRequest, create_checkout
        from fastapi import HTTPException

        with patch.dict(os.environ, {}, clear=True), \
             patch("api.routers.billing.get_tenant_db", new_callable=AsyncMock, return_value=_valid_tenant()):
            with pytest.raises(HTTPException) as exc:
                await create_checkout(CheckoutRequest(type="rental", period="hour"), credentials=auth_bearer)
            assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_checkout_requires_auth(self):
        from api.routers.billing import CheckoutRequest, create_checkout
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            await create_checkout(CheckoutRequest(type="rental", period="hour"), credentials=None)
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_checkout_tenant_not_found(self, auth_bearer):
        from api.routers.billing import CheckoutRequest, create_checkout
        from fastapi import HTTPException

        with patch("api.routers.billing.get_tenant_db", new_callable=AsyncMock, return_value=None):
            with pytest.raises(HTTPException) as exc:
                await create_checkout(CheckoutRequest(type="rental", period="hour"), credentials=auth_bearer)
            assert exc.value.status_code == 404


class TestCheckoutTopup:
    @pytest.mark.asyncio
    async def test_topup_checkout_creates_session(self, auth_bearer):
        from api.routers.billing import CheckoutRequest, create_checkout

        with patch.dict(os.environ, {"STRIPE_PRICE_TOPUP_1000_DEEPSEEK": "price_topup"}), \
             patch("api.routers.billing.get_tenant_db", new_callable=AsyncMock, return_value=_valid_tenant()), \
             patch("api.routers.billing.create_one_time_checkout") as mock_session:

            mock_session.return_value = {"id": "cs_test", "url": "https://checkout.stripe.com/test", "mock": True}

            result = await create_checkout(
                CheckoutRequest(type="topup", pack=1000, mode="deepseek"),
                credentials=auth_bearer,
            )
            assert result["checkout_url"] == "https://checkout.stripe.com/test"
            kwargs = mock_session.call_args.kwargs
            assert kwargs["metadata"]["type"] == "topup"
            assert kwargs["metadata"]["pack"] == "1000"

    @pytest.mark.asyncio
    async def test_topup_rejects_invalid_pack(self, auth_bearer):
        from api.routers.billing import CheckoutRequest, create_checkout
        from fastapi import HTTPException

        with patch("api.routers.billing.get_tenant_db", new_callable=AsyncMock, return_value=_valid_tenant()):
            with pytest.raises(HTTPException) as exc:
                await create_checkout(CheckoutRequest(type="topup", pack=12345), credentials=auth_bearer)
            assert exc.value.status_code == 400


class TestPortal:
    @pytest.mark.asyncio
    async def test_portal_creates_session(self, auth_bearer):
        from api.routers.billing import create_portal

        with patch("api.routers.billing.create_portal_session", new_callable=AsyncMock) as mock_portal, \
             patch("api.routers.billing.get_tenant_db", new_callable=AsyncMock) as mock_get_tenant:

            mock_get_tenant.return_value = {"stripe_customer_id": "cus_test"}
            mock_portal.return_value = {"url": "https://billing.stripe.com/test", "mock": True}

            result = await create_portal(credentials=auth_bearer)
            assert result["portal_url"] == "https://billing.stripe.com/test"

    @pytest.mark.asyncio
    async def test_portal_requires_stripe_customer(self, auth_bearer):
        from api.routers.billing import create_portal
        from fastapi import HTTPException

        with patch("api.routers.billing.get_tenant_db", new_callable=AsyncMock, return_value={}):
            with pytest.raises(HTTPException) as exc:
                await create_portal(credentials=auth_bearer)
            assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_portal_requires_auth(self):
        from api.routers.billing import create_portal
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            await create_portal(credentials=None)
        assert exc.value.status_code == 401


class TestBYOK:
    @pytest.mark.asyncio
    async def test_save_byok_keys_encrypts_and_sets_mode(self, auth_bearer):
        from api.routers.billing import BYOKRequest, save_byok_keys

        with patch("api.routers.billing.get_tenant_db", new_callable=AsyncMock, return_value=_valid_tenant()), \
             patch("api.services.db_pool.encrypt_val", side_effect=lambda v: f"enc::{v}"), \
             patch("api.routers.billing.set_tenant_billing_settings_db", new_callable=AsyncMock) as mock_settings:

            mock_settings.return_value = {"ai_mode": "byok", "byok_keys": {"openai": "enc::sk-x"}}

            result = await save_byok_keys(
                BYOKRequest(keys={"openai": "sk-x"}), credentials=auth_bearer
            )
            assert result["success"] is True
            assert result["mode"] == "byok"
            updates = mock_settings.call_args.args[1]
            assert updates["ai_mode"] == "byok"
            assert updates["byok_keys"]["openai"] == "enc::sk-x"

    @pytest.mark.asyncio
    async def test_save_byok_requires_auth(self):
        from api.routers.billing import BYOKRequest, save_byok_keys
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            await save_byok_keys(BYOKRequest(keys={"openai": "sk-x"}), credentials=None)
        assert exc.value.status_code == 401


class TestWebhook:
    @pytest.fixture
    def mock_request(self):
        req = MagicMock()
        req.body = AsyncMock(return_value=b'{"type":"webhook"}')
        return req

    @pytest.mark.asyncio
    async def test_webhook_activates_rental(self, mock_request):
        from api.routers.billing import stripe_webhook

        event = {
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": "cs_rental_1",
                    "customer": "cus_test",
                    "payment_intent": "pi_test",
                    "metadata": {
                        "tenant_id": "TENANT-001",
                        "type": "rental",
                        "period": "hour",
                        "mode": "deepseek",
                        "quantity": "2",
                    },
                }
            },
        }

        with patch("api.routers.billing.verify_webhook_signature", return_value=event), \
             patch("api.routers.billing.get_tenant_db", new_callable=AsyncMock, return_value=_valid_tenant()), \
             patch("api.routers.billing.get_rental_by_session_db", new_callable=AsyncMock, return_value=None), \
             patch("api.routers.billing.set_tenant_billing_settings_db", new_callable=AsyncMock), \
             patch("api.routers.billing.activate_rental_db", new_callable=AsyncMock) as mock_activate:

            result = await stripe_webhook(mock_request, stripe_signature="t=123,v1=abc")

            assert result["received"] is True
            kwargs = mock_activate.call_args.kwargs
            assert kwargs["period"] == "hour"
            assert kwargs["quantity"] == 2
            assert kwargs["included_minutes"] == 80  # 40 min * 2 agents
            assert kwargs["stripe_session_id"] == "cs_rental_1"

    @pytest.mark.asyncio
    async def test_webhook_rental_idempotent(self, mock_request):
        from api.routers.billing import stripe_webhook

        event = {
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": "cs_rental_1",
                    "metadata": {
                        "tenant_id": "TENANT-001",
                        "type": "rental",
                        "period": "hour",
                        "mode": "deepseek",
                        "quantity": "1",
                    },
                }
            },
        }

        with patch("api.routers.billing.verify_webhook_signature", return_value=event), \
             patch("api.routers.billing.get_rental_by_session_db", new_callable=AsyncMock, return_value={"id": "r1"}), \
             patch("api.routers.billing.activate_rental_db", new_callable=AsyncMock) as mock_activate:

            await stripe_webhook(mock_request, stripe_signature="t=123,v1=abc")
            mock_activate.assert_not_called()

    @pytest.mark.asyncio
    async def test_webhook_credits_topup(self, mock_request):
        from api.routers.billing import stripe_webhook

        event = {
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": "cs_topup_1",
                    "metadata": {
                        "tenant_id": "TENANT-001",
                        "type": "topup",
                        "pack": "1000",
                        "quantity": "1",
                    },
                }
            },
        }

        with patch("api.routers.billing.verify_webhook_signature", return_value=event), \
             patch("api.routers.billing.get_rental_by_session_db", new_callable=AsyncMock, return_value=None), \
             patch("api.routers.billing.credit_minutes_db", new_callable=AsyncMock) as mock_credit:

            await stripe_webhook(mock_request, stripe_signature="t=123,v1=abc")
            mock_credit.assert_awaited_once_with("TENANT-001", 1000)

    @pytest.mark.asyncio
    async def test_webhook_handles_subscription_deleted(self, mock_request):
        from api.routers.billing import stripe_webhook

        with patch("api.routers.billing.verify_webhook_signature") as mock_verify, \
             patch("api.routers.billing.get_tenant_by_stripe_customer_db", new_callable=AsyncMock) as mock_lookup, \
             patch("api.routers.billing.update_tenant_subscription_db", new_callable=AsyncMock) as mock_update:

            mock_verify.return_value = {
                "type": "customer.subscription.deleted",
                "data": {"object": {"customer": "cus_test"}},
            }
            mock_lookup.return_value = {"id": "tenant-1"}

            result = await stripe_webhook(mock_request, stripe_signature="t=123,v1=abc")
            assert result["event_type"] == "customer.subscription.deleted"
            mock_update.assert_called_once()

    @pytest.mark.asyncio
    async def test_webhook_rejects_invalid_signature(self, mock_request):
        from api.routers.billing import stripe_webhook
        from fastapi import HTTPException

        with patch("api.routers.billing.verify_webhook_signature", return_value=None):
            with pytest.raises(HTTPException) as exc:
                await stripe_webhook(mock_request, stripe_signature="invalid")
            assert exc.value.status_code == 400


class TestSubscription:
    @pytest.mark.asyncio
    async def test_subscription_returns_rental(self, auth_bearer):
        from api.routers.billing import get_subscription

        rental = {
            "period": "day",
            "quantity": 2,
            "included_minutes": 640,
            "rental_start": "2026-01-01",
            "rental_end": "2026-01-02",
        }

        with patch("api.routers.billing.get_tenant_db", new_callable=AsyncMock, return_value=_valid_tenant()), \
             patch("api.routers.billing.get_active_rental_db", new_callable=AsyncMock, return_value=rental), \
             patch("api.routers.billing.get_minute_balance_db", new_callable=AsyncMock, return_value=700), \
             patch("api.routers.billing.get_tenant_billing_settings_db", new_callable=AsyncMock,
                   return_value={"ai_mode": "deepseek"}):

            result = await get_subscription(credentials=auth_bearer)
            assert result["plan_name"] == "day"
            assert result["active"] is True
            assert result["minute_balance"] == 700
            assert result["included_minutes"] == 640

    @pytest.mark.asyncio
    async def test_subscription_defaults_to_free(self, auth_bearer):
        from api.routers.billing import get_subscription

        with patch("api.routers.billing.get_tenant_db", new_callable=AsyncMock, return_value=_valid_tenant()), \
             patch("api.routers.billing.get_active_rental_db", new_callable=AsyncMock, return_value=None), \
             patch("api.routers.billing.get_minute_balance_db", new_callable=AsyncMock, return_value=0), \
             patch("api.routers.billing.get_tenant_billing_settings_db", new_callable=AsyncMock,
                   return_value={"ai_mode": "deepseek"}):

            result = await get_subscription(credentials=auth_bearer)
            assert result["plan_name"] == "free"
            assert result["active"] is False

    @pytest.mark.asyncio
    async def test_subscription_requires_auth(self):
        from api.routers.billing import get_subscription
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            await get_subscription(credentials=None)
        assert exc.value.status_code == 401


class TestUsage:
    @pytest.mark.asyncio
    async def test_usage_recorded(self, auth_bearer):
        from api.routers.billing import UsageRequest, report_usage

        with patch("api.routers.billing.record_usage_db", new_callable=AsyncMock) as mock_record:
            result = await report_usage(
                UsageRequest(metric="agent_minutes", quantity=42.5), credentials=auth_bearer
            )
            assert result["recorded"] is True
            mock_record.assert_called_once()

    @pytest.mark.asyncio
    async def test_usage_requires_auth(self):
        from api.routers.billing import UsageRequest, report_usage
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            await report_usage(UsageRequest(metric="agent_minutes", quantity=1.0), credentials=None)
        assert exc.value.status_code == 401


class TestGetBilling:
    def test_get_billing_returns_unified_payload(self, client):
        mock_summary = {
            "total_calls": 50,
            "total_minutes": 120.0,
            "total_cost": 1.80,
            "currency": "USD",
        }
        rental = {
            "period": "day",
            "quantity": 1,
            "included_minutes": 320,
            "rental_start": "2026-01-01T00:00:00Z",
            "rental_end": "2026-01-02T00:00:00Z",
        }

        with patch("api.routers.billing.get_billing_summary", new_callable=AsyncMock, return_value=mock_summary), \
             patch("api.routers.billing.get_active_rental_db", new_callable=AsyncMock, return_value=rental), \
             patch("api.routers.billing.get_minute_balance_db", new_callable=AsyncMock, return_value=250), \
             patch("api.routers.billing.get_tenant_billing_settings_db", new_callable=AsyncMock,
                   return_value={"ai_mode": "deepseek"}):

            resp = client.get("/api/v1/billing")

            assert resp.status_code == 200
            body = resp.json()
            assert body["plan"] == "day"
            assert body["status"] == "active"
            assert body["minute_balance"] == 250
            assert body["minutes_limit"] == 320
            assert body["price_per_min"] == 0.05
            assert body["calls_this_month"] == 50

    def test_get_billing_free_when_no_rental(self, client):
        mock_summary = {
            "total_calls": 0,
            "total_minutes": 0.0,
            "total_cost": 0.0,
            "currency": "USD",
        }

        with patch("api.routers.billing.get_billing_summary", new_callable=AsyncMock, return_value=mock_summary), \
             patch("api.routers.billing.get_active_rental_db", new_callable=AsyncMock, return_value=None), \
             patch("api.routers.billing.get_minute_balance_db", new_callable=AsyncMock, return_value=0), \
             patch("api.routers.billing.get_tenant_billing_settings_db", new_callable=AsyncMock,
                   return_value={"ai_mode": "deepseek"}):

            resp = client.get("/api/v1/billing")

            body = resp.json()
            assert body["plan"] == "free"
            assert body["status"] == "inactive"


class TestPlanEnforcement:
    @pytest.mark.asyncio
    async def test_agent_limit_exceeded(self):
        from api.services.plan_enforcement import check_agent_limit

        with patch("api.services.db_tenants.get_tenant_plan_db", new_callable=AsyncMock) as mock_plan, \
             patch("api.services.db_tenants.count_active_agents_db", new_callable=AsyncMock) as mock_count:

            mock_plan.return_value = {"plan_name": "starter", "max_agents": 2}
            mock_count.return_value = 2

            ok, info = await check_agent_limit("tenant-1")
            assert ok is False
            assert info["limit"] == 2

    @pytest.mark.asyncio
    async def test_call_limit_ok(self):
        from api.services.plan_enforcement import check_call_limit

        with patch("api.services.db_tenants.get_tenant_plan_db", new_callable=AsyncMock) as mock_plan, \
             patch("api.services.db_tenants.count_active_calls_db", new_callable=AsyncMock) as mock_count:

            mock_plan.return_value = {"plan_name": "enterprise", "max_concurrent_calls": 50}
            mock_count.return_value = 10

            ok, info = await check_call_limit("tenant-1")
            assert ok is True
