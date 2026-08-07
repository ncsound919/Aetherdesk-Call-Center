import os
import re
from datetime import UTC, datetime, timedelta
from typing import Literal

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field

logger = structlog.get_logger()

from api.services.auth import verify_access_token, verify_tenant_access
from api.services.database import get_billing_summary
from api.services.db_billing import (
    activate_rental_db,
    credit_minutes_db,
    get_active_rental_db,
    get_minute_balance_db,
    get_rental_by_session_db,
    get_tenant_billing_settings_db,
    set_tenant_billing_settings_db,
)
from api.services.db_tenants import (
    create_tenant,
    get_tenant_by_stripe_customer_db,
    get_tenant_db,
    record_usage_db,
    update_tenant_subscription_db,
)
from api.services.pricing import (
    RATE_PER_MINUTE,
    catalog,
    get_period,
    rental_price_env,
    rental_window,
    topup_price,
    topup_price_env,
)
from api.services.stripe_service import (
    create_one_time_checkout,
    create_portal_session,
    verify_webhook_signature,
)

router = APIRouter(prefix="/billing", tags=["billing"])

# Default checkout URLs (overridable per request)
_DEFAULT_SUCCESS = "/billing?success=true"
_DEFAULT_CANCEL = "/billing?canceled=true"


class CheckoutRequest(BaseModel):
    type: Literal["rental", "topup"] = "rental"
    period: str | None = None
    pack: int | None = None
    mode: Literal["byok", "deepseek"] = "deepseek"
    quantity: int = Field(default=1, ge=1, le=100)
    success_url: str = _DEFAULT_SUCCESS
    cancel_url: str = _DEFAULT_CANCEL


class BYOKRequest(BaseModel):
    keys: dict[str, str] = Field(..., description="provider -> api key")


class UsageRequest(BaseModel):
    metric: str
    quantity: float


@router.get("/plans")
async def get_plans():
    """Public pricing catalog (rental periods, rates, top-up packs)."""
    return catalog()


@router.get("")
async def get_billing(
    tenant_id: str = Query(default="TENANT-001", description="Tenant ID"),
    x_api_key: str = Header(default="dev-api-key"),
    period_start: datetime = Query(default=None),
    period_end: datetime = Query(default=None),
    _=Depends(verify_tenant_access),
):
    """Get unified billing payload for the tenant."""
    now = datetime.now(UTC)
    if period_start is None:
        period_start = now - timedelta(days=7)
    if period_end is None:
        period_end = now

    summary = await get_billing_summary(tenant_id, period_start, period_end)
    rental = await get_active_rental_db(tenant_id)
    balance = await get_minute_balance_db(tenant_id)
    settings = await get_tenant_billing_settings_db(tenant_id)
    mode = settings.get("ai_mode", "deepseek")
    price_per_min = RATE_PER_MINUTE.get(mode, RATE_PER_MINUTE["deepseek"])

    return {
        "plan": (rental["period"] if rental else "free"),
        "mode": mode,
        "status": "active" if rental else "inactive",
        "rental_start": rental["rental_start"] if rental else None,
        "rental_end": rental["rental_end"] if rental else None,
        "rental_quantity": rental["quantity"] if rental else 0,
        "calls_this_month": summary["total_calls"],
        "minutes_used": round(summary["total_minutes"], 2),
        "minute_balance": balance,
        "minutes_limit": rental["included_minutes"] if rental else None,
        "calls_limit": None,
        "total_cost": summary["total_cost"],
        "currency": summary["currency"],
        "price_per_min": price_per_min,
        "breakdown": {
            "per_minute": price_per_min,
            "ai_minutes": round(summary["total_minutes"] * 0.5, 2),
            "standard_minutes": round(summary["total_minutes"] * 0.5, 2),
        },
    }


