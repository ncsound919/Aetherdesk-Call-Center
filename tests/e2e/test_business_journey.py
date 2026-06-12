"""
Playwright E2E — Full Business User Journey
Tests the complete AetherDesk flow: login → dashboard → agent management → settings
"""
import pytest
from playwright.sync_api import Page, expect

BASE_URL = "http://127.0.0.1:3001"
API_URL = "http://127.0.0.1:8000"


class TestBusinessJourney:
    """Walk through the full platform as a business user."""

    @pytest.fixture(autouse=True)
    def setup(self, page: Page):
        page.set_viewport_size({"width": 1440, "height": 900})

    def test_01_landing_page(self, page: Page):
        page.goto(BASE_URL)
        expect(page.locator("text=AetherDesk")).to_be_visible(timeout=5000)

    def test_02_login_flow(self, page: Page):
        """User logs into the platform."""
        page.goto(f"{BASE_URL}/login")
        page.fill("input[type=email]", "admin@aetherdesk.com")
        page.fill("input[type=password]", "admin123")
        page.click("button:has-text('Sign in')")
        expect(page).to_have_url(f"{BASE_URL}/dashboard", timeout=5000)

    def test_03_dashboard_loads(self, page: Page):
        """Dashboard shows key metrics after login."""
        page.goto(f"{BASE_URL}/login")
        page.fill("input[type=email]", "admin@aetherdesk.com")
        page.fill("input[type=password]", "admin123")
        page.click("button:has-text('Sign in')")
        page.wait_for_url(f"{BASE_URL}/dashboard", timeout=5000)
        expect(page.locator("text=Dashboard")).to_be_visible()
        expect(page.locator("text=Active Calls")).to_be_visible()
        expect(page.locator("text=Available Agents")).to_be_visible()

    def test_04_sidebar_navigation(self, page: Page):
        """User can navigate through all sidebar sections."""
        page.goto(f"{BASE_URL}/login")
        page.fill("input[type=email]", "admin@aetherdesk.com")
        page.fill("input[type=password]", "admin123")
        page.click("button:has-text('Sign in')")
        page.wait_for_url(f"{BASE_URL}/dashboard", timeout=5000)

        sections = ["Call Logs", "Agents", "Voice Cloning", "Settings"]
        for section in sections:
            page.click(f"button:has-text('{section}')")
            page.wait_for_timeout(500)

    def test_05_agent_list(self, page: Page):
        """User views the agent management page."""
        page.goto(f"{BASE_URL}/login")
        page.fill("input[type=email]", "admin@aetherdesk.com")
        page.fill("input[type=password]", "admin123")
        page.click("button:has-text('Sign in')")
        page.wait_for_url(f"{BASE_URL}/dashboard", timeout=5000)
        page.click("button:has-text('Agents')")
        page.wait_for_timeout(1000)

    def test_06_call_logs(self, page: Page):
        """User views call history."""
        page.goto(f"{BASE_URL}/login")
        page.fill("input[type=email]", "admin@aetherdesk.com")
        page.fill("input[type=password]", "admin123")
        page.click("button:has-text('Sign in')")
        page.wait_for_url(f"{BASE_URL}/dashboard", timeout=5000)
        page.click("button:has-text('Call Logs')")
        page.wait_for_timeout(1000)

    def test_07_logout(self, page: Page):
        """User can sign out."""
        page.goto(f"{BASE_URL}/login")
        page.fill("input[type=email]", "admin@aetherdesk.com")
        page.fill("input[type=password]", "admin123")
        page.click("button:has-text('Sign in')")
        page.wait_for_url(f"{BASE_URL}/dashboard", timeout=5000)
        page.click("button:has-text('Sign Out')")
        page.wait_for_url(f"{BASE_URL}/login", timeout=5000)
