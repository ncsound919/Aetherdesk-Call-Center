"""Unit tests for api.routers.platform_ops."""

import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# The api.routers package __init__ pulls in api.services.asr, which imports
# faster_whisper -> ctranslate2 -> torch at module level. Stub it out so the
# router imports stay fast and hermetic (no real model/torch loading).
_faster_whisper = types.ModuleType("faster_whisper")
_faster_whisper.WhisperModel = MagicMock
sys.modules.setdefault("faster_whisper", _faster_whisper)

from api.routers.platform_ops import router
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


class TestBranding:
    def test_get_branding(self, client):
        with patch(
            "api.routers.platform_ops.white_label_service.get_branding",
            new_callable=AsyncMock,
            return_value={"tenant_id": "TENANT-001", "company_name": "Acme"},
        ) as mock_branding:
            resp = client.get("/platform/branding")
        assert resp.status_code == 200
        assert resp.json()["company_name"] == "Acme"
        mock_branding.assert_awaited_once_with("TENANT-001")

    def test_update_branding_success(self, client):
        with patch(
            "api.routers.platform_ops.white_label_service.set_branding",
            new_callable=AsyncMock,
            return_value={"tenant_id": "TENANT-001", "company_name": "Acme"},
        ) as mock_set:
            resp = client.put(
                "/platform/branding",
                json={
                    "company_name": "Acme",
                    "primary_color": "#ff0000",
                    "logo_url": None,
                },
            )
        assert resp.status_code == 200
        # None values filtered out before calling set_branding
        mock_set.assert_awaited_once_with(
            "TENANT-001", {"company_name": "Acme", "primary_color": "#ff0000"}
        )

    def test_update_branding_failure(self, client):
        with patch(
            "api.routers.platform_ops.white_label_service.set_branding",
            new_callable=AsyncMock,
            return_value=None,
        ):
            resp = client.put("/platform/branding", json={"company_name": "Acme"})
        assert resp.status_code == 400
        assert resp.json()["detail"] == "Failed to update branding"


class TestDomain:
    def test_get_domain_default(self, client):
        with patch(
            "api.routers.platform_ops.white_label_service.get_custom_domain",
            new_callable=AsyncMock,
            return_value=None,
        ):
            resp = client.get("/platform/domain")
        assert resp.status_code == 200
        assert resp.json() == {
            "tenant_id": "TENANT-001",
            "domain": None,
            "ssl_status": None,
            "verified": False,
        }

    def test_get_domain_existing(self, client):
        with patch(
            "api.routers.platform_ops.white_label_service.get_custom_domain",
            new_callable=AsyncMock,
            return_value={
                "domain": "acme.example.com",
                "ssl_status": "active",
                "verified": True,
            },
        ):
            resp = client.get("/platform/domain")
        assert resp.status_code == 200
        assert resp.json()["domain"] == "acme.example.com"
        assert resp.json()["ssl_status"] == "active"
        assert resp.json()["verified"] is True

    def test_set_domain_success(self, client):
        with patch(
            "api.routers.platform_ops.white_label_service.set_custom_domain",
            new_callable=AsyncMock,
            return_value={"domain": "acme.example.com", "ssl_status": "pending"},
        ) as mock_set:
            resp = client.put(
                "/platform/domain", json={"domain": "acme.example.com"}
            )
        assert resp.status_code == 200
        mock_set.assert_awaited_once_with(
            "TENANT-001", "acme.example.com", "pending"
        )

    def test_set_domain_custom_ssl(self, client):
        with patch(
            "api.routers.platform_ops.white_label_service.set_custom_domain",
            new_callable=AsyncMock,
            return_value={"ssl_status": "issued"},
        ) as mock_set:
            resp = client.put(
                "/platform/domain",
                json={"domain": "acme.example.com", "ssl_status": "issued"},
            )
        assert resp.status_code == 200
        mock_set.assert_awaited_once_with(
            "TENANT-001", "acme.example.com", "issued"
        )

    def test_set_domain_failure(self, client):
        with patch(
            "api.routers.platform_ops.white_label_service.set_custom_domain",
            new_callable=AsyncMock,
            return_value=None,
        ):
            resp = client.put("/platform/domain", json={"domain": "acme.example.com"})
        assert resp.status_code == 400
        assert resp.json()["detail"] == "Failed to set custom domain"

    def test_verify_domain(self, client):
        with patch(
            "api.routers.platform_ops.white_label_service.verify_domain",
            new_callable=AsyncMock,
            return_value={"verified": True, "ssl_status": "active"},
        ) as mock_verify:
            resp = client.post(
                "/platform/domain/verify", params={"domain": "acme.example.com"}
            )
        assert resp.status_code == 200
        assert resp.json()["verified"] is True
        mock_verify.assert_awaited_once_with("TENANT-001", "acme.example.com")


