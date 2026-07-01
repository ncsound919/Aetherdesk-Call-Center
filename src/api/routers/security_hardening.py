import ipaddress
import socket
from urllib.parse import urlparse

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query

from api.services.auth import verify_tenant_access
from api.services.default_creds import audit_credential_strength, force_password_reset
from api.services.security_enhancements import (
    data_classification_service,
    pen_test_service,
    rbac_test_service,
    waf_service,
)

logger = structlog.get_logger()
router = APIRouter(prefix="/security-hardening", tags=["security-hardening"])

SENSITIVITY_LEVELS = ("public", "internal", "confidential", "restricted")

_BLOCKED_HOSTNAMES = {"localhost", "metadata.google.internal"}


def _validate_pen_test_target(target_url: str) -> str:
    """Guard against SSRF: only allow http(s) URLs pointing at public,
    non-internal hosts. Rejects loopback, link-local, private, and
    cloud metadata addresses.
    """
    parsed = urlparse(target_url)
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(status_code=400, detail="target_url must use http or https")

    hostname = parsed.hostname
    if not hostname:
        raise HTTPException(status_code=400, detail="target_url must include a valid host")

    if hostname.lower() in _BLOCKED_HOSTNAMES:
        raise HTTPException(status_code=400, detail="target_url host is not allowed")

    try:
        resolved_ips = {info[4][0] for info in socket.getaddrinfo(hostname, None)}
    except socket.gaierror:
        raise HTTPException(status_code=400, detail="target_url host could not be resolved") from None

    for ip_str in resolved_ips:
        ip = ipaddress.ip_address(ip_str)
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
        ):
            raise HTTPException(
                status_code=400,
                detail="target_url resolves to a private/internal address, which is not allowed",
            )

    return target_url


@router.post("/pen-test/scan")
async def run_pen_test_scan(
    target_url: str = Query(..., description="Target URL to scan"),
    tenant_id: str = Depends(verify_tenant_access),
):
    target_url = _validate_pen_test_target(target_url)
    result = await pen_test_service.run_scan(target_url, tenant_id)
    if not result:
        raise HTTPException(status_code=400, detail="Failed to start pen test scan")
    return result


@router.get("/pen-test/scans")
async def list_pen_test_scans(
    tenant_id: str = Depends(verify_tenant_access),
):
    return await pen_test_service.list_scans(tenant_id)


@router.get("/pen-test/scans/{scan_id}")
async def get_pen_test_scan(
    scan_id: str,
    tenant_id: str = Depends(verify_tenant_access),
):
    result = await pen_test_service.get_scan_report(scan_id)
    if not result:
        raise HTTPException(status_code=404, detail="Scan not found")
    return result


@router.get("/waf/rules")
async def get_waf_rules(
    tenant_id: str = Depends(verify_tenant_access),
):
    return waf_service.get_waf_rules()


@router.put("/waf/rules/{rule_id}")
async def update_waf_rule(
    rule_id: str,
    action: str = Query(..., description="enable, disable, block, log, or captcha"),
    tenant_id: str = Depends(verify_tenant_access),
):
    result = waf_service.update_waf_rule(rule_id, action)
    if not result:
        raise HTTPException(status_code=404, detail="WAF rule not found")
    return result


@router.get("/waf/events")
async def get_waf_events(
    limit: int = Query(100, ge=1, le=1000),
    tenant_id: str = Depends(verify_tenant_access),
):
    return await waf_service.get_waf_events(limit, tenant_id)


@router.get("/data-classification")
async def get_data_classification(
    tenant_id: str = Depends(verify_tenant_access),
):
    return await data_classification_service.get_classification_schema(tenant_id)


@router.post("/data-classification")
async def classify_field(
    table: str = Query(...),
    column: str = Query(...),
    sensitivity: str = Query(..., description=f"One of: {', '.join(SENSITIVITY_LEVELS)}"),
    description: str = Query(None),
    tenant_id: str = Depends(verify_tenant_access),
):
    if sensitivity not in SENSITIVITY_LEVELS:
        raise HTTPException(status_code=400, detail=f"Invalid sensitivity. Must be one of {SENSITIVITY_LEVELS}")
    return await data_classification_service.classify_field(table, column, sensitivity, tenant_id, description=description)


@router.get("/data-classification/validate")
async def validate_data_access(
    role: str = Query(...),
    table: str = Query(...),
    column: str = Query(...),
    tenant_id: str = Depends(verify_tenant_access),
):
    return await data_classification_service.validate_access(role, table, column, tenant_id)


@router.post("/rbac/audit")
async def run_rbac_audit(
    tenant_id: str = Depends(verify_tenant_access),
):
    results = await rbac_test_service.run_full_audit(tenant_id)
    return {"total_tests": len(results), "results": results}


@router.get("/rbac/audit-results")
async def get_rbac_audit_results(
    tenant_id: str = Depends(verify_tenant_access),
):
    return await rbac_test_service.get_audit_results(tenant_id)


@router.get("/credentials/audit")
async def get_credential_audit(
    tenant_id: str = Depends(verify_tenant_access),
):
    return await audit_credential_strength()


@router.post("/credentials/force-reset/{user_id}")
async def force_user_password_reset(
    user_id: str,
    tenant_id: str = Depends(verify_tenant_access),
):
    result = await force_password_reset(user_id)
    if not result:
        raise HTTPException(status_code=404, detail="User not found")
    return {"success": True, "user_id": user_id, "email": result["email"], "message": "Password reset forced"}
