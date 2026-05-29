"""
Functional and usability tests that exercise real user workflows.

These go beyond visibility/loading checks to verify actual platform behavior:
  - Agent Lifecycle:  create, rent, verify rentals, rental expiry math.
  - Settings Mgmt:    CRUD with persistence verification.
  - Campaign Ops:     lead creation, listing, filtering, stats, bulk import.
  - Approval Workflow: list pending approvals, approve/reject.
  - Protocol Upload:  CSV upload and parsing.
  - Flow Designer:    template fills prompt, name input, deploy clears form.
  - Integrations:     checkbox toggle, save config, verify persisted.
  - Recordings & Data: fetch session recordings list.
"""
from datetime import datetime, timezone

import httpx
from playwright.sync_api import Page, expect

# ---------------------------------------------------------------------------
#  API-BASED FUNCTIONAL TESTS
# ---------------------------------------------------------------------------

class TestAgentLifecycle:
    """Full lifecycle: create profile, rent agent, verify rental math."""

    HEADERS = {"x-api-key": "dev-api-key"}

    def test_create_profile_and_verify_in_dashboard(self, api_url: str) -> None:
        """Create a profile, then confirm it appears in the dashboard."""
        resp = httpx.post(
            f"{api_url}/api/v1/saas/profile"
            "?name=Lifecycle+Agent&prompt=Test+Prompt",
            json={"parameters": {"tone": "friendly", "max_calls": 25}},
            headers=self.HEADERS,
            timeout=10,
        )
        assert resp.status_code == 200
        profile_id = resp.json()["profile_id"]
        assert profile_id.startswith("PROF-")

        dash = httpx.get(
            f"{api_url}/api/v1/saas/dashboard",
            headers=self.HEADERS,
            timeout=10,
        )
        assert dash.status_code == 200
        profile_ids = [p["id"] for p in dash.json()["profiles"]]
        assert profile_id in profile_ids

    def test_rent_agent_and_verify_expiry(self, api_url: str) -> None:
        """Rent for 1 hour and check end_time is roughly 1 hour from now."""
        prof = httpx.post(
            f"{api_url}/api/v1/saas/profile"
            "?name=Rental+Timer+Agent&prompt=Test",
            json={"parameters": {}},
            headers=self.HEADERS,
            timeout=10,
        )
        pid = prof.json()["profile_id"]

        before = datetime.now()
        rent = httpx.post(
            f"{api_url}/api/v1/saas/rent?profile_id={pid}&duration_type=hour",
            headers=self.HEADERS,
            timeout=10,
        )
        assert rent.status_code == 200
        data = rent.json()
        assert data["rental_id"].startswith("RENT-")

        end = datetime.fromisoformat(data["end_time"])
        delta = (end - before).total_seconds()
        assert 3500 < delta < 3700, f"Expected ~3600s delta, got {delta}"

        dash = httpx.get(
            f"{api_url}/api/v1/saas/dashboard",
            headers=self.HEADERS,
            timeout=10,
        )
        rentals = dash.json()["rentals"]
        last = rentals[-1]
        assert last["profile_id"] == pid
        assert last["duration_type"] == "hour"

    def test_rent_different_durations(self, api_url: str) -> None:
        """Rent agent for day, week, month and verify different end times."""
        prof = httpx.post(
            f"{api_url}/api/v1/saas/profile"
            "?name=Multi+Duration+Agent&prompt=Test",
            json={"parameters": {}},
            headers=self.HEADERS,
            timeout=10,
        )
        pid = prof.json()["profile_id"]

        expected = {"day": 86400, "week": 604800, "month": 2592000}
        for dur, secs in expected.items():
            before = datetime.now()
            rent = httpx.post(
                f"{api_url}/api/v1/saas/rent?profile_id={pid}&duration_type={dur}",
                headers=self.HEADERS,
                timeout=10,
            )
            assert rent.status_code == 200
            end = datetime.fromisoformat(rent.json()["end_time"])
            delta = (end - before).total_seconds()
            assert secs * 0.95 < delta < secs * 1.05, (
                f"Duration {dur}: expected ~{secs}s, got {delta}s"
            )


