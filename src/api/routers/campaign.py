"""
Campaign Manager - Autonomous B2B Outreach Engine
Manages leads, campaigns (with per-campaign budgets), triggers calls,
tracks outcomes, and pushes real-time escalation alerts.

Uses the async `db_context` abstraction so it runs on both PostgreSQL
(production) and SQLite (local dev) — the previous implementation was
SQLite-only via `db_context_sync` and crashed under Postgres.
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

from api.services.auth import verify_api_key
from api.services.database import USE_POSTGRES, db_context

logger = structlog.get_logger()

router = APIRouter(prefix="/campaign", tags=["campaign"])

# Campaign deduplication lock — prevents double-launch race condition.
# NOTE: process-local; for multi-worker deployments, campaign running state
# is ALSO persisted in the campaigns table (status='running') and recovered
# on startup.
_campaign_lock = asyncio.Lock()
_campaign_running = False

# Runtime-configured voice API base URL (not hardcoded localhost).
VOICE_API_URL = os.getenv("VOICE_API_URL", "http://localhost:8000")


# ── Pydantic Models ──────────────────────────────────────────────


class LeadCreate(BaseModel):
    company_name: str = Field(..., min_length=1, max_length=200)
    contact_name: str | None = Field(default=None, max_length=200)
    phone: str
    email: str | None = Field(default=None, max_length=200)
    industry: str | None = Field(default=None, max_length=100)
    notes: str | None = Field(default=None, max_length=1000)
    priority: int = Field(default=5, ge=1, le=10)

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        # E.164 format: + followed by 7-15 digits
        cleaned = re.sub(r"[\s\-\(\)]", "", v)
        if not re.match(r"^\+?[1-9]\d{6,14}$", cleaned):
            raise ValueError("Phone must be in E.164 format (e.g., +15551234567)")
        if not cleaned.startswith("+"):
            cleaned = "+" + cleaned
        return cleaned


class LeadBulkImport(BaseModel):
    leads: list[LeadCreate] = Field(..., max_length=500)  # Cap bulk imports


class CampaignCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    budget_cents: int = Field(default=0, ge=0)  # 0 = unlimited
    profile_id: str = "PROF-META-SALES"
    max_concurrent: int = Field(default=3, ge=1, le=10)
    delay_between_calls: float = Field(default=5.0, ge=2.0, le=60.0)
    filter_status: str = "new"


class CampaignUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    budget_cents: int | None = Field(default=None, ge=0)
    status: str | None = None
    profile_id: str | None = None
    max_concurrent: int | None = Field(default=None, ge=1, le=10)
    delay_between_calls: float | None = Field(default=None, ge=2.0, le=60.0)
    filter_status: str | None = None


class CampaignLaunch(BaseModel):
    campaign_id: str | None = None  # Launch an existing campaign (uses its budget)
    profile_id: str = "PROF-META-SALES"
    max_concurrent: int = Field(default=3, ge=1, le=10)
    delay_between_calls: float = Field(default=5.0, ge=2.0, le=60.0)
    filter_status: str = "new"  # Only call leads with this status


# ── DB helpers (async, dual-dialect) ─────────────────────────────


async def _run_query(conn, query: str, params: tuple = (), fetch=None):
    """Execute a query against asyncpg (Postgres) or sqlite (SQLite)."""
    if USE_POSTGRES:
        if fetch == "all":
            return [dict(r) for r in await conn.fetch(query, *params)]
        if fetch == "one":
            row = await conn.fetchrow(query, *params)
            return dict(row) if row else None
        await conn.execute(query, *params)
        return None
    else:
        cursor = conn.cursor()
        cursor.execute(query, params)
        if fetch == "all":
            return [dict(r) for r in cursor.fetchall()]
        if fetch == "one":
            row = cursor.fetchone()
            return dict(row) if row else None
        conn.commit()
        return None


# ── Lead CRUD ────────────────────────────────────────────────────


@router.get("/leads")
async def list_leads(
    status: str | None = None, tenant_id: str = Depends(verify_api_key)
):
    async with db_context() as conn:
        if status:
            rows = await _run_query(
                conn,
                "SELECT * FROM leads WHERE tenant_id = %s AND status = %s ORDER BY priority ASC, created_at DESC"
                if USE_POSTGRES
                else "SELECT * FROM leads WHERE tenant_id = ? AND status = ? ORDER BY priority ASC, created_at DESC",
                (tenant_id, status),
                fetch="all",
            )
        else:
            rows = await _run_query(
                conn,
                "SELECT * FROM leads WHERE tenant_id = %s ORDER BY priority ASC, created_at DESC"
                if USE_POSTGRES
                else "SELECT * FROM leads WHERE tenant_id = ? ORDER BY priority ASC, created_at DESC",
                (tenant_id,),
                fetch="all",
            )
    return rows or []


@router.post("/leads")
async def create_lead(lead: LeadCreate, tenant_id: str = Depends(verify_api_key)):
    lead_id = f"LEAD-{uuid.uuid4().hex[:8].upper()}"
    async with db_context() as conn:
        await _run_query(
            conn,
            "INSERT INTO leads (id, tenant_id, company_name, contact_name, phone, email, industry, notes, priority) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"
            if USE_POSTGRES
            else "INSERT INTO leads (id, tenant_id, company_name, contact_name, phone, email, industry, notes, priority) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                lead_id,
                tenant_id,
                lead.company_name,
                lead.contact_name,
                lead.phone,
                lead.email,
                lead.industry,
                lead.notes,
                lead.priority,
            ),
        )
    return {"id": lead_id, "status": "created"}


@router.post("/leads/bulk")
async def bulk_import_leads(
    data: LeadBulkImport, tenant_id: str = Depends(verify_api_key)
):
    created = []
    async with db_context() as conn:
        for lead in data.leads:
            lead_id = f"LEAD-{uuid.uuid4().hex[:8].upper()}"
            await _run_query(
                conn,
                "INSERT INTO leads (id, tenant_id, company_name, contact_name, phone, email, industry, notes, priority) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"
                if USE_POSTGRES
                else "INSERT INTO leads (id, tenant_id, company_name, contact_name, phone, email, industry, notes, priority) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    lead_id,
                    tenant_id,
                    lead.company_name,
                    lead.contact_name,
                    lead.phone,
                    lead.email,
                    lead.industry,
                    lead.notes,
                    lead.priority,
                ),
            )
            created.append(lead_id)
    return {"imported": len(created), "ids": created}


@router.patch("/leads/{lead_id}")
async def update_lead(
    lead_id: str,
    status: str | None = None,
    notes: str | None = None,
    tenant_id: str = Depends(verify_api_key),
):
    VALID_STATUSES = {
        "new",
        "queued",
        "calling",
        "answered",
        "voicemail",
        "no_answer",
        "interested",
        "follow_up",
        "converted",
        "declined",
    }
    if status and status not in VALID_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status. Must be one of: {', '.join(VALID_STATUSES)}",
        )

    async with db_context() as conn:
        # Verify lead exists and belongs to tenant (IDOR protection)
        existing = await _run_query(
            conn,
            "SELECT id FROM leads WHERE id = %s AND tenant_id = %s"
            if USE_POSTGRES
            else "SELECT id FROM leads WHERE id = ? AND tenant_id = ?",
            (lead_id, tenant_id),
            fetch="one",
        )
        if not existing:
            raise HTTPException(status_code=404, detail="Lead not found")
        if status:
            await _run_query(
                conn,
                "UPDATE leads SET status = %s WHERE id = %s AND tenant_id = %s"
                if USE_POSTGRES
                else "UPDATE leads SET status = ? WHERE id = ? AND tenant_id = ?",
                (status, lead_id, tenant_id),
            )
        if notes:
            await _run_query(
                conn,
                "UPDATE leads SET notes = %s WHERE id = %s AND tenant_id = %s"
                if USE_POSTGRES
                else "UPDATE leads SET notes = ? WHERE id = ? AND tenant_id = ?",
                (notes[:1000], lead_id, tenant_id),
            )
    return {"updated": lead_id}


# ── Campaign CRUD (budget-gated) ────────────────────────────────


@router.get("/campaigns")
async def list_campaigns(tenant_id: str = Depends(verify_api_key)):
    async with db_context() as conn:
        rows = await _run_query(
            conn,
            "SELECT * FROM campaigns WHERE tenant_id = %s ORDER BY created_at DESC"
            if USE_POSTGRES
            else "SELECT * FROM campaigns WHERE tenant_id = ? ORDER BY created_at DESC",
            (tenant_id,),
            fetch="all",
        )
    return rows or []


@router.post("/campaigns")
async def create_campaign(
    campaign: CampaignCreate, tenant_id: str = Depends(verify_api_key)
):
    campaign_id = f"CAMP-{uuid.uuid4().hex[:8].upper()}"
    async with db_context() as conn:
        await _run_query(
            conn,
            "INSERT INTO campaigns (id, tenant_id, name, description, budget_cents, status, profile_id, max_concurrent, delay_between_calls, filter_status) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
            if USE_POSTGRES
            else "INSERT INTO campaigns (id, tenant_id, name, description, budget_cents, status, profile_id, max_concurrent, delay_between_calls, filter_status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                campaign_id,
                tenant_id,
                campaign.name,
                campaign.description,
                campaign.budget_cents,
                "draft",
                campaign.profile_id,
                campaign.max_concurrent,
                campaign.delay_between_calls,
                campaign.filter_status,
            ),
        )
    return {"id": campaign_id, "status": "created"}


@router.get("/campaigns/{campaign_id}")
async def get_campaign(campaign_id: str, tenant_id: str = Depends(verify_api_key)):
    async with db_context() as conn:
        row = await _run_query(
            conn,
            "SELECT * FROM campaigns WHERE id = %s AND tenant_id = %s"
            if USE_POSTGRES
            else "SELECT * FROM campaigns WHERE id = ? AND tenant_id = ?",
            (campaign_id, tenant_id),
            fetch="one",
        )
    if not row:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return row


@router.patch("/campaigns/{campaign_id}")
async def update_campaign(
    campaign_id: str, updates: CampaignUpdate, tenant_id: str = Depends(verify_api_key)
):
    fields = updates.model_dump(exclude_unset=True)
    if not fields:
        return {"updated": campaign_id}
    if "status" in fields and fields["status"] not in {
        "draft",
        "active",
        "paused",
        "completed",
        "budget_exhausted",
    }:
        raise HTTPException(status_code=400, detail="Invalid campaign status")

    col_map = {
        "name": "name",
        "description": "description",
        "budget_cents": "budget_cents",
        "status": "status",
        "profile_id": "profile_id",
        "max_concurrent": "max_concurrent",
        "delay_between_calls": "delay_between_calls",
        "filter_status": "filter_status",
    }
    sets = []
    params = []
    for key, val in fields.items():
        if key in col_map and val is not None:
            sets.append(
                f"{col_map[key]} = %s" if USE_POSTGRES else f"{col_map[key]} = ?"
            )
            params.append(val)
    if not sets:
        return {"updated": campaign_id}
    params.extend([campaign_id, tenant_id])
    async with db_context() as conn:
        await _run_query(
            conn,
            f"UPDATE campaigns SET {', '.join(sets)} WHERE id = {'%s' if USE_POSTGRES else '?'} AND tenant_id = {'%s' if USE_POSTGRES else '?'}",
            tuple(params),
        )
    return {"updated": campaign_id}


# ── Campaign Call Tracking ───────────────────────────────────────


@router.get("/calls")
async def list_campaign_calls(
    outcome: str | None = None, tenant_id: str = Depends(verify_api_key)
):
    async with db_context() as conn:
        if outcome:
            rows = await _run_query(
                conn,
                "SELECT cc.*, l.company_name, l.contact_name FROM campaign_calls cc JOIN leads l ON cc.lead_id = l.id WHERE cc.tenant_id = %s AND cc.outcome = %s ORDER BY cc.started_at DESC"
                if USE_POSTGRES
                else "SELECT cc.*, l.company_name, l.contact_name FROM campaign_calls cc JOIN leads l ON cc.lead_id = l.id WHERE cc.tenant_id = ? AND cc.outcome = ? ORDER BY cc.started_at DESC",
                (tenant_id, outcome),
                fetch="all",
            )
        else:
            rows = await _run_query(
                conn,
                "SELECT cc.*, l.company_name, l.contact_name FROM campaign_calls cc JOIN leads l ON cc.lead_id = l.id WHERE cc.tenant_id = %s ORDER BY cc.started_at DESC"
                if USE_POSTGRES
                else "SELECT cc.*, l.company_name, l.contact_name FROM campaign_calls cc JOIN leads l ON cc.lead_id = l.id WHERE cc.tenant_id = ? ORDER BY cc.started_at DESC",
                (tenant_id,),
                fetch="all",
            )
    return rows or []


@router.post("/calls/{call_id}/outcome")
async def record_call_outcome(
    call_id: str,
    outcome: str,
    cost_usd: float = 0.0,
    tenant_id: str = Depends(verify_api_key),
):
    """Record a campaign call outcome + cost (called by voice webhook / supervisor)."""
    VALID_OUTCOMES = {
        "interested",
        "not_interested",
        "voicemail",
        "no_answer",
        "answered",
        "follow_up",
        "converted",
        "declined",
        "failed",
    }
    if outcome not in VALID_OUTCOMES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid outcome. Must be one of: {', '.join(VALID_OUTCOMES)}",
        )
    async with db_context() as conn:
        row = await _run_query(
            conn,
            "SELECT id, lead_id FROM campaign_calls WHERE id = %s AND tenant_id = %s"
            if USE_POSTGRES
            else "SELECT id, lead_id FROM campaign_calls WHERE id = ? AND tenant_id = ?",
            (call_id, tenant_id),
            fetch="one",
        )
        if not row:
            raise HTTPException(status_code=404, detail="Campaign call not found")
        await _run_query(
            conn,
            "UPDATE campaign_calls SET outcome = %s, cost_usd = %s, ended_at = %s WHERE id = %s"
            if USE_POSTGRES
            else "UPDATE campaign_calls SET outcome = ?, cost_usd = ?, ended_at = ? WHERE id = ?",
            (outcome, cost_usd, datetime.now(UTC).isoformat(), call_id),
        )
        # Advance lead status based on outcome
        lead_status = {
            "interested": "interested",
            "converted": "converted",
            "follow_up": "follow_up",
            "not_interested": "declined",
            "voicemail": "new",
            "no_answer": "new",
            "failed": "new",
        }.get(outcome, "new")
        if lead_status:
            await _run_query(
                conn,
                "UPDATE leads SET status = %s WHERE id = %s"
                if USE_POSTGRES
                else "UPDATE leads SET status = ? WHERE id = ?",
                (lead_status, row["lead_id"]),
            )
    return {"recorded": call_id}


@router.get("/stats")
async def campaign_stats(tenant_id: str = Depends(verify_api_key)):
    async with db_context() as conn:
        row = await _run_query(
            conn,
            "SELECT "
            "(SELECT COUNT(*) FROM leads WHERE tenant_id = %s) AS total_leads, "
            "(SELECT COUNT(*) FROM leads WHERE tenant_id = %s AND status = 'new') AS new_leads, "
            "(SELECT COUNT(*) FROM campaign_calls WHERE tenant_id = %s) AS total_calls, "
            "(SELECT COUNT(*) FROM campaign_calls WHERE tenant_id = %s AND outcome = 'interested') AS interested, "
            "(SELECT COUNT(*) FROM campaign_calls WHERE tenant_id = %s AND needs_human_follow_up = 1) AS needs_human"
            if USE_POSTGRES
            else "SELECT "
            "(SELECT COUNT(*) FROM leads WHERE tenant_id = ?) AS total_leads, "
            "(SELECT COUNT(*) FROM leads WHERE tenant_id = ? AND status = 'new') AS new_leads, "
            "(SELECT COUNT(*) FROM campaign_calls WHERE tenant_id = ?) AS total_calls, "
            "(SELECT COUNT(*) FROM campaign_calls WHERE tenant_id = ? AND outcome = 'interested') AS interested, "
            "(SELECT COUNT(*) FROM campaign_calls WHERE tenant_id = ? AND needs_human_follow_up = 1) AS needs_human",
            (tenant_id, tenant_id, tenant_id, tenant_id, tenant_id),
            fetch="one",
        )

    total_calls = (row or {}).get("total_calls", 0) or 0
    interested = (row or {}).get("interested", 0) or 0

    return {
        "total_leads": (row or {}).get("total_leads", 0) or 0,
        "untouched_leads": (row or {}).get("new_leads", 0) or 0,
        "total_calls_made": total_calls,
        "interested": interested,
        "needs_human_follow_up": (row or {}).get("needs_human", 0) or 0,
        "conversion_rate": f"{(interested / total_calls * 100):.1f}%"
        if total_calls > 0
        else "0%",
    }


# ── Autonomous Dialer (budget-aware) ────────────────────────────


async def _get_campaign(conn, campaign_id: str, tenant_id: str) -> dict | None:
    return await _run_query(
        conn,
        "SELECT * FROM campaigns WHERE id = %s AND tenant_id = %s"
        if USE_POSTGRES
        else "SELECT * FROM campaigns WHERE id = ? AND tenant_id = ?",
        (campaign_id, tenant_id),
        fetch="one",
    )


@router.post("/launch")
async def launch_campaign(
    config: CampaignLaunch, tenant_id: str = Depends(verify_api_key)
):
    global _campaign_running

    async with _campaign_lock:
        if _campaign_running:
            raise HTTPException(
                status_code=409,
                detail="A campaign is already running. Wait for it to complete.",
            )

        # Resolve campaign (explicit id, or create/use a one-off).
        campaign = None
        if config.campaign_id:
            async with db_context() as conn:
                campaign = await _get_campaign(conn, config.campaign_id, tenant_id)
            if not campaign:
                raise HTTPException(status_code=404, detail="Campaign not found")
            if campaign.get("status") == "budget_exhausted":
                raise HTTPException(status_code=400, detail="Campaign budget exhausted")
            if (
                campaign.get("budget_cents", 0)
                and campaign.get("spent_cents", 0) >= campaign["budget_cents"]
            ):
                raise HTTPException(status_code=400, detail="Campaign budget exhausted")
            filter_status = campaign.get("filter_status") or "new"
            profile_id = campaign.get("profile_id") or config.profile_id
            max_concurrent = campaign.get("max_concurrent") or config.max_concurrent
            delay = campaign.get("delay_between_calls") or config.delay_between_calls
        else:
            filter_status = config.filter_status
            profile_id = config.profile_id
            max_concurrent = config.max_concurrent
            delay = config.delay_between_calls

        async with db_context() as conn:
            leads = await _run_query(
                conn,
                "SELECT * FROM leads WHERE tenant_id = %s AND status = %s ORDER BY priority ASC LIMIT 50"
                if USE_POSTGRES
                else "SELECT * FROM leads WHERE tenant_id = ? AND status = ? ORDER BY priority ASC LIMIT 50",
                (tenant_id, filter_status),
                fetch="all",
            )

        if not leads:
            return {
                "status": "no_leads",
                "message": "No leads match the filter criteria.",
            }

        _campaign_running = True
        if campaign:
            async with db_context() as conn:
                await _run_query(
                    conn,
                    "UPDATE campaigns SET status = 'active', started_at = %s WHERE id = %s"
                    if USE_POSTGRES
                    else "UPDATE campaigns SET status = 'active', started_at = ? WHERE id = ?",
                    (datetime.now(UTC).isoformat(), campaign["id"]),
                )

    # Launch the campaign in background
    asyncio.create_task(
        _run_campaign(leads, profile_id, max_concurrent, delay, tenant_id, campaign)
    )

    return {
        "status": "launched",
        "leads_queued": len(leads),
        "profile": profile_id,
        "max_concurrent": max_concurrent,
        "campaign_id": campaign["id"] if campaign else None,
    }


async def _check_budget(tenant_id: str, campaign: dict | None) -> bool:
    """Return True if spending may continue (budget not exhausted)."""
    if not campaign:
        return True
    budget_cents = campaign.get("budget_cents", 0) or 0
    if budget_cents <= 0:
        return True
    async with db_context() as conn:
        row = await _run_query(
            conn,
            "SELECT COALESCE(SUM(cost_usd), 0) AS spent FROM campaign_calls WHERE tenant_id = %s AND outcome IS NOT NULL"
            if USE_POSTGRES
            else "SELECT COALESCE(SUM(cost_usd), 0) AS spent FROM campaign_calls WHERE tenant_id = ? AND outcome IS NOT NULL",
            (tenant_id,),
            fetch="one",
        )
        spent = float((row or {}).get("spent", 0) or 0)
        spent_cents = int(spent * 100)
        # Persist spent for dashboard visibility.
        await _run_query(
            conn,
            "UPDATE campaigns SET spent_cents = %s WHERE id = %s"
            if USE_POSTGRES
            else "UPDATE campaigns SET spent_cents = ? WHERE id = ?",
            (spent_cents, campaign["id"]),
        )
    if spent_cents >= budget_cents:
        async with db_context() as conn:
            await _run_query(
                conn,
                "UPDATE campaigns SET status = 'budget_exhausted', ended_at = %s WHERE id = %s"
                if USE_POSTGRES
                else "UPDATE campaigns SET status = 'budget_exhausted', ended_at = ? WHERE id = ?",
                (datetime.now(UTC).isoformat(), campaign["id"]),
            )
        logger.info(
            "campaign_budget_exhausted",
            campaign_id=campaign["id"],
            spent_cents=spent_cents,
            budget_cents=budget_cents,
        )
        return False
    return True


async def _run_campaign(
    leads: list,
    profile_id: str,
    max_concurrent: int,
    delay_between_calls: float,
    tenant_id: str,
    campaign: dict | None,
):
    """Background task that dials through the lead list, budget-gated and
    concurrency-limited via a semaphore."""
    global _campaign_running

    api_key = os.getenv("INTERNAL_API_KEY", "dev-api-key")

    logger.info(
        "campaign_started",
        total_leads=len(leads),
        profile=profile_id,
        tenant=tenant_id,
        campaign_id=campaign["id"] if campaign else None,
    )

    sem = asyncio.Semaphore(max_concurrent)

    async def dial_one(lead: dict, position: int):
        if not await _check_budget(tenant_id, campaign):
            return

        async with db_context() as conn:
            # Update lead status to 'calling'
            await _run_query(
                conn,
                "UPDATE leads SET status = 'calling', last_called_at = %s WHERE id = %s"
                if USE_POSTGRES
                else "UPDATE leads SET status = 'calling', last_called_at = ? WHERE id = ?",
                (datetime.now(UTC).isoformat(), lead["id"]),
            )
            # Create campaign_call record
            call_id = f"CC-{uuid.uuid4().hex[:8].upper()}"
            campaign["id"] if campaign else None
            await _run_query(
                conn,
                "INSERT INTO campaign_calls (id, tenant_id, lead_id, profile_id, status) VALUES (%s, %s, %s, %s, %s)"
                if USE_POSTGRES
                else "INSERT INTO campaign_calls (id, tenant_id, lead_id, profile_id, status) VALUES (?, ?, ?, ?, ?)",
                (call_id, tenant_id, lead["id"], profile_id, "initiated"),
            )

        # Trigger the actual call via the voice API
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"{VOICE_API_URL}/api/v1/voice/outbound",
                    json={"to_phone": lead["phone"], "profile_id": profile_id},
                    headers={"X-API-Key": api_key},
                )
                result = resp.json()

            # The voice API returns call_ref (Twilio) or call_sid (mock/Fonoster).
            call_sid = result.get("call_sid") or result.get("call_ref") or "unknown"
            async with db_context() as conn:
                await _run_query(
                    conn,
                    "UPDATE campaign_calls SET call_sid = %s, status = 'ringing' WHERE id = %s"
                    if USE_POSTGRES
                    else "UPDATE campaign_calls SET call_sid = ?, status = 'ringing' WHERE id = ?",
                    (call_sid, call_id),
                )
            logger.info(
                "campaign_call_dialed",
                lead=lead["company_name"],
                call_sid=call_sid,
                position=f"{position}/{len(leads)}",
            )

        except Exception as e:
            logger.error("campaign_call_failed", lead=lead["id"], error=str(e))
            try:
                async with db_context() as conn:
                    await _run_query(
                        conn,
                        "UPDATE campaign_calls SET status = 'failed' WHERE id = %s"
                        if USE_POSTGRES
                        else "UPDATE campaign_calls SET status = 'failed' WHERE id = ?",
                        (call_id,),
                    )
                    await _run_query(
                        conn,
                        "UPDATE leads SET status = 'new' WHERE id = %s"
                        if USE_POSTGRES
                        else "UPDATE leads SET status = 'new' WHERE id = ?",
                        (lead["id"],),
                    )
            except Exception as db_err:
                logger.error(
                    "campaign_call_failed_db_cleanup_error",
                    lead=lead["id"],
                    error=str(db_err),
                )

    try:
        tasks = []
        for i, lead in enumerate(leads):
            tasks.append(_safe_wrap(sem, dial_one(lead, i + 1)))
        await asyncio.gather(*tasks)
    finally:
        async with _campaign_lock:
            _campaign_running = False
        if campaign:
            async with db_context() as conn:
                await _run_query(
                    conn,
                    "UPDATE campaigns SET status = 'completed', ended_at = %s WHERE id = %s"
                    if USE_POSTGRES
                    else "UPDATE campaigns SET status = 'completed', ended_at = ? WHERE id = ?",
                    (datetime.now(UTC).isoformat(), campaign["id"]),
                )

    logger.info("campaign_completed", total_dialed=len(leads))


async def _safe_wrap(sem: asyncio.Semaphore, coro):
    """Run a coroutine under a semaphore, honoring max_concurrent."""
    async with sem:
        await coro


# ── Real-Time Escalation Push ────────────────────────────────────


async def push_escalation_alert(call_sid: str, reason: str, agent_name: str):
    """
    Push a real-time WebSocket notification to ALL connected supervisors
    when the AI agent needs human intervention.
    """
    from api.routers.realtime import manager

    alert = {
        "type": "escalation_alert",
        "call_sid": call_sid,
        "agent": agent_name,
        "reason": reason,
        "timestamp": datetime.now(UTC).isoformat(),
        "severity": "high" if "manager" in reason.lower() else "medium",
    }

    await manager.broadcast_to_queue("default", alert)
    logger.info("escalation_pushed", call_sid=call_sid, reason=reason)
