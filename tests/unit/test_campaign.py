import pytest
from unittest.mock import AsyncMock, patch, MagicMock


class AsyncContextMock:
    """Mocks `async with db_context() as conn:` returning a fake conn."""

    def __init__(self):
        self.conn = MagicMock()

    def __call__(self, *a, **kw):
        self._cm = self
        return self

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, *exc):
        return False


def patch_db(return_map=None, side_effect_map=None):
    """Patch campaign._run_query with a fake that returns canned rows.

    return_map: dict mapping a substring of the SQL to the rows to return
                (used for fetch='all' / 'one').
    """
    async def fake_run_query(conn, query, params=(), fetch=None):
        if return_map:
            for needle, rows in return_map.items():
                if needle in query:
                    if fetch == "all":
                        return list(rows)
                    if fetch == "one":
                        return rows if isinstance(rows, dict) else (rows[0] if rows else None)
                    return None
        if fetch == "all":
            return []
        if fetch == "one":
            return None
        return None

    return patch("api.routers.campaign._run_query", new_callable=AsyncMock, side_effect=fake_run_query)


class TestCampaignLeads:
    """Tests for campaign lead CRUD endpoints."""

    @pytest.mark.asyncio
    async def test_list_leads_no_filter(self):
        from api.routers.campaign import list_leads

        mock_rows = [
            {"id": "LEAD-1", "tenant_id": "tenant-1", "company_name": "Acme", "phone": "+15551234567", "status": "new"},
            {"id": "LEAD-2", "tenant_id": "tenant-1", "company_name": "Globex", "phone": "+15559876543", "status": "interested"},
        ]

        with patch_db(return_map={"ORDER BY priority ASC, created_at DESC": mock_rows}), \
             patch("api.routers.campaign.db_context") as mock_db:
            mock_db.return_value = mock_db
            mock_db.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_db.__aexit__ = AsyncMock(return_value=False)

            result = await list_leads(tenant_id="tenant-1")
            assert len(result) == 2
            assert result[0]["company_name"] == "Acme"

    @pytest.mark.asyncio
    async def test_list_leads_with_status_filter(self):
        from api.routers.campaign import list_leads

        mock_rows = [
            {"id": "LEAD-1", "tenant_id": "tenant-1", "company_name": "Acme", "phone": "+15551234567", "status": "new"},
        ]

        with patch_db(return_map={"WHERE tenant_id = ? AND status = ?": mock_rows}), \
             patch("api.routers.campaign.db_context") as mock_db:
            mock_db.return_value = mock_db
            mock_db.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_db.__aexit__ = AsyncMock(return_value=False)

            result = await list_leads(status="new", tenant_id="tenant-1")
            assert len(result) == 1
            assert result[0]["status"] == "new"

    @pytest.mark.asyncio
    async def test_create_lead_success(self):
        from api.routers.campaign import create_lead, LeadCreate

        with patch_db(), \
             patch("api.routers.campaign.db_context") as mock_db:
            mock_db.return_value = mock_db
            mock_db.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_db.__aexit__ = AsyncMock(return_value=False)

            lead = LeadCreate(
                company_name="Acme Corp",
                contact_name="John Doe",
                phone="+15551234567",
                email="john@acme.com",
                industry="tech",
                notes="Interested in AI",
                priority=8
            )
            result = await create_lead(lead, tenant_id="tenant-1")
            assert "id" in result
            assert result["id"].startswith("LEAD-")
            assert result["status"] == "created"

    @pytest.mark.asyncio
    async def test_create_lead_invalid_phone(self):
        from api.routers.campaign import LeadCreate
        from pydantic import ValidationError

        with pytest.raises(ValidationError) as exc:
            LeadCreate(
                company_name="Acme Corp",
                phone="invalid-phone"
            )
        assert "Phone must be in E.164 format" in str(exc.value)

    @pytest.mark.asyncio
    async def test_bulk_import_leads(self):
        from api.routers.campaign import bulk_import_leads, LeadBulkImport, LeadCreate

        with patch_db(), \
             patch("api.routers.campaign.db_context") as mock_db:
            mock_db.return_value = mock_db
            mock_db.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_db.__aexit__ = AsyncMock(return_value=False)

            leads = [
                LeadCreate(company_name="Acme", phone="+15551111111"),
                LeadCreate(company_name="Globex", phone="+15552222222"),
                LeadCreate(company_name="Initech", phone="+15553333333"),
            ]
            data = LeadBulkImport(leads=leads)
            result = await bulk_import_leads(data, tenant_id="tenant-1")
            assert result["imported"] == 3
            assert len(result["ids"]) == 3

    @pytest.mark.asyncio
    async def test_bulk_import_respects_max_limit(self):
        from api.routers.campaign import LeadBulkImport, LeadCreate
        from pydantic import ValidationError

        with pytest.raises(ValidationError) as exc:
            leads = [LeadCreate(company_name=f"Co{i}", phone=f"+1555{i:07d}") for i in range(501)]
            LeadBulkImport(leads=leads)
        assert "at most 500 items" in str(exc.value)

    @pytest.mark.asyncio
    async def test_update_lead_status(self):
        from api.routers.campaign import update_lead

        with patch_db(return_map={"SELECT id FROM leads": {"id": "LEAD-1"}}), \
             patch("api.routers.campaign.db_context") as mock_db:
            mock_db.return_value = mock_db
            mock_db.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_db.__aexit__ = AsyncMock(return_value=False)

            result = await update_lead("LEAD-1", status="interested", tenant_id="tenant-1")
            assert result["updated"] == "LEAD-1"

    @pytest.mark.asyncio
    async def test_update_lead_not_found(self):
        from api.routers.campaign import update_lead
        from fastapi import HTTPException

        with patch_db(return_map={"SELECT id FROM leads": None}), \
             patch("api.routers.campaign.db_context") as mock_db:
            mock_db.return_value = mock_db
            mock_db.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_db.__aexit__ = AsyncMock(return_value=False)

            with pytest.raises(HTTPException) as exc:
                await update_lead("LEAD-999", status="interested", tenant_id="tenant-1")
            assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_update_lead_invalid_status(self):
        from api.routers.campaign import update_lead
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            await update_lead("LEAD-1", status="invalid_status", tenant_id="tenant-1")
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_update_lead_notes(self):
        from api.routers.campaign import update_lead

        with patch_db(return_map={"SELECT id FROM leads": {"id": "LEAD-1"}}), \
             patch("api.routers.campaign.db_context") as mock_db:
            mock_db.return_value = mock_db
            mock_db.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_db.__aexit__ = AsyncMock(return_value=False)

            result = await update_lead("LEAD-1", notes="New notes here", tenant_id="tenant-1")
            assert result["updated"] == "LEAD-1"

    @pytest.mark.asyncio
    async def test_update_lead_notes_truncated(self):
        from api.routers.campaign import update_lead

        with patch_db(return_map={"SELECT id FROM leads": {"id": "LEAD-1"}}), \
             patch("api.routers.campaign.db_context") as mock_db:
            mock_db.return_value = mock_db
            mock_db.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_db.__aexit__ = AsyncMock(return_value=False)

            long_notes = "x" * 2000
            result = await update_lead("LEAD-1", notes=long_notes, tenant_id="tenant-1")
            assert result["updated"] == "LEAD-1"


