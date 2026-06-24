"""Stripe SDK wrapper.

When STRIPE_SECRET_KEY is unset, all functions return mock data so dev/test
environments work without network calls. In production, set STRIPE_SECRET_KEY
in the environment.
"""
import os
from typing import Any, Optional

import structlog

logger = structlog.get_logger()

_STRIPE_ENABLED = bool(os.getenv("STRIPE_SECRET_KEY", "").strip())

if _STRIPE_ENABLED:
    try:
        import stripe
        stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
        _stripe = stripe
    except ImportError:
        logger.warning("stripe package not installed; running in mock mode")
        _stripe = None
        _STRIPE_ENABLED = False
else:
    _stripe = None


def is_stripe_enabled() -> bool:
    """Return True if Stripe SDK is configured."""
    return _STRIPE_ENABLED and _stripe is not None


def get_price_id(plan: str) -> Optional[str]:
    """Map plan name → Stripe price_id from env."""
    return os.getenv(f"STRIPE_PRICE_{plan.upper()}")


def create_checkout_session(customer_id: str, price_id: str, success_url: str, cancel_url: str, metadata: Optional[dict] = None) -> dict:
    """Create a Stripe Checkout session for subscription upgrade."""
    if not is_stripe_enabled():
        # Mock response for dev/test
        return {
            "id": f"cs_mock_{price_id}",
            "url": f"{success_url}?mock=true",
            "mock": True,
        }
    session = _stripe.checkout.Session.create(
        customer=customer_id,
        mode="subscription",
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=success_url,
        cancel_url=cancel_url,
        metadata=metadata or {},
    )
    return {"id": session.id, "url": session.url, "mock": False}


def create_portal_session(customer_id: str, return_url: str) -> dict:
    """Create a Stripe Customer Portal session."""
    if not is_stripe_enabled():
        return {
            "id": f"portal_mock_{customer_id}",
            "url": f"{return_url}?mock=true",
            "mock": True,
        }
    portal = _stripe.billing_portal.Session.create(
        customer=customer_id,
        return_url=return_url,
    )
    return {"id": portal.id, "url": portal.url, "mock": False}


def get_customer(customer_id: str) -> dict:
    """Retrieve Stripe customer details."""
    if not is_stripe_enabled():
        return {"id": customer_id, "email": "mock@example.com", "mock": True}
    return _stripe.Customer.retrieve(customer_id).to_dict()


def create_customer(email: str, name: Optional[str] = None, metadata: Optional[dict] = None) -> dict:
    """Create a new Stripe customer."""
    if not is_stripe_enabled():
        return {
            "id": f"cus_mock_{email.replace('@', '_').replace('.', '_')}",
            "email": email,
            "mock": True,
        }
    customer = _stripe.Customer.create(email=email, name=name, metadata=metadata or {})
    return customer.to_dict()


def report_usage(subscription_item_id: str, quantity: int, timestamp: Optional[int] = None) -> dict:
    """Report metered usage to Stripe."""
    if not is_stripe_enabled():
        return {"id": f"mbur_mock_{subscription_item_id}", "quantity": quantity, "mock": True}
    usage = _stripe.SubscriptionItem.create_usage_record(
        subscription_item_id,
        quantity=quantity,
        timestamp=timestamp,
    )
    return usage.to_dict()


def verify_webhook_signature(payload: bytes, sig_header: str, secret: str) -> Optional[Any]:
    """Verify and parse Stripe webhook signature."""
    if not is_stripe_enabled():
        # In mock mode, try to parse JSON directly
        import json
        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            return None
    try:
        return _stripe.Webhook.construct_event(payload, sig_header, secret)
    except Exception as e:
        logger.error("stripe_webhook_verify_failed", error=str(e))
        return None

