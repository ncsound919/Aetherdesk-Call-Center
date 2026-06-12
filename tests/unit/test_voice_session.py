import pytest
from apps.api.services.call_session import VoiceSession


class TestVoiceSession:
    def test_create_session(self):
        session = VoiceSession("SESS-001", "CALL-001", "PROF-DEFAULT", "TENANT-001")
        assert session.session_id == "SESS-001"
        assert session.call_sid == "CALL-001"
        assert session.profile_id == "PROF-DEFAULT"
        assert session.tenant_id == "TENANT-001"
        assert session.is_active is True
        assert session.transcript == []
        assert session.audio_buffer == b""

    def test_to_dict(self):
        session = VoiceSession("SESS-001", "CALL-001")
        d = session.to_dict()
        assert d["session_id"] == "SESS-001"
        assert d["call_sid"] == "CALL-001"
        assert d["is_active"] is True

    def test_from_dict(self):
        data = {
            "session_id": "SESS-001",
            "call_sid": "CALL-001",
            "profile_id": "PROF-001",
            "tenant_id": "TENANT-001",
            "agent_state": {},
            "transcript": [{"from": "customer", "text": "hello"}],
            "is_active": True,
        }
        session = VoiceSession.from_dict(data)
        assert session.session_id == "SESS-001"
        assert len(session.transcript) == 1
        assert session.transcript[0]["text"] == "hello"

    def test_from_dict_default_profile(self):
        data = {
            "session_id": "SESS-002",
            "call_sid": "CALL-002",
            "is_active": False,
        }
        session = VoiceSession.from_dict(data)
        assert session.profile_id == "PROF-001"
        assert session.is_active is False

    def test_max_buffer_size(self):
        session = VoiceSession("SESS-001", "CALL-001")
        assert session.MAX_BUFFER_SIZE == 10 * 1024 * 1024

    def test_max_transcript_length(self):
        session = VoiceSession("SESS-001", "CALL-001")
        assert session.MAX_TRANSCRIPT_LENGTH == 100

    def test_agent_state_initialization(self):
        session = VoiceSession("SESS-001", "CALL-001")
        assert session.agent_state == {}