class TestCampaignCalls:
    """Tests for campaign calls tracking."""

    @pytest.mark.asyncio
    async def test_list_campaign_calls_no_filter(self):
        from api.routers.campaign import list_campaign_calls

        mock_rows = [
            {"id": "CC-1", "tenant_id": "tenant-1", "lead_id": "LEAD-1", "outcome": "interested", "company_name": "Acme"},
            {"id": "CC-2", "tenant_id": "tenant-1", "lead_id": "LEAD-2", "outcome": "voicemail", "company_name": "Globex"},
        ]

        with patch_db(return_map={"ORDER BY cc.started_at DESC": mock_rows}), \
             patch("api.routers.campaign.db_context") as mock_db:
            mock_db.return_value = mock_db
            mock_db.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_db.__aexit__ = AsyncMock(return_value=False)

            result = await list_campaign_calls(tenant_id="tenant-1")
            assert len(result) == 2

    @pytest.mark.asyncio
    async def test_list_campaign_calls_with_outcome_filter(self):
        from api.routers.campaign import list_campaign_calls

        mock_rows = [
            {"id": "CC-1", "tenant_id": "tenant-1", "lead_id": "LEAD-1", "outcome": "interested", "company_name": "Acme"},
        ]

        with patch_db(return_map={"AND cc.outcome =": mock_rows}), \
             patch("api.routers.campaign.db_context") as mock_db:
            mock_db.return_value = mock_db
            mock_db.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_db.__aexit__ = AsyncMock(return_value=False)

            result = await list_campaign_calls(outcome="interested", tenant_id="tenant-1")
            assert len(result) == 1
            assert result[0]["outcome"] == "interested"

    @pytest.mark.asyncio
    async def test_record_call_outcome_success(self):
        from api.routers.campaign import record_call_outcome

        with patch_db(return_map={"SELECT id, lead_id FROM campaign_calls": {"id": "CC-1", "lead_id": "LEAD-1"}}), \
             patch("api.routers.campaign.db_context") as mock_db:
            mock_db.return_value = mock_db
            mock_db.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_db.__aexit__ = AsyncMock(return_value=False)

            result = await record_call_outcome("CC-1", outcome="interested", cost_usd=0.02, tenant_id="tenant-1")
            assert result["recorded"] == "CC-1"

    @pytest.mark.asyncio
    async def test_record_call_outcome_not_found(self):
        from api.routers.campaign import record_call_outcome
        from fastapi import HTTPException

        with patch_db(return_map={"SELECT id, lead_id FROM campaign_calls": None}), \
             patch("api.routers.campaign.db_context") as mock_db:
            mock_db.return_value = mock_db
            mock_db.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_db.__aexit__ = AsyncMock(return_value=False)

            with pytest.raises(HTTPException) as exc:
                await record_call_outcome("CC-999", outcome="interested", tenant_id="tenant-1")
            assert exc.value.status_code == 404


