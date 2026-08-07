"""Tests for the reliability router (circuit breakers, rate limits, DR, cache)."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers.reliability import router
from api.services.auth import verify_tenant_access


@pytest.fixture
def app():
    application = FastAPI()
    application.include_router(router)

    async def _override_tenant():
        return "TENANT-001"

    application.dependency_overrides[verify_tenant_access] = _override_tenant
    return application


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c


class TestCircuitBreakers:
    def test_list_circuit_breakers(self, client):
        with patch(
            "api.routers.reliability.circuit_breaker_registry.list_state",
            return_value=[{"name": "db", "state": "CLOSED"}],
        ):
            resp = client.get("/reliability/circuit-breakers")
        assert resp.status_code == 200
        assert resp.json()[0]["name"] == "db"

    def test_reset_circuit_breaker_success(self, client):
        with patch(
            "api.routers.reliability.circuit_breaker_registry.reset",
            new_callable=AsyncMock,
            return_value=True,
        ):
            resp = client.post("/reliability/circuit-breakers/db/reset")
        assert resp.status_code == 200
        assert resp.json() == {"success": True, "name": "db", "state": "RESET"}

    def test_reset_circuit_breaker_not_found(self, client):
        with patch(
            "api.routers.reliability.circuit_breaker_registry.reset",
            new_callable=AsyncMock,
            return_value=False,
        ):
            resp = client.post("/reliability/circuit-breakers/nope/reset")
        assert resp.status_code == 404


class TestRateLimits:
    def test_get_rate_limits(self, client):
        with patch(
            "api.routers.reliability.rate_limiter.get_all_limits",
            new_callable=AsyncMock,
            return_value={"TENANT-001": {"default": {"max_requests": 100}}},
        ):
            resp = client.get("/reliability/rate-limits")
        assert resp.status_code == 200

    def test_set_rate_limit(self, client):
        with patch(
            "api.routers.reliability.rate_limiter.set_limits",
            new_callable=AsyncMock,
            return_value={"success": True},
        ) as mock_set:
            resp = client.put(
                "/reliability/rate-limits/TENANT-002",
                params={"route_key": "/api/v1/calls", "max_requests": 500, "window_seconds": 120},
            )
        assert resp.status_code == 200
        assert resp.json() == {"success": True}
        call_kwargs = mock_set.call_args
        assert call_kwargs.args[0] == "TENANT-002"
        assert call_kwargs.args[2] == 500

    def test_set_rate_limit_validation(self, client):
        # max_requests > 10000 rejected
        resp = client.put(
            "/reliability/rate-limits/TENANT-002",
            params={"route_key": "/x", "max_requests": 99999},
        )
        assert resp.status_code == 422


class TestDrStatus:
    def test_get_dr_status(self, client):
        with patch(
            "api.routers.reliability.dr_testing_service.get_dr_status",
            new_callable=AsyncMock,
            return_value={"status": "healthy"},
        ):
            resp = client.get("/reliability/dr/status")
        assert resp.status_code == 200
        assert resp.json() == {"status": "healthy"}

    def test_run_full_dr_drill(self, client):
        with patch(
            "api.routers.reliability.dr_testing_service.run_full_dr_drill",
            new_callable=AsyncMock,
            return_value={"drill": "complete"},
        ) as mock_drill:
            resp = client.post("/reliability/dr/test", params={"test_type": "full"})
        assert resp.status_code == 200
        assert resp.json() == {"drill": "complete"}
        mock_drill.assert_awaited_once_with("TENANT-001")

    def test_run_database_failover(self, client):
        with patch(
            "api.routers.reliability.dr_testing_service.test_database_failover",
            new_callable=AsyncMock,
            return_value={"failover": "ok"},
        ):
            resp = client.post("/reliability/dr/test", params={"test_type": "database_failover"})
        assert resp.status_code == 200

    def test_run_service_restart_uses_default(self, client):
        with patch(
            "api.routers.reliability.dr_testing_service.test_service_restart",
            new_callable=AsyncMock,
            return_value={"restart": "ok"},
        ) as mock_restart:
            resp = client.post("/reliability/dr/test", params={"test_type": "service_restart"})
        assert resp.status_code == 200
        assert mock_restart.call_args.args[0] == "api-gateway"

    def test_run_network_partition(self, client):
        with patch(
            "api.routers.reliability.dr_testing_service.test_network_partition",
            new_callable=AsyncMock,
            return_value={"partition": "ok"},
        ) as mock_partition:
            resp = client.post("/reliability/dr/test", params={"test_type": "network_partition"})
        assert resp.status_code == 200
        assert mock_partition.call_args.args[0] == "TENANT-001"

    def test_run_unknown_test_type_400(self, client):
        resp = client.post("/reliability/dr/test", params={"test_type": "banana"})
        assert resp.status_code == 400

    def test_get_dr_config(self, client):
        with patch(
            "api.routers.reliability.dr_testing_service.get_dr_config",
            new_callable=AsyncMock,
            return_value={"region": "us-east"},
        ):
            resp = client.get("/reliability/dr/config")
        assert resp.status_code == 200


class TestCache:
    def test_get_cache_stats(self, client):
        with patch(
            "api.routers.reliability.redis_cache_service.get_stats",
            new_callable=AsyncMock,
            return_value={"keys": 5},
        ):
            resp = client.get("/reliability/cache/stats")
        assert resp.status_code == 200
        assert resp.json() == {"keys": 5}

    def test_warm_cache_with_value(self, client):
        with patch(
            "api.routers.reliability.redis_cache_service.set",
            new_callable=AsyncMock,
        ) as mock_set:
            resp = client.post(
                "/reliability/cache/warm",
                params={"key": "agent:1", "value": "data", "ttl": 600},
            )
        assert resp.status_code == 200
        assert resp.json() == {"success": True, "key": "agent:1", "cached": True}
        mock_set.assert_awaited_once_with("agent:1", "data", 600)

    def test_warm_cache_without_value(self, client):
        resp = client.post("/reliability/cache/warm", params={"key": "agent:2"})
        assert resp.status_code == 200
        assert resp.json()["cached"] is False
