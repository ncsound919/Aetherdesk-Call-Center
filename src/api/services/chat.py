from datetime import UTC, datetime

import structlog

logger = structlog.get_logger()

_in_memory_sessions: dict = {}


class ChatService:
    """Live chat service with in-memory session state for development."""

    async def create_session(self, visitor_id, tenant_id, name=None, email=None, initial_message=None):
        from api.services.db_omnichannel import (
            add_chat_message_db,
            create_chat_session_db,
        )

        session = await create_chat_session_db(tenant_id, visitor_id, name, email)
        if not session:
            return None

        _in_memory_sessions[session["id"]] = {"visitor_id": visitor_id, "tenant_id": tenant_id}

        if initial_message:
            await add_chat_message_db(session["id"], "visitor", initial_message, name)

        logger.info("chat_session_created", session_id=session["id"], visitor_id=visitor_id)
        return session

    async def send_message(self, session_id, sender_type, content):
        from api.services.db_omnichannel import add_chat_message_db
        message = await add_chat_message_db(session_id, sender_type, content)
        logger.info("chat_message_sent", session_id=session_id, sender_type=sender_type)
        return message

    async def assign_agent(self, session_id, agent_id):
        from api.services.db_omnichannel import update_chat_session_db
        now = datetime.now(UTC).isoformat()
        result = await update_chat_session_db(session_id, agent_id=agent_id, status="active", assigned_at=now)
        logger.info("chat_agent_assigned", session_id=session_id, agent_id=agent_id)
        return result

    async def get_messages(self, session_id, after_id=None):
        from api.services.db_omnichannel import get_chat_messages_db
        return await get_chat_messages_db(session_id, after_id=after_id)

    async def close_session(self, session_id):
        from api.services.db_omnichannel import update_chat_session_db
        now = datetime.now(UTC).isoformat()
        result = await update_chat_session_db(session_id, status="closed", closed_at=now)
        _in_memory_sessions.pop(session_id, None)
        logger.info("chat_session_closed", session_id=session_id)
        return result

    async def get_waiting_sessions(self, tenant_id):
        from api.services.db_omnichannel import list_waiting_sessions_db
        rows = await list_waiting_sessions_db(tenant_id)
        for row in rows:
            row["wait_time_seconds"] = self._compute_wait_time(row.get("created_at"))
        return rows

    def _compute_wait_time(self, created_at):
        if not created_at:
            return 0
        try:
            created = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
            now = datetime.now(UTC)
            return int((now - created.replace(tzinfo=UTC)).total_seconds())
        except (ValueError, TypeError):
            return 0


chat_service = ChatService()
