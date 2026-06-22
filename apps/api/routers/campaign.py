"""
Campaign Manager - Autonomous B2B Outreach Engine
Manages leads, triggers calls, tracks outcomes, and pushes real-time escalation alerts.
"""
import asyncio
import os
import re
import uuid
from datetime import UTC, datetime

import httpx
import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from apps.api.services.auth import verify_api_key
from apps.api.services.database import db_context_sync

logger = structlog.get_logger()

router = APIRouter(prefix="/campaign", tags=["campaign"])

# Campaign deduplication lock — prevents double-launch race condition
_campaign_lock = asyncio.Lock()
_campaign_running = False


# ── Pydantic Models ──────────────────────────────────────────────

class LeadCreate(BaseModel):
    company_name: str = Field(..., min_length=1, max_length=200)
    contact_name: str | None = Field(default=None, max_length=200)
    phone: str
    email: str | None = Field(default=None, max_length=200)
    industry: str | None = Field(default=None, max_length=100)
    notes: str | None = Field(default=None, max_length=1000)
    priority: int = Field(default=5, ge=1, le=10)

    @field_validator('phone')
    @classmethod
    def validate_phone(cls, v: str) -> str:
        # E.164 format: + followed by 7-15 digits
        cleaned = re.sub(r'[\s\-\(\)]', '', v)
        if not re.match(r'^\+?[1-9]\d{6,14}$', cleaned):
            raise ValueError('Phone must be in E.164 format (e.g., +15551234567)')
        if not cleaned.startswith('+'):
            cleaned = '+' + cleaned
        return cleaned


class LeadBulkImport(BaseModel):
    leads: list[LeadCreate] = Field(..., max_length=500)  # Cap bulk imports


class CampaignLaunch(BaseModel):
    profile_id: str = "PROF-META-SALES"
    max_concurrent: int = Field(default=3, ge=1, le=10)
    delay_between_calls: float = Field(default=5.0, ge=2.0, le=60.0)
    filter_status: str = "new"  # Only call leads with this status


# ── Lead CRUD ────────────────────────────────────────────────────

@router.get("/leads")
async def list_leads(status: str | None = None, tenant_id: str = Depends(verify_api_key)):
    with db_context_sync() as conn:
        cursor = conn.cursor()
        if status:
            cursor.execute(
                "SELECT * FROM leads WHERE tenant_id = ? AND status = ? ORDER BY priority ASC, created_at DESC",
                (tenant_id, status)
            )
        else:
            cursor.execute(
                "SELECT * FROM leads WHERE tenant_id = ? ORDER BY priority ASC, created_at DESC",
                (tenant_id,)
            )
        rows = cursor.fetchall()
    return [dict(r) for r in rows]


@router.post("/leads")
async def create_lead(lead: LeadCreate, tenant_id: str = Depends(verify_api_key)):
    lead_id = f"LEAD-{uuid.uuid4().hex[:8].upper()}"
    with db_context_sync() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO leads (id, tenant_id, company_name, contact_name, phone, email, industry, notes, priority) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (lead_id, tenant_id, lead.company_name, lead.contact_name, lead.phone, lead.email, lead.industry, lead.notes, lead.priority)
        )
        conn.commit()
    return {"id": lead_id, "status": "created"}


@router.post("/leads/bulk")
async def bulk_import_leads(data: LeadBulkImport, tenant_id: str = Depends(verify_api_key)):
    created = []
    with db_context_sync() as conn:
        cursor = conn.cursor()
        for lead in data.leads:
            lead_id = f"LEAD-{uuid.uuid4().hex[:8].upper()}"
            cursor.execute(
                "INSERT INTO leads (id, tenant_id, company_name, contact_name, phone, email, industry, notes, priority) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (lead_id, tenant_id, lead.company_name, lead.contact_name, lead.phone, lead.email, lead.industry, lead.notes, lead.priority)
            )
            created.append(lead_id)
        conn.commit()
    return {"imported": len(created), "ids": created}


@router.patch("/leads/{lead_id}")
async def update_lead(lead_id: str, status: str | None = None, notes: str | None = None, tenant_id: str = Depends(verify_api_key)):
    VALID_STATUSES = {'new', 'queued', 'calling', 'answered', 'voicemail', 'no_answer', 'interested', 'follow_up', 'converted', 'declined'}
    if status and status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {', '.join(VALID_STATUSES)}")

    with db_context_sync() as conn:
        cursor = conn.cursor()
        # Verify lead exists and belongs to tenant (IDOR protection)
        cursor.execute("SELECT id FROM leads WHERE id = ? AND tenant_id = ?", (lead_id, tenant_id))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Lead not found")
        if status:
            cursor.execute("UPDATE leads SET status = ? WHERE id = ? AND tenant_id = ?", (status, lead_id, tenant_id))
        if notes:
            cursor.execute("UPDATE leads SET notes = ? WHERE id = ? AND tenant_id = ?", (notes[:1000], lead_id, tenant_id))
        conn.commit()
    return {"updated": lead_id}


# ── Campaign Call Tracking ───────────────────────────────────────

@router.get("/calls")
async def list_campaign_calls(outcome: str | None = None, tenant_id: str = Depends(verify_api_key)):
    with db_context_sync() as conn:
        cursor = conn.cursor()
        if outcome:
            cursor.execute(
                "SELECT cc.*, l.company_name, l.contact_name FROM campaign_calls cc JOIN leads l ON cc.lead_id = l.id WHERE cc.tenant_id = ? AND cc.outcome = ? ORDER BY cc.started_at DESC",
                (tenant_id, outcome)
            )
        else:
            cursor.execute(
                "SELECT cc.*, l.company_name, l.contact_name FROM campaign_calls cc JOIN leads l ON cc.lead_id = l.id WHERE cc.tenant_id = ? ORDER BY cc.started_at DESC",
                (tenant_id,)
            )
        rows = cursor.fetchall()
    return [dict(r) for r in rows]


