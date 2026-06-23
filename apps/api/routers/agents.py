from fastapi import APIRouter, Depends, HTTPException, Request
from datetime import UTC, datetime
import json
import logging

from apps.api.models.dto import AgentCreate, AgentResponse, AgentStatusUpdate
from apps.api.services.auth import verify_tenant_access, get_current_user
from apps.api.services.database import (
    create_agent as create_agent_db,
    list_agents as list_agents_db,
    get_agent_db,
    update_agent_db,
    delete_agent_db,
    update_agent_status,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["agents"])

async def safe_redis_publish(request: Request, channel: str, message: str) -> bool:
    """Publish to Redis using app state."""
    try:
        redis_client = request.app.state.redis
        await redis_client.publish(channel, message)
        return True
    except Exception as e:
        logger.error(f"redis_publish_failed: channel={channel} error={e}")
        return False

@router.post("/tenants/{tenant_id}/agents", response_model=AgentResponse, status_code=201)
async def create_agent(request: Request, tenant_id: str, agent: AgentCreate, _=Depends(verify_tenant_access)):
    """Create a new agent with SIP extension and Fonster integration"""
    db_agent = await create_agent_db(
        tenant_id=tenant_id,
        name=agent.name,
        display_name=agent.display_name,
        agent_type=agent.agent_type,
        skills=agent.skills,
        config=agent.config,
    )
    agent_id = db_agent["id"]
    sip_extension = db_agent["sip_extension"]

    # Create Fonster Voice Application for agent
    fonster_client = request.app.state.fonster_client
    if fonster_client:
        try:
            await fonster_client.create_application({
                "name": f"Agent-{agent.name}",
                "type": "EXTERNAL",
                "endpoint": "tcp://aetherdesk-voice:50061",
                "speechToText": {
                    "productRef": "stt.deepgram",
                    "config": {"languageCode": "en-US"}
                },
                "textToSpeech": {
                    "productRef": "tts.chatterbox",
                    "config": {"voice": "default", "emotion": "neutral"}
                },
            })
        except Exception as e:
            logger.warning(f"Fonster agent app creation failed (non-fatal): {e}")

    return AgentResponse(
        id=agent_id,
        tenant_id=tenant_id,
        name=agent.name,
        display_name=agent.display_name or agent.name,
        agent_type=agent.agent_type,
        status="offline",
        skills=agent.skills,
        sip_extension=sip_extension,
        total_calls=0,
        total_talk_time_seconds=0,
        avg_rating=0.0,
        created_at=datetime.now(UTC),
    )


@router.get("/tenants/{tenant_id}/agents")
async def list_agents(tenant_id: str, _=Depends(verify_tenant_access)):
    """List all agents for a tenant with status"""
    agents = await list_agents_db(tenant_id)
    result = []
    for a in agents:
        skills_raw = a.get("skills", "[]")
        if isinstance(skills_raw, str):
            try:
                skills_parsed = json.loads(skills_raw)
            except json.JSONDecodeError:
                skills_parsed = []
        else:
            skills_parsed = skills_raw or []

        result.append(AgentResponse(
            id=a["id"],
            tenant_id=a["tenant_id"],
            name=a["name"],
            display_name=a.get("display_name") or a["name"],
            agent_type=a.get("agent_type", "ai"),
            status=a.get("status", "offline"),
            skills=skills_parsed,
            sip_extension=a.get("sip_extension"),
            total_calls=a.get("total_calls", 0) or 0,
            total_talk_time_seconds=a.get("total_talk_time_seconds", 0) or 0,
            avg_rating=float(a.get("avg_rating", 0) or 0),
            created_at=a.get("created_at") or datetime.now(UTC),
        ))
    return result


@router.get("/tenants/{tenant_id}/agents/{agent_id}", response_model=AgentResponse)
async def get_agent(tenant_id: str, agent_id: str, _=Depends(verify_tenant_access)):
    """Get agent details"""
    agent = await get_agent_db(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    skills_raw = agent.get("skills", "[]")
    if isinstance(skills_raw, str):
        try:
            skills_parsed = json.loads(skills_raw)
        except json.JSONDecodeError:
            skills_parsed = []
    else:
        skills_parsed = skills_raw or []

    return AgentResponse(
        id=agent["id"],
        tenant_id=agent["tenant_id"],
        name=agent["name"],
        display_name=agent.get("display_name") or agent["name"],
        agent_type=agent.get("agent_type", "ai"),
        status=agent.get("status", "offline"),
        skills=skills_parsed,
        sip_extension=agent.get("sip_extension"),
        total_calls=agent.get("total_calls", 0) or 0,
        total_talk_time_seconds=agent.get("total_talk_time_seconds", 0) or 0,
        avg_rating=float(agent.get("avg_rating", 0) or 0),
        created_at=agent.get("created_at") or datetime.now(UTC),
    )


@router.put("/tenants/{tenant_id}/agents/{agent_id}", response_model=AgentResponse)
async def update_agent(tenant_id: str, agent_id: str, agent: AgentCreate, _=Depends(verify_tenant_access)):
    """Update an agent's configuration"""
    updated = await update_agent_db(
        agent_id=agent_id, tenant_id=tenant_id,
        name=agent.name, display_name=agent.display_name,
        agent_type=agent.agent_type, skills=agent.skills,
        config=agent.config,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Agent not found")

    skills_raw = updated.get("skills", "[]")
    if isinstance(skills_raw, str):
        try:
            skills_parsed = json.loads(skills_raw)
        except json.JSONDecodeError:
            skills_parsed = []
    else:
        skills_parsed = skills_raw or []

    return AgentResponse(
        id=updated["id"], tenant_id=updated["tenant_id"],
        name=updated["name"],
        display_name=updated.get("display_name") or updated["name"],
        agent_type=updated.get("agent_type", "ai"),
        status=updated.get("status", "offline"),
        skills=skills_parsed,
        sip_extension=updated.get("sip_extension"),
        total_calls=updated.get("total_calls", 0) or 0,
        total_talk_time_seconds=updated.get("total_talk_time_seconds", 0) or 0,
        avg_rating=float(updated.get("avg_rating", 0) or 0),
        created_at=updated.get("created_at") or datetime.now(UTC),
    )


@router.delete("/tenants/{tenant_id}/agents/{agent_id}")
async def delete_agent(tenant_id: str, agent_id: str, _=Depends(verify_tenant_access)):
    """Delete an agent"""
    deleted = await delete_agent_db(agent_id, tenant_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Agent not found")
    return {"success": True, "agent_id": agent_id}


@router.patch("/agents/{agent_id}/status")
async def handle_update_agent_status(
    request: Request,
    agent_id: str,
    status: AgentStatusUpdate,
    current_user: dict = Depends(get_current_user),
):
    """Update agent status with real-time WebSocket notification"""
    result = await update_agent_status(agent_id, status.status, status.session_ref)

    # Ownership check: agent must belong to the token's tenant
    agent = await get_agent_db(agent_id)
    if agent and agent.get("tenant_id") != current_user.get("tenant_id"):
        raise HTTPException(
            status_code=403,
            detail="Access denied: agent does not belong to this tenant",
        )

    # Publish status change to Redis for real-time updates
    await safe_redis_publish(
        request,
        f"agent:{agent_id}:status",
        json.dumps({
            "agent_id": agent_id,
            "status": status.status,
            "session_ref": status.session_ref,
            "timestamp": datetime.now(UTC).isoformat(),
        })
    )

    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("error", "Agent not found"))

    return result
