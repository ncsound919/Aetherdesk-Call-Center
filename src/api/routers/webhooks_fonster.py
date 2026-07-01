import hashlib
import hmac
import json
import logging
import os
from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request

from api.services.database import update_call_status as db_update_call_status

router = APIRouter(tags=["webhooks"])
logger = logging.getLogger(__name__)

@router.post("/api/v1/webhooks/fonster")
async def fonster_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_fonoster_signature: str = Header(default=None),
):
    """Handle Fonster call events (call.answered, call.completed, call.failed)"""
    # HMAC signature verification
    fonster_webhook_secret = os.getenv("FONOSTER_WEBHOOK_SECRET")
    is_production = os.getenv("APP_ENV", "development") == "production"

    if not fonster_webhook_secret:
        if is_production:
            raise HTTPException(
                status_code=503,
                detail="FONOSTER_WEBHOOK_SECRET not configured",
            )
        logger.warning(
            "fonster_webhook_secret_not_set: webhook signature validation "
            "is disabled. This must never happen in production."
        )
    else:
        if not x_fonoster_signature:
            # Secret is configured but no signature sent — reject in
            # production; allow in dev/test for local convenience.
            if is_production:
                raise HTTPException(status_code=401, detail="Missing webhook signature")
        else:
            raw_body = await request.body()
            expected_sig = hmac.HMAC(
                fonster_webhook_secret.encode(),
                raw_body,
                hashlib.sha256,
            ).hexdigest()
            if not hmac.compare_digest(expected_sig, x_fonoster_signature):
                raise HTTPException(status_code=401, detail="Invalid webhook signature")

    payload = await request.json()
    event_type = payload.get("event_type")
    call_id = payload.get("call_id")
    session_ref = payload.get("session_ref")

    logger.info(f"Fonster webhook: {event_type} for call {call_id}")

    if event_type == "call.answered":
        background_tasks.add_task(handle_fonster_webhook, request, call_id, "active", session_ref)
    elif event_type == "call.completed":
        background_tasks.add_task(handle_fonster_webhook, request, call_id, "completed")
    elif event_type == "call.failed":
        background_tasks.add_task(handle_fonster_webhook, request, call_id, "failed")

    return {"status": "ok"}


async def handle_fonster_webhook(request: Request, call_id: str, status: str, session_ref: str = None):
    """Update call status in DB and notify via WebSocket/Redis"""
    logger.info(f"Call {call_id} status updated to {status}")

    try:
        await db_update_call_status(call_id, status)
    except Exception as e:
        logger.error(f"Call status DB update failed: {e}")

    # Access redis_client from app state
    redis_client = request.app.state.redis
    if redis_client:
        await redis_client.publish(
            f"call:{call_id}:status",
            json.dumps({
                "call_id": call_id,
                "status": status,
                "session_ref": session_ref,
                "timestamp": datetime.now(UTC).isoformat(),
            })
        )
