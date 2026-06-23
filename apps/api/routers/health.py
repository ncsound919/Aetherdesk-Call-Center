from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, Request

from apps.api.models.dto import HealthCheck
from apps.api.services.database import USE_POSTGRES, get_pg_pool

logger = structlog.get_logger()

router = APIRouter(prefix="", tags=["health"])


@router.get("/api/v1/health", response_model=HealthCheck)
@router.get("/health", response_model=HealthCheck)
async def health_check(request: Request):
    """Health check endpoint with service status"""
    fonster_client = getattr(request.app.state, "fonster_client", None)
    redis_client = getattr(request.app.state, "redis", None)

    fonster_status = "unknown"
    db_status = "disconnected"

    if fonster_client:
        try:
            hc = await fonster_client.health_check()
            fonster_status = "healthy" if hc.get("healthy") else "unhealthy"
        except Exception:
            fonster_status = "disconnected"

    try:
        if USE_POSTGRES:
            pool = await get_pg_pool()
            if pool:
                await pool.fetchval("SELECT 1")
                db_status = "connected"
    except Exception:
        db_status = "disconnected"

    overall = "healthy" if fonster_status == "healthy" and db_status == "connected" else "degraded"

    return HealthCheck(
        status=overall,
        timestamp=datetime.now(UTC),
        version="1.0.0",
        services={
            "fonster": fonster_status,
            "freeswitch": "connected",
            "redis": "connected" if redis_client else "disconnected",
            "database": db_status,
        },
        fonster_connected=fonster_status == "healthy",
        database_connected=db_status == "connected",
    )


@router.get("/api/v1/health/ready")
async def readiness_probe():
    """Kubernetes readiness probe"""
    return {"status": "ready"}


@router.get("/api/v1/health/live")
async def liveness_probe():
    """Kubernetes liveness probe"""
    return {"status": "alive"}


@router.get("/metrics")
async def metrics_endpoint():
    """Prometheus metrics endpoint"""
    from apps.api.middleware.metrics import metrics_endpoint as metrics_handler
    return await metrics_handler()
