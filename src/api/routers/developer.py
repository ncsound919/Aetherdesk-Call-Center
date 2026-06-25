import structlog
from fastapi import APIRouter, Depends, HTTPException, Query

from api.models.dto import (
    APIKeyCreatedResponse,
    APIKeyCreateRequest,
    APIKeyResponse,
    APIKeyUsageResponse,
    EventCatalogEntry,
    EventCatalogResponse,
    WebhookDeliveryLogResponse,
    WebhookRegisterRequest,
    WebhookResponse,
)
from api.services.api_keys import api_key_service
from api.services.auth import verify_tenant_access
from api.services.webhook_engine import webhook_engine

logger = structlog.get_logger()
router = APIRouter(prefix="/developer", tags=["developer"])


# ── API Key Endpoints ──────────────────────────────────────────────

@router.post("/api-keys", response_model=APIKeyCreatedResponse)
async def create_api_key(
    data: APIKeyCreateRequest,
    tenant_id: str = Depends(verify_tenant_access),
):
    result = await api_key_service.create_key(
        tenant_id, data.name, data.scopes, data.expires_in_days
    )
    return APIKeyCreatedResponse(
        id=result["id"],
        name=result["name"],
        masked_key=result.get("key_prefix", "") + "****",
        scopes=data.scopes,
        full_key=result["full_key"],
        created_at=str(result.get("created_at", "")),
        expires_at=str(result.get("expires_at", "")),
        is_active=True,
    )


@router.get("/api-keys", response_model=list[APIKeyResponse])
async def list_api_keys(
    tenant_id: str = Depends(verify_tenant_access),
):
    keys = await api_key_service.list_keys(tenant_id)
    return [
        APIKeyResponse(
            id=k["id"],
            name=k["name"],
            masked_key=k["masked_key"],
            scopes=k["scopes"],
            created_at=str(k.get("created_at", "")),
            last_used_at=str(k.get("last_used_at", "")),
            expires_at=str(k.get("expires_at", "")),
            is_active=k["is_active"],
        )
        for k in keys
    ]


@router.delete("/api-keys/{key_id}")
async def revoke_api_key(
    key_id: str,
    tenant_id: str = Depends(verify_tenant_access),
):
    ok = await api_key_service.revoke_key(tenant_id, key_id)
    if not ok:
        raise HTTPException(status_code=404, detail="API key not found")
    return {"success": True}


@router.post("/api-keys/{key_id}/rotate", response_model=APIKeyCreatedResponse)
async def rotate_api_key(
    key_id: str,
    tenant_id: str = Depends(verify_tenant_access),
):
    result = await api_key_service.rotate_key(tenant_id, key_id)
    if not result:
        raise HTTPException(status_code=404, detail="API key not found")
    return APIKeyCreatedResponse(
        id=result["id"],
        name=result["name"],
        masked_key=result.get("key_prefix", "") + "****",
        scopes=result.get("scopes", ["all"]),
        full_key=result["full_key"],
        created_at=str(result.get("created_at", "")),
        expires_at=str(result.get("expires_at", "")),
        is_active=True,
    )


@router.get("/api-keys/{key_id}/usage", response_model=APIKeyUsageResponse)
async def get_api_key_usage(
    key_id: str,
    tenant_id: str = Depends(verify_tenant_access),
    period: str = Query("7d"),
):
    result = await api_key_service.get_key_usage(tenant_id, key_id, period)
    if not result:
        raise HTTPException(status_code=404, detail="API key not found")
    return APIKeyUsageResponse(**result)


# ── Webhook Endpoints ──────────────────────────────────────────────

@router.post("/webhooks", response_model=WebhookResponse)
async def register_webhook(
    data: WebhookRegisterRequest,
    tenant_id: str = Depends(verify_tenant_access),
):
    result = await webhook_engine.register_webhook(
        tenant_id, data.url, data.events, data.secret
    )
    if not result:
        raise HTTPException(status_code=400, detail="Failed to register webhook")

    events = result.get("events_json", [])
    if isinstance(events, str):
        import json
        events = json.loads(events)

    return WebhookResponse(
        id=result["id"],
        url=result["url"],
        events=events,
        secret=result.get("secret"),
        is_active=bool(result.get("is_active", True)),
        created_at=str(result.get("created_at", "")),
    )


@router.get("/webhooks", response_model=list[WebhookResponse])
async def list_webhooks(
    tenant_id: str = Depends(verify_tenant_access),
):
    whs = await webhook_engine.list_webhooks(tenant_id)
    result = []
    for wh in whs:
        events = wh.get("events_json", [])
        if isinstance(events, str):
            import json
            events = json.loads(events)
        result.append(WebhookResponse(
            id=wh["id"],
            url=wh["url"],
            events=events,
            secret=wh.get("secret"),
            is_active=bool(wh.get("is_active", True)),
            created_at=str(wh.get("created_at", "")),
        ))
    return result


@router.delete("/webhooks/{webhook_id}")
async def unregister_webhook(
    webhook_id: str,
    tenant_id: str = Depends(verify_tenant_access),
):
    ok = await webhook_engine.unregister_webhook(tenant_id, webhook_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Webhook not found")
    return {"success": True}


@router.post("/webhooks/{webhook_id}/test")
async def test_webhook(
    webhook_id: str,
    tenant_id: str = Depends(verify_tenant_access),
):
    wh = await webhook_engine.get_webhook(tenant_id, webhook_id)
    if not wh:
        raise HTTPException(status_code=404, detail="Webhook not found")

    test_payload = {
        "event_type": "webhook.test",
        "event_id": "test",
        "created_at": "2026-01-01T00:00:00Z",
        "data": {"message": "This is a test event"},
    }

    from api.services.webhook_engine import (
        _deliver_webhook,
        create_webhook_delivery_log_db,
    )
    log_entry = await create_webhook_delivery_log_db(
        tenant_id, webhook_id, "webhook.test", "test"
    )
    if log_entry:
        success = await _deliver_webhook(
            wh["url"], test_payload, wh.get("secret"),
            log_entry["id"], tenant_id, webhook_id,
        )
        return {"success": success, "log_id": log_entry["id"]}
    return {"success": False}


@router.get("/webhooks/{webhook_id}/logs", response_model=list[WebhookDeliveryLogResponse])
async def get_webhook_logs(
    webhook_id: str,
    tenant_id: str = Depends(verify_tenant_access),
    limit: int = Query(50, ge=1, le=200),
):
    logs = await webhook_engine.get_delivery_logs(tenant_id, webhook_id, limit)
    return [
        WebhookDeliveryLogResponse(
            id=log["id"],
            webhook_id=log["webhook_id"],
            event_type=log["event_type"],
            status=log["status"],
            request_body=log.get("request_body"),
            response_status=log.get("response_status"),
            response_body=log.get("response_body"),
            error_message=log.get("error_message"),
            retry_count=log.get("retry_count", 0) or 0,
            created_at=str(log.get("created_at", "")),
        )
        for log in logs
    ]


@router.post("/webhooks/logs/{log_id}/retry")
async def retry_webhook_delivery(
    log_id: str,
    tenant_id: str = Depends(verify_tenant_access),
):
    success = await webhook_engine.retry_delivery(tenant_id, log_id)
    return {"success": success}


# ── Event Catalog ──────────────────────────────────────────────────

@router.get("/events", response_model=EventCatalogResponse)
async def get_event_catalog():
    catalog = webhook_engine.get_event_catalog()
    events = {
        key: EventCatalogEntry(description=val["description"], schema=val["schema"])
        for key, val in catalog.items()
    }
    return EventCatalogResponse(events=events)
