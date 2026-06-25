from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from api.services.auth import verify_tenant_access
from api.services.disaster_recovery import dr_service

router = APIRouter(prefix="/business-continuity", tags=["business-continuity"])


class FailoverTestRequest(BaseModel):
    service: str


class ChaosRunRequest(BaseModel):
    target: str
    fault_type: str
    duration_seconds: int = 30


class ContractCreateRequest(BaseModel):
    vendor: str
    terms: str
    renewal_date: str
    cost: float | None = None


class BackupChannelCreateRequest(BaseModel):
    channel_type: str
    config: dict


@router.post("/failover/test")
async def run_failover_test(data: FailoverTestRequest, tenant_id: str = Depends(verify_tenant_access)):
    result = await dr_service.test_failover(data.service, tenant_id)
    if not result:
        raise HTTPException(status_code=400, detail="Failover test failed")
    return result


@router.get("/failover/tests")
async def list_failover_tests(tenant_id: str = Depends(verify_tenant_access)):
    return await dr_service.list_failover_tests(tenant_id)


@router.get("/failover/multi-region")
async def get_multi_region_status(tenant_id: str = Depends(verify_tenant_access)):
    return await dr_service.get_multi_region_status()


@router.post("/chaos/run")
async def run_chaos(data: ChaosRunRequest, tenant_id: str = Depends(verify_tenant_access)):
    result = await dr_service.run_chaos_experiment(data.target, data.fault_type, data.duration_seconds, tenant_id)
    if not result:
        raise HTTPException(status_code=400, detail="Failed to start chaos experiment")
    return result


@router.get("/chaos/experiments")
async def list_chaos_experiments(tenant_id: str = Depends(verify_tenant_access)):
    return await dr_service.list_chaos_experiments(tenant_id)


@router.post("/contracts")
async def create_contract(data: ContractCreateRequest, tenant_id: str = Depends(verify_tenant_access)):
    result = await dr_service.manage_contract(tenant_id, data.vendor, data.terms, data.renewal_date, data.cost)
    if not result:
        raise HTTPException(status_code=400, detail="Failed to create contract")
    return result


@router.get("/contracts")
async def list_contracts(tenant_id: str = Depends(verify_tenant_access)):
    return await dr_service.list_contracts(tenant_id)


@router.get("/contracts/alerts")
async def get_contract_alerts(
    tenant_id: str = Depends(verify_tenant_access),
    days_ahead: int = Query(30, ge=1, le=365),
):
    return await dr_service.get_contract_alerts(tenant_id, days_ahead)


@router.post("/backup-channels")
async def configure_backup_channel(data: BackupChannelCreateRequest, tenant_id: str = Depends(verify_tenant_access)):
    result = await dr_service.configure_backup_channel(tenant_id, data.channel_type, data.config)
    if not result:
        raise HTTPException(status_code=400, detail="Failed to configure backup channel")
    return result


@router.post("/backup-channels/test")
async def test_backup_channel(
    channel_type: str = Query(...),
    tenant_id: str = Depends(verify_tenant_access),
):
    result = await dr_service.test_backup_channel(tenant_id, channel_type)
    return result


@router.get("/backup-channels")
async def list_backup_channels(tenant_id: str = Depends(verify_tenant_access)):
    return await dr_service.list_backup_channels(tenant_id)
