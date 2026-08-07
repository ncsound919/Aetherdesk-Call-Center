"""Unit tests for api.services.white_label.WhiteLabelService."""

from unittest.mock import AsyncMock, patch

import pytest

from api.services.white_label import white_label_service

BRANDING = {
    "tenant_id": "t1",
    "company_name": "Acme",
    "logo_url": "https://logo",
    "primary_color": "#ff0000",
    "secondary_color": "#00ff00",
    "favicon_url": "https://favicon",
}


@pytest.fixture(autouse=True)
def _noop_logger():
    pass


@pytest.mark.asyncio
class TestWhiteLabelService:
    async def test_get_branding_default_when_missing(self):
        with patch(
            "api.services.white_label.get_tenant_branding_db",
            new_callable=AsyncMock,
            return_value=None,
        ) as mock_db:
            result = await white_label_service.get_branding("t1")
        mock_db.assert_awaited_once_with("t1")
        assert result == {
            "tenant_id": "t1",
            "company_name": "",
            "logo_url": "",
            "primary_color": "#2563eb",
            "secondary_color": "#7c3aed",
            "favicon_url": "",
        }

    async def test_get_branding_returns_existing(self):
        with patch(
            "api.services.white_label.get_tenant_branding_db",
            new_callable=AsyncMock,
            return_value=BRANDING,
        ):
            result = await white_label_service.get_branding("t1")
        assert result == BRANDING

    async def test_set_branding(self):
        config = {"company_name": "Acme"}
        with patch(
            "api.services.white_label.set_tenant_branding_db",
            new_callable=AsyncMock,
            return_value={"tenant_id": "t1", **config},
        ) as mock_db:
            result = await white_label_service.set_branding("t1", config)
        mock_db.assert_awaited_once_with("t1", config)
        assert result["company_name"] == "Acme"

    async def test_get_custom_domain(self):
        with patch(
            "api.services.white_label.get_custom_domain_db",
            new_callable=AsyncMock,
            return_value={"id": "d1", "domain": "acme.com"},
        ) as mock_db:
            result = await white_label_service.get_custom_domain("t1")
        mock_db.assert_awaited_once_with("t1")
        assert result["domain"] == "acme.com"

    async def test_set_custom_domain_default_ssl_status(self):
        with patch(
            "api.services.white_label.set_custom_domain_db",
            new_callable=AsyncMock,
            return_value={"domain": "acme.com"},
        ) as mock_db:
            result = await white_label_service.set_custom_domain("t1", "acme.com")
        mock_db.assert_awaited_once_with("t1", "acme.com", "pending")
        assert result["domain"] == "acme.com"

    async def test_set_custom_domain_custom_ssl_status(self):
        with patch(
            "api.services.white_label.set_custom_domain_db",
            new_callable=AsyncMock,
            return_value={"ssl_status": "issued"},
        ) as mock_db:
            result = await white_label_service.set_custom_domain(
                "t1", "acme.com", ssl_status="issued"
            )
        mock_db.assert_awaited_once_with("t1", "acme.com", "issued")
        assert result["ssl_status"] == "issued"

    async def test_verify_domain_no_config(self):
        with patch(
            "api.services.white_label.get_custom_domain_db",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await white_label_service.verify_domain("t1", "acme.com")
        assert result == {
            "verified": False,
            "message": "No custom domain configured",
        }

    async def test_verify_domain_no_id(self):
        with patch(
            "api.services.white_label.get_custom_domain_db",
            new_callable=AsyncMock,
            return_value={"domain": "acme.com"},
        ):
            result = await white_label_service.verify_domain("t1", "acme.com")
        assert result == {"verified": False, "message": "Domain record not found"}

    async def test_verify_domain_success_via_domain_id(self):
        with patch(
            "api.services.white_label.get_custom_domain_db",
            new_callable=AsyncMock,
            return_value={"domain_id": "did-1", "domain": "acme.com"},
        ), patch(
            "api.services.white_label.verify_domain_db",
            new_callable=AsyncMock,
            return_value={"verified": True, "ssl_status": "active"},
        ) as mock_verify:
            result = await white_label_service.verify_domain("t1", "acme.com")
        mock_verify.assert_awaited_once_with("did-1")
        assert result == {"verified": True, "ssl_status": "active", "domain": "acme.com"}

    async def test_verify_domain_dns_failure(self):
        with patch(
            "api.services.white_label.get_custom_domain_db",
            new_callable=AsyncMock,
            return_value={"id": "d1"},
        ), patch(
            "api.services.white_label.verify_domain_db",
            new_callable=AsyncMock,
            return_value={"verified": False},
        ):
            result = await white_label_service.verify_domain("t1", "acme.com")
        assert result == {"verified": False, "message": "DNS verification failed"}

    async def test_get_tenant_theme_default(self):
        with patch(
            "api.services.white_label.get_tenant_branding_db",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await white_label_service.get_tenant_theme("t1")
        assert result == {
            "--primary": "#2563eb",
            "--secondary": "#7c3aed",
            "--background": "#ffffff",
            "--text": "#111827",
        }

    async def test_get_tenant_theme_with_branding(self):
        with patch(
            "api.services.white_label.get_tenant_branding_db",
            new_callable=AsyncMock,
            return_value=BRANDING,
        ):
            result = await white_label_service.get_tenant_theme("t1")
        assert result["--primary"] == "#ff0000"
        assert result["--secondary"] == "#00ff00"

    async def test_get_tenant_theme_missing_colors_uses_defaults(self):
        with patch(
            "api.services.white_label.get_tenant_branding_db",
            new_callable=AsyncMock,
            return_value={"tenant_id": "t1"},
        ):
            result = await white_label_service.get_tenant_theme("t1")
        assert result["--primary"] == "#2563eb"
        assert result["--secondary"] == "#7c3aed"

    async def test_list_white_label_tenants(self):
        with patch(
            "api.services.white_label.list_white_label_tenants_db",
            new_callable=AsyncMock,
            return_value=[{"tenant_id": "t1"}],
        ) as mock_db:
            result = await white_label_service.list_white_label_tenants()
        mock_db.assert_awaited_once()
        assert result == [{"tenant_id": "t1"}]
