"""
E2E test for the Right to be Forgotten (GDPR) data flow.
Calls the anonymization endpoint and verifies the response structure.
"""

import os
import pytest
import httpx

E2E_API_URL = os.getenv("E2E_API_URL", "http://localhost:8000/api/v1")

pytestmark = pytest.mark.skipif(
    not os.getenv("E2E_RUN"),
    reason="Set E2E_RUN=1 to run end-to-end tests against a live server",
)


class TestGDPRCompliance:
    """GDPR Right to be Forgotten and Data Export E2E."""

    @pytest.mark.asyncio
    async def test_delete_nonexistent_user_returns_404(self):
        async with httpx.AsyncClient(base_url=E2E_API_URL, timeout=10) as client:
            resp = await client.delete(
                "/data-governance/users/nonexistent-id/data",
                headers={"x-api-key": "dev-api-key"},
            )
            assert resp.status_code == 404
            body = resp.json()
            assert "detail" in body

    @pytest.mark.asyncio
    async def test_export_nonexistent_user_returns_404(self):
        async with httpx.AsyncClient(base_url=E2E_API_URL, timeout=10) as client:
            resp = await client.get(
                "/data-governance/users/nonexistent-id/export",
                headers={"x-api-key": "dev-api-key"},
            )
            assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_lineage_record_endpoint_requires_auth(self):
        async with httpx.AsyncClient(base_url=E2E_API_URL, timeout=10) as client:
            resp = await client.get(
                "/data-governance/lineage/record?table=users&record_id=1",
            )
            assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_health_score_endpoint_returns_data(self):
        async with httpx.AsyncClient(base_url=E2E_API_URL, timeout=10) as client:
            resp = await client.get(
                "/data-governance/health-score",
                headers={"x-api-key": "dev-api-key"},
            )
            assert resp.status_code == 200
            body = resp.json()
            assert "success" in body or "score" in body or "health_score" in body or "status" in body
