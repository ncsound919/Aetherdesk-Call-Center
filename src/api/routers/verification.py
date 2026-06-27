"""Verification router for BlockLabor-Aetherdesk integration.
Handles Business Identity Verification and Ghost-Job Audit calls.
"""
import os
import logging
import uuid
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from api.models.dto import CallCreate, CallResponse
from api.services.auth import verify_tenant_access
from api.services.database import (
    create_call_session,
    log_audit_event,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/verification", tags=["verification"])


class BusinessVerificationRequest(BaseModel):
    business_name: str = Field(..., min_length=1, max_length=200)
    business_phone: str = Field(..., min_length=10, max_length=20)
    business_ein: str = Field(..., min_length=9, max_length=20)
    business_state: str = Field(..., min_length=2, max_length=2)
    tenant_id: str = Field(..., min_length=1, max_length=100)


class GhostJobAuditRequest(BaseModel):
    job_id: str = Field(..., min_length=1, max_length=100)
    business_phone: str = Field(..., min_length=10, max_length=20)
    job_title: str = Field(..., min_length=1, max_length=200)
    tenant_id: str = Field(..., min_length=1, max_length=100)


class ApplicationSLABreachRequest(BaseModel):
    job_id: str = Field(..., min_length=1, max_length=100)
    business_phone: str = Field(..., min_length=10, max_length=20)
    applicant_name: str = Field(..., min_length=1, max_length=200)
    sla_hours_breached: int = Field(..., gt=0, le=720)
    tenant_id: str = Field(..., min_length=1, max_length=100)


async def _trigger_outbound_call(
    request: Request,
    tenant_id: str,
    called_number: str,
    script: str,
    verification_type: Literal["business_identity", "ghost_job_audit", "application_sla"],
    target_id: str,
) -> CallResponse:
    """Internal helper to trigger an outbound verification call via Twilio."""
    # Prefix with 'verify-' so the Twilio call-status webhook in
    # webhooks_twilio.py knows this is a verification call to forward
    # to BlockLabor.
    call_id = f"verify-{verification_type}-{uuid.uuid4()}"

    # Create a CallCreate DTO that matches calls.py signature
    call_dto = CallCreate(
        caller_number=called_number,
        called_number=called_number,
        call_direction="outbound",
        intent=f"verification:{verification_type}",
        agent_id=None,
    )

    # Create call session
    await create_call_session(
        tenant_id=tenant_id,
        agent_id=None,
        caller_number=call_dto.caller_number,
        called_number=call_dto.called_number,
        call_direction=call_dto.call_direction,
        intent_detected=call_dto.intent,
        sip_call_id=call_id,
    )

    # Place outbound call via Twilio with verification-specific TwiML
    try:
        from dotenv import load_dotenv
        load_dotenv(override=True)
        twilio_sid = os.environ.get("TWILIO_ACCOUNT_SID", "")
        twilio_token = os.environ.get("TWILIO_AUTH_TOKEN", "")
        twilio_from = os.environ.get("TWILIO_FROM_NUMBER", "")
        if twilio_sid and twilio_token and twilio_from:
            from twilio.rest import Client as TwilioRest
            tc = TwilioRest(twilio_sid, twilio_token)
            twiml = f'<Response><Say>{script}</Say></Response>'
            tc.calls.create(
                to=call_dto.caller_number,
                from_=twilio_from,
                twiml=twiml,
                timeout=30,
            )
    except Exception as e:
        logger.warning(f"Twilio verification call failed: {e}")

    # Log audit event
    await log_audit_event(
        tenant_id=tenant_id,
        event_type=f"verification_call_initiated",
        event_data={
            "verification_type": verification_type,
            "target_id": target_id,
            "called_number": called_number,
            "call_id": call_id,
        },
    )

    return CallResponse(
        id=call_id,
        tenant_id=tenant_id,
        agent_id=None,
        caller_number=call_dto.caller_number,
        call_direction=call_dto.call_direction,
        call_status="initiated",
        duration_seconds=0,
        cost=0.0,
        sip_call_id=call_id,
        intent_detected=call_dto.intent,
        created_at=datetime.now(UTC),
    )


@router.post("/business-identity")
async def verify_business_identity(
    request: Request,
    payload: BusinessVerificationRequest,
    token: str = Depends(lambda: None),
):
    """Initiate an outbound call to verify a business's identity.
    Called by BlockLabor when a new business is registered.
    """
    # Note: In production, use verify_access_token(token)
    tenant_id = payload.tenant_id

    script = (
        f"Hello, this is Overlay365 Trust Operations calling to verify the identity of "
        f"{payload.business_name}. We have your registered EIN as {payload.business_ein} "
        f"in the state of {payload.business_state}. Please confirm this information is correct "
        f"by pressing 1, or press 2 to speak with a representative."
    )

    result = await _trigger_outbound_call(
        request=request,
        tenant_id=tenant_id,
        called_number=payload.business_phone,
        script=script,
        verification_type="business_identity",
        target_id=payload.business_name,
    )

    return {
        "status": "verification_initiated",
        "call_id": result.id,
        "verification_type": "business_identity",
    }


@router.post("/ghost-job-audit")
async def audit_ghost_job(
    request: Request,
    payload: GhostJobAuditRequest,
    token: str = Depends(lambda: None),
):
    """Initiate an outbound call to audit whether a job posting is still active.
    Called by BlockLabor as part of the 3-day TTL ping protocol.
    """
    tenant_id = payload.tenant_id

    script = (
        f"Hello, this is Overlay365 calling to confirm whether the job posting for "
        f"{payload.job_title} is still active. If the position is still open, "
        f"please press 1. If the position has been filled or removed, please press 2."
    )

    result = await _trigger_outbound_call(
        request=request,
        tenant_id=tenant_id,
        called_number=payload.business_phone,
        script=script,
        verification_type="ghost_job_audit",
        target_id=payload.job_id,
    )

    return {
        "status": "audit_initiated",
        "call_id": result.id,
        "verification_type": "ghost_job_audit",
    }


@router.post("/application-sla-breach")
async def alert_sla_breach(
    request: Request,
    payload: ApplicationSLABreachRequest,
    token: str = Depends(lambda: None),
):
    """Initiate an outbound call to alert an employer about an SLA breach
    on candidate response time.
    """
    tenant_id = payload.tenant_id

    script = (
        f"Hello, this is Overlay365 calling regarding job {payload.job_id}. "
        f"Candidate {payload.applicant_name} has been waiting for a response for "
        f"{payload.sla_hours_breached} hours. Please review and respond to this application "
        f"within the next 24 hours to maintain your verified employer status. "
        f"Press 1 to acknowledge, or press 2 to speak with a representative."
    )

    result = await _trigger_outbound_call(
        request=request,
        tenant_id=tenant_id,
        called_number=payload.business_phone,
        script=script,
        verification_type="application_sla",
        target_id=payload.job_id,
    )

    return {
        "status": "sla_alert_initiated",
        "call_id": result.id,
        "verification_type": "application_sla",
    }
