"""Unit tests for pydantic DTOs."""

import pytest

from api.models.dto import AgentCreate, TenantCreate


class TestAgentCreate:
    def test_filters_disallowed_skills(self):
        agent = AgentCreate(name="Test Agent", skills=["sales", "hacking", "support"])
        assert agent.skills == ["sales", "support"]

    def test_validate_skills_returns_non_list_unchanged(self):
        result = AgentCreate.validate_skills("not-a-list")
        assert result == "not-a-list"

    def test_default_skills_empty(self):
        agent = AgentCreate(name="Test Agent")
        assert agent.skills == []

    def test_default_config_empty(self):
        agent = AgentCreate(name="Test Agent")
        assert agent.config == {}

    def test_invalid_agent_type_rejected(self):
        with pytest.raises(ValueError):
            AgentCreate(name="Bad", agent_type="robot")


class TestTenantCreate:
    def test_defaults(self):
        tenant = TenantCreate(name="Acme Corp", email="admin@acme.com")
        assert tenant.phone is None
        assert tenant.plan_id is None
        assert tenant.gdpr_consent is False

    def test_short_name_rejected(self):
        with pytest.raises(ValueError):
            TenantCreate(name="ab", email="admin@acme.com")
