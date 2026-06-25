from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from api.models.dto import HealthCheck
from api.services.database import USE_POSTGRES, get_pg_pool

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
@router.get("/health/ready")
async def readiness_probe(request: Request):
    """Kubernetes readiness probe — checks all dependencies."""
    checks = {}
    all_healthy = True

    # Check DB
    try:
        from api.services.db_pool import get_pg_pool as db_get_pool
        pool = await db_get_pool()
        if pool:
            checks["database"] = "healthy"
        else:
            checks["database"] = "unhealthy"
            all_healthy = False
    except Exception:
        checks["database"] = "unhealthy"
        all_healthy = False

    # Check Redis
    try:
        redis_client = getattr(request.app.state, "redis", None)
        if redis_client:
            await redis_client.ping()
            checks["redis"] = "healthy"
        else:
            checks["redis"] = "unhealthy"
            all_healthy = False
    except Exception:
        checks["redis"] = "unhealthy"
        all_healthy = False

    # Check Voice Client
    try:
        fonster_client = getattr(request.app.state, "fonster_client", None)
        checks["voice"] = "healthy" if fonster_client else "degraded"
    except Exception:
        checks["voice"] = "unhealthy"

    status_code = 200 if all_healthy else 503
    return JSONResponse(
        status_code=status_code,
        content={"status": "ready" if all_healthy else "not_ready", "checks": checks}
    )


@router.get("/api/v1/health/live")
@router.get("/health/live")
async def liveness_probe():
    """Kubernetes liveness probe — app process only."""
    return {"status": "alive", "timestamp": datetime.now(UTC).isoformat()}


@router.get("/health/sla")
async def sla_metrics():
    """SLA metrics endpoint."""
    from api.services.observability import sla_metrics as sla
    return sla.get_sla_summary()


@router.get("/health/vendors")
async def vendor_health():
    """Vendor health check status."""
    from api.services.vendor_health import vendor_health_monitor
    results = await vendor_health_monitor.check_all_vendors()
    return {"vendors": results, "degraded": vendor_health_monitor.get_degraded_vendors()}


@router.get("/health/pool")
async def pool_stats():
    """Database connection pool statistics."""
    from api.services.connection_pool import get_pool_stats
    return await get_pool_stats()


@router.get("/metrics")
async def metrics_endpoint():
    """Prometheus metrics endpoint"""
    from api.middleware.metrics import metrics_endpoint as metrics_handler
    return await metrics_handler()
