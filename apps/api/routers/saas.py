import os
import uuid
from datetime import datetime, timedelta

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException

from apps.api.services.database import (
    create_agent_profile_db,
    get_pending_approvals_db,
    get_saas_dashboard_db,
    get_session_recordings_db,
    get_tenant_by_api_key,
    get_tenant_settings_db,
    process_approval_db,
    rent_agent_db,
    update_tenant_settings_db,
)

router = APIRouter(prefix="/saas", tags=["saas"])


async def get_tenant_id(x_api_key: str = Header(...)):
    if os.getenv("ENV") == "test":
        return "TENANT-001"
    if os.getenv("ENV") != "production" and x_api_key == os.getenv("DEV_API_KEY", "dev-api-key"):
        return "TENANT-001"

    row = await get_tenant_by_api_key(x_api_key)
    if not row:
        raise HTTPException(status_code=401, detail="Invalid Tenant API Key")
    return row["id"]


@router.get("/dashboard")
async def get_saas_dashboard(tenant_id: str = Depends(get_tenant_id)):
    data = await get_saas_dashboard_db(tenant_id)
    return data


@router.post("/profile")
async def create_profile(name: str, prompt: str, parameters: dict, tenant_id: str = Depends(get_tenant_id)):
    profile_id = f"PROF-{uuid.uuid4().hex[:6].upper()}"
    await create_agent_profile_db(profile_id, tenant_id, name, prompt, parameters)
    return {"ok": True, "profile_id": profile_id}


@router.post("/rent")
async def rent_agent(profile_id: str, duration_type: str, tenant_id: str = Depends(get_tenant_id)):
    # duration_type: hour, day, week, month
    rental_id = f"RENT-{uuid.uuid4().hex[:6].upper()}"

    now = datetime.now()
    if duration_type == "hour":
        end_time = now + timedelta(hours=1)
    elif duration_type == "day":
        end_time = now + timedelta(days=1)
    elif duration_type == "week":
        end_time = now + timedelta(weeks=1)
    elif duration_type == "month":
        end_time = now + timedelta(days=30)
    else:
        raise HTTPException(status_code=400, detail="Invalid duration type")

    await rent_agent_db(rental_id, tenant_id, profile_id, duration_type, end_time)
    return {"ok": True, "rental_id": rental_id, "end_time": end_time}


@router.get("/settings")
async def get_settings(tenant_id: str = Depends(get_tenant_id)):
    row = await get_tenant_settings_db(tenant_id)
    if row:
        return {
            "api_feeds": row["api_feeds"] or "{}",
            "auto_mode_enabled": bool(row["auto_mode_enabled"]),
            "redact_pii": bool(row["redact_pii"]),
            "require_consent": bool(row["require_consent"]),
            "sync_dnc": bool(row["sync_dnc"]),
            "mcp_servers": row["mcp_servers"] or "{}"
        }
    return {"api_feeds": "{}", "auto_mode_enabled": False, "redact_pii": True, "require_consent": True, "sync_dnc": False, "mcp_servers": "{}"}


@router.post("/settings")
async def update_settings(settings: dict, tenant_id: str = Depends(get_tenant_id)):
    await update_tenant_settings_db(tenant_id, settings)
    return {"ok": True}


OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:1b")


@router.post("/generate-script")
async def generate_script(goal: dict, tenant_id: str = Depends(get_tenant_id)):
    objective = goal.get("objective", "general sales")
    prompt = f"Write a system prompt for an AI call center agent. The objective is: {objective}. Include objection handling and compliance."

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            res = await client.post(
                f"{OLLAMA_HOST}/api/chat",
                json={
                    "model": OLLAMA_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": False
                }
            )
            data = res.json().get("message", {}).get("content", "")
            return {"script": data}
    except Exception:
        return {"script": f"You are an AI agent designed to handle: {objective}. Be polite, handle objections gracefully, and ensure compliance with all requests."}


@router.get("/recordings")
async def get_recordings(tenant_id: str = Depends(get_tenant_id)):
    rows = await get_session_recordings_db(tenant_id)
    return rows


@router.get("/approvals")
async def get_approvals(tenant_id: str = Depends(get_tenant_id)):
    rows = await get_pending_approvals_db(tenant_id)
    return rows


@router.post("/approvals/{approval_id}")
async def process_approval(approval_id: str, status: str, tenant_id: str = Depends(get_tenant_id)):
    # Whitelist valid statuses to prevent injection
    if status not in ("approved", "rejected"):
        raise HTTPException(status_code=400, detail="Status must be 'approved' or 'rejected'")
    success = await process_approval_db(approval_id, status, tenant_id)
    if not success:
        raise HTTPException(status_code=404, detail="Approval not found or unauthorized")
    return {"ok": True}
