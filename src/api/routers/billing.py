import os
import re
from datetime import UTC, datetime, timedelta

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel

logger = structlog.get_logger()

from api.services.auth import verify_access_token, verify_tenant_access
from api.services.database import get_billing_summary
from api.services.db_tenants import (
    create_tenant,
    get_tenant_by_stripe_customer_db,
    get_tenant_db,
    get_tenant_plan_db,
    record_usage_db,
    update_tenant_subscription_db,
)
from api.services.stripe_service import (
    create_checkout_session,
    create_portal_session,
    get_price_id,
    verify_webhook_signature,
)

router = APIRouter(prefix="/billing", tags=["billing"])


class CheckoutRequest(BaseModel):
    plan: str
    success_url: str = "/billing/success"
    cancel_url: str = "/billing/cancel"


class UsageRequest(BaseModel):
    metric: str
    quantity: float


@router.get("")
async def get_billing(
    tenant_id: str = Query(default="TENANT-001", description="Tenant ID"),
    x_api_key: str = Header(default="dev-api-key"),
    period_start: datetime = Query(default=None),
    period_end: datetime = Query(default=None),
    _=Depends(verify_tenant_access),
):
    """Get billing summary"""
    # Use verify_tenant_access for authorization

    # Default to last 7 days if not specified
    now = datetime.now(UTC)
    if period_start is None:
        period_start = now - timedelta(days=7)
    if period_end is None:
        period_end = now

    summary = await get_billing_summary(tenant_id, period_start, period_end)
    cost_per_minute = float(os.getenv("CALL_COST_PER_MINUTE", "0.015"))
    return {
        "total_calls": summary["total_calls"],
        "total_minutes": summary["total_minutes"],
        "total_cost": summary["total_cost"],
        "currency": summary["currency"],
        "breakdown": {
            "per_minute": cost_per_minute,
            "ai_minutes": summary["total_minutes"] * 0.5,
            "standard_minutes": summary["total_minutes"] * 0.5,
        },
    }


@router.post("/checkout")
async def create_checkout(
    request: CheckoutRequest,
    credentials=Depends(verify_access_token),
):
    """Create a Stripe Checkout session for subscription upgrade."""
    if not credentials:
        raise HTTPException(status_code=401, detail="Authentication required")

    tenant_id = credentials["tenant_id"]
    tenant = await get_tenant_db(tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    price_id = get_price_id(request.plan)
    if not price_id:
        raise HTTPException(status_code=400, detail="Invalid plan")

    success_url = request.success_url
    cancel_url = request.cancel_url

    session = await create_checkout_session(
        customer_id=tenant.get("stripe_customer_id"),
        price_id=price_id,
        success_url=success_url,
        cancel_url=cancel_url,
        metadata={"tenant_id": tenant_id, "plan": request.plan},
    )
    return {"checkout_url": session["url"], **session}


@router.post("/portal")
async def create_portal(
    return_url: str = "/billing",
    credentials=Depends(verify_access_token),
):
    """Create a Stripe Customer Portal session."""
    if not credentials:
        raise HTTPException(status_code=401, detail="Authentication required")

    tenant_id = credentials["tenant_id"]
    tenant = await get_tenant_db(tenant_id)
    if not tenant or not tenant.get("stripe_customer_id"):
        raise HTTPException(status_code=400, detail="No Stripe customer ID")

    session = await create_portal_session(
        customer_id=tenant["stripe_customer_id"],
        return_url=return_url,
    )
    return {"portal_url": session["url"], **session}


@router.get("/subscription")
async def get_subscription(
    credentials=Depends(verify_access_token),
):
    """Get current subscription details."""
    if not credentials:
        raise HTTPException(status_code=401, detail="Authentication required")

    tenant_id = credentials["tenant_id"]
    tenant = await get_tenant_db(tenant_id)
    plan = await get_tenant_plan_db(tenant_id)

    if not plan:
        return {
            "plan_name": "free",
            "active": False,
            "max_agents": 1,
            "max_concurrent_calls": 1,
        }

    return {
        "plan_name": plan.get("plan_name", "free"),
        "active": bool(tenant and tenant.get("stripe_subscription_id")),
        **plan,
    }


@router.post("/usage")
async def report_usage(
    request: UsageRequest,
    credentials=Depends(verify_access_token),
):
    """Report metered usage to Stripe."""
    if not credentials:
        raise HTTPException(status_code=401, detail="Authentication required")

    tenant_id = credentials["tenant_id"]
    now = datetime.now(UTC)
    period_start = now.replace(day=1).isoformat()
    period_end = now.isoformat()

    await record_usage_db(
        tenant_id=tenant_id,
        metric=request.metric,
        quantity=request.quantity,
        period_start=period_start,
        period_end=period_end,
    )
    return {"recorded": True, "quantity": request.quantity}


@router.post("/webhooks/stripe")
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(...),
):
    """Handle Stripe webhook events."""
    payload = await request.body()
    event = verify_webhook_signature(
        payload=payload,
        sig_header=stripe_signature,
        secret=os.getenv("STRIPE_WEBHOOK_SECRET", "whsec_test"),
    )

    if not event:
        raise HTTPException(status_code=400, detail="Invalid signature")

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        customer_id = session.get("customer")
        subscription_id = session.get("subscription")
        metadata = session.get("metadata", {}) or {}

        if customer_id:
            tenant = await get_tenant_by_stripe_customer_db(customer_id)
            if not tenant and subscription_id:
                # New signup (from signup_overlay365 or the general checkout):
                # provision a tenant + API key from the checkout metadata so the
                # account actually exists after payment.
                tenant_email = (
                    metadata.get("email")
                    or session.get("customer_details", {}).get("email")
                    or f"user+{customer_id}@overlay365.com"
                )
                company_name = metadata.get("company_name") or "New Overlay365 Customer"
                tenant_name = company_name
                slug = (
                    re.sub(r"[^a-z0-9]+", "-", company_name.lower()).strip("-")[:60]
                    or f"tenant-{customer_id[-8:]}"
                )
                try:
                    new_tenant = await create_tenant(
                        name=tenant_name,
                        email=tenant_email,
                        slug=slug,
                        phone=metadata.get("phone") or None,
                        plan_id=metadata.get("plan") or "PLAN-STARTER",
                        settings={
                            "source": "overlay365_signup",
                            "tier": metadata.get("tier") or "starter",
                        },
                        gdpr_consent=True,
                    )
                    if new_tenant:
                        await update_tenant_subscription_db(
                            tenant_id=new_tenant["id"],
                            stripe_customer_id=customer_id,
                            stripe_subscription_id=subscription_id,
                            plan_id=metadata.get("plan"),
                        )
                        logger.info(
                            "tenant_provisioned_from_checkout",
                            tenant_id=new_tenant["id"],
                            source="overlay365",
                        )
                        tenant = new_tenant
                except Exception as e:
                    logger.error("tenant_provision_failed", error=str(e))

            if tenant and subscription_id:
                await update_tenant_subscription_db(
                    tenant_id=tenant["id"],
                    stripe_customer_id=customer_id,
                    stripe_subscription_id=subscription_id,
                    plan_id=metadata.get("plan"),
                )

    elif event["type"] == "customer.subscription.deleted":
        subscription = event["data"]["object"]
        customer_id = subscription.get("customer")

        if customer_id:
            tenant = await get_tenant_by_stripe_customer_db(customer_id)
            if tenant:
                await update_tenant_subscription_db(
                    tenant_id=tenant["id"],
                    stripe_subscription_id=None,
                    plan_id=None,
                )

    return {"received": True, "event_type": event["type"]}