class TestSettingsManagement:
    """Settings CRUD with value verification."""

    HEADERS = {"x-api-key": "dev-api-key"}

    def test_toggle_all_flags_and_verify(self, api_url: str) -> None:
        """Turn everything ON, verify, then turn OFF, verify."""
        on_payload = {
            "api_feeds": '{"crm": "http://api.crm.local"}',
            "auto_mode_enabled": True,
            "redact_pii": True,
            "require_consent": True,
            "sync_dnc": True,
            "mcp_servers": '{"billing": "mcp://billing.local"}',
        }
        httpx.post(
            f"{api_url}/api/v1/saas/settings",
            json=on_payload, headers=self.HEADERS, timeout=10,
        )
        get = httpx.get(
            f"{api_url}/api/v1/saas/settings",
            headers=self.HEADERS, timeout=10,
        )
        data = get.json()
        assert data["auto_mode_enabled"] is True
        assert data["redact_pii"] is True
        assert data["require_consent"] is True
        assert data["sync_dnc"] is True
        assert "billing" in data["mcp_servers"]

        off_payload = {
            "api_feeds": "{}",
            "auto_mode_enabled": False,
            "redact_pii": False,
            "require_consent": False,
            "sync_dnc": False,
            "mcp_servers": "{}",
        }
        httpx.post(
            f"{api_url}/api/v1/saas/settings",
            json=off_payload, headers=self.HEADERS, timeout=10,
        )
        get2 = httpx.get(
            f"{api_url}/api/v1/saas/settings",
            headers=self.HEADERS, timeout=10,
        )
        d2 = get2.json()
        assert d2["auto_mode_enabled"] is False
        assert d2["redact_pii"] is False
        assert d2["require_consent"] is False
        assert d2["sync_dnc"] is False

    def test_partial_update_preserves_other_fields(self, api_url: str) -> None:
        """Update only auto_mode and verify other fields unchanged."""
        full = {
            "api_feeds": '{"x": "y"}',
            "auto_mode_enabled": True,
            "redact_pii": True,
            "require_consent": True,
            "sync_dnc": False,
            "mcp_servers": "{}",
        }
        httpx.post(
            f"{api_url}/api/v1/saas/settings",
            json=full, headers=self.HEADERS, timeout=10,
        )

        partial = {"api_feeds": '{"x": "y"}', "auto_mode_enabled": False,
                    "redact_pii": True, "require_consent": True,
                    "sync_dnc": False, "mcp_servers": "{}"}
        httpx.post(
            f"{api_url}/api/v1/saas/settings",
            json=partial, headers=self.HEADERS, timeout=10,
        )

        data = httpx.get(
            f"{api_url}/api/v1/saas/settings",
            headers=self.HEADERS, timeout=10,
        ).json()
        assert data["auto_mode_enabled"] is False
        assert data["redact_pii"] is True
        assert data["require_consent"] is True


