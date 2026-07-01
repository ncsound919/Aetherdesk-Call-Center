import pytest
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock


@pytest.fixture(autouse=True)
def reset_app_env():
    import os
    orig = os.environ.get("APP_ENV")
    os.environ.setdefault("APP_ENV", "testing")
    yield
    if orig is None:
        os.environ.pop("APP_ENV", None)
    else:
        os.environ["APP_ENV"] = orig


class _MockDbConn:
    """A connection mock that works with both await and sync execute patterns."""

    def __init__(self, rowcount=1):
        self._call_count = 0
        self._rowcount = rowcount
        self.row_factory = None

    def execute(self, sql, *args):
        self._call_count += 1
        return self

    def fetchone(self):
        return None

    def fetchall(self):
        return []

    @property
    def rowcount(self):
        return self._rowcount

    def close(self):
        pass


class _MockDbConnWithPhone(_MockDbConn):
    def fetchone(self):
        return {"phone": "+1234567890", "email": "user@example.com"}


class TestGDPRDeleteEndpoint:
    @pytest.mark.asyncio
    async def test_delete_user_not_found(self):
        with patch("api.routers.data_governance.get_user_by_id_db", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = None

            from api.routers.data_governance import delete_user_data
            from fastapi import HTTPException

            with pytest.raises(HTTPException) as exc:
                await delete_user_data("nonexistent-user", tenant_id="tenant-1")
            assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_user_wrong_tenant(self):
        with patch("api.routers.data_governance.get_user_by_id_db", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {"id": "user-1", "tenant_id": "tenant-2", "email": "test@example.com"}

            from api.routers.data_governance import delete_user_data
            from fastapi import HTTPException

            with pytest.raises(HTTPException) as exc:
                await delete_user_data("user-1", tenant_id="tenant-1")
            assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_delete_user_success_sqlite(self):
        with (
            patch("api.routers.data_governance.get_user_by_id_db", new_callable=AsyncMock) as mock_get,
            patch("api.routers.data_governance.USE_POSTGRES", False),
            patch("api.routers.data_governance.log_audit_event", new_callable=AsyncMock),
            patch("api.routers.data_governance.db_context") as mock_db_ctx,
        ):
            mock_get.return_value = {
                "id": "user-1", "tenant_id": "tenant-1",
                "email": "user@example.com", "phone": "+1234567890",
            }

            mock_conn = _MockDbConnWithPhone()
            mock_db_ctx.return_value = MagicMock(
                __aenter__=AsyncMock(return_value=mock_conn),
                __aexit__=AsyncMock(return_value=None),
            )

            from api.routers.data_governance import delete_user_data
            result = await delete_user_data("user-1", tenant_id="tenant-1")

            assert result["success"] is True
            assert result["details"]["calls_anonymized"] == 2

    @pytest.mark.asyncio
    async def test_delete_user_no_phone(self):
        with (
            patch("api.routers.data_governance.get_user_by_id_db", new_callable=AsyncMock) as mock_get,
            patch("api.routers.data_governance.USE_POSTGRES", False),
            patch("api.routers.data_governance.log_audit_event", new_callable=AsyncMock),
            patch("api.routers.data_governance.db_context") as mock_db_ctx,
        ):
            mock_get.return_value = {
                "id": "user-1", "tenant_id": "tenant-1",
                "email": "user@example.com",
            }

            mock_conn = _MockDbConn()
            mock_db_ctx.return_value = MagicMock(
                __aenter__=AsyncMock(return_value=mock_conn),
                __aexit__=AsyncMock(return_value=None),
            )

            from api.routers.data_governance import delete_user_data
            result = await delete_user_data("user-1", tenant_id="tenant-1")

            assert result["success"] is True
            assert result["details"]["calls_anonymized"] == 0


class TestGDPRExportEndpoint:
    @pytest.mark.asyncio
    async def test_export_user_not_found(self):
        with patch("api.routers.data_governance.get_user_by_id_db", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = None

            from api.routers.data_governance import export_user_data
            from fastapi import HTTPException

            with pytest.raises(HTTPException) as exc:
                await export_user_data("nonexistent", tenant_id="tenant-1")
            assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_export_user_wrong_tenant(self):
        with patch("api.routers.data_governance.get_user_by_id_db", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {"id": "user-1", "tenant_id": "tenant-2"}

            from api.routers.data_governance import export_user_data
            from fastapi import HTTPException

            with pytest.raises(HTTPException) as exc:
                await export_user_data("user-1", tenant_id="tenant-1")
            assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_export_user_success(self):
        with (
            patch("api.routers.data_governance.get_user_by_id_db", new_callable=AsyncMock) as mock_get,
            patch("api.routers.data_governance.USE_POSTGRES", False),
            patch("api.routers.data_governance.db_context") as mock_db_ctx,
        ):
            mock_get.return_value = {
                "id": "user-1", "tenant_id": "tenant-1",
                "email": "user@example.com", "full_name": "Test User",
                "role": "agent", "email_verified": True,
                "onboarding_completed": True, "onboarding_step": "done",
                "created_at": "2024-01-01T00:00:00", "updated_at": "2024-06-01T00:00:00",
            }

            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_cursor.fetchall.return_value = []
            mock_conn.execute.return_value = mock_cursor

            mock_db_ctx.return_value = MagicMock(
                __aenter__=AsyncMock(return_value=mock_conn),
                __aexit__=AsyncMock(return_value=None),
            )

            from api.routers.data_governance import export_user_data
            result = await export_user_data("user-1", tenant_id="tenant-1")

            assert result["success"] is True
            assert result["user_id"] == "user-1"
            assert result["data"]["profile"]["email"] == "user@example.com"
            assert result["data"]["profile"]["full_name"] == "Test User"

    @pytest.mark.asyncio
    async def test_export_user_returns_all_sections(self):
        with (
            patch("api.routers.data_governance.get_user_by_id_db", new_callable=AsyncMock) as mock_get,
            patch("api.routers.data_governance.USE_POSTGRES", False),
            patch("api.routers.data_governance.db_context") as mock_db_ctx,
        ):
            mock_get.return_value = {
                "id": "user-1", "tenant_id": "tenant-1", "email": "u@test.com",
            }

            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_cursor.fetchall.return_value = [
                {"id": 1, "agent_id": "a1", "caller_number": "+15551234567"},
            ]
            mock_conn.execute.return_value = mock_cursor

            mock_db_ctx.return_value = MagicMock(
                __aenter__=AsyncMock(return_value=mock_conn),
                __aexit__=AsyncMock(return_value=None),
            )

            from api.routers.data_governance import export_user_data
            result = await export_user_data("user-1", tenant_id="tenant-1")

            sections = ["profile", "calls", "recordings", "transcriptions", "customer_profiles", "leads"]
            for s in sections:
                assert s in result["data"], f"Missing section: {s}"
