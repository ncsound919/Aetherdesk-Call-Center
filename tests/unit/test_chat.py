"""Unit tests for api.services.chat.ChatService."""

from unittest.mock import AsyncMock, patch

import pytest

import api.services.chat as chat_module
from api.services.chat import chat_service


@pytest.fixture(autouse=True)
def clean_sessions():
    chat_module._in_memory_sessions.clear()
    yield
    chat_module._in_memory_sessions.clear()


@pytest.mark.asyncio
class TestChatService:
    async def test_create_session_success_with_initial_message(self):
        session = {"id": "s1", "tenant_id": "t1"}
        with patch(
            "api.services.db_omnichannel.create_chat_session_db",
            new_callable=AsyncMock,
            return_value=session,
        ) as mock_create, patch(
            "api.services.db_omnichannel.add_chat_message_db",
            new_callable=AsyncMock,
        ) as mock_add:
            result = await chat_service.create_session(
                "v1", "t1", name="Alice", email="a@b.com", initial_message="hi"
            )
        mock_create.assert_awaited_once_with("t1", "v1", "Alice", "a@b.com")
        mock_add.assert_awaited_once_with("s1", "visitor", "hi", "Alice")
        assert result == session
        assert chat_module._in_memory_sessions["s1"] == {
            "visitor_id": "v1",
            "tenant_id": "t1",
        }

    async def test_create_session_without_initial_message(self):
        session = {"id": "s2", "tenant_id": "t1"}
        with patch(
            "api.services.db_omnichannel.create_chat_session_db",
            new_callable=AsyncMock,
            return_value=session,
        ), patch(
            "api.services.db_omnichannel.add_chat_message_db",
            new_callable=AsyncMock,
        ) as mock_add:
            result = await chat_service.create_session("v1", "t1")
        assert result == session
        mock_add.assert_not_awaited()

    async def test_create_session_returns_none(self):
        with patch(
            "api.services.db_omnichannel.create_chat_session_db",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await chat_service.create_session("v1", "t1")
        assert result is None
        assert chat_module._in_memory_sessions == {}

    async def test_send_message(self):
        message = {"id": "m1", "content": "hello"}
        with patch(
            "api.services.db_omnichannel.add_chat_message_db",
            new_callable=AsyncMock,
            return_value=message,
        ) as mock_add:
            result = await chat_service.send_message("s1", "agent", "hello")
        mock_add.assert_awaited_once_with("s1", "agent", "hello")
        assert result == message

    async def test_assign_agent(self):
        with patch(
            "api.services.db_omnichannel.update_chat_session_db",
            new_callable=AsyncMock,
            return_value={"id": "s1", "agent_id": "a1"},
        ) as mock_update:
            result = await chat_service.assign_agent("s1", "a1")
        kwargs = mock_update.await_args.kwargs
        assert kwargs["agent_id"] == "a1"
        assert kwargs["status"] == "active"
        assert "assigned_at" in kwargs
        assert result["agent_id"] == "a1"

    async def test_get_messages(self):
        with patch(
            "api.services.db_omnichannel.get_chat_messages_db",
            new_callable=AsyncMock,
            return_value=[{"id": "m1"}],
        ) as mock_get:
            result = await chat_service.get_messages("s1", after_id="m0")
        mock_get.assert_awaited_once_with("s1", after_id="m0")
        assert result == [{"id": "m1"}]

    async def test_close_session(self):
        chat_module._in_memory_sessions["s1"] = {"visitor_id": "v1", "tenant_id": "t1"}
        with patch(
            "api.services.db_omnichannel.update_chat_session_db",
            new_callable=AsyncMock,
            return_value={"id": "s1", "status": "closed"},
        ) as mock_update:
            result = await chat_service.close_session("s1")
        kwargs = mock_update.await_args.kwargs
        assert kwargs["status"] == "closed"
        assert "closed_at" in kwargs
        assert "s1" not in chat_module._in_memory_sessions
        assert result["status"] == "closed"

    async def test_get_waiting_sessions(self):
        rows = [{"id": "s1", "created_at": "2020-01-01T00:00:00Z"}]
        with patch(
            "api.services.db_omnichannel.list_waiting_sessions_db",
            new_callable=AsyncMock,
            return_value=rows,
        ) as mock_list:
            result = await chat_service.get_waiting_sessions("t1")
        mock_list.assert_awaited_once_with("t1")
        assert result[0]["wait_time_seconds"] > 0

    async def test_compute_wait_time_no_timestamp(self):
        assert chat_service._compute_wait_time(None) == 0

    async def test_compute_wait_time_valid(self):
        assert chat_service._compute_wait_time("2020-01-01T00:00:00Z") > 0

    async def test_compute_wait_time_invalid(self):
        assert chat_service._compute_wait_time("not-a-date") == 0
