"""
E2E tests from a human user perspective.

Scenarios:
  Business Owner:  Visit landing page, log in, explore dashboard.
  Affiliate:       View portal after login.
  API Consumer:    Health check, metrics, CRUD, edge cases.
"""
import json as _json

import httpx
from playwright.sync_api import Page, expect


class TestLandingPage:
    """A visitor arrives at the aetherdesk.io landing page."""

    def test_landing_shows_brand_and_nav(self, page: Page, ui_url: str) -> None:
        page.goto(ui_url)
        expect(page.locator(".brand")).to_be_visible()
        expect(page.locator(".brand")).to_contain_text("AETHERDESK")
        expect(page.locator("text=Rent Your Own").first).to_be_visible()
        expect(page.locator("text=Features").first).to_be_visible()
        expect(page.locator("text=Pricing").first).to_be_visible()
        expect(page.locator("text=Login").first).to_be_visible()

    def test_pricing_tiers_visible(self, page: Page, ui_url: str) -> None:
        page.goto(ui_url)
        loc = page.locator("text=Flexible Rental Blocks").first
        loc.scroll_into_view_if_needed()
        expect(loc).to_be_visible()
        expect(page.locator(".glass-card:has-text('Startup')")).to_be_visible()
        expect(page.locator(".glass-card:has-text('Business')")).to_be_visible()
        expect(
            page.locator(".glass-card:has-text('Enterprise')").first
        ).to_be_visible()


class TestLoginAndDashboard:
    """A business owner logs in and accesses the dashboard."""

    def test_login_flow(self, page: Page, ui_url: str) -> None:
        page.goto(ui_url)
        page.locator("text=Login").first.click()
        page.wait_for_url(lambda u: "/login" in u)
        expect(
            page.locator("h2:has-text('Login to AetherDesk')")
        ).to_be_visible()

        page.locator("button:has-text('Sign In')").first.click()
        page.wait_for_url(lambda u: "/dashboard" in u)
        expect(page.locator(".sidebar")).to_be_visible()

    def test_navigate_tabs(self, page: Page, ui_url: str) -> None:
        page.goto(ui_url)
        page.locator("text=Login").first.click()
        page.locator("button:has-text('Sign In')").first.click()
        expect(page.locator(".sidebar")).to_be_visible()

        expect(
            page.locator("text=Operational Fleet Overview").first
        ).to_be_visible()

        page.locator("text=Command Center").first.click()
        expect(page.locator("text=Command Center").first).to_be_visible()

        page.locator("text=Marketplace").first.click()
        expect(
            page.locator("h2:has-text('Community-Led Template Marketplace')")
        ).to_be_visible()


class TestAffiliate:
    """An affiliate checks their portal after login."""

    def test_affiliate_page_loads(self, page: Page, ui_url: str) -> None:
        page.goto(ui_url)
        page.locator("text=Login").first.click()
        page.locator("button:has-text('Sign In')").first.click()
        expect(page.locator(".sidebar")).to_be_visible()

        page.locator("text=Affiliate").first.click()
        expect(page.locator("text=Affiliate")).to_be_visible()


class TestCommandCenter:
    """Operations manager monitors fleet."""

    def test_command_center_loads(self, page: Page, ui_url: str) -> None:
        page.goto(ui_url)
        page.locator("text=Login").first.click()
        page.locator("button:has-text('Sign In')").first.click()

        page.locator("text=Command Center").first.click()
        expect(page.locator("text=Command Center").first).to_be_visible()


class TestMarketplace:
    """User browses community templates."""

    def test_marketplace_loads(self, page: Page, ui_url: str) -> None:
        page.goto(ui_url)
        page.locator("text=Login").first.click()
        page.locator("button:has-text('Sign In')").first.click()

        page.locator("text=Marketplace").first.click()
        expect(
            page.locator("h2:has-text('Community-Led Template Marketplace')")
        ).to_be_visible()


