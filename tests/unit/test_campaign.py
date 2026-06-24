import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, UTC


class TestCampaignLeads:
    """Tests for campaign lead CRUD endpoints."""

    @pytest.mark.asyncio
    async def test_list_leads_no_filter(self):
        from apps.api.routers.campaign import list_leads

        mock_rows = [
            {"id": "LEAD-1", "tenant_id": "tenant-1", "company_name": "Acme", "phone": "+15551234567", "status": "new"},
            {"id": "LEAD-2", "tenant_id": "tenant-1", "company_name": "Globex", "phone": "+15559876543", "status": "interested"},
        ]

        with patch("apps.api.routers.campaign.db_context_sync") as mock_db:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_cursor.fetchall.return_value = mock_rows
            mock_conn.cursor.return_value = mock_cursor
            mock_db.return_value.__enter__.return_value = mock_conn

            result = await list_leads(tenant_id="tenant-1")
            assert len(result) == 2
            assert result[0]["company_name"] == "Acme"
            mock_cursor.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_leads_with_status_filter(self):
        from apps.api.routers.campaign import list_leads

        mock_rows = [
            {"id": "LEAD-1", "tenant_id": "tenant-1", "company_name": "Acme", "phone": "+15551234567", "status": "new"},
        ]

        with patch("apps.api.routers.campaign.db_context_sync") as mock_db:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_cursor.fetchall.return_value = mock_rows
            mock_conn.cursor.return_value = mock_cursor
            mock_db.return_value.__enter__.return_value = mock_conn

            result = await list_leads(status="new", tenant_id="tenant-1")
            assert len(result) == 1
            assert result[0]["status"] == "new"
            mock_cursor.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_lead_success(self):
        from apps.api.routers.campaign import create_lead, LeadCreate

        with patch("apps.api.routers.campaign.db_context_sync") as mock_db:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.cursor.return_value = mock_cursor
            mock_db.return_value.__enter__.return_value = mock_conn

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
            mock_cursor.execute.assert_called_once()
            mock_conn.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_lead_invalid_phone(self):
        from apps.api.routers.campaign import LeadCreate
        from pydantic import ValidationError

        with pytest.raises(ValidationError) as exc:
            LeadCreate(
                company_name="Acme Corp",
                phone="invalid-phone"
            )
        assert "Phone must be in E.164 format" in str(exc.value)

    @pytest.mark.asyncio
    async def test_bulk_import_leads(self):
        from apps.api.routers.campaign import bulk_import_leads, LeadBulkImport, LeadCreate

        with patch("apps.api.routers.campaign.db_context_sync") as mock_db:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.cursor.return_value = mock_cursor
            mock_db.return_value.__enter__.return_value = mock_conn

            leads = [
                LeadCreate(company_name="Acme", phone="+15551111111"),
                LeadCreate(company_name="Globex", phone="+15552222222"),
                LeadCreate(company_name="Initech", phone="+15553333333"),
            ]
            data = LeadBulkImport(leads=leads)
            result = await bulk_import_leads(data, tenant_id="tenant-1")
            assert result["imported"] == 3
            assert len(result["ids"]) == 3
            assert mock_cursor.execute.call_count == 3
            mock_conn.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_bulk_import_respects_max_limit(self):
        from apps.api.routers.campaign import LeadBulkImport, LeadCreate
        from pydantic import ValidationError

        with pytest.raises(ValidationError) as exc:
            leads = [LeadCreate(company_name=f"Co{i}", phone=f"+1555{i:07d}") for i in range(501)]
            LeadBulkImport(leads=leads)
        assert "at most 500 items" in str(exc.value)

    @pytest.mark.asyncio
    async def test_update_lead_status(self):
        from apps.api.routers.campaign import update_lead

        with patch("apps.api.routers.campaign.db_context_sync") as mock_db:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_cursor.fetchone.return_value = {"id": "LEAD-1"}
            mock_conn.cursor.return_value = mock_cursor
            mock_db.return_value.__enter__.return_value = mock_conn

            result = await update_lead("LEAD-1", status="interested", tenant_id="tenant-1")
            assert result["updated"] == "LEAD-1"
            mock_cursor.execute.assert_any_call("SELECT id FROM leads WHERE id = ? AND tenant_id = ?", ("LEAD-1", "tenant-1"))
            mock_cursor.execute.assert_any_call("UPDATE leads SET status = ? WHERE id = ? AND tenant_id = ?", ("interested", "LEAD-1", "tenant-1"))
            mock_conn.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_lead_not_found(self):
        from apps.api.routers.campaign import update_lead
        from fastapi import HTTPException

        with patch("apps.api.routers.campaign.db_context_sync") as mock_db:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_cursor.fetchone.return_value = None
            mock_conn.cursor.return_value = mock_cursor
            mock_db.return_value.__enter__.return_value = mock_conn

            with pytest.raises(HTTPException) as exc:
                await update_lead("LEAD-999", status="interested", tenant_id="tenant-1")
            assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_update_lead_invalid_status(self):
        from apps.api.routers.campaign import update_lead
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            await update_lead("LEAD-1", status="invalid_status", tenant_id="tenant-1")
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_update_lead_notes(self):
        from apps.api.routers.campaign import update_lead

        with patch("apps.api.routers.campaign.db_context_sync") as mock_db:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_cursor.fetchone.return_value = {"id": "LEAD-1"}
            mock_conn.cursor.return_value = mock_cursor
            mock_db.return_value.__enter__.return_value = mock_conn

            result = await update_lead("LEAD-1", notes="New notes here", tenant_id="tenant-1")
            assert result["updated"] == "LEAD-1"
            mock_cursor.execute.assert_any_call("UPDATE leads SET notes = ? WHERE id = ? AND tenant_id = ?", ("New notes here", "LEAD-1", "tenant-1"))

    @pytest.mark.asyncio
    async def test_update_lead_notes_truncated(self):
        from apps.api.routers.campaign import update_lead

        with patch("apps.api.routers.campaign.db_context_sync") as mock_db:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_cursor.fetchone.return_value = {"id": "LEAD-1"}
            mock_conn.cursor.return_value = mock_cursor
            mock_db.return_value.__enter__.return_value = mock_conn

            long_notes = "x" * 2000
            result = await update_lead("LEAD-1", notes=long_notes, tenant_id="tenant-1")
            assert result["updated"] == "LEAD-1"
            # Verify notes was truncated to 1000 chars
            update_call = [c for c in mock_cursor.execute.call_args_list if c[0][0].startswith("UPDATE leads SET notes")][0]
            assert len(update_call[0][1][0]) == 1000


