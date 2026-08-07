"""Unit tests for api.services.vertical_templates.VerticalTemplatesService."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.services.vertical_templates import VERTICALS, vertical_templates_service


@pytest.fixture(autouse=True)
def _use_sqlite_default():
    yield


class TestVerticalTemplatesService:
    def test_get_verticals_lists_all(self):
        result = vertical_templates_service.get_verticals()
        assert len(result) == len(VERTICALS)
        for entry in result:
            assert set(entry.keys()) == {
                "id",
                "name",
                "description",
                "icon",
                "compliance",
                "intent_count",
                "script_count",
            }
        by_id = {e["id"]: e for e in result}
        assert by_id["healthcare"]["intent_count"] == 7
        assert by_id["healthcare"]["script_count"] == 1

    def test_get_vertical_config_existing(self):
        config = vertical_templates_service.get_vertical_config("healthcare")
        assert config == VERTICALS["healthcare"]
        assert config["name"] == "Healthcare"

    def test_get_vertical_config_missing(self):
        assert vertical_templates_service.get_vertical_config("nope") is None

    def test_get_vertical_compliance_existing(self):
        result = vertical_templates_service.get_vertical_compliance("finance/debt_collection")
        assert result["vertical_id"] == "finance/debt_collection"
        assert result["name"] == "Finance & Debt Collection"
        assert "FDCPA" in result["compliance_standards"]
        assert result["compliance_rules"]["max_call_attempts"] == 3

    def test_get_vertical_compliance_missing(self):
        assert vertical_templates_service.get_vertical_compliance("nope") is None

    def test_get_vertical_scripts_existing(self):
        result = vertical_templates_service.get_vertical_scripts("real_estate")
        assert result["vertical_id"] == "real_estate"
        assert result["script_templates"] == ["TPL-REAL-ESTATE"]
        assert "property_inquiry" in result["intents"]

    def test_get_vertical_scripts_missing(self):
        assert vertical_templates_service.get_vertical_scripts("nope") is None

    @pytest.mark.asyncio
    async def test_apply_vertical_template_unknown_returns_none(self):
        result = await vertical_templates_service.apply_vertical_template("t1", "nope")
        assert result is None

    @pytest.mark.asyncio
    async def test_apply_vertical_template_sqlite(self):
        conn = MagicMock()
        row = {"id": "d1", "tenant_id": "t1", "vertical_id": "healthcare"}
        conn.execute.return_value.fetchone.return_value = row
        with patch(
            "api.services.vertical_templates._get_sqlite_conn", return_value=conn
        ):
            result = await vertical_templates_service.apply_vertical_template(
                "t1", "healthcare"
            )
        assert result == row
        assert conn.execute.call_count == 2
        conn.commit.assert_called_once()
        conn.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_apply_vertical_template_sqlite_no_row(self):
        conn = MagicMock()
        conn.execute.return_value.fetchone.return_value = None
        with patch(
            "api.services.vertical_templates._get_sqlite_conn", return_value=conn
        ):
            result = await vertical_templates_service.apply_vertical_template(
                "t1", "ecommerce"
            )
        assert result is None
        conn.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_apply_vertical_template_postgres(self):
        pool = AsyncMock()
        row = {"id": "d1", "tenant_id": "t1", "vertical_id": "healthcare"}
        pool.fetchrow.return_value = row
        with patch("api.services.vertical_templates.USE_POSTGRES", True), patch(
            "api.services.vertical_templates.get_pg_pool",
            new_callable=AsyncMock,
            return_value=pool,
        ):
            result = await vertical_templates_service.apply_vertical_template(
                "t1", "healthcare"
            )
        assert result == row
        pool.execute.assert_awaited_once()
        pool.fetchrow.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_apply_vertical_template_postgres_no_row(self):
        pool = AsyncMock()
        pool.fetchrow.return_value = None
        with patch("api.services.vertical_templates.USE_POSTGRES", True), patch(
            "api.services.vertical_templates.get_pg_pool",
            new_callable=AsyncMock,
            return_value=pool,
        ):
            result = await vertical_templates_service.apply_vertical_template(
                "t1", "healthcare"
            )
        assert result is None
