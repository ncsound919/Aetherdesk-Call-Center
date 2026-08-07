"""Unit tests for api.services.self_service_portal."""

import pytest

import api.services.self_service_portal as ssp
from api.services.self_service_portal import SelfServicePortalService

SERVICE = ssp.SelfServicePortalService()


@pytest.fixture(autouse=True)
def _reset_globals():
    ssp._in_memory_complaints.clear()
    ssp._in_memory_callbacks.clear()
    ssp._in_memory_portal_data.clear()
    yield


@pytest.mark.asyncio
async def test_get_customer_portal_data_new_customer():
    data = await SERVICE.get_customer_portal_data("CUST-1")
    assert data["customer_id"] == "CUST-1"
    assert len(data["call_history"]) == 3
    assert len(data["invoices"]) == 3
    assert data["average_csat"] == 4.5
    assert data["preferences"]["timezone"] == "America/New_York"


@pytest.mark.asyncio
async def test_get_customer_portal_data_cached():
    cached = {"customer_id": "CUST-1", "call_history": [], "invoices": []}
    ssp._in_memory_portal_data["CUST-1"] = cached
    data = await SERVICE.get_customer_portal_data("CUST-1")
    assert data is cached


@pytest.mark.asyncio
async def test_preview_call_recording():
    data = await SERVICE.preview_call_recording("CL-ABC")
    assert data["call_id"] == "CL-ABC"
    assert data["recording_url"].endswith("CL-ABC.mp3")
    assert data["preview_url"].endswith("CL-ABC_preview.mp3")
    assert data["format"] == "mp3"
    assert data["transcript_available"] is True


@pytest.mark.asyncio
async def test_submit_complaint():
    complaint = await SERVICE.submit_complaint(
        "CUST-1", "Billing error", "Charged twice"
    )
    assert complaint["id"]
    assert complaint["customer_id"] == "CUST-1"
    assert complaint["subject"] == "Billing error"
    assert complaint["description"] == "Charged twice"
    assert complaint["status"] == "open"
    assert "created_at" in complaint
    assert len(ssp._in_memory_complaints) == 1


@pytest.mark.asyncio
async def test_schedule_call_back():
    callback = await SERVICE.schedule_call_back(
        "CUST-1", "2026-08-06T10:00:00Z", "Follow up on order"
    )
    assert callback["id"]
    assert callback["customer_id"] == "CUST-1"
    assert callback["preferred_time"] == "2026-08-06T10:00:00Z"
    assert callback["reason"] == "Follow up on order"
    assert callback["status"] == "scheduled"
    assert len(ssp._in_memory_callbacks) == 1


@pytest.mark.asyncio
async def test_get_billing_history():
    history = await SERVICE.get_billing_history("CUST-NEW")
    assert len(history) == 3
    assert history[0]["id"] == "INV-001"
    assert history[0]["amount"] == 149.00


@pytest.mark.asyncio
async def test_get_billing_history_cached_customer_no_invoices():
    ssp._in_memory_portal_data["CUST-1"] = {"customer_id": "CUST-1", "invoices": []}
    history = await SERVICE.get_billing_history("CUST-1")
    assert history == []


@pytest.mark.asyncio
async def test_update_preferences_filters_unknown_keys():
    result = await SERVICE.update_preferences(
        "CUST-1",
        {
            "communication_email": True,
            "communication_sms": False,
            "timezone": "UTC",
            "evil_key": "drop me",
            "marketing_emails": True,
        },
    )
    assert result["customer_id"] == "CUST-1"
    assert result["preferences"] == {
        "communication_email": True,
        "communication_sms": False,
        "timezone": "UTC",
        "marketing_emails": True,
    }
    assert "updated_at" in result


@pytest.mark.asyncio
async def test_update_preferences_empty():
    result = await SERVICE.update_preferences("CUST-1", {})
    assert result["preferences"] == {}


@pytest.mark.asyncio
async def test_update_preferences_all_allowed_keys():
    prefs = {
        "communication_email": True,
        "communication_sms": True,
        "communication_phone": False,
        "marketing_emails": False,
        "callback_preference": "business-hours",
        "timezone": "America/New_York",
    }
    result = await SERVICE.update_preferences("CUST-1", prefs)
    assert result["preferences"] == prefs