class TestSignup:
    def test_signup(self, client):
        with patch(
            "api.routers.platform_ops.self_serve_service.create_trial_tenant",
            new_callable=AsyncMock,
            return_value={"tenant_id": "t1", "api_key": "k", "slug": "acme"},
        ) as mock_signup:
            resp = client.post(
                "/platform/signup",
                json={"email": "admin@acme.com", "company_name": "Acme", "password": "secret"},
            )
        assert resp.status_code == 200
        assert resp.json()["slug"] == "acme"
        mock_signup.assert_awaited_once_with("admin@acme.com", "Acme", "secret")


class TestOnboarding:
    def test_get_onboarding_status(self, client):
        with patch(
            "api.routers.platform_ops.self_serve_service.get_onboarding_status",
            new_callable=AsyncMock,
            return_value={"steps_completed": [], "current_step": "welcome"},
        ) as mock_status:
            resp = client.get("/platform/onboarding/status")
        assert resp.status_code == 200
        assert resp.json()["current_step"] == "welcome"
        mock_status.assert_awaited_once_with("TENANT-001")

    def test_complete_onboarding_step(self, client):
        with patch(
            "api.routers.platform_ops.self_serve_service.complete_step",
            new_callable=AsyncMock,
            return_value={"steps_completed": ["welcome"], "completed": False},
        ) as mock_step:
            resp = client.post("/platform/onboarding/step", json={"step": "welcome"})
        assert resp.status_code == 200
        mock_step.assert_awaited_once_with("TENANT-001", "welcome")

    def test_get_quickstart(self, client):
        with patch(
            "api.routers.platform_ops.self_serve_service.get_quickstart_guide",
            new_callable=AsyncMock,
            return_value={"tenant_id": "TENANT-001", "steps": []},
        ):
            resp = client.get("/platform/onboarding/quickstart")
        assert resp.status_code == 200

    def test_provision_number(self, client):
        with patch(
            "api.routers.platform_ops.self_serve_service.provision_phone_number",
            new_callable=AsyncMock,
            return_value={"phone_number": "+12125550123", "status": "reserved"},
        ) as mock_provision:
            resp = client.post("/platform/provision/number", json={"area_code": "212"})
        assert resp.status_code == 200
        assert resp.json()["phone_number"] == "+12125550123"
        mock_provision.assert_awaited_once_with("TENANT-001", "212")

    def test_get_setup_progress(self, client):
        with patch(
            "api.routers.platform_ops.self_serve_service.get_setup_progress",
            new_callable=AsyncMock,
            return_value={"percent_complete": 25, "remaining_steps": []},
        ):
            resp = client.get("/platform/setup/progress")
        assert resp.status_code == 200
        assert resp.json()["percent_complete"] == 25

    def test_run_health_check(self, client):
        with patch(
            "api.routers.platform_ops.self_serve_service.run_health_check",
            new_callable=AsyncMock,
            return_value={"overall_status": "passed", "checks": {}},
        ):
            resp = client.post("/platform/health-check")
        assert resp.status_code == 200
        assert resp.json()["overall_status"] == "passed"
