"""Tests for the verification router (BlockLabor integration).

Uses a minimal FastAPI app with the router mounted and mocks the DB + Twilio
dependencies so no live services are contacted.
"""

from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers.verification import router


@pytest.fixture
def app():
    application = FastAPI()
    application.include_router(router)
    return application


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c


def _valid_business_payload():
    return {
        "business_name": "Acme Corp",
        "business_phone": "5551234567",
        "business_ein": "123456789",
        "business_state": "TX",
        "tenant_id": "TENANT-001",
    }


class TestVerifyBusinessIdentity:
    def test_verification_initiated(self, client):
        with patch(
            "api.routers.verification._trigger_outbound_call",
            new_callable=AsyncMock,
        ) as mock_trigger:
            mock_trigger.return_value = AsyncMock(
                id="verify-business_identity-abc"
            )

            resp = client.post("/api/v1/verification/business-identity", json=_valid_business_payload())
            assert resp.status_code == 200
            body = resp.json()
            assert body["status"] == "verification_initiated"
            assert body["verification_type"] == "business_identity"
            assert body["call_id"] == "verify-business_identity-abc"

            # Verify the call was triggered with the right type + number
            call_kwargs = mock_trigger.call_args.kwargs
            assert call_kwargs["verification_type"] == "business_identity"
            assert call_kwargs["called_number"] == "5551234567"

    def test_missing_required_field_returns_422(self, client):
        payload = _valid_business_payload()
        del payload["business_ein"]
        resp = client.post("/api/v1/verification/business-identity", json=payload)
        assert resp.status_code == 422

    def test_short_phone_rejected(self, client):
        payload = _valid_business_payload()
        payload["business_phone"] = "123"  # under min_length=10
        resp = client.post("/api/v1/verification/business-identity", json=payload)
        assert resp.status_code == 422


class TestGhostJobAudit:
    def test_audit_initiated(self, client):
        with patch(
            "api.routers.verification._trigger_outbound_call",
            new_callable=AsyncMock,
        ) as mock_trigger:
            mock_trigger.return_value = AsyncMock(id="verify-ghost_job_audit-xyz")

            resp = client.post(
                "/api/v1/verification/ghost-job-audit",
                json={
                    "job_id": "job-42",
                    "business_phone": "5559876543",
                    "job_title": "Software Engineer",
                    "tenant_id": "TENANT-001",
                },
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["status"] == "audit_initiated"
            assert body["verification_type"] == "ghost_job_audit"
            assert mock_trigger.call_args.kwargs["target_id"] == "job-42"


class TestSlaBreach:
    def test_sla_alert_initiated(self, client):
        with patch(
            "api.routers.verification._trigger_outbound_call",
            new_callable=AsyncMock,
        ) as mock_trigger:
            mock_trigger.return_value = AsyncMock(id="verify-application_sla-1")

            resp = client.post(
                "/api/v1/verification/application-sla-breach",
                json={
                    "job_id": "job-7",
                    "business_phone": "5554443333",
                    "applicant_name": "Jane Doe",
                    "sla_hours_breached": 48,
                    "tenant_id": "TENANT-001",
                },
            )
            assert resp.status_code == 200
            assert resp.json()["status"] == "sla_alert_initiated"
            assert mock_trigger.call_args.kwargs["verification_type"] == "application_sla"

    def test_sla_breach_zero_hours_rejected(self, client):
        resp = client.post(
            "/api/v1/verification/application-sla-breach",
            json={
                "job_id": "job-7",
                "business_phone": "5554443333",
                "applicant_name": "Jane Doe",
                "sla_hours_breached": 0,  # gt=0
                "tenant_id": "TENANT-001",
            },
        )
        assert resp.status_code == 422


class TestTriggerOutboundCall:
    @pytest.mark.asyncio
    async def test_creates_call_session_and_returns_response(self):
        with patch(
            "api.routers.verification.create_call_session",
            new_callable=AsyncMock,
        ) as mock_create_call, patch(
            "api.routers.verification.log_audit_event",
            new_callable=AsyncMock,
        ) as mock_log, patch(
            "api.routers.verification.os.environ.get", return_value=""
        ):
            from api.routers.verification import _trigger_outbound_call
            from types import SimpleNamespace

            request = SimpleNamespace()
            result = await _trigger_outbound_call(
                request=request,
                tenant_id="TENANT-001",
                called_number="5551234567",
                script="Hello",
                verification_type="business_identity",
                target_id="Acme",
            )

            assert result.id.startswith("verify-business_identity-")
            # Validate the id suffix is a UUID
            suffix = result.id.split("verify-business_identity-")[1]
            UUID(suffix)
            assert result.call_status == "initiated"
            assert result.intent_detected == "verification:business_identity"
            mock_create_call.assert_awaited_once()
            mock_log.assert_awaited_once()
