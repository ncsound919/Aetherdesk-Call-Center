from fastapi import APIRouter, Depends, HTTPException, Query

from api.models.dto import IntegrationConfigCreate, TicketCreate
from api.services.auth import verify_tenant_access
from api.services.crm_connector import CRMConnectorFactory
from api.services.db_integrations import (
    create_integration_config_db,
    create_ticket_sync_log_db,
    get_integration_config_db,
    list_integration_configs_db,
    update_integration_config_db,
)
from api.services.ticketing import TicketingFactory, TicketingService

router = APIRouter(prefix="/integrations", tags=["integrations"])


# ── CRM Endpoints ──────────────────────────────────────────────

@router.post("/crm/contacts")
async def create_crm_contact(
    data: dict,
    tenant_id: str = Depends(verify_tenant_access),
):
    config = await _get_crm_config(tenant_id)
    if not config:
        raise HTTPException(status_code=400, detail="No CRM integration configured")
    connector = CRMConnectorFactory.get_connector(tenant_id, config["provider"], config.get("config_json", {}))
    return await connector.create_contact(data)


@router.get("/crm/contacts")
async def search_crm_contacts(
    query: str = Query(""),
    tenant_id: str = Depends(verify_tenant_access),
):
    config = await _get_crm_config(tenant_id)
    if not config:
        return {"success": True, "data": {"contacts": [], "total": 0}, "provider": "none", "timestamp": ""}
    connector = CRMConnectorFactory.get_connector(tenant_id, config["provider"], config.get("config_json", {}))
    return await connector.search_contacts(query)


@router.get("/crm/contacts/{contact_id}")
async def get_crm_contact(
    contact_id: str,
    tenant_id: str = Depends(verify_tenant_access),
):
    config = await _get_crm_config(tenant_id)
    if not config:
        raise HTTPException(status_code=400, detail="No CRM integration configured")
    connector = CRMConnectorFactory.get_connector(tenant_id, config["provider"], config.get("config_json", {}))
    return await connector.get_contact(contact_id)


@router.put("/crm/contacts/{contact_id}")
async def update_crm_contact(
    contact_id: str,
    data: dict,
    tenant_id: str = Depends(verify_tenant_access),
):
    config = await _get_crm_config(tenant_id)
    if not config:
        raise HTTPException(status_code=400, detail="No CRM integration configured")
    connector = CRMConnectorFactory.get_connector(tenant_id, config["provider"], config.get("config_json", {}))
    return await connector.update_contact(contact_id, data)


@router.post("/crm/sync")
async def sync_crm_contacts(
    tenant_id: str = Depends(verify_tenant_access),
):
    config = await _get_crm_config(tenant_id)
    if not config:
        raise HTTPException(status_code=400, detail="No CRM integration configured")
    connector = CRMConnectorFactory.get_connector(tenant_id, config["provider"], config.get("config_json", {}))
    result = await connector.sync_contacts()
    await update_integration_config_db(
        tenant_id, config["provider"],
        last_sync_at=result.get("timestamp"),
        status="active",
    )
    return result


@router.get("/crm/health")
async def crm_health(
    tenant_id: str = Depends(verify_tenant_access),
):
    config = await _get_crm_config(tenant_id)
    if not config:
        return {"success": True, "data": {"status": "not_configured"}, "provider": "none", "timestamp": ""}
    connector = CRMConnectorFactory.get_connector(tenant_id, config["provider"], config.get("config_json", {}))
    return await connector.get_health()


# ── Ticketing Endpoints ────────────────────────────────────────

@router.post("/ticketing/tickets")
async def create_ticket(
    data: TicketCreate,
    tenant_id: str = Depends(verify_tenant_access),
):
    config = await _get_ticketing_config(tenant_id)
    if not config:
        raise HTTPException(status_code=400, detail="No ticketing integration configured")
    connector = TicketingFactory.get_connector(tenant_id, config["provider"], config.get("config_json", {}))
    service = TicketingService(connector)
    result = await service.create_ticket(data.model_dump())
    await create_ticket_sync_log_db(
        tenant_id, result.get("data", {}).get("id", ""),
        call_id=data.call_id, direction="outbound", status="success",
        payload_json=data.model_dump(), response_json=result,
    )
    return result


@router.get("/ticketing/tickets")
async def list_tickets(
    status: str | None = Query(None),
    tenant_id: str = Depends(verify_tenant_access),
):
    config = await _get_ticketing_config(tenant_id)
    if not config:
        return {"success": True, "data": {"tickets": [], "total": 0}, "provider": "none", "timestamp": ""}
    connector = TicketingFactory.get_connector(tenant_id, config["provider"], config.get("config_json", {}))
    service = TicketingService(connector)
    return await service.list_tickets(tenant_id, status)