class TestCampaignCalls:
    """Tests for campaign calls tracking."""

    @pytest.mark.asyncio
    async def test_list_campaign_calls_no_filter(self):
        from apps.api.routers.campaign import list_campaign_calls

        mock_rows = [
            {"id": "CC-1", "tenant_id": "tenant-1", "lead_id": "LEAD-1", "outcome": "interested", "company_name": "Acme"},
            {"id": "CC-2", "tenant_id": "tenant-1", "lead_id": "LEAD-2", "outcome": "voicemail", "company_name": "Globex"},
        ]

        with patch("apps.api.routers.campaign.db_context_sync") as mock_db:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_cursor.fetchall.return_value = mock_rows
            mock_conn.cursor.return_value = mock_cursor
            mock_db.return_value.__enter__.return_value = mock_conn

            result = await list_campaign_calls(tenant_id="tenant-1")
            assert len(result) == 2
            mock_cursor.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_campaign_calls_with_outcome_filter(self):
        from apps.api.routers.campaign import list_campaign_calls

        mock_rows = [
            {"id": "CC-1", "tenant_id": "tenant-1", "lead_id": "LEAD-1", "outcome": "interested", "company_name": "Acme"},
        ]

        with patch("apps.api.routers.campaign.db_context_sync") as mock_db:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_cursor.fetchall.return_value = mock_rows
            mock_conn.cursor.return_value = mock_cursor
            mock_db.return_value.__enter__.return_value = mock_conn

            result = await list_campaign_calls(outcome="interested", tenant_id="tenant-1")
            assert len(result) == 1
            assert result[0]["outcome"] == "interested"


