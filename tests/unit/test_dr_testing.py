"""Unit tests for src/api/services/dr_testing.py."""

from unittest.mock import AsyncMock, patch

import pytest

from api.services.dr_testing import DRTestingService, dr_testing_service


def _make_service():
    return DRTestingService()


class TestDatabaseFailover:
    @pytest.mark.asyncio
    async def test_success(self):
        svc = _make_service()
        with patch("api.services.dr_testing.random.uniform", return_value=5.5), \
             patch("api.services.dr_testing.random.random", return_value=0.9), \
             patch(
                 "api.services.dr_testing.create_dr_test_db",
                 new_callable=AsyncMock,
             ) as mock_db:
            result = await svc.test_database_failover("tenant-1")
        assert result["test_type"] == "database_failover"
        assert result["success"] is True
        assert result["failover_time_seconds"] == 5.5
        assert result["data_loss_seconds"] == 0
        assert "Simulated primary DB outage" in result["details"]
        args = mock_db.call_args[0]
        assert args[0] == "tenant-1"
        assert args[1] == "database_failover"
        assert args[2] == "passed"
        assert args[3]["test_type"] == "database_failover"
        assert isinstance(args[4], float)
        assert args[4] >= 5.5

    @pytest.mark.asyncio
    async def test_failure(self):
        svc = _make_service()
        with patch("api.services.dr_testing.random.uniform", return_value=6.25), \
             patch("api.services.dr_testing.random.random", return_value=0.01), \
             patch("api.services.dr_testing.random.randint", return_value=20), \
             patch(
                 "api.services.dr_testing.create_dr_test_db",
                 new_callable=AsyncMock,
             ) as mock_db:
            result = await svc.test_database_failover()
        assert result["success"] is False
        assert result["data_loss_seconds"] == 20
        args = mock_db.call_args[0]
        assert args[2] == "failed"

    @pytest.mark.asyncio
    async def test_default_tenant(self):
        svc = _make_service()
        with patch("api.services.dr_testing.random.uniform", return_value=2.0), \
             patch("api.services.dr_testing.random.random", return_value=0.9), \
             patch(
                 "api.services.dr_testing.create_dr_test_db",
                 new_callable=AsyncMock,
             ) as mock_db:
            await svc.test_database_failover()
        assert mock_db.call_args[0][0] == "system"


class TestServiceRestart:
    @pytest.mark.asyncio
    async def test_success(self):
        svc = _make_service()
        with patch("api.services.dr_testing.random.uniform", return_value=2.5), \
             patch("api.services.dr_testing.random.random", return_value=0.9), \
             patch(
                 "api.services.dr_testing.create_dr_test_db",
                 new_callable=AsyncMock,
             ) as mock_db:
            result = await svc.test_service_restart("api-gateway", "tenant-1")
        assert result["test_type"] == "service_restart"
        assert result["service_name"] == "api-gateway"
        assert result["success"] is True
        assert result["downtime_seconds"] == 2.5
        args = mock_db.call_args[0]
        assert args[1] == "service_restart:api-gateway"
        assert args[2] == "passed"

    @pytest.mark.asyncio
    async def test_failure(self):
        svc = _make_service()
        with patch("api.services.dr_testing.random.uniform", return_value=3.0), \
             patch("api.services.dr_testing.random.random", return_value=0.01), \
             patch(
                 "api.services.dr_testing.create_dr_test_db",
                 new_callable=AsyncMock,
             ) as mock_db:
            result = await svc.test_service_restart("worker")
        assert result["success"] is False
        assert mock_db.call_args[0][2] == "failed"


