"""
Metabase dashboard embedding — provides signed iframe URLs for tenant dashboards.

When Metabase is configured, generates embedded dashboard URLs that can be
iframe'd into the AetherDesk analytics UI. When not configured, returns
mock data from ClickHouse directly.
"""

import base64
import hashlib
import hmac
import json
import logging
import os
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from api.services.analytics_db import (
    is_clickhouse_enabled,
    query_agent_performance,
    query_call_stats,
    query_hourly_volume,
    query_intent_distribution,
)
from api.services.auth import verify_tenant_access

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/metabase", tags=["metabase"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_metabase_configured() -> bool:
    return bool(os.getenv("METABASE_SECRET_KEY") and os.getenv("METABASE_SITE_URL"))


def _sign_metabase_resource(resource_id: int, expiry_minutes: int = 10) -> str:
    """Generate a signed URL for embedding a Metabase question/dashboard."""
    secret_key = os.getenv("METABASE_SECRET_KEY", "")
    site_url = os.getenv("METABASE_SITE_URL", "http://localhost:3002")

    payload = {
        "resource": {"question": resource_id},
        "params": {},
        "exp": int((datetime.utcnow() + timedelta(minutes=expiry_minutes)).timestamp()),
    }
    # HMAC-SHA256 signing
    token = base64.urlsafe_b64encode(
        hmac.new(
            secret_key.encode(),
            json.dumps(payload).encode(),
            hashlib.sha256,
        ).digest()
    ).decode()

    encoded_payload = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()
    return f"{site_url}/embed/question/{encoded_payload}#{token}"


# ---------------------------------------------------------------------------
# Dashboard data endpoints (fallback when Metabase is not configured)
# ---------------------------------------------------------------------------

class CallStatsResponse(BaseModel):
    source: str  # "clickhouse" or "mock"
    total_calls: int = 0
    total_minutes: float = 0
    avg_duration: float = 0
    completed: int = 0
    missed: int = 0
    avg_satisfaction: float = 0
    total_tokens: int = 0
    total_cost_cents: int = 0


class IntentDistributionResponse(BaseModel):
    source: str
    intents: list[dict] = []


class AgentPerformanceResponse(BaseModel):
    source: str
    agents: list[dict] = []


class HourlyVolumeResponse(BaseModel):
    source: str
    hours: list[dict] = []


@router.get("/stats", response_model=CallStatsResponse)
async def get_call_stats(
    start_date: str | None = Query(None, description="ISO date, default 30 days ago"),
    end_date: str | None = Query(None, description="ISO date, default now"),
    tenant_id: str = Depends(verify_tenant_access),
):
    """Get call statistics for the current tenant."""
    if not is_clickhouse_enabled():
        return CallStatsResponse(source="mock")

    try:
        end = datetime.fromisoformat(end_date) if end_date else datetime.utcnow()
        start = datetime.fromisoformat(start_date) if start_date else end - timedelta(days=30)
        stats = query_call_stats(tenant_id, start, end)
        return CallStatsResponse(source="clickhouse", **stats)
    except Exception as exc:
        logger.warning(f"Stats query failed: {exc}")
        return CallStatsResponse(source="mock")


@router.get("/intents", response_model=IntentDistributionResponse)
async def get_intent_distribution(
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    tenant_id: str = Depends(verify_tenant_access),
):
    """Get intent distribution for the current tenant."""
    if not is_clickhouse_enabled():
        return IntentDistributionResponse(source="mock")

    try:
        end = datetime.fromisoformat(end_date) if end_date else datetime.utcnow()
        start = datetime.fromisoformat(start_date) if start_date else end - timedelta(days=30)
        intents = query_intent_distribution(tenant_id, start, end)
        return IntentDistributionResponse(source="clickhouse", intents=intents)
    except Exception as exc:
        logger.warning(f"Intent query failed: {exc}")
        return IntentDistributionResponse(source="mock")


@router.get("/agents", response_model=AgentPerformanceResponse)
async def get_agent_performance(
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    tenant_id: str = Depends(verify_tenant_access),
):
    """Get per-agent performance stats."""
    if not is_clickhouse_enabled():
        return AgentPerformanceResponse(source="mock")

    try:
        end = datetime.fromisoformat(end_date) if end_date else datetime.utcnow()
        start = datetime.fromisoformat(start_date) if start_date else end - timedelta(days=30)
        agents = query_agent_performance(tenant_id, start, end)
        return AgentPerformanceResponse(source="clickhouse", agents=agents)
    except Exception as exc:
        logger.warning(f"Agent query failed: {exc}")
        return AgentPerformanceResponse(source="mock")


@router.get("/hourly", response_model=HourlyVolumeResponse)
async def get_hourly_volume(
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    tenant_id: str = Depends(verify_tenant_access),
):
    """Get hourly call volume for time-series charts."""
    if not is_clickhouse_enabled():
        return HourlyVolumeResponse(source="mock")

    try:
        end = datetime.fromisoformat(end_date) if end_date else datetime.utcnow()
        start = datetime.fromisoformat(start_date) if start_date else end - timedelta(days=7)
        hours = query_hourly_volume(tenant_id, start, end)
        return HourlyVolumeResponse(source="clickhouse", hours=hours)
    except Exception as exc:
        logger.warning(f"Hourly query failed: {exc}")
        return HourlyVolumeResponse(source="mock")


# ---------------------------------------------------------------------------
# Embedded dashboard URL
# ---------------------------------------------------------------------------

class EmbedResponse(BaseModel):
    configured: bool
    url: str | None = None


@router.get("/embed/{question_id}", response_model=EmbedResponse)
async def get_embed_url(
    question_id: int,
    tenant_id: str = Depends(verify_tenant_access),
):
    """Get a signed Metabase embed URL for a specific question/dashboard."""
    if not _is_metabase_configured():
        return EmbedResponse(configured=False)

    url = _sign_metabase_resource(question_id)
    return EmbedResponse(configured=True, url=url)
