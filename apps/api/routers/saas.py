import json
import os
import uuid
from datetime import datetime, timedelta

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException

from apps.api.services.database import db_context

router = APIRouter(prefix="/saas", tags=["saas"])


def get_tenant_id(x_api_key: str = Header(...)):
    if os.getenv("ENV") == "test":
        return "TENANT-001"
    if os.getenv("ENV") != "production" and x_api_key == os.getenv("DEV_API_KEY", "dev-api-key"):
        return "TENANT-001"

    with db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM tenants WHERE api_key = ?", (x_api_key,))
        row = cursor.fetchone()

    if not row:
        raise HTTPException(status_code=401, detail="Invalid Tenant API Key")
    return row["id"]

@router.get("/dashboard")
async def get_saas_dashboard(tenant_id: str = Depends(get_tenant_id)):
    with db_context() as conn:
        cursor = conn.cursor()

        # Get Rentals
        cursor.execute("SELECT * FROM rentals WHERE tenant_id = ?", (tenant_id,))
        rentals = [dict(row) for row in cursor.fetchall()]

        # Get Profiles
        cursor.execute("SELECT * FROM agent_profiles WHERE tenant_id = ?", (tenant_id,))
        profiles = [dict(row) for row in cursor.fetchall()]

    return {
        "rentals": rentals,
        "profiles": profiles
    }

@router.post("/profile")
async def create_profile(name: str, prompt: str, parameters: dict, tenant_id: str = Depends(get_tenant_id)):
    profile_id = f"PROF-{uuid.uuid4().hex[:6].upper()}"
    with db_context() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO agent_profiles (id, tenant_id, name, prompt, parameters) VALUES (?, ?, ?, ?, ?)",
            (profile_id, tenant_id, name, prompt, json.dumps(parameters))
        )
        conn.commit()
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

    with db_context() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO rentals (id, tenant_id, profile_id, duration_type, end_time) VALUES (?, ?, ?, ?, ?)",
            (rental_id, tenant_id, profile_id, duration_type, end_time.strftime("%Y-%m-%d %H:%M:%S"))
        )
        conn.commit()
    return {"ok": True, "rental_id": rental_id, "end_time": end_time}

@router.get("/settings")
async def get_settings(tenant_id: str = Depends(get_tenant_id)):
    with db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM tenant_settings WHERE tenant_id = ?", (tenant_id,))
        row = cursor.fetchone()
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
    with db_context() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO tenant_settings (tenant_id, api_feeds, auto_mode_enabled, redact_pii, require_consent, sync_dnc, mcp_servers)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(tenant_id) DO UPDATE SET
               api_feeds=excluded.api_feeds,
               auto_mode_enabled=excluded.auto_mode_enabled,
               redact_pii=excluded.redact_pii,
               require_consent=excluded.require_consent,
               sync_dnc=excluded.sync_dnc,
               mcp_servers=excluded.mcp_servers""",
            (tenant_id, json.dumps(settings.get("api_feeds")),
             settings.get("auto_mode_enabled", 0),
             settings.get("redact_pii", 1),
             settings.get("require_consent", 1),
             settings.get("sync_dnc", 0),
             json.dumps(settings.get("mcp_servers", "{}")))
        )
        conn.commit()
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
    with db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM session_recordings WHERE tenant_id = ? ORDER BY created_at DESC", (tenant_id,))
        rows = [dict(r) for r in cursor.fetchall()]
    return rows

@router.get("/approvals")
async def get_approvals(tenant_id: str = Depends(get_tenant_id)):
    with db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM action_approvals WHERE status = 'pending' AND tenant_id = ?", (tenant_id,))
        rows = [dict(r) for r in cursor.fetchall()]
    return rows

@router.post("/approvals/{approval_id}")
async def process_approval(approval_id: str, status: str, tenant_id: str = Depends(get_tenant_id)):
    # Whitelist valid statuses to prevent injection
    if status not in ("approved", "rejected"):
        raise HTTPException(status_code=400, detail="Status must be 'approved' or 'rejected'")
    with db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE action_approvals SET status = ? WHERE id = ? AND tenant_id = ?", (status, approval_id, tenant_id))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Approval not found or unauthorized")
        conn.commit()
    return {"ok": True}