@router.post("/checkout")
async def create_checkout(
    request: CheckoutRequest,
    credentials=Depends(verify_access_token),
):
    """Create a one-time Stripe Checkout session for a rental or top-up."""
    if not credentials:
        raise HTTPException(status_code=401, detail="Authentication required")

    tenant_id = credentials["tenant_id"]
    tenant = await get_tenant_db(tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    metadata = {
        "tenant_id": tenant_id,
        "type": request.type,
        "mode": request.mode,
        "quantity": str(request.quantity),
    }

    if request.type == "rental":
        period = get_period(request.period) if request.period else None
        if period is None:
            raise HTTPException(status_code=400, detail="Invalid rental period")
        price_id = os.getenv(rental_price_env(period.key))
        if not price_id:
            raise HTTPException(
                status_code=400,
                detail=f"Billing not configured for period '{period.key}'",
            )
        metadata.update({"period": period.key})
        session = create_one_time_checkout(
            price_id=price_id,
            quantity=request.quantity,
            success_url=request.success_url,
            cancel_url=request.cancel_url,
            metadata=metadata,
            customer_email=tenant.get("email"),
        )
    elif request.type == "topup":
        price = topup_price(request.pack, request.mode)
        if price is None:
            raise HTTPException(status_code=400, detail="Invalid top-up pack")
        price_id = os.getenv(topup_price_env(request.pack, request.mode))
        if not price_id:
            raise HTTPException(
                status_code=400,
                detail=f"Billing not configured for top-up pack {request.pack} ({request.mode})",
            )
        metadata.update({"pack": str(request.pack)})
        session = create_one_time_checkout(
            price_id=price_id,
            quantity=request.quantity,
            success_url=request.success_url,
            cancel_url=request.cancel_url,
            metadata=metadata,
            customer_email=tenant.get("email"),
        )
    else:
        raise HTTPException(status_code=400, detail="Invalid checkout type")

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


@router.put("/byok")
async def save_byok_keys(
    request: BYOKRequest,
    credentials=Depends(verify_access_token),
):
    """Store the tenant's own LLM API keys (BYOK mode), encrypted at rest."""
    if not credentials:
        raise HTTPException(status_code=401, detail="Authentication required")

    tenant_id = credentials["tenant_id"]
    tenant = await get_tenant_db(tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    from api.services.db_pool import encrypt_val

    encrypted = {provider: encrypt_val(key) for provider, key in request.keys.items()}
    settings = await set_tenant_billing_settings_db(
        tenant_id, {"byok_keys": encrypted, "ai_mode": "byok"}
    )
    return {
        "success": True,
        "mode": settings.get("ai_mode", "byok"),
        "providers": list(request.keys.keys()),
    }


@router.get("/subscription")
async def get_subscription(
    credentials=Depends(verify_access_token),
):
    """Get current rental/subscription details."""
    if not credentials:
        raise HTTPException(status_code=401, detail="Authentication required")

    tenant_id = credentials["tenant_id"]
    rental = await get_active_rental_db(tenant_id)
    balance = await get_minute_balance_db(tenant_id)
    settings = await get_tenant_billing_settings_db(tenant_id)

    if not rental:
        return {
            "plan_name": "free",
            "active": False,
            "mode": settings.get("ai_mode", "deepseek"),
            "minute_balance": balance,
        }

    return {
        "plan_name": rental["period"],
        "active": True,
        "mode": settings.get("ai_mode", "deepseek"),
        "rental_start": rental["rental_start"],
        "rental_end": rental["rental_end"],
        "included_minutes": rental["included_minutes"],
        "minute_balance": balance,
        "quantity": rental["quantity"],
    }


@router.post("/usage")
async def report_usage(
    request: UsageRequest,
    credentials=Depends(verify_access_token),
):
    """Report metered usage (internal)."""
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
    """Handle Stripe webhook events (one-time checkout payments)."""
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
        metadata = session.get("metadata", {}) or {}
        customer_id = session.get("customer")
        payment_intent = session.get("payment_intent")
        checkout_type = metadata.get("type", "rental")

        if checkout_type == "rental":
            await _handle_rental_completed(
                metadata, customer_id, payment_intent, session.get("id")
            )
        elif checkout_type == "topup":
            await _handle_topup_completed(metadata, customer_id, session.get("id"))

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


async def _handle_rental_completed(
    metadata: dict, customer_id: str, payment_intent: str | None, session_id: str | None
) -> None:
    """Activate a rental window and credit included minutes (idempotent)."""
    tenant_id = metadata.get("tenant_id")
    period_key = metadata.get("period")
    mode = metadata.get("mode", "deepseek")
    quantity = int(metadata.get("quantity", 1) or 1)

    if not tenant_id or not period_key:
        logger.warning("rental_webhook_missing_metadata", metadata=metadata)
        return

    period = get_period(period_key)
    if period is None:
        logger.warning("rental_webhook_bad_period", period=period_key)
        return

    # Idempotency: skip if this Stripe session already activated a rental.
    if session_id:
        existing = await get_rental_by_session_db(session_id)
        if existing:
            logger.info("rental_already_activated", session_id=session_id)
            return

    tenant = await get_tenant_db(tenant_id)
    if not tenant:
        # Provision tenant from checkout (e.g. anonymous signup with rental).
        email = metadata.get("email") or f"user+{customer_id}@aetherdesk.com"
        company = metadata.get("company_name") or "New AetherDesk Customer"
        slug = (
            re.sub(r"[^a-z0-9]+", "-", company.lower()).strip("-")[:60]
            or f"tenant-{str(customer_id)[-8:]}"
        )
        try:
            new_tenant = await create_tenant(
                name=company,
                email=email,
                slug=slug,
                phone=metadata.get("phone"),
                plan_id=None,
                settings={"source": "rental_checkout", "tier": mode},
                gdpr_consent=True,
            )
            if new_tenant:
                await set_tenant_billing_settings_db(
                    new_tenant["id"], {"ai_mode": mode}
                )
                tenant = new_tenant
                tenant_id = new_tenant["id"]
        except Exception as e:
            logger.error("tenant_provision_failed", error=str(e))
            return

    start, end = rental_window(period_key)
    await set_tenant_billing_settings_db(tenant_id, {"ai_mode": mode})
    await activate_rental_db(
        tenant_id=tenant_id,
        period=period_key,
        ai_mode=mode,
        quantity=quantity,
        included_minutes=period.included_minutes * quantity,
        rental_start=start.isoformat(),
        rental_end=end.isoformat(),
        stripe_session_id=session_id,
        payment_intent_id=payment_intent,
    )
    logger.info(
        "rental_activated",
        tenant_id=tenant_id,
        period=period_key,
        quantity=quantity,
        mode=mode,
    )


async def _handle_topup_completed(
    metadata: dict, customer_id: str, session_id: str | None
) -> None:
    """Credit prepaid minutes from a top-up purchase (idempotent)."""
    tenant_id = metadata.get("tenant_id")
    pack = metadata.get("pack")
    quantity = int(metadata.get("quantity", 1) or 1)

    if not tenant_id or not pack:
        logger.warning("topup_webhook_missing_metadata", metadata=metadata)
        return

    # Idempotency: track credited sessions to avoid double-crediting.
    if session_id:
        existing = await get_rental_by_session_db(session_id)
        if existing:
            logger.info("topup_already_credited", session_id=session_id)
            return

    try:
        minutes = int(pack) * quantity
    except (TypeError, ValueError):
        logger.warning("topup_webhook_bad_pack", pack=pack)
        return

    await credit_minutes_db(tenant_id, minutes)
    logger.info("topup_credited", tenant_id=tenant_id, minutes=minutes)
