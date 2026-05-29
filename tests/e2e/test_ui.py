
from playwright.sync_api import Page, expect


def test_landing_page_loads_and_navigates(page: Page):
    """
    Tests that the landing page loads and navigation works.
    """
    page.goto("http://localhost:8000/")

    expect(page.locator(".brand")).to_be_visible()
    expect(page.locator(".brand")).to_contain_text("AETHERDESK")

    expect(page.locator("text=Rent Your Own").first).to_be_visible()
    expect(page.locator("text=Agentic Call Center").first).to_be_visible()

    expect(page.locator("text=Features").first).to_be_visible()
    expect(page.locator("text=Pricing").first).to_be_visible()
    expect(page.locator("text=Login").first).to_be_visible()

    loc = page.locator("text=Flexible Rental Blocks").first
    loc.scroll_into_view_if_needed()
    expect(loc).to_be_visible()


def test_login_and_dashboard(page: Page):
    """
    Tests login flow and dashboard access.
    """
    page.goto("http://localhost:8000/")

    page.locator("text=Login").first.click()
    page.wait_for_url(lambda u: "/login" in u)
    expect(page.locator("h2:has-text('Login to AetherDesk')")).to_be_visible()

    page.locator("button:has-text('Sign In')").first.click()

    page.wait_for_url(lambda u: "/dashboard" in u)
    expect(page.locator(".sidebar")).to_be_visible()
    expect(page.locator(".brand:has-text('AETHERDESK')")).to_be_visible()

    expect(page.locator("text=Operational Fleet Overview").first).to_be_visible()

    page.locator("text=Command Center").first.click()
    expect(page.locator("text=Command Center").first).to_be_visible()

    page.locator("text=Marketplace").first.click()
    expect(
        page.locator("h2:has-text('Community-Led Template Marketplace')")
    ).to_be_visible()


def test_pricing_section(page: Page):
    """
    Tests the pricing tiers are visible on the landing page.
    """
    page.goto("http://localhost:8000/")

    loc = page.locator("text=Flexible Rental Blocks").first
    loc.scroll_into_view_if_needed()

    expect(loc).to_be_visible()
    expect(page.locator(".glass-card:has-text('Startup')")).to_be_visible()
    expect(page.locator(".glass-card:has-text('Business')")).to_be_visible()
    expect(page.locator(".glass-card:has-text('Enterprise')").first).to_be_visible()

    business_btn = page.locator("button:has-text('Choose Business')").first
    expect(business_btn).to_have_class("btn-primary")