class TestCampaignStats:
    """Tests for campaign stats endpoint."""

    @pytest.mark.asyncio
    async def test_campaign_stats_with_data(self):
        from apps.api.routers.campaign import campaign_stats

        mock_row = {
            "total_leads": 100,
            "new_leads": 50,
            "total_calls": 30,
            "interested": 5,
            "needs_human": 2
        }

        with patch("apps.api.routers.campaign.db_context_sync") as mock_db:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_cursor.fetchone.return_value = mock_row
            mock_conn.cursor.return_value = mock_cursor
            mock_db.return_value.__enter__.return_value = mock_conn

            result = await campaign_stats(tenant_id="tenant-1")
            assert result["total_leads"] == 100
            assert result["untouched_leads"] == 50
            assert result["total_calls_made"] == 30
            assert result["interested"] == 5
            assert result["needs_human_follow_up"] == 2
            assert result["conversion_rate"] == "16.7%"

    @pytest.mark.asyncio
    async def test_campaign_stats_zero_calls(self):
        from apps.api.routers.campaign import campaign_stats

        mock_row = {
            "total_leads": 100,
            "new_leads": 100,
            "total_calls": 0,
            "interested": 0,
            "needs_human": 0
        }

        with patch("apps.api.routers.campaign.db_context_sync") as mock_db:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_cursor.fetchone.return_value = mock_row
            mock_conn.cursor.return_value = mock_cursor
            mock_db.return_value.__enter__.return_value = mock_conn

            result = await campaign_stats(tenant_id="tenant-1")
            assert result["conversion_rate"] == "0%"

    @pytest.mark.asyncio
    async def test_campaign_stats_none_values(self):
        from apps.api.routers.campaign import campaign_stats

        mock_row = {
            "total_leads": None,
            "new_leads": None,
            "total_calls": None,
            "interested": None,
            "needs_human": None
        }

        with patch("apps.api.routers.campaign.db_context_sync") as mock_db:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_cursor.fetchone.return_value = mock_row
            mock_conn.cursor.return_value = mock_cursor
            mock_db.return_value.__enter__.return_value = mock_conn

            result = await campaign_stats(tenant_id="tenant-1")
            assert result["total_leads"] == 0
            assert result["total_calls_made"] == 0


class TestCampaignLaunch:
    """Tests for campaign launch endpoint."""

    @pytest.mark.asyncio
    async def test_launch_campaign_success(self):
        from apps.api.routers.campaign import launch_campaign, CampaignLaunch

        mock_leads = [
            {"id": "LEAD-1", "phone": "+15551111111", "company_name": "Acme"},
            {"id": "LEAD-2", "phone": "+15552222222", "company_name": "Globex"},
        ]

        with patch("apps.api.routers.campaign.db_context_sync") as mock_db, \
             patch("apps.api.routers.campaign._campaign_running", False), \
             patch("apps.api.routers.campaign._campaign_lock", AsyncMock()), \
             patch("apps.api.routers.campaign.asyncio.create_task") as mock_create_task:

            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_cursor.fetchall.return_value = mock_leads
            mock_conn.cursor.return_value = mock_cursor
            mock_db.return_value.__enter__.return_value = mock_conn

            config = CampaignLaunch(profile_id="PROF-META-SALES", max_concurrent=3, delay_between_calls=5.0, filter_status="new")
            result = await launch_campaign(config, tenant_id="tenant-1")

            assert result["status"] == "launched"
            assert result["leads_queued"] == 2
            assert result["profile"] == "PROF-META-SALES"
            assert result["max_concurrent"] == 3
            mock_create_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_launch_campaign_no_leads(self):
        from apps.api.routers.campaign import launch_campaign, CampaignLaunch

        with patch("apps.api.routers.campaign.db_context_sync") as mock_db, \
             patch("apps.api.routers.campaign._campaign_running", False), \
             patch("apps.api.routers.campaign._campaign_lock", AsyncMock()):

            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_cursor.fetchall.return_value = []
            mock_conn.cursor.return_value = mock_cursor
            mock_db.return_value.__enter__.return_value = mock_conn

            config = CampaignLaunch(filter_status="new")
            result = await launch_campaign(config, tenant_id="tenant-1")

            assert result["status"] == "no_leads"
            assert "No leads match" in result["message"]

    @pytest.mark.asyncio
    async def test_launch_campaign_already_running(self):
        from apps.api.routers.campaign import launch_campaign, CampaignLaunch
        from fastapi import HTTPException

        with patch("apps.api.routers.campaign._campaign_running", True), \
             patch("apps.api.routers.campaign._campaign_lock", AsyncMock()):

            config = CampaignLaunch(filter_status="new")
            with pytest.raises(HTTPException) as exc:
                await launch_campaign(config, tenant_id="tenant-1")
            assert exc.value.status_code == 409
            assert "already running" in exc.value.detail.lower()