@router.get("/stats")
async def campaign_stats(tenant_id: str = Depends(verify_api_key)):
    with db_context_sync() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                (SELECT COUNT(*) FROM leads WHERE tenant_id = ?) AS total_leads,
                (SELECT COUNT(*) FROM leads WHERE tenant_id = ? AND status = 'new') AS new_leads,
                (SELECT COUNT(*) FROM campaign_calls WHERE tenant_id = ?) AS total_calls,
                (SELECT COUNT(*) FROM campaign_calls WHERE tenant_id = ? AND outcome = 'interested') AS interested,
                (SELECT COUNT(*) FROM campaign_calls WHERE tenant_id = ? AND needs_human_follow_up = 1) AS needs_human
        """, (tenant_id, tenant_id, tenant_id, tenant_id, tenant_id))
        row = cursor.fetchone() or {}

    total_calls = row.get("total_calls", 0) or 0
    interested = row.get("interested", 0) or 0

    return {
        "total_leads": row.get("total_leads", 0) or 0,
        "untouched_leads": row.get("new_leads", 0) or 0,
        "total_calls_made": total_calls,
        "interested": interested,
        "needs_human_follow_up": row.get("needs_human", 0) or 0,
        "conversion_rate": f"{(interested / total_calls * 100):.1f}%" if total_calls > 0 else "0%"
    }


# ── Autonomous Dialer ───────────────────────────────────────────

@router.post("/launch")
async def launch_campaign(config: CampaignLaunch, tenant_id: str = Depends(verify_api_key)):
    global _campaign_running

    async with _campaign_lock:
        if _campaign_running:
            raise HTTPException(status_code=409, detail="A campaign is already running. Wait for it to complete.")

        with db_context_sync() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM leads WHERE tenant_id = ? AND status = ? ORDER BY priority ASC LIMIT 50",
                (tenant_id, config.filter_status)
            )
            leads = [dict(r) for r in cursor.fetchall()]

        if not leads:
            return {"status": "no_leads", "message": "No leads match the filter criteria."}

        _campaign_running = True

    # Launch the campaign in background
    asyncio.create_task(_run_campaign(leads, config, tenant_id))

    return {
        "status": "launched",
        "leads_queued": len(leads),
        "profile": config.profile_id,
        "max_concurrent": config.max_concurrent
    }


async def _run_campaign(leads: list, config: CampaignLaunch, tenant_id: str):
    """Background task that dials through the lead list."""
    global _campaign_running

    api_key = os.getenv("INTERNAL_API_KEY", "dev-api-key")

    logger.info("campaign_started", total_leads=len(leads), profile=config.profile_id, tenant=tenant_id)

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            for i, lead in enumerate(leads):
                # Update lead status to 'calling'
                with db_context_sync() as conn:
                    cursor = conn.cursor()
                    cursor.execute("UPDATE leads SET status = 'calling', last_called_at = ? WHERE id = ?",
                                 (datetime.now(UTC).isoformat(), lead["id"]))
                    conn.commit()

                # Create campaign_call record
                call_id = f"CC-{uuid.uuid4().hex[:8].upper()}"
                with db_context_sync() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        "INSERT INTO campaign_calls (id, tenant_id, lead_id, profile_id, status) VALUES (?, ?, ?, ?, ?)",
                        (call_id, tenant_id, lead["id"], config.profile_id, "initiated")
                    )
                    conn.commit()

                # Trigger the actual call via the voice API
                try:
                    resp = await client.post(
                        "http://localhost:8000/api/v1/voice/outbound",
                        json={"to_phone": lead["phone"], "profile_id": config.profile_id},
                        headers={"X-API-Key": api_key}
                    )
                    result = resp.json()

                    call_sid = result.get("call_sid", "unknown")
                    with db_context_sync() as conn:
                        cursor = conn.cursor()
                        cursor.execute("UPDATE campaign_calls SET call_sid = ?, status = 'ringing' WHERE id = ?",
                                     (call_sid, call_id))
                        conn.commit()

                    logger.info("campaign_call_dialed", lead=lead["company_name"], call_sid=call_sid, position=f"{i+1}/{len(leads)}")

                except Exception as e:
                    logger.error("campaign_call_failed", lead=lead["id"], error=str(e))
                    try:
                        with db_context_sync() as conn:
                            cursor = conn.cursor()
                            cursor.execute("UPDATE campaign_calls SET status = 'failed' WHERE id = ?", (call_id,))
                            cursor.execute("UPDATE leads SET status = 'new' WHERE id = ?", (lead["id"],))
                            conn.commit()
                    except Exception as db_err:
                        logger.error("campaign_call_failed_db_cleanup_error", lead=lead["id"], error=str(db_err))

                # Throttle between calls
                await asyncio.sleep(config.delay_between_calls)
    finally:
        async with _campaign_lock:
            _campaign_running = False

    logger.info("campaign_completed", total_dialed=len(leads))


# ── Real-Time Escalation Push ────────────────────────────────────

async def push_escalation_alert(call_sid: str, reason: str, agent_name: str):
    """
    Push a real-time WebSocket notification to ALL connected supervisors
    when the AI agent needs human intervention.
    """
    from apps.api.routers.realtime import manager

    alert = {
        "type": "escalation_alert",
        "call_sid": call_sid,
        "agent": agent_name,
        "reason": reason,
        "timestamp": datetime.now(UTC).isoformat(),
        "severity": "high" if "manager" in reason.lower() else "medium"
    }

    await manager.broadcast_to_queue("default", alert)
    logger.info("escalation_pushed", call_sid=call_sid, reason=reason)
