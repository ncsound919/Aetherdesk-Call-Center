import os
from datetime import UTC, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Header, Query, Request, HTTPException
from pydantic import BaseModel

from apps.api.services.auth import verify_access_token, verify_tenant_access
from apps.api.services.database import get_billing_summary
from apps.api.services.db_tenants import (
    get_tenant_db,
    update_tenant_subscription_db,
    get_tenant_by_stripe_customer_db,
    get_tenant_plan_db,
    record_usage_db,
)
from apps.api.services.stripe_service import (
    get_price_id,
    create_checkout_session,
    create_portal_session,
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


@router.get("/billing")
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
    return {
        "total_calls": summary["total_calls"],
        "total_minutes": summary["total_minutes"],
        "total_cost": summary["total_cost"],
        "currency": summary["currency"],
        "breakdown": {
            "per_minute": 0.015,
            "ai_minutes": summary["total_minutes"] * 0.5,
            "standard_minutes": summary["total_minutes"] * 0.5,
        },
    }


@router.post("/billing/checkout")
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


@router.post("/billing/portal")
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


@router.get("/billing/subscription")
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


@router.post("/billing/usage")
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

        if customer_id and subscription_id:
            tenant = await get_tenant_by_stripe_customer_db(customer_id)
            if tenant:
                await update_tenant_subscription_db(
                    tenant_id=tenant["id"],
                    stripe_customer_id=customer_id,
                    stripe_subscription_id=subscription_id,
                    plan_id=session.get("metadata", {}).get("plan"),
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
