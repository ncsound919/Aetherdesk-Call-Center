
import uuid
from datetime import datetime, UTC
from fastapi import APIRouter, Depends, HTTPException, Request

from apps.api.models.dto import CallAction, CallCreate, CallResponse
from apps.api.services.auth import verify_tenant_access
from apps.api.services.database import (
    create_call_session,
    get_agent_db,
    get_available_agents,
    enqueue_call,
    get_call_session,
    log_audit_event,
    list_calls as list_calls_db,
)

router = APIRouter(prefix="/api/v1", tags=["calls"])

@router.post("/calls", response_model=CallResponse, status_code=201)
async def create_call(
    request: Request,
    call: CallCreate,
    tenant_id: str = Depends(verify_tenant_access)
):
    """Create and initiate a call via Fonster"""
    fonster_client = request.app.state.fonster_client
    call_id = str(uuid.uuid4())

    # Find available agent or queue
    agent_id = call.agent_id

    if agent_id:
        agent = await get_agent_db(agent_id)
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")
        await create_call_session(
            tenant_id=tenant_id,
            agent_id=agent_id,
            caller_number=call.caller_number,
            called_number=call.called_number or call.caller_number,
            call_direction=call.call_direction,
            intent_detected=call.intent,
            sip_call_id=call_id,
        )
    else:
        # Auto-route: find available agent by intent
        skills = [call.intent] if call.intent else None
        available = await get_available_agents(tenant_id, skills)
        if available:
            agent_id = available[0]["id"]
            await create_call_session(
                tenant_id=tenant_id,
                agent_id=agent_id,
                caller_number=call.caller_number,
                called_number=call.called_number or call.caller_number,
                call_direction=call.call_direction,
                intent_detected=call.intent,
                sip_call_id=call_id,
            )
        else:
            # No agents available, enqueue
            await enqueue_call(tenant_id, call.caller_number, call.intent)
            await create_call_session(
                tenant_id=tenant_id,
                agent_id=None,
                caller_number=call.caller_number,
                called_number=call.called_number or call.caller_number,
                call_direction=call.call_direction,
                intent_detected=call.intent,
                sip_call_id=call_id,
            )

    # Create voice application in Fonster
    if fonster_client:
        try:
            await fonster_client.create_application({
                "name": f"Call-{call_id}",
                "type": "EXTERNAL",
                "endpoint": "tcp://aetherdesk-voice:50061",
            })
        except Exception as e:
            # Need access to logger, I'll just use print or assume it's not strictly needed for this task to be perfect, 
            # or better: import logging.
            import logging
            logging.warning(f"Fonster call app creation failed: {e}")

    return CallResponse(
        id=call_id,
        tenant_id=tenant_id,
        agent_id=agent_id,
        caller_number=call.caller_number,
        call_direction=call.call_direction,
        call_status="initiated",
        duration_seconds=0,
        cost=0.0,
        sip_call_id=call_id,
        intent_detected=call.intent,
        created_at=datetime.now(UTC),
    )


@router.post("/calls/{call_id}/action")
async def call_action(
    request: Request,
    call_id: str,
    action: CallAction,
    tenant_id: str = Depends(verify_tenant_access),
):
    """Perform call action via Fonster"""
    fonster_client = request.app.state.fonster_client
    call_session = await get_call_session(call_id)
    if not call_session:
        raise HTTPException(status_code=404, detail="Call not found")

    # IDOR protection: confirm call belongs to requesting tenant
    if call_session.get("tenant_id") != tenant_id:
        raise HTTPException(
            status_code=403,
            detail="Access denied: call does not belong to this tenant",
        )

    await log_audit_event(
        tenant_id=call_session.get("tenant_id", ""),
        user_id="system",
        action=f"call_{action.action}",
        resource_type="call",
        resource_id=call_id,
        new_values={"action": action.action, "target": action.target},
    )

    if not fonster_client:
        return {"success": True, "action": action.action, "note": "Fonster not connected (dev mode)"}

    if action.action == "answer":
        result = await fonster_client.answer_call(call_id)
    elif action.action == "hangup":
        result = await fonster_client.hangup_call(call_id)
    elif action.action == "mute":
        result = await fonster_client.mute_call(call_id)
    elif action.action == "hold":
        result = await fonster_client.hold_call(call_id)
    elif action.action == "unmute":
        result = await fonster_client.unmute_call(call_id)
    elif action.action == "unhold":
        result = await fonster_client.unhold_call(call_id)
    elif action.action == "transfer":
        if not action.target:
            raise HTTPException(status_code=400, detail="Transfer target required")
        result = await fonster_client.transfer_call(call_id, action.target)
    elif action.action == "gather":
        hints = action.data.get("hints", ["sales", "support", "billing", "technical"]) if action.data else []
        result = await fonster_client.gather_speech(call_id, hints=hints, language="en-US")
    elif action.action == "say":
        text = action.data.get("text", "") if action.data else ""
        result = await fonster_client.say_text(call_id, text)
    elif action.action == "play":
        url = action.data.get("url", "") if action.data else ""
        result = await fonster_client.play_audio(call_id, url)
    elif action.action == "record":
        record_action = action.data.get("action", "start") if action.data else "start"
        result = await fonster_client.record_call(call_id, record_action)
    elif action.action == "dtmf":
        digits = action.data.get("digits", "") if action.data else ""
        result = await fonster_client.send_dtmf(call_id, digits)
    else:
        raise HTTPException(status_code=400, detail=f"Unknown action: {action.action}")

    return result


@router.get("/calls/{call_id}", response_model=CallResponse)
async def get_call(call_id: str, tenant_id: str = Depends(verify_tenant_access)):
    """Get call details"""
    call = await get_call_session(call_id)
    if not call:
        raise HTTPException(status_code=404, detail="Call not found")

    return CallResponse(
        id=call["id"],
        tenant_id=call["tenant_id"],
        agent_id=call.get("agent_id"),
        caller_number=call["caller_number"],
        call_direction=call.get("call_direction", "inbound"),
        call_status=call.get("call_status", "initiated"),
        duration_seconds=call.get("duration_seconds", 0) or 0,
        cost=float(call.get("total_cost", 0) or 0),
        sip_call_id=call.get("sip_call_id"),
        intent_detected=call.get("intent_detected"),
        created_at=call.get("created_at") or datetime.now(UTC),
    )


@router.get("/calls")
async def list_calls(
    tenant_id: str = Depends(verify_tenant_access),
    status: str | None = None,
):
    """List calls for a tenant"""
    calls = await list_calls_db(tenant_id, status)
    return [
        CallResponse(
            id=c["id"],
            tenant_id=c["tenant_id"],
            agent_id=c.get("agent_id"),
            caller_number=c["caller_number"],
            call_direction=c.get("call_direction", "inbound"),
            call_status=c["call_status"],
            duration_seconds=c.get("duration_seconds", 0) or 0,
            cost=float(c.get("total_cost", 0) or 0),
            sip_call_id=c.get("sip_call_id"),
            intent_detected=c.get("intent_detected"),
            created_at=c.get("created_at") or datetime.now(UTC),
        )
        for c in calls
    ]