class TestCampaignStats:
    """Tests for campaign stats endpoint."""

    @pytest.mark.asyncio
    async def test_campaign_stats_with_data(self):
        from api.routers.campaign import campaign_stats

        mock_row = {
            "total_leads": 100,
            "new_leads": 50,
            "total_calls": 30,
            "interested": 5,
            "needs_human": 2
        }

        with patch_db(return_map={"AS total_leads": mock_row}), \
             patch("api.routers.campaign.db_context") as mock_db:
            mock_db.return_value = mock_db
            mock_db.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_db.__aexit__ = AsyncMock(return_value=False)

            result = await campaign_stats(tenant_id="tenant-1")
            assert result["total_leads"] == 100
            assert result["untouched_leads"] == 50
            assert result["total_calls_made"] == 30
            assert result["interested"] == 5
            assert result["needs_human_follow_up"] == 2
            assert result["conversion_rate"] == "16.7%"

    @pytest.mark.asyncio
    async def test_campaign_stats_zero_calls(self):
        from api.routers.campaign import campaign_stats

        mock_row = {
            "total_leads": 100,
            "new_leads": 100,
            "total_calls": 0,
            "interested": 0,
            "needs_human": 0
        }

        with patch_db(return_map={"AS total_leads": mock_row}), \
             patch("api.routers.campaign.db_context") as mock_db:
            mock_db.return_value = mock_db
            mock_db.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_db.__aexit__ = AsyncMock(return_value=False)

            result = await campaign_stats(tenant_id="tenant-1")
            assert result["conversion_rate"] == "0%"

    @pytest.mark.asyncio
    async def test_campaign_stats_none_values(self):
        from api.routers.campaign import campaign_stats

        mock_row = {
            "total_leads": None,
            "new_leads": None,
            "total_calls": None,
            "interested": None,
            "needs_human": None
        }

        with patch_db(return_map={"AS total_leads": mock_row}), \
             patch("api.routers.campaign.db_context") as mock_db:
            mock_db.return_value = mock_db
            mock_db.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_db.__aexit__ = AsyncMock(return_value=False)

            result = await campaign_stats(tenant_id="tenant-1")
            assert result["total_leads"] == 0
            assert result["total_calls_made"] == 0


