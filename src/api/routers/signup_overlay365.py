"""Public signup endpoint for Overlay 365 Aetherdesk trial."""
import os
import logging
from typing import Optional, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field
from slowapi import Limiter
from slowapi.util import get_remote_address

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/signup", tags=["signup"])

# Rate limiter: 5 signups per IP per hour
limiter = Limiter(key_func=get_remote_address)

VALID_TIERS = Literal["starter", "pro", "scale", "enterprise"]


TIERS = [
    {"id": "starter", "name": "Starter", "price": 99, "features": ["1 AI agent", "100 min/mo", "Basic scripts"]},
    {"id": "pro", "name": "Pro", "price": 299, "features": ["5 AI agents", "1000 min/mo", "Custom scripts", "Blocklabor lite"]},
    {"id": "scale", "name": "Scale", "price": 999, "features": ["Unlimited agents", "Full Blocklabor", "AgentBrowser", "Claw Protect"]},
    {"id": "enterprise", "name": "Enterprise", "price": 5000, "features": ["Everything in Scale", "Custom AI training", "Dedicated support", "SLA"]},
]


class SignupRequest(BaseModel):
    email: EmailStr
    company_name: str = Field(..., min_length=1, max_length=200)
    phone: Optional[str] = Field(default=None, max_length=20)
    tier: VALID_TIERS = Field(default="starter")


class SignupResponse(BaseModel):
    status: str
    checkout_url: str
    customer_id: str
    tier: str


@router.get("/tiers")
async def get_pricing_tiers():
    """Return available Overlay 365 pricing tiers."""
    return {"tiers": TIERS}


@router.post("/create-checkout", response_model=SignupResponse)
@limiter.limit("5/hour")
async def create_checkout_session(
    request: Request,
    body: SignupRequest,
):
    """Create Stripe checkout session for Overlay 365 Aetherdesk trial."""
    return await _create_checkout(body)


async def _create_checkout(request: SignupRequest):
    """Create Stripe checkout session for Overlay 365 Aetherdesk trial."""
    price_map = {
        "starter": os.getenv("STRIPE_PRICE_STARTER"),
        "pro": os.getenv("STRIPE_PRICE_PRO"),
        "scale": os.getenv("STRIPE_PRICE_SCALE"),
        "enterprise": os.getenv("STRIPE_PRICE_ENTERPRISE"),
    }
    price_id = price_map.get(request.tier)
    if not price_id:
        raise HTTPException(status_code=400, detail=f"Invalid tier: {request.tier}")

    stripe_secret = os.getenv("STRIPE_SECRET_KEY")

    # Mock mode for development without Stripe keys
    if not stripe_secret or stripe_secret == "":
        from api.services.security_guard import mask_email
        logger.info(f"[MOCK] Stripe checkout for {mask_email(request.email)}, tier={request.tier}")
        return SignupResponse(
            status="mock_checkout",
            checkout_url=f"https://overlay365.com/aetherdesk/mock-checkout?email={request.email}&tier={request.tier}",
            customer_id=f"mock_cus_{request.email}",
            tier=request.tier,
        )

    # Real Stripe integration
    try:
        import stripe

        stripe.api_key = stripe_secret
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{"price": price_id, "quantity": 1}],
            mode="subscription",
            customer_email=request.email,
            metadata={
                "company_name": request.company_name,
                "phone": request.phone or "",
                "tier": request.tier,
                "platform": "overlay365",
            },
            success_url=os.getenv("STRIPE_SUCCESS_URL", "http://localhost:5173/billing?success=true"),
            cancel_url=os.getenv("STRIPE_CANCEL_URL", "http://localhost:5173/billing?canceled=true"),
        )
        from api.services.security_guard import mask_email
        logger.info(f"Stripe checkout created: email={mask_email(request.email)}, tier={request.tier}")
        return SignupResponse(
            status="success",
            checkout_url=checkout_session.url,
            customer_id=checkout_session.customer,
            tier=request.tier,
        )
    except stripe.error.StripeError as e:
        logger.error(f"Stripe checkout failed: {type(e).__name__}")
        raise HTTPException(status_code=500, detail="Checkout creation failed")
    except Exception as e:
        logger.error(f"Unexpected checkout error: {type(e).__name__}")
        raise HTTPException(status_code=500, detail="Checkout creation failed")