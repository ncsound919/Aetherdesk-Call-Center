"""Unit tests for the API versioning service."""

import pytest

from api.services import api_versioning
from api.services.api_versioning import APIVersioningService, _get_breaking_changes

svc = APIVersioningService()


@pytest.fixture(autouse=True)
def _restore_versions():
    """deprecate_version mutates the shared module list — snapshot & restore."""
    original = [
        dict(v) for v in api_versioning._versions
    ]
    yield
    api_versioning._versions.clear()
    api_versioning._versions.extend(original)


@pytest.mark.asyncio
async def test_get_api_versions_returns_all():
    versions = await svc.get_api_versions()
    assert len(versions) == 4
    assert all(v["status"] in ("sunset", "deprecated", "active") for v in versions)


@pytest.mark.asyncio
async def test_deprecate_existing_version():
    result = await svc.deprecate_version("v1", "2026-12-31")
    assert result["success"] is True
    assert result["status"] == "deprecated"
    assert result["sunset_date"] == "2026-12-31"


@pytest.mark.asyncio
async def test_deprecate_unknown_version():
    result = await svc.deprecate_version("v99", "2026-12-31")
    assert result["success"] is False
    assert "not found" in result["error"]


@pytest.mark.asyncio
async def test_migration_guide_known_path():
    guide = await svc.get_migration_guide("v2", "v3")
    assert guide["from_version"] == "v2"
    assert guide["to_version"] == "v3"
    assert guide["to_status"] == "active"
    assert "breaking_changes" in guide


@pytest.mark.asyncio
async def test_migration_guide_unknown_versions():
    guide = await svc.get_migration_guide("v99", "v100")
    assert guide["from_status"] == "unknown"
    assert guide["migration_notes"] == "No migration guide available."


@pytest.mark.asyncio
async def test_get_changelog_specific_version():
    entries = await svc.get_changelog("v3")
    assert len(entries) == 1
    assert entries[0]["version"] == "v3"


@pytest.mark.asyncio
async def test_get_changelog_unknown_version_empty():
    assert await svc.get_changelog("v99") == []


@pytest.mark.asyncio
async def test_get_changelog_all_versions():
    entries = await svc.get_changelog()
    assert len(entries) == 4
    assert all(v["version"] in ("v1", "v2", "v3", "v4") for v in entries)


@pytest.mark.asyncio
async def test_validate_version_header_active():
    result = await svc.validate_version_header({"x-api-version": "v4"})
    assert result["valid"] is True
    assert result["status"] == "active"


@pytest.mark.asyncio
async def test_validate_version_header_defaults_to_v3():
    result = await svc.validate_version_header({})
    assert result["version"] == "v3"
    assert result["valid"] is True


@pytest.mark.asyncio
async def test_validate_version_header_sunset_blocked():
    result = await svc.validate_version_header({"x-api-version": "v1"})
    assert result["valid"] is False
    assert result["status"] == "sunset"


@pytest.mark.asyncio
async def test_validate_version_header_deprecated_warns():
    result = await svc.validate_version_header({"x-api-version": "v2"})
    assert result["valid"] is True
    assert result["status"] == "deprecated"
    assert "warning" in result


@pytest.mark.asyncio
async def test_validate_version_header_unknown():
    result = await svc.validate_version_header({"x-api-version": "v42"})
    assert result["valid"] is False
    assert "error" in result


@pytest.mark.asyncio
async def test_usage_stats_all_and_specific():
    all_stats = await svc.get_usage_stats()
    assert "v3" in all_stats
    specific = await svc.get_usage_stats("v3")
    assert specific["active_tenants"] > 0
    missing = await svc.get_usage_stats("v99")
    assert "error" in missing


def test_breaking_changes_known_path():
    changes = _get_breaking_changes("v1", "v3")
    assert "Complete API redesign" in changes


def test_breaking_changes_unknown_path():
    changes = _get_breaking_changes("v4", "v9")
    assert "No breaking changes documented" in changes[0]
