"""Tests for the Blocklabor integration router."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers.blocklabor_overlay365 import (
    BLOCKLABOR_API_KEY,
    BLOCKLABOR_URL,
    get_verified_tenant,
    router,
)


def _async_client_mock(post=None, get=None):
    """Build an AsyncClient double usable with `async with`."""
    client = MagicMock()
    client.post = post if post is not None else AsyncMock()
    client.get = get if get is not None else AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return client


@pytest.fixture
def app():
    application = FastAPI()
    application.include_router(router)

    async def _override_verified_tenant():
        return "TENANT-001"

    application.dependency_overrides[get_verified_tenant] = _override_verified_tenant
    return application


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c


class TestPostJob:
    def test_post_job_success(self, client):
        mock_client = _async_client_mock(
            post=AsyncMock(return_value=AsyncMock(status_code=200, json=lambda: {"id": "job-1", "status": "active"}))
        )
        with patch("httpx.AsyncClient", return_value=mock_client):
            resp = client.post(
                "/api/v1/blocklabor/post-job",
                json={
                    "title": "Warehouse Worker",
                    "description": "Load and unload trucks",
                    "skills_required": ["lifting", "forklift"],
                    "pay_rate": 18.5,
                    "duration": "temp",
                    "tenant_id": "TENANT-001",
                },
            )
        assert resp.status_code == 200
        assert resp.json() == {"status": "posted", "job": {"id": "job-1", "status": "active"}}
        # Verify payload sent to Blocklabor
        call_kwargs = mock_client.post.call_args
        assert call_kwargs.kwargs["json"]["source"] == "aetherdesk"
        assert call_kwargs.kwargs["json"]["tenant_id"] == "TENANT-001"

    def test_post_job_error_response(self, client):
        mock_client = _async_client_mock(
            post=AsyncMock(return_value=AsyncMock(status_code=400, text="bad request"))
        )
        with patch("httpx.AsyncClient", return_value=mock_client):
            resp = client.post(
                "/api/v1/blocklabor/post-job",
                json={
                    "title": "Worker",
                    "description": "desc",
                    "pay_rate": 15,
                    "tenant_id": "TENANT-001",
                },
            )
        assert resp.status_code == 200
        assert resp.json()["status"] == "error"

    def test_post_job_unreachable_503(self, client):
        import httpx
        mock_client = _async_client_mock(
            post=AsyncMock(side_effect=httpx.ConnectError("connection refused"))
        )
        with patch("httpx.AsyncClient", return_value=mock_client):
            resp = client.post(
                "/api/v1/blocklabor/post-job",
                json={
                    "title": "Worker",
                    "description": "desc",
                    "pay_rate": 15,
                    "tenant_id": "TENANT-001",
                },
            )
        assert resp.status_code == 503

    def test_post_job_validation(self, client):
        # Zero pay rate rejected (gt=0)
        resp = client.post(
            "/api/v1/blocklabor/post-job",
            json={"title": "Worker", "description": "d", "pay_rate": 0, "tenant_id": "T"},
        )
        assert resp.status_code == 422


class TestMatchWorkers:
    def test_match_success(self, client):
        mock_client = _async_client_mock(
            get=AsyncMock(return_value=AsyncMock(status_code=200, json=lambda: {"workers": [{"id": "w1", "skills": ["forklift"]}]}))
        )
        with patch("httpx.AsyncClient", return_value=mock_client):
            resp = client.get(
                "/api/v1/blocklabor/workers/match?skills=forklift&pay_rate=18"
            )
        assert resp.status_code == 200
        assert resp.json() == {"workers": [{"id": "w1", "skills": ["forklift"]}]}

    def test_match_error_returns_empty(self, client):
        import httpx
        mock_client = _async_client_mock(
            get=AsyncMock(side_effect=httpx.ConnectError("down"))
        )
        with patch("httpx.AsyncClient", return_value=mock_client):
            resp = client.get(
                "/api/v1/blocklabor/workers/match?skills=forklift&pay_rate=18"
            )
        assert resp.status_code == 200
        assert resp.json() == {"workers": []}


class TestBlocklaborHealth:
    def test_health_reachable(self, client):
        mock_client = _async_client_mock(
            get=AsyncMock(return_value=AsyncMock(status_code=200))
        )
        with patch("httpx.AsyncClient", return_value=mock_client):
            resp = client.get("/api/v1/blocklabor/health")
        assert resp.json() == {"reachable": True}

    def test_health_unreachable(self, client):
        import httpx
        mock_client = _async_client_mock(
            get=AsyncMock(side_effect=httpx.ConnectError("down"))
        )
        with patch("httpx.AsyncClient", return_value=mock_client):
            resp = client.get("/api/v1/blocklabor/health")
        assert resp.json() == {"reachable": False}


class TestGetVerifiedTenant:
    @pytest.mark.asyncio
    async def test_missing_credentials_401(self):
        with pytest.raises(Exception) as exc:
            await get_verified_tenant(credentials=None, x_api_key="key")
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_invalid_token_401(self):
        class Creds:
            credentials = "bad-token"

        with patch(
            "api.routers.blocklabor_overlay365.verify_access_token",
            new_callable=AsyncMock,
            return_value=None,
        ):
            with pytest.raises(Exception) as exc:
                await get_verified_tenant(credentials=Creds(), x_api_key="key")
            assert exc.value.status_code == 401
