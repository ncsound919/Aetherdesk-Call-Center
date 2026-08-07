"""Unit tests for api.services.sms."""

from unittest.mock import AsyncMock, patch

import pytest

from api.services.sms import SMSService, sms_service


@pytest.mark.asyncio
async def test_send_sms_returns_stub_success():
    result = await sms_service.send_sms("+15551234567", "Hello world")
    assert result["success"] is True
    assert result["to"] == "+15551234567"
    assert result["status"] == "sent"
    assert result["sid"].startswith("SM")
    assert len(result["sid"]) == 26
    assert result["body"] == "Hello world"


@pytest.mark.asyncio
async def test_send_sms_body_truncated_to_50_chars():
    result = await sms_service.send_sms("+15551234567", "x" * 100)
    assert len(result["body"]) == 50


@pytest.mark.asyncio
async def test_send_sms_unique_sids():
    r1 = await sms_service.send_sms("+1", "a")
    r2 = await sms_service.send_sms("+1", "a")
    assert r1["sid"] != r2["sid"]


@pytest.mark.asyncio
async def test_send_bulk_sms_multiple_recipients():
    result = await sms_service.send_bulk_sms(["+1", "+2", "+3"], "hi")
    assert result["success"] is True
    assert result["total"] == 3
    assert len(result["results"]) == 3
    for r in result["results"]:
        assert r["success"] is True
        assert r["status"] == "sent"
        assert r["sid"].startswith("SM")


@pytest.mark.asyncio
async def test_send_bulk_sms_empty_recipients():
    result = await sms_service.send_bulk_sms([], "hi")
    assert result["success"] is True
    assert result["total"] == 0
    assert result["results"] == []


@pytest.mark.asyncio
async def test_process_inbound_sms():
    result = await sms_service.process_inbound_sms("+1555", "URGENT", session_id="s1")
    assert result == {
        "success": True,
        "from": "+1555",
        "body": "URGENT",
        "session_id": "s1",
        "processed": True,
    }


@pytest.mark.asyncio
async def test_process_inbound_sms_default_session():
    result = await sms_service.process_inbound_sms("+1555", "hi")
    assert result["session_id"] is None


@pytest.mark.asyncio
async def test_get_sms_templates():
    with patch(
        "api.services.db_omnichannel.list_sms_templates_db", new_callable=AsyncMock
    ) as m:
        m.return_value = [{"id": 1, "name": "welcome"}]
        result = await sms_service.get_sms_templates("T1")
    assert result == [{"id": 1, "name": "welcome"}]
    m.assert_awaited_once_with("T1")


@pytest.mark.asyncio
async def test_create_sms_template():
    with patch(
        "api.services.db_omnichannel.create_sms_template_db", new_callable=AsyncMock
    ) as m:
        m.return_value = {"id": 2, "name": "n", "body": "b"}
        result = await sms_service.create_sms_template("T1", "n", "b")
    assert result == {"id": 2, "name": "n", "body": "b"}
    m.assert_awaited_once_with("T1", "n", "b")


@pytest.mark.asyncio
async def test_get_sms_log():
    with patch(
        "api.services.db_omnichannel.list_sms_log_db", new_callable=AsyncMock
    ) as m:
        m.return_value = [{"sid": "SM123"}]
        result = await sms_service.get_sms_log("T1", limit=25, offset=5)
    assert result == [{"sid": "SM123"}]
    m.assert_awaited_once_with("T1", limit=25, offset=5)


@pytest.mark.asyncio
async def test_get_sms_log_defaults():
    with patch(
        "api.services.db_omnichannel.list_sms_log_db", new_callable=AsyncMock
    ) as m:
        await sms_service.get_sms_log("T1")
    m.assert_awaited_once_with("T1", limit=100, offset=0)


@pytest.mark.asyncio
async def test_template_db_error_propagates():
    with patch(
        "api.services.db_omnichannel.list_sms_templates_db", new_callable=AsyncMock
    ) as m:
        m.side_effect = RuntimeError("db down")
        with pytest.raises(RuntimeError):
            await sms_service.get_sms_templates("T1")