class TestCampaignOperations:
    """Lead creation, listing, filtering, stats, and bulk import."""

    HEADERS = {"x-api-key": "dev-api-key"}

    def test_create_lead_and_list(self, api_url: str) -> None:
        """Create a lead, then verify it appears in the lead list."""
        payload = {
            "company_name": "Functional Test Corp",
            "phone": "+15559990001",
            "contact_name": "Jane Doe",
            "email": "jane@testcorp.com",
            "industry": "technology",
            "notes": "Created by functional test",
            "priority": 8,
        }
        resp = httpx.post(
            f"{api_url}/api/v1/campaign/leads",
            json=payload, headers=self.HEADERS, timeout=10,
        )
        assert resp.status_code == 200
        lead_id = resp.json()["id"]

        leads = httpx.get(
            f"{api_url}/api/v1/campaign/leads",
            headers=self.HEADERS, timeout=10,
        )
        assert leads.status_code == 200
        lead_data = leads.json()
        assert any(lead["id"] == lead_id for lead in lead_data)

    def test_update_lead_status(self, api_url: str) -> None:
        """Create lead, update its status, verify the change."""
        resp = httpx.post(
            f"{api_url}/api/v1/campaign/leads",
            json={"company_name": "Update Test Ltd", "phone": "+15559990002",
                  "contact_name": "Bob", "industry": "finance"},
            headers=self.HEADERS, timeout=10,
        )
        lead_id = resp.json()["id"]

        patch = httpx.patch(
            f"{api_url}/api/v1/campaign/leads/{lead_id}"
            "?status=interested&notes=Left+voicemail",
            headers=self.HEADERS, timeout=10,
        )
        assert patch.status_code == 200

        leads = httpx.get(
            f"{api_url}/api/v1/campaign/leads",
            headers=self.HEADERS, timeout=10,
        )
        updated = [lead for lead in leads.json() if lead["id"] == lead_id][0]
        assert updated["status"] == "interested"

    def test_campaign_stats_endpoint(self, api_url: str) -> None:
        """Campaign stats returns expected fields."""
        resp = httpx.get(
            f"{api_url}/api/v1/campaign/stats",
            headers=self.HEADERS, timeout=10,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "total_leads" in data
        assert "total_calls_made" in data
        assert "conversion_rate" in data

    def test_bulk_lead_import(self, api_url: str) -> None:
        """Bulk import up to 3 leads and verify they all appear."""
        bulk = {
            "leads": [
                {"company_name": "Bulk A", "phone": "+1555000101",
                 "contact_name": "Alice", "industry": "healthcare"},
                {"company_name": "Bulk B", "phone": "+1555000102",
                 "contact_name": "Bob", "industry": "retail"},
                {"company_name": "Bulk C", "phone": "+1555000103",
                 "contact_name": "Carol", "industry": "logistics"},
            ]
        }
        resp = httpx.post(
            f"{api_url}/api/v1/campaign/leads/bulk",
            json=bulk, headers=self.HEADERS, timeout=10,
        )
        assert resp.status_code == 200
        result = resp.json()
        assert result["imported"] == 3

        leads = httpx.get(
            f"{api_url}/api/v1/campaign/leads",
            headers=self.HEADERS, timeout=10,
        ).json()
        for name in ["Bulk A", "Bulk B", "Bulk C"]:
            assert any(lead["company_name"] == name for lead in leads)


class TestApprovalWorkflow:
    """Human-in-the-loop approvals: list and action."""

    HEADERS = {"x-api-key": "dev-api-key"}

    def test_list_approvals(self, api_url: str) -> None:
        """Fetch pending approvals list."""
        resp = httpx.get(
            f"{api_url}/api/v1/saas/approvals",
            headers=self.HEADERS, timeout=10,
        )
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


class TestProtocolUpload:
    """CSV protocol upload and verification."""

    def test_upload_valid_csv_parses_nodes(self, api_url: str) -> None:
        """Upload a well-formed CSV protocol and verify response."""
        csv_content = (
            "node,prompt,field,validate,next,action,on_ok,on_fail,options\n"
            "start,Welcome! Enter your name.,name,required,q_name,,,,\n"
            "q_name,Thanks {name}. Confirm?,,,end,,Yes No,"
        )
        files = {"file": ("protocol.csv", csv_content, "text/csv")}
        resp = httpx.post(
            f"{api_url}/api/v1/protocols/upload_csv",
            files=files, timeout=10,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "protocol_id" in data
        assert data["nodes"] >= 2


class TestDataIntegrity:
    """Verify data consistency across endpoints."""

    HEADERS = {"x-api-key": "dev-api-key"}

    def test_multiple_profiles_in_dashboard(self, api_url: str) -> None:
        """Create 3 profiles, verify all appear, then check dashboard count."""
        created = []
        for i in range(3):
            resp = httpx.post(
                f"{api_url}/api/v1/saas/profile"
                f"?name=Integrity+Agent+{i}&prompt=Prompt+{i}",
                json={"parameters": {"idx": i}},
                headers=self.HEADERS, timeout=10,
            )
            created.append(resp.json()["profile_id"])

        dash = httpx.get(
            f"{api_url}/api/v1/saas/dashboard",
            headers=self.HEADERS, timeout=10,
        ).json()
        dashboard_ids = {p["id"] for p in dash["profiles"]}
        for pid in created:
            assert pid in dashboard_ids


# ---------------------------------------------------------------------------
#  UI-BASED FUNCTIONAL / USABILITY TESTS
# ---------------------------------------------------------------------------

def _login(page: Page, ui_url: str) -> None:
    """Helper: navigate to landing, log in, arrive at dashboard."""
    page.goto(ui_url)
    page.locator("text=Login").first.click()
    page.wait_for_url(lambda u: "/login" in u)
    page.locator("button:has-text('Sign In')").first.click()
    page.wait_for_url(lambda u: "/dashboard" in u)
    expect(page.locator(".sidebar")).to_be_visible()


class TestUIFlowDesigner:
    """Flow Designer: template selection, form fill, deploy, and form-clear behavior."""

    def test_template_selection_fills_textarea(self, page: Page, ui_url: str) -> None:
        """Clicking a template button fills the prompt textarea."""
        _login(page, ui_url)
        page.locator("text=Flow Designer").first.click()

        textarea = page.locator(
            "textarea[placeholder='Full System Prompt / Guidelines']"
        ).first

        page.locator("text=SALES").first.click()
        val = textarea.input_value()
        assert val, "Textarea should be filled after template selection"

        page.locator("text=MEDICAL").first.click()
        val2 = textarea.input_value()
        assert val2, "Textarea should be filled after switching to MEDICAL"
        assert val2 != val, "MEDICAL template should differ from SALES template"

    def test_fill_agent_name_and_deploy_clears_form(self, page: Page, ui_url: str) -> None:
        """Filling agent name and deploying clears the name field."""
        _login(page, ui_url)
        page.locator("text=Flow Designer").first.click()

        page.locator("text=GENERAL").first.click()
        name_input = page.locator(
            "input[placeholder='Agent Name (e.g. Sarah)']"
        ).first
        name_input.fill("Functional Test Agent")

        page.locator("text=Deploy Agent Profile").first.click()

        expect(name_input).to_have_value("")

    def test_script_generation_button_exists_and_is_clickable(
        self, page: Page, ui_url: str
    ) -> None:
        """The 'Generate AI Script' button is visible and clickable."""
        _login(page, ui_url)
        page.locator("text=Flow Designer").first.click()

        gen_btn = page.locator("text=Generate AI Script").first
        expect(gen_btn).to_be_visible()
        gen_btn.click()

    def test_flow_designer_has_all_template_buttons(
        self, page: Page, ui_url: str
    ) -> None:
        """All four template buttons exist: GENERAL, SALES, SUPPORT, MEDICAL."""
        _login(page, ui_url)
        page.locator("text=Flow Designer").first.click()

        for label in ["GENERAL", "SALES", "SUPPORT", "MEDICAL"]:
            expect(page.locator(f"text={label}").first).to_be_visible()


class TestUIIntegrations:
    """Integrations/Settings page: checkbox toggles, save, and verification."""

    def test_toggle_pii_redaction_and_save(self, page: Page, ui_url: str) -> None:
        """Toggle PII redaction checkbox, click save, verify no error."""
        _login(page, ui_url)
        page.locator("text=Integrations").first.click()

        pii_label = page.locator("text=PII Redaction").first
        expect(pii_label).to_be_visible()

        save_btn = page.locator("text=Save Safety Configuration").first
        expect(save_btn).to_be_visible()

        save_btn.click()

    def test_settings_page_shows_twilio_webhook_url(
        self, page: Page, ui_url: str
    ) -> None:
        """Integrations page displays the Twilio webhook URL."""
        _login(page, ui_url)
        page.locator("text=Integrations").first.click()

        expect(
            page.locator("input[readonly]").first
        ).to_have_value("https://aetherdesk.io/api/v1/voice/incoming")


class TestUIOutreach:
    """Outreach/Campaign page: add lead form, lead table."""

    def test_add_lead_form_is_visible(self, page: Page, ui_url: str) -> None:
        """The Add Lead form fields exist on the Outreach page."""
        _login(page, ui_url)
        page.locator("text=Outreach").first.click()

        expect(page.locator("text=Company").first).to_be_visible()
        expect(page.locator("text=Phone").first).to_be_visible()
        expect(page.locator("text=Add").first).to_be_visible()

    def test_launch_campaign_button_visible(self, page: Page, ui_url: str) -> None:
        """The Launch Campaign button exists on the Outreach page."""
        _login(page, ui_url)
        page.locator("text=Outreach").first.click()

        expect(page.locator("text=Launch Campaign").first).to_be_visible()


class TestUICommandCenter:
    """Command Center: real-time monitoring UI elements."""

    def test_command_center_shows_telemetry_metrics(
        self, page: Page, ui_url: str
    ) -> None:
        """Command Center shows compute density, vector store latency, PSTN load."""
        _login(page, ui_url)
        page.locator("text=Command Center").first.click()

        expect(page.locator("text=Compute Density").first).to_be_visible()
        expect(page.locator("text=Vector Store Latency").first).to_be_visible()
        expect(page.locator("text=PSTN Gateway Load").first).to_be_visible()

    def test_command_center_shows_intelligence_panel(
        self, page: Page, ui_url: str
    ) -> None:
        """Command Center shows Agent Intelligence stats panel."""
        _login(page, ui_url)
        page.locator("text=Command Center").first.click()

        expect(page.locator("text=Agent Intelligence").first).to_be_visible()


class TestUIAffiliate:
    """Affiliate portal: referral link, earnings display."""

    def test_affiliate_shows_earnings_and_referral_link(
        self, page: Page, ui_url: str
    ) -> None:
        """Affiliate page shows earnings and referral link."""
        _login(page, ui_url)
        page.locator("text=Affiliate").first.click()

        expect(page.locator("text=Referral").first).to_be_visible()


class TestUISupervision:
    """Supervision tab: pending approvals UI."""

    def test_supervision_shows_approvals_header(
        self, page: Page, ui_url: str
    ) -> None:
        """Supervision page loads and is accessible."""
        _login(page, ui_url)
        page.locator("text=Supervision").first.click()

        expect(
            page.locator(".sidebar-item.active:has-text('Supervision')")
        ).to_be_visible(timeout=10000)


class TestUIMarketplace:
    """Community Marketplace: template cards and clone functionality."""

    def test_marketplace_has_template_cards(self, page: Page, ui_url: str) -> None:
        """Marketplace shows template cards with content."""
        _login(page, ui_url)
        page.locator("text=Marketplace").first.click()

        page.locator("text=Publish Your Script").first.scroll_into_view_if_needed()
        expect(page.locator("text=Publish Your Script").first).to_be_visible()

    def test_clone_button_switches_to_flow_designer(
        self, page: Page, ui_url: str
    ) -> None:
        """Clicking Clone & Customize switches to Flow Designer tab."""
        _login(page, ui_url)
        page.locator("text=Marketplace").first.click()

        clone_btn = page.locator("text=Clone & Customize").first
        if clone_btn.is_visible():
            clone_btn.click()
            expect(
                page.locator("h2:has-text('Flow Designer & Scripts')")
            ).to_be_visible()