class TestCampaignCRUD:
    """Tests for budget-gated campaign CRUD."""

    @pytest.mark.asyncio
    async def test_create_campaign(self):
        from api.routers.campaign import create_campaign, CampaignCreate

        with patch_db(), \
             patch("api.routers.campaign.db_context") as mock_db:
            mock_db.return_value = mock_db
            mock_db.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_db.__aexit__ = AsyncMock(return_value=False)

            c = CampaignCreate(name="Community Outreach", budget_cents=50000)
            result = await create_campaign(c, tenant_id="tenant-1")
            assert result["id"].startswith("CAMP-")
            assert result["status"] == "created"

    @pytest.mark.asyncio
    async def test_get_campaign_not_found(self):
        from api.routers.campaign import get_campaign
        from fastapi import HTTPException

        with patch_db(return_map={"SELECT * FROM campaigns WHERE": None}), \
             patch("api.routers.campaign.db_context") as mock_db:
            mock_db.return_value = mock_db
            mock_db.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_db.__aexit__ = AsyncMock(return_value=False)

            with pytest.raises(HTTPException) as exc:
                await get_campaign("CAMP-1", tenant_id="tenant-1")
            assert exc.value.status_code == 404


class TestCampaignLaunch:
    """Tests for campaign launch endpoint."""

    @pytest.mark.asyncio
    async def test_launch_campaign_success(self):
        from api.routers.campaign import launch_campaign, CampaignLaunch

        mock_leads = [
            {"id": "LEAD-1", "phone": "+15551111111", "company_name": "Acme"},
            {"id": "LEAD-2", "phone": "+15552222222", "company_name": "Globex"},
        ]

        with patch_db(return_map={"ORDER BY priority ASC LIMIT 50": mock_leads}), \
             patch("api.routers.campaign._campaign_running", False), \
             patch("api.routers.campaign._campaign_lock", AsyncMock()), \
             patch("api.routers.campaign.asyncio.create_task") as mock_create_task, \
             patch("api.routers.campaign.db_context") as mock_db:
            mock_db.return_value = mock_db
            mock_db.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_db.__aexit__ = AsyncMock(return_value=False)

            config = CampaignLaunch(profile_id="PROF-META-SALES", max_concurrent=3, delay_between_calls=5.0, filter_status="new")
            result = await launch_campaign(config, tenant_id="tenant-1")

            assert result["status"] == "launched"
            assert result["leads_queued"] == 2
            assert result["profile"] == "PROF-META-SALES"
            assert result["max_concurrent"] == 3
            mock_create_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_launch_campaign_no_leads(self):
        from api.routers.campaign import launch_campaign, CampaignLaunch

        with patch_db(return_map={"ORDER BY priority ASC LIMIT 50": []}), \
             patch("api.routers.campaign._campaign_running", False), \
             patch("api.routers.campaign._campaign_lock", AsyncMock()), \
             patch("api.routers.campaign.db_context") as mock_db:
            mock_db.return_value = mock_db
            mock_db.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_db.__aexit__ = AsyncMock(return_value=False)

            config = CampaignLaunch(filter_status="new")
            result = await launch_campaign(config, tenant_id="tenant-1")

            assert result["status"] == "no_leads"
            assert "No leads match" in result["message"]

    @pytest.mark.asyncio
    async def test_launch_campaign_already_running(self):
        from api.routers.campaign import launch_campaign, CampaignLaunch
        from fastapi import HTTPException

        with patch("api.routers.campaign._campaign_running", True), \
             patch("api.routers.campaign._campaign_lock", AsyncMock()):

            config = CampaignLaunch(filter_status="new")
            with pytest.raises(HTTPException) as exc:
                await launch_campaign(config, tenant_id="tenant-1")
            assert exc.value.status_code == 409
            assert "already running" in exc.value.detail.lower()

    @pytest.mark.asyncio
    async def test_launch_campaign_with_budget_exhausted(self):
        from api.routers.campaign import launch_campaign, CampaignLaunch
        from fastapi import HTTPException

        campaign = {
            "id": "CAMP-1", "status": "active", "budget_cents": 1000, "spent_cents": 1000,
            "filter_status": "new", "profile_id": "PROF-1", "max_concurrent": 2, "delay_between_calls": 5.0,
        }
        with patch_db(return_map={"SELECT * FROM campaigns WHERE": campaign}), \
             patch("api.routers.campaign._campaign_running", False), \
             patch("api.routers.campaign._campaign_lock", AsyncMock()), \
             patch("api.routers.campaign.db_context") as mock_db:
            mock_db.return_value = mock_db
            mock_db.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_db.__aexit__ = AsyncMock(return_value=False)

            config = CampaignLaunch(campaign_id="CAMP-1")
            with pytest.raises(HTTPException) as exc:
                await launch_campaign(config, tenant_id="tenant-1")
            assert exc.value.status_code == 400
            assert "budget exhausted" in exc.value.detail.lower()


