import structlog

from api.services.db_platform_ops import (
    get_custom_domain_db,
    get_tenant_branding_db,
    list_white_label_tenants_db,
    set_custom_domain_db,
    set_tenant_branding_db,
    verify_domain_db,
)

logger = structlog.get_logger()


class WhiteLabelService:

    @staticmethod
    async def get_branding(tenant_id: str) -> dict | None:
        branding = await get_tenant_branding_db(tenant_id)
        if not branding:
            return {
                "tenant_id": tenant_id,
                "company_name": "",
                "logo_url": "",
                "primary_color": "#2563eb",
                "secondary_color": "#7c3aed",
                "favicon_url": "",
            }
        return branding

    @staticmethod
    async def set_branding(tenant_id: str, config: dict) -> dict | None:
        result = await set_tenant_branding_db(tenant_id, config)
        logger.info("branding_updated", tenant_id=tenant_id)
        return result

    @staticmethod
    async def get_custom_domain(tenant_id: str) -> dict | None:
        return await get_custom_domain_db(tenant_id)

    @staticmethod
    async def set_custom_domain(tenant_id: str, domain: str, ssl_status: str = "pending") -> dict | None:
        result = await set_custom_domain_db(tenant_id, domain, ssl_status)
        logger.info("custom_domain_set", tenant_id=tenant_id, domain=domain)
        return result

    @staticmethod
    async def verify_domain(tenant_id: str, domain: str) -> dict:
        existing = await get_custom_domain_db(tenant_id)
        if not existing:
            return {"verified": False, "message": "No custom domain configured"}

        domain_id = existing.get("id") or existing.get("domain_id")
        if not domain_id:
            return {"verified": False, "message": "Domain record not found"}

        result = await verify_domain_db(domain_id)
        if result and result.get("verified"):
            logger.info("domain_verified", tenant_id=tenant_id, domain=domain)
            return {"verified": True, "ssl_status": "active", "domain": domain}
        return {"verified": False, "message": "DNS verification failed"}

    @staticmethod
    async def get_tenant_theme(tenant_id: str) -> dict:
        branding = await get_tenant_branding_db(tenant_id)
        if not branding:
            return {
                "--primary": "#2563eb",
                "--secondary": "#7c3aed",
                "--background": "#ffffff",
                "--text": "#111827",
            }
        return {
            "--primary": branding.get("primary_color", "#2563eb"),
            "--secondary": branding.get("secondary_color", "#7c3aed"),
            "--background": "#ffffff",
            "--text": "#111827",
        }

    @staticmethod
    async def list_white_label_tenants() -> list:
        return await list_white_label_tenants_db()


white_label_service = WhiteLabelService()
