"""Tests for the Overlay365 signup router."""

from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers.signup_overlay365 import SignupRequest, _create_checkout, router


@pytest.fixture
def app():
    application = FastAPI()
    application.include_router(router)
    return application


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c


class TestPricingTiers:
    def test_tiers_endpoint(self, client):
        resp = client.get("/api/v1/signup/tiers")
        assert resp.status_code == 200
        tiers = resp.json()["tiers"]
        assert len(tiers) == 4
        ids = {t["id"] for t in tiers}
        assert ids == {"starter", "pro", "scale", "enterprise"}
        # Tiers are ordered cheapest first
        prices = [t["price"] for t in tiers]
        assert prices == sorted(prices)


class TestCreateCheckout:
    @pytest.mark.asyncio
    async def test_mock_checkout_when_no_stripe_key(self):
        req = SignupRequest(
            email="test@example.com",
            company_name="Acme",
            tier="pro",
        )
        env = {"STRIPE_PRICE_PRO": "price_pro", "STRIPE_PRICE_STARTER": "price_starter"}
        with patch.dict("os.environ", env, clear=True):
            result = await _create_checkout(req)
        assert result.status == "mock_checkout"
        assert "overlay365.com" in result.checkout_url
        assert "test%40example.com" in result.checkout_url
        assert result.tier == "pro"
        assert result.customer_id.startswith("mock_cus_")

    @pytest.mark.asyncio
    async def test_mock_checkout_default_tier(self):
        req = SignupRequest(email="x@example.com", company_name="X")
        env = {"STRIPE_PRICE_STARTER": "price_starter", "STRIPE_PRICE_PRO": "price_pro"}
        with patch.dict("os.environ", env, clear=True):
            result = await _create_checkout(req)
        assert result.tier == "starter"

    @pytest.mark.asyncio
    async def test_missing_price_id_raises_400(self):
        req = SignupRequest(email="x@example.com", company_name="X", tier="pro")
        # Stripe key present (so not mock mode) but STRIPE_PRICE_PRO unset
        with patch.dict("os.environ", {"STRIPE_SECRET_KEY": "sk_live_123"}, clear=True):
            from fastapi import HTTPException
            with pytest.raises(HTTPException) as exc:
                await _create_checkout(req)
            assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_real_stripe_checkout(self):
        req = SignupRequest(email="x@example.com", company_name="X", tier="pro")
        mock_session = type("S", (), {"url": "https://checkout.stripe.com/c/pay", "customer": "cus_123"})
        env = {
            "STRIPE_SECRET_KEY": "sk_live_123",
            "STRIPE_PRICE_PRO": "price_123",
            "STRIPE_PRICE_STARTER": "price_starter",
        }
        with patch.dict("os.environ", env, clear=True), \
             patch("stripe.checkout.Session.create", return_value=mock_session) as mock_create:
            result = await _create_checkout(req)
        assert result.status == "success"
        assert result.checkout_url == "https://checkout.stripe.com/c/pay"
        assert result.customer_id == "cus_123"
        mock_create.assert_called_once()
        assert mock_create.call_args.kwargs["mode"] == "subscription"
        assert mock_create.call_args.kwargs["customer_email"] == "x@example.com"


def _env_with_price(key):
    env = {
        "STRIPE_SECRET_KEY": "sk_live_123",
        "STRIPE_PRICE_PRO": "price_123",
        "STRIPE_PRICE_STARTER": None,
        "STRIPE_PRICE_SCALE": None,
        "STRIPE_PRICE_ENTERPRISE": None,
    }
    return env.get(key)