class TestPhoneValidation:
    """Tests for phone number validation."""

    @pytest.mark.asyncio
    async def test_valid_e164_phone(self):
        from api.routers.campaign import LeadCreate

        lead = LeadCreate(company_name="Test", phone="+15551234567")
        assert lead.phone == "+15551234567"

    @pytest.mark.asyncio
    async def test_valid_phone_without_plus(self):
        from api.routers.campaign import LeadCreate

        lead = LeadCreate(company_name="Test", phone="15551234567")
        assert lead.phone == "+15551234567"

    @pytest.mark.asyncio
    async def test_valid_phone_with_spaces_dashes(self):
        from api.routers.campaign import LeadCreate

        lead = LeadCreate(company_name="Test", phone="+1 (555) 123-4567")
        assert lead.phone == "+15551234567"

    @pytest.mark.asyncio
    async def test_invalid_phone_too_short(self):
        from api.routers.campaign import LeadCreate
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            LeadCreate(company_name="Test", phone="12345")

    @pytest.mark.asyncio
    async def test_invalid_phone_letters(self):
        from api.routers.campaign import LeadCreate
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            LeadCreate(company_name="Test", phone="+1555-ABC-DEFG")


class TestEscalationAlert:
    @pytest.mark.asyncio
    async def test_push_escalation_alert_high_severity(self):
        from api.routers.campaign import push_escalation_alert

        mock_mgr = MagicMock()
        mock_mgr.broadcast_to_queue = AsyncMock()
        with patch("api.routers.realtime.manager", mock_mgr):
            await push_escalation_alert("CC-123", "Customer requested manager", "Agent-1")
            mock_mgr.broadcast_to_queue.assert_called_once()
            args = mock_mgr.broadcast_to_queue.call_args
            assert args[0][0] == "default"
            alert = args[0][1]
            assert alert["type"] == "escalation_alert"
            assert alert["severity"] == "high"
            assert alert["call_sid"] == "CC-123"

    @pytest.mark.asyncio
    async def test_push_escalation_alert_medium_severity(self):
        from api.routers.campaign import push_escalation_alert

        mock_mgr = MagicMock()
        mock_mgr.broadcast_to_queue = AsyncMock()
        with patch("api.routers.realtime.manager", mock_mgr):
            await push_escalation_alert("CC-456", "Technical issue", "Agent-2")
            alert = mock_mgr.broadcast_to_queue.call_args[0][1]
            assert alert["severity"] == "medium"