class TestAPIIntegration:
    """A developer tests the REST API surface directly."""

    def test_health_endpoint_returns_ok(self, api_url: str) -> None:
        resp = httpx.get(
            f"{api_url}/health", headers={"x-api-key": "dev-api-key"}, timeout=10
        )
        assert resp.status_code == 200, f"Health check failed: {resp.text}"
        data = resp.json()
        assert "status" in data

    def test_metrics_endpoint_returns_prometheus(self, api_url: str) -> None:
        resp = httpx.get(
            f"{api_url}/metrics", headers={"x-api-key": "dev-api-key"}, timeout=10
        )
        assert resp.status_code == 200
        assert "http_requests_total" in resp.text or "process_" in resp.text

    def test_saas_dashboard_api_works(self, api_url: str) -> None:
        resp = httpx.get(
            f"{api_url}/api/v1/saas/dashboard",
            headers={"x-api-key": "dev-api-key"},
            timeout=10,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "rentals" in data
        assert "profiles" in data

    def test_saas_settings_full_crud_cycle(self, api_url: str) -> None:
        headers = {"x-api-key": "dev-api-key"}
        payload = {
            "api_feeds": '{"inventory": "http://test-feed.io"}',
            "auto_mode_enabled": True,
            "redact_pii": True,
            "require_consent": False,
            "sync_dnc": True,
            "mcp_servers": '{"wiki": "mcp://wiki.local"}',
        }
        post_resp = httpx.post(
            f"{api_url}/api/v1/saas/settings",
            json=payload,
            headers=headers,
            timeout=10,
        )
        assert post_resp.status_code == 200

        get_resp = httpx.get(
            f"{api_url}/api/v1/saas/settings",
            headers=headers,
            timeout=10,
        )
        assert get_resp.status_code == 200
        data = get_resp.json()
        assert data["auto_mode_enabled"]
        assert not data["require_consent"]
        assert data["sync_dnc"]
        assert "wiki" in data["mcp_servers"]

    def test_create_agent_profile_via_api(self, api_url: str) -> None:
        headers = {"x-api-key": "dev-api-key"}
        prof = {
            "name": "E2E Journey Agent",
            "prompt": "You are a test agent from the human user journey.",
            "parameters": {"tone": "professional", "industry": "logistics"},
        }
        create_resp = httpx.post(
            f"{api_url}/api/v1/saas/profile?name=E2E+Journey+Agent&prompt=Test+Prompt",
            json=prof,
            headers=headers,
            timeout=10,
        )
        assert create_resp.status_code == 200
        profile_id = create_resp.json()["profile_id"]
        assert profile_id.startswith("PROF-")

        dash_resp = httpx.get(
            f"{api_url}/api/v1/saas/dashboard",
            headers=headers,
            timeout=10,
        )
        assert dash_resp.status_code == 200
        profile_ids = [p["id"] for p in dash_resp.json()["profiles"]]
        assert profile_id in profile_ids

    def test_rent_agent_via_api(self, api_url: str) -> None:
        headers = {"x-api-key": "dev-api-key"}
        prof = {
            "name": "E2E Rental Agent",
            "prompt": "Rent me for testing.",
            "parameters": {"tone": "casual"},
        }
        create_resp = httpx.post(
            f"{api_url}/api/v1/saas/profile?name=E2E+Rental+Agent&prompt=Rent+Test",
            json=prof,
            headers=headers,
            timeout=10,
        )
        profile_id = create_resp.json()["profile_id"]

        rent_resp = httpx.post(
            f"{api_url}/api/v1/saas/rent?profile_id={profile_id}&duration_type=day",
            headers=headers,
            timeout=10,
        )
        assert rent_resp.status_code == 200
        data = rent_resp.json()
        assert "rental_id" in data
        assert data["rental_id"].startswith("RENT-")
        assert "end_time" in data


class TestEdgeCasesAndResilience:
    """Non-happy-path scenarios that a real user might encounter."""

    def test_invalid_tenant_key_is_rejected(self, api_url: str) -> None:
        resp = httpx.get(
            f"{api_url}/api/v1/saas/dashboard",
            headers={"x-api-key": "totally-fake-key-123"},
            timeout=10,
        )
        assert resp.status_code == 401

    def test_missing_api_key_gets_default_tenant(self, api_url: str) -> None:
        resp = httpx.get(f"{api_url}/api/v1/saas/dashboard", timeout=10)
        assert resp.status_code == 200
        data = resp.json()
        assert "rentals" in data

    def test_invalid_duration_type_rejected(self, api_url: str) -> None:
        headers = {"x-api-key": "dev-api-key"}
        resp = httpx.post(
            f"{api_url}/api/v1/saas/rent?profile_id=PROF-FAKE01&duration_type=century",
            headers=headers,
            timeout=10,
        )
        assert resp.status_code == 400

    def test_api_handles_large_payload_gracefully(self, api_url: str) -> None:
        headers = {"x-api-key": "dev-api-key"}
        payload = {
            "api_feeds": _json.dumps(
                {f"feed_{i}": f"http://api{i}.example.com" for i in range(100)}
            ),
            "auto_mode_enabled": True,
            "redact_pii": True,
            "require_consent": True,
            "sync_dnc": False,
            "mcp_servers": '{}',
        }
        resp = httpx.post(
            f"{api_url}/api/v1/saas/settings",
            json=payload,
            headers=headers,
            timeout=10,
        )
        assert resp.status_code == 200
