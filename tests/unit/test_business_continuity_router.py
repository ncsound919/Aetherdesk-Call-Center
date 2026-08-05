"""Tests for the business continuity router (failover, chaos, contracts)."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers.business_continuity import router
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


class TestFailover:
    def test_run_failover_test(self, client):
        with patch(
            "api.routers.business_continuity.dr_service.test_failover",
            new_callable=AsyncMock,
            return_value={"id": "fo-1", "status": "passed"},
        ) as mock_fo:
            resp = client.post(
                "/business-continuity/failover/test",
                json={"service": "postgres"},
            )
        assert resp.status_code == 200
        assert resp.json()["status"] == "passed"
        assert mock_fo.call_args.args[0] == "postgres"

    def test_run_failover_test_failed(self, client):
        with patch(
            "api.routers.business_continuity.dr_service.test_failover",
            new_callable=AsyncMock,
            return_value=None,
        ):
            resp = client.post(
                "/business-continuity/failover/test",
                json={"service": "postgres"},
            )
        assert resp.status_code == 400

    def test_list_failover_tests(self, client):
        with patch(
            "api.routers.business_continuity.dr_service.list_failover_tests",
            new_callable=AsyncMock,
            return_value=[{"id": "fo-1"}],
        ):
            resp = client.get("/business-continuity/failover/tests")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_multi_region_status(self, client):
        with patch(
            "api.routers.business_continuity.dr_service.get_multi_region_status",
            new_callable=AsyncMock,
            return_value={"regions": ["us-east-1", "us-west-2"]},
        ):
            resp = client.get("/business-continuity/failover/multi-region")
        assert resp.status_code == 200


class TestChaos:
    def test_run_chaos(self, client):
        with patch(
            "api.routers.business_continuity.dr_service.run_chaos_experiment",
            new_callable=AsyncMock,
            return_value={"id": "chaos-1", "status": "running"},
        ) as mock_chaos:
            resp = client.post(
                "/business-continuity/chaos/run",
                json={"target": "api-gateway", "fault_type": "terminate", "duration_seconds": 60},
            )
        assert resp.status_code == 200
        assert mock_chaos.call_args.args[0] == "api-gateway"
        assert mock_chaos.call_args.args[2] == 60

    def test_run_chaos_failed(self, client):
        with patch(
            "api.routers.business_continuity.dr_service.run_chaos_experiment",
            new_callable=AsyncMock,
            return_value=None,
        ):
            resp = client.post(
                "/business-continuity/chaos/run",
                json={"target": "api", "fault_type": "terminate"},
            )
        assert resp.status_code == 400

    def test_list_chaos_experiments(self, client):
        with patch(
            "api.routers.business_continuity.dr_service.list_chaos_experiments",
            new_callable=AsyncMock,
            return_value=[],
        ):
            resp = client.get("/business-continuity/chaos/experiments")
        assert resp.status_code == 200
        assert resp.json() == []


class TestContracts:
    def test_create_contract(self, client):
        with patch(
            "api.routers.business_continuity.dr_service.manage_contract",
            new_callable=AsyncMock,
            return_value={"id": "c-1", "status": "active"},
        ) as mock_contract:
            resp = client.post(
                "/business-continuity/contracts",
                json={
                    "vendor": "AWS",
                    "terms": "99.9% uptime",
                    "renewal_date": "2027-01-01",
                    "cost": 10000,
                },
            )
        assert resp.status_code == 200
        assert mock_contract.call_args.args[0] == "TENANT-001"
        assert mock_contract.call_args.args[1] == "AWS"

    def test_create_contract_validation(self, client):
        resp = client.post("/business-continuity/contracts", json={})
        assert resp.status_code == 422

    def test_list_contracts(self, client):
        with patch(
            "api.routers.business_continuity.dr_service.list_contracts",
            new_callable=AsyncMock,
            return_value=[{"id": "c-1"}],
        ):
            resp = client.get("/business-continuity/contracts")
        assert resp.status_code == 200
        assert len(resp.json()) == 1


class TestBackupChannels:
    def test_configure_backup_channel(self, client):
        with patch(
            "api.routers.business_continuity.dr_service.configure_backup_channel",
            new_callable=AsyncMock,
            return_value={"channel_type": "whatsapp", "configured": True},
        ) as mock_cfg:
            resp = client.post(
                "/business-continuity/backup-channels",
                json={"channel_type": "whatsapp", "config": {"number": "+1"}},
            )
        assert resp.status_code == 200
        assert mock_cfg.call_args.args[1] == "whatsapp"

    def test_test_backup_channel(self, client):
        with patch(
            "api.routers.business_continuity.dr_service.test_backup_channel",
            new_callable=AsyncMock,
            return_value={"reachable": True},
        ) as mock_test:
            resp = client.post(
                "/business-continuity/backup-channels/test",
                params={"channel_type": "whatsapp"},
            )
        assert resp.status_code == 200
        assert mock_test.call_args.args[1] == "whatsapp"

    def test_list_backup_channels(self, client):
        with patch(
            "api.routers.business_continuity.dr_service.list_backup_channels",
            new_callable=AsyncMock,
            return_value=[{"channel_type": "whatsapp"}],
        ):
            resp = client.get("/business-continuity/backup-channels")
        assert resp.status_code == 200