class TestRunCampaign:
    @pytest.mark.asyncio
    async def test_run_campaign_all_calls_succeed(self):
        from api.routers.campaign import _run_campaign

        leads = [
            {"id": "LEAD-1", "phone": "+15551111111", "company_name": "Acme"},
            {"id": "LEAD-2", "phone": "+15552222222", "company_name": "Globex"},
        ]

        mock_response = MagicMock()
        mock_response.json.return_value = {"call_sid": "CA-123"}
        mock_http = AsyncMock()
        mock_http.post.return_value = mock_response
        mock_http.__aenter__.return_value = mock_http

        with patch("api.routers.campaign._run_query", new_callable=AsyncMock) as mock_run, \
             patch("api.routers.campaign._campaign_lock", AsyncMock()), \
             patch("api.routers.campaign._check_budget", AsyncMock(return_value=True)), \
             patch("api.routers.campaign.httpx.AsyncClient", return_value=mock_http), \
             patch("api.routers.campaign.db_context") as mock_db:
            mock_db.return_value = mock_db
            mock_db.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_db.__aexit__ = AsyncMock(return_value=False)

            await _run_campaign(leads, "PROF-TEST", 2, 2.0, "tenant-1", None)

            assert mock_http.post.call_count == 2
            ringing_updates = [c for c in mock_run.call_args_list if "UPDATE campaign_calls SET call_sid" in str(c.args[1])]
            assert len(ringing_updates) == 2

    @pytest.mark.asyncio
    async def test_run_campaign_call_fails(self):
        from api.routers.campaign import _run_campaign

        leads = [{"id": "LEAD-1", "phone": "+15551111111", "company_name": "Acme"}]

        mock_http = AsyncMock()
        mock_http.post.side_effect = Exception("Voice API unavailable")
        mock_http.__aenter__.return_value = mock_http

        with patch("api.routers.campaign._run_query", new_callable=AsyncMock) as mock_run, \
             patch("api.routers.campaign._campaign_lock", AsyncMock()), \
             patch("api.routers.campaign._check_budget", AsyncMock(return_value=True)), \
             patch("api.routers.campaign.httpx.AsyncClient", return_value=mock_http), \
             patch("api.routers.campaign.db_context") as mock_db:
            mock_db.return_value = mock_db
            mock_db.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_db.__aexit__ = AsyncMock(return_value=False)

            await _run_campaign(leads, "PROF-TEST", 1, 2.0, "tenant-1", None)

            failed_updates = [c for c in mock_run.call_args_list if "status = 'failed'" in str(c.args[1])]
            assert len(failed_updates) == 1

    @pytest.mark.asyncio
    async def test_run_campaign_respects_budget(self):
        from api.routers.campaign import _run_campaign

        leads = [{"id": "LEAD-1", "phone": "+15551111111", "company_name": "Acme"}]
        campaign = {"id": "CAMP-1", "budget_cents": 500}

        mock_http = AsyncMock()
        mock_http.post.return_value = MagicMock(json=lambda: {"call_sid": "CA-123"})
        mock_http.__aenter__.return_value = mock_http

        with patch("api.routers.campaign._run_query", new_callable=AsyncMock), \
             patch("api.routers.campaign._campaign_lock", AsyncMock()), \
             patch("api.routers.campaign._check_budget", AsyncMock(return_value=False)), \
             patch("api.routers.campaign.httpx.AsyncClient", return_value=mock_http), \
             patch("api.routers.campaign.db_context") as mock_db:
            mock_db.return_value = mock_db
            mock_db.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_db.__aexit__ = AsyncMock(return_value=False)

            await _run_campaign(leads, "PROF-TEST", 1, 2.0, "tenant-1", campaign)

            # Budget exhausted -> no HTTP dial should happen.
            mock_http.post.assert_not_called()
