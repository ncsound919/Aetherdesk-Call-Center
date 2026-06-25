
import structlog

logger = structlog.get_logger()

_versions = [
    {
        "version": "v1",
        "status": "sunset",
        "release_date": "2024-01-15",
        "sunset_date": "2025-06-30",
        "changelog": "Initial release — core voice calling, basic agent management, and call routing.",
        "migration_notes": "Upgrade to v2 for enhanced security, webhooks, and real-time analytics.",
    },
    {
        "version": "v2",
        "status": "deprecated",
        "release_date": "2024-06-01",
        "sunset_date": "2025-12-31",
        "changelog": "Added webhook support, improved call routing, real-time analytics, and audit logging.",
        "migration_notes": "Upgrade to v3 for AI-powered features, multi-channel support, and improved performance.",
    },
    {
        "version": "v3",
        "status": "active",
        "release_date": "2025-01-01",
        "sunset_date": None,
        "changelog": "Major overhaul: AI intent detection, sentiment analysis, WFM, QA scoring, and integration marketplace.",
        "migration_notes": "Current stable version. No migration needed.",
    },
    {
        "version": "v4",
        "status": "active",
        "release_date": "2025-06-01",
        "sunset_date": None,
        "changelog": "Enterprise features: failover testing, conversation quality scoring, API versioning, and self-service portal.",
        "migration_notes": "Latest stable version. All new integrations should target this version.",
    },
]

_usage_stats: dict[str, dict] = {
    "v1": {"total_requests": 12450, "active_tenants": 3, "last_request_at": "2025-03-15T10:00:00Z"},
    "v2": {"total_requests": 89200, "active_tenants": 18, "last_request_at": "2025-06-20T14:30:00Z"},
    "v3": {"total_requests": 456000, "active_tenants": 156, "last_request_at": "2025-06-24T08:15:00Z"},
    "v4": {"total_requests": 12300, "active_tenants": 45, "last_request_at": "2025-06-24T08:20:00Z"},
}


class APIVersioningService:

    async def get_api_versions(self) -> list[dict]:
        return list(_versions)

    async def deprecate_version(self, version: str, sunset_date: str) -> dict:
        for v in _versions:
            if v["version"] == version:
                v["status"] = "deprecated"
                v["sunset_date"] = sunset_date
                logger.info("Version deprecated", version=version, sunset_date=sunset_date)
                return {"success": True, "version": version, "status": "deprecated", "sunset_date": sunset_date}
        return {"success": False, "error": f"Version {version} not found"}

    async def get_migration_guide(self, old_version: str, new_version: str) -> dict:
        old = next((v for v in _versions if v["version"] == old_version), None)
        new = next((v for v in _versions if v["version"] == new_version), None)

        return {
            "from_version": old_version,
            "to_version": new_version,
            "from_status": old["status"] if old else "unknown",
            "to_status": new["status"] if new else "unknown",
            "migration_notes": new["migration_notes"] if new else "No migration guide available.",
            "breaking_changes": _get_breaking_changes(old_version, new_version),
        }

    async def get_changelog(self, version: str | None = None) -> list[dict]:
        if version:
            v = next((v for v in _versions if v["version"] == version), None)
            return [v] if v else []
        return list(_versions)

    async def validate_version_header(self, headers: dict) -> dict:
        version = headers.get("x-api-version", headers.get("X-Api-Version", "v3"))
        v = next((v for v in _versions if v["version"] == version), None)
        if not v:
            return {"valid": False, "version": version, "error": "Unknown version"}
        if v["status"] == "sunset":
            return {"valid": False, "version": version, "status": "sunset", "error": "This version has been sunset"}
        if v["status"] == "deprecated":
            return {"valid": True, "version": version, "status": "deprecated", "warning": "This version is deprecated"}
        return {"valid": True, "version": version, "status": "active"}

    async def get_usage_stats(self, version: str | None = None) -> dict:
        if version:
            return _usage_stats.get(version, {"error": "No data for this version"})
        return _usage_stats


def _get_breaking_changes(old_version: str, new_version: str) -> list[str]:
    changes = {
        ("v1", "v2"): ["Webhook payload format changed", "Authentication now requires Bearer token"],
        ("v1", "v3"): ["Complete API redesign", "All endpoints moved to /api/v3/", "New authentication flow"],
        ("v2", "v3"): ["Response format changed for call objects", "New required fields in agent creation"],
        ("v3", "v4"): ["Some deprecated endpoints removed", "Rate limiting introduced"],
    }
    return changes.get((old_version, new_version), ["No breaking changes documented for this migration path"])


api_versioning_service = APIVersioningService()