class TestNetworkPartition:
    @pytest.mark.asyncio
    async def test_success(self):
        svc = _make_service()
        with patch("api.services.dr_testing.random.uniform", return_value=7.25), \
             patch("api.services.dr_testing.random.random", return_value=0.9), \
             patch(
                 "api.services.dr_testing.create_dr_test_db",
                 new_callable=AsyncMock,
             ) as mock_db:
            result = await svc.test_network_partition("tenant-1")
        assert result["test_type"] == "network_partition"
        assert result["success"] is True
        assert result["recovery_time_seconds"] == 7.25
        assert result["services_affected"] == []
        args = mock_db.call_args[0]
        assert args[1] == "network_partition"
        assert args[2] == "passed"

    @pytest.mark.asyncio
    async def test_failure(self):
        svc = _make_service()
        with patch("api.services.dr_testing.random.uniform", return_value=10.0), \
             patch("api.services.dr_testing.random.random", return_value=0.05), \
             patch(
                 "api.services.dr_testing.create_dr_test_db",
                 new_callable=AsyncMock,
             ) as mock_db:
            result = await svc.test_network_partition()
        assert result["success"] is False
        assert result["services_affected"] == ["api", "database", "websocket"]
        assert mock_db.call_args[0][2] == "failed"


class TestDRStatus:
    @pytest.mark.asyncio
    async def test_get_dr_status(self):
        result = await _make_service().get_dr_status()
        assert result["dr_ready"] is True
        assert result["rto_seconds"] == 300
        assert result["rpo_seconds"] == 600
        assert result["last_dr_test"] is None
        assert result["backup_enabled"] is True
        assert result["failover_enabled"] is True
        assert result["healthy_regions"] == ["us-east-1", "us-west-2"]

    @pytest.mark.asyncio
    async def test_get_dr_config_returns_top_level_copy(self):
        svc = _make_service()
        config = await svc.get_dr_config()
        config["dr_ready"] = False
        config["last_dr_test"] = {"something": "else"}
        status = await svc.get_dr_status()
        assert status["dr_ready"] is True
        assert status["last_dr_test"] is None


class TestFullDrill:
    @pytest.mark.asyncio
    async def test_all_pass(self):
        svc = _make_service()
        with patch.object(
            svc,
            "test_database_failover",
            new_callable=AsyncMock,
            return_value={"test_type": "database_failover", "success": True},
        ), patch.object(
            svc,
            "test_service_restart",
            new_callable=AsyncMock,
            return_value={"test_type": "service_restart", "success": True},
        ), patch.object(
            svc,
            "test_network_partition",
            new_callable=AsyncMock,
            return_value={"test_type": "network_partition", "success": True},
        ):
            result = await svc.run_full_dr_drill("tenant-1")
        assert result["all_passed"] is True
        assert set(result["results"].keys()) == {
            "database_failover",
            "service_restart",
            "network_partition",
        }
        assert isinstance(result["duration_seconds"], float)
        assert svc._config["last_dr_test"]["all_passed"] is True
        assert "timestamp" in svc._config["last_dr_test"]

    @pytest.mark.asyncio
    async def test_failure_fails_drill(self):
        svc = _make_service()
        with patch.object(
            svc,
            "test_database_failover",
            new_callable=AsyncMock,
            return_value={"success": False},
        ), patch.object(
            svc,
            "test_service_restart",
            new_callable=AsyncMock,
            return_value={"success": True},
        ), patch.object(
            svc,
            "test_network_partition",
            new_callable=AsyncMock,
            return_value={"success": True},
        ):
            result = await svc.run_full_dr_drill()
        assert result["all_passed"] is False
        assert svc._config["last_dr_test"]["all_passed"] is False

    @pytest.mark.asyncio
    async def test_default_tenant_used(self):
        svc = _make_service()
        with patch.object(
            svc,
            "test_database_failover",
            new_callable=AsyncMock,
            return_value={"success": True},
        ) as db, patch.object(
            svc,
            "test_service_restart",
            new_callable=AsyncMock,
            return_value={"success": True},
        ) as restart, patch.object(
            svc,
            "test_network_partition",
            new_callable=AsyncMock,
            return_value={"success": True},
        ) as net:
            await svc.run_full_dr_drill()
        assert db.call_args[0][0] == "system"
        assert restart.call_args[0][0] == "api-gateway"
        assert restart.call_args[0][1] == "system"
        assert net.call_args[0][0] == "system"


class TestSingleton:
    def test_singleton_instance(self):
        assert isinstance(dr_testing_service, DRTestingService)
