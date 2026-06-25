import structlog
from fastapi import APIRouter, Depends, HTTPException, Query

from api.services.auth import verify_tenant_access
from api.services.circuit_breaker import circuit_breaker_registry
from api.services.dr_testing import dr_testing_service
from api.services.per_tenant_rate_limit import rate_limiter
from api.services.redis_cache import redis_cache_service

logger = structlog.get_logger()
router = APIRouter(prefix="/reliability", tags=["reliability"])


@router.get("/circuit-breakers")
async def list_circuit_breakers(
    tenant_id: str = Depends(verify_tenant_access),
):
    return circuit_breaker_registry.list_state()


@router.post("/circuit-breakers/{name}/reset")
async def reset_circuit_breaker(
    name: str,
    tenant_id: str = Depends(verify_tenant_access),
):
    reset = await circuit_breaker_registry.reset(name)
    if not reset:
        raise HTTPException(status_code=404, detail=f"Circuit breaker '{name}' not found")
    return {"success": True, "name": name, "state": "RESET"}


@router.get("/rate-limits")
async def get_rate_limits(
    tenant_id: str = Depends(verify_tenant_access),
):
    return await rate_limiter.get_all_limits()


@router.put("/rate-limits/{target_tenant_id}")
async def set_rate_limit(
    target_tenant_id: str,
    route_key: str = Query(...),
    max_requests: int = Query(100, ge=1, le=10000),
    window_seconds: int = Query(60, ge=1, le=3600),
    tenant_id: str = Depends(verify_tenant_access),
):
    result = await rate_limiter.set_limits(target_tenant_id, route_key, max_requests, window_seconds)
    return result


@router.get("/dr/status")
async def get_dr_status(
    tenant_id: str = Depends(verify_tenant_access),
):
    return await dr_testing_service.get_dr_status()


@router.post("/dr/test")
async def run_dr_test(
    test_type: str = Query("full", description="full, database_failover, service_restart, or network_partition"),
    service_name: str = Query(None, description="Service name for service_restart test"),
    tenant_id: str = Depends(verify_tenant_access),
):
    if test_type == "full":
        return await dr_testing_service.run_full_dr_drill(tenant_id)
    elif test_type == "database_failover":
        return await dr_testing_service.test_database_failover(tenant_id)
    elif test_type == "service_restart":
        sn = service_name or "api-gateway"
        return await dr_testing_service.test_service_restart(sn, tenant_id)
    elif test_type == "network_partition":
        return await dr_testing_service.test_network_partition(tenant_id)
    else:
        raise HTTPException(status_code=400, detail=f"Unknown test type: {test_type}")


@router.get("/dr/config")
async def get_dr_config(
    tenant_id: str = Depends(verify_tenant_access),
):
    return await dr_testing_service.get_dr_config()


@router.get("/cache/stats")
async def get_cache_stats(
    tenant_id: str = Depends(verify_tenant_access),
):
    return await redis_cache_service.get_stats()


@router.post("/cache/warm")
async def warm_cache_key(
    key: str = Query(...),
    value: str = Query(None),
    ttl: int = Query(300, ge=1, le=86400),
    tenant_id: str = Depends(verify_tenant_access),
):
    if value:
        await redis_cache_service.set(key, value, ttl)
        return {"success": True, "key": key, "cached": True}
    return {"success": False, "key": key, "cached": False, "message": "No value provided"}
