from fastapi import APIRouter, Depends, HTTPException, Query

from api.models.dto import (
    ChatMessageCreate,
    ChatSessionCreate,
    SMSSendRequest,
    SMSTemplateCreate,
)
from api.services.auth import verify_tenant_access
from api.services.chat import chat_service
from api.services.db_omnichannel import log_sms_db
from api.services.sms import sms_service

router = APIRouter(prefix="/omnichannel", tags=["omnichannel"])


# ── SMS Endpoints ─────────────────────────────────────────────────

@router.post("/sms/send")
async def send_sms(
    data: SMSSendRequest,
    tenant_id: str = Depends(verify_tenant_access),
):
    result = await sms_service.send_sms(data.to_number, data.message)
    await log_sms_db(tenant_id, data.to_number, data.message, status="sent", sid=result.get("sid"))
    return result


@router.post("/sms/bulk")
async def send_bulk_sms(
    data: dict,
    tenant_id: str = Depends(verify_tenant_access),
):
    recipients = data.get("recipients", [])
    message = data.get("message", "")
    if not recipients or not message:
        raise HTTPException(status_code=400, detail="recipients and message are required")
    result = await sms_service.send_bulk_sms(recipients, message)
    for r in result.get("results", []):
        await log_sms_db(tenant_id, r["to"], message, status="sent", sid=r.get("sid"))
    return result


@router.post("/sms/templates")
async def create_sms_template(
    data: SMSTemplateCreate,
    tenant_id: str = Depends(verify_tenant_access),
):
    result = await sms_service.create_sms_template(tenant_id, data.name, data.body)
    if not result:
        raise HTTPException(status_code=400, detail="Failed to create SMS template")
    return result


@router.get("/sms/templates")
async def list_sms_templates(
    tenant_id: str = Depends(verify_tenant_access),
):
    return await sms_service.get_sms_templates(tenant_id)


@router.get("/sms/log")
async def get_sms_log(
    tenant_id: str = Depends(verify_tenant_access),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    return await sms_service.get_sms_log(tenant_id, limit=limit, offset=offset)


@router.post("/sms/inbound")
async def sms_inbound_webhook(
    data: dict,
    tenant_id: str = Depends(verify_tenant_access),
):
    from_number = data.get("from", data.get("From", ""))
    body = data.get("body", data.get("Body", ""))
    session_id = data.get("session_id")

    result = await sms_service.process_inbound_sms(from_number, body, session_id)
    await log_sms_db(tenant_id, from_number, body, direction="inbound", status="received")
    return result


# ── Chat Endpoints ────────────────────────────────────────────────

@router.post("/chat/sessions")
async def create_chat_session(
    data: ChatSessionCreate,
    tenant_id: str = Depends(verify_tenant_access),
):
    session = await chat_service.create_session(
        data.visitor_id, tenant_id,
        name=data.visitor_name, email=data.visitor_email,
        initial_message=data.initial_message,
    )
    if not session:
        raise HTTPException(status_code=400, detail="Failed to create chat session")
    return session


@router.post("/chat/sessions/{session_id}/messages")
async def send_chat_message(
    session_id: str,
    data: ChatMessageCreate,
    tenant_id: str = Depends(verify_tenant_access),
):
    result = await chat_service.send_message(session_id, data.sender_type, data.content)
    if not result:
        raise HTTPException(status_code=404, detail="Chat session not found")
    return result


@router.get("/chat/sessions/{session_id}/messages")
async def get_chat_messages(
    session_id: str,
    tenant_id: str = Depends(verify_tenant_access),
    after_id: str | None = Query(None),
):
    return await chat_service.get_messages(session_id, after_id=after_id)


@router.post("/chat/sessions/{session_id}/assign")
async def assign_chat_agent(
    session_id: str,
    data: dict,
    tenant_id: str = Depends(verify_tenant_access),
):
    agent_id = data.get("agent_id")
    if not agent_id:
        raise HTTPException(status_code=400, detail="agent_id is required")
    result = await chat_service.assign_agent(session_id, agent_id)
    if not result:
        raise HTTPException(status_code=404, detail="Chat session not found")
    return result


@router.post("/chat/sessions/{session_id}/close")
async def close_chat_session(
    session_id: str,
    tenant_id: str = Depends(verify_tenant_access),
):
    result = await chat_service.close_session(session_id)
    if not result:
        raise HTTPException(status_code=404, detail="Chat session not found")
    return result


@router.get("/chat/waiting")
async def get_waiting_sessions(
    tenant_id: str = Depends(verify_tenant_access),
):
    return await chat_service.get_waiting_sessions(tenant_id)