class TestPhoneValidation:
    """Tests for phone number validation."""

    @pytest.mark.asyncio
    async def test_valid_e164_phone(self):
        from apps.api.routers.campaign import LeadCreate

        lead = LeadCreate(company_name="Test", phone="+15551234567")
        assert lead.phone == "+15551234567"

    @pytest.mark.asyncio
    async def test_valid_phone_without_plus(self):
        from apps.api.routers.campaign import LeadCreate

        lead = LeadCreate(company_name="Test", phone="15551234567")
        assert lead.phone == "+15551234567"

    @pytest.mark.asyncio
    async def test_valid_phone_with_spaces_dashes(self):
        from apps.api.routers.campaign import LeadCreate

        lead = LeadCreate(company_name="Test", phone="+1 (555) 123-4567")
        assert lead.phone == "+15551234567"

    @pytest.mark.asyncio
    async def test_invalid_phone_too_short(self):
        from apps.api.routers.campaign import LeadCreate
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            LeadCreate(company_name="Test", phone="+123")

    @pytest.mark.asyncio
    async def test_invalid_phone_letters(self):
        from apps.api.routers.campaign import LeadCreate
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            LeadCreate(company_name="Test", phone="+1555-ABC-DEFG")


class TestEscalationAlert:
    @pytest.mark.asyncio
    async def test_push_escalation_alert_high_severity(self):
        from apps.api.routers.campaign import push_escalation_alert

        mock_mgr = MagicMock()
        mock_mgr.broadcast_to_queue = AsyncMock()
        with patch("apps.api.routers.realtime.manager", mock_mgr):
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
        from apps.api.routers.campaign import push_escalation_alert

        mock_mgr = MagicMock()
        mock_mgr.broadcast_to_queue = AsyncMock()
        with patch("apps.api.routers.realtime.manager", mock_mgr):
            await push_escalation_alert("CC-456", "Technical issue", "Agent-2")
            alert = mock_mgr.broadcast_to_queue.call_args[0][1]
            assert alert["severity"] == "medium"


class TestRunCampaign:
    @pytest.mark.asyncio
    async def test_run_campaign_all_calls_succeed(self):
        from apps.api.routers.campaign import _run_campaign, CampaignLaunch

        leads = [
            {"id": "LEAD-1", "phone": "+15551111111", "company_name": "Acme"},
            {"id": "LEAD-2", "phone": "+15552222222", "company_name": "Globex"},
        ]
        config = CampaignLaunch(profile_id="PROF-TEST", delay_between_calls=2.0)

        mock_response = MagicMock()
        mock_response.json.return_value = {"call_sid": "CA-123"}
        mock_http = AsyncMock()
        mock_http.post.return_value = mock_response
        mock_http.__aenter__.return_value = mock_http

        with patch("apps.api.routers.campaign.db_context_sync") as mock_db, \
             patch("apps.api.routers.campaign._campaign_lock", AsyncMock()), \
             patch("apps.api.routers.campaign.httpx.AsyncClient", return_value=mock_http):
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.cursor.return_value = mock_cursor
            mock_db.return_value.__enter__.return_value = mock_conn

            await _run_campaign(leads, config, "tenant-1")

            assert mock_http.post.call_count == 2
            update_queries = [c[0][0] for c in mock_cursor.execute.call_args_list]
            ringing_updates = [q for q in update_queries if "status = 'ringing'" in q]
            assert len(ringing_updates) == 2

    @pytest.mark.asyncio
    async def test_run_campaign_call_fails(self):
        from apps.api.routers.campaign import _run_campaign, CampaignLaunch

        leads = [{"id": "LEAD-1", "phone": "+15551111111", "company_name": "Acme"}]
        config = CampaignLaunch(profile_id="PROF-TEST", delay_between_calls=2.0)

        mock_http = AsyncMock()
        mock_http.post.side_effect = Exception("Voice API unavailable")
        mock_http.__aenter__.return_value = mock_http

        with patch("apps.api.routers.campaign.db_context_sync") as mock_db, \
             patch("apps.api.routers.campaign._campaign_lock", AsyncMock()), \
             patch("apps.api.routers.campaign.httpx.AsyncClient", return_value=mock_http):
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.cursor.return_value = mock_cursor
            mock_db.return_value.__enter__.return_value = mock_conn

            await _run_campaign(leads, config, "tenant-1")

            update_queries = [c[0][0] for c in mock_cursor.execute.call_args_list]
            assert any("status = 'failed'" in q for q in update_queries)
            assert any("status = 'new'" in q for q in update_queries)