@router.get("/ticketing/tickets/{ticket_id}")
async def get_ticket(
    ticket_id: str,
    tenant_id: str = Depends(verify_tenant_access),
):
    config = await _get_ticketing_config(tenant_id)
    if not config:
        raise HTTPException(status_code=400, detail="No ticketing integration configured")
    connector = TicketingFactory.get_connector(tenant_id, config["provider"], config.get("config_json", {}))
    service = TicketingService(connector)
    return await service.get_ticket(ticket_id)


@router.put("/ticketing/tickets/{ticket_id}")
async def update_ticket(
    ticket_id: str,
    data: dict,
    tenant_id: str = Depends(verify_tenant_access),
):
    config = await _get_ticketing_config(tenant_id)
    if not config:
        raise HTTPException(status_code=400, detail="No ticketing integration configured")
    connector = TicketingFactory.get_connector(tenant_id, config["provider"], config.get("config_json", {}))
    service = TicketingService(connector)
    return await service.update_ticket(ticket_id, data)


@router.post("/ticketing/sync-from-call")
async def sync_from_call(
    data: dict,
    tenant_id: str = Depends(verify_tenant_access),
):
    config = await _get_ticketing_config(tenant_id)
    if not config:
        raise HTTPException(status_code=400, detail="No ticketing integration configured")
    connector = TicketingFactory.get_connector(tenant_id, config["provider"], config.get("config_json", {}))
    service = TicketingService(connector)
    result = await service.sync_from_call(data)
    await create_ticket_sync_log_db(
        tenant_id, result.get("data", {}).get("id", ""),
        call_id=data.get("call_id"), direction="outbound", status="success",
        payload_json=data, response_json=result,
    )
    return result


@router.get("/ticketing/health")
async def ticketing_health(
    tenant_id: str = Depends(verify_tenant_access),
):
    config = await _get_ticketing_config(tenant_id)
    if not config:
        return {"success": True, "data": {"status": "not_configured"}, "provider": "none", "timestamp": ""}
    connector = TicketingFactory.get_connector(tenant_id, config["provider"], config.get("config_json", {}))
    service = TicketingService(connector)
    return await service.get_health()


# ── Integration Management ─────────────────────────────────────

@router.get("/configs")
async def list_configs(
    tenant_id: str = Depends(verify_tenant_access),
):
    configs = await list_integration_configs_db(tenant_id)
    return {"configs": configs}


@router.post("/configs")
async def create_or_update_config(
    data: IntegrationConfigCreate,
    tenant_id: str = Depends(verify_tenant_access),
):
    existing = await get_integration_config_db(tenant_id, data.provider)
    if existing:
        result = await update_integration_config_db(
            tenant_id, data.provider,
            config_json=data.config, status=data.status,
        )
    else:
        result = await create_integration_config_db(
            tenant_id, data.provider, data.integration_type,
            data.config, data.status,
        )
    if not result:
        raise HTTPException(status_code=400, detail="Failed to save integration config")
    return result


@router.get("/health")
async def all_health(
    tenant_id: str = Depends(verify_tenant_access),
):
    configs = await list_integration_configs_db(tenant_id)
    health = {}
    for cfg in configs:
        ptype = cfg.get("integration_type", "")
        provider = cfg.get("provider", "")
        try:
            if ptype == "crm":
                connector = CRMConnectorFactory.get_connector(tenant_id, provider, cfg.get("config_json", {}))
                h = await connector.get_health()
            elif ptype == "ticketing":
                connector = TicketingFactory.get_connector(tenant_id, provider, cfg.get("config_json", {}))
                service = TicketingService(connector)
                h = await service.get_health()
            else:
                h = {"success": False, "data": {"status": "unknown_type"}}
            health[provider] = h
        except Exception as e:
            health[provider] = {"success": False, "data": {"status": "error", "error": str(e)}}
    return {"health": health}


# ── Helpers ─────────────────────────────────────────────────────

async def _get_crm_config(tenant_id: str) -> dict | None:
    configs = await list_integration_configs_db(tenant_id, integration_type="crm")
    return configs[0] if configs else None


async def _get_ticketing_config(tenant_id: str) -> dict | None:
    configs = await list_integration_configs_db(tenant_id, integration_type="ticketing")
    return configs[0] if configs else None
