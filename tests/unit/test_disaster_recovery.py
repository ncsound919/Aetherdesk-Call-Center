"""Unit tests for src/api/services/disaster_recovery.py.

DRService is a service layer: its methods delegate to the db_bc helpers
(imported by name into the module) and to httpx / db_pool for connectivity
probes. All of those are mocked, so no real network or database I/O happens.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from api.services.disaster_recovery import DRService, dr_service


class FakeExec:
    def __init__(self, row=None):
        self._row = row

    def fetchone(self):
        return self._row


class FakeConn:
    def __init__(self, row=None, exc=None):
        self._row = row
        self._exc = exc
        self.closed = False

    def execute(self, sql):
        if self._exc:
            raise self._exc
        return FakeExec(self._row)

    def close(self):
        self.closed = True


class FakeAsyncClient:
    def __init__(self, responses=None, exc=None):
        self.responses = list(responses) if responses else []
        self.exc = exc
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if self.exc:
            raise self.exc
        if self.responses:
            return self.responses.pop(0)
        return httpx.Response(200)


def _patch_http(responses=None, exc=None):
    client = FakeAsyncClient(responses=responses, exc=exc)
    return patch.object(httpx, "AsyncClient", MagicMock(return_value=client)), client


def _patch_pg_pool(pool):
    return patch(
        "api.services.db_pool.get_pg_pool",
        new_callable=AsyncMock,
        return_value=pool,
    )


def _patch_sqlite_conn(conn):
    return patch(
        "api.services.db_pool._get_sqlite_conn",
        MagicMock(return_value=conn),
    )


def _pg_true():
    return patch("api.services.disaster_recovery.USE_POSTGRES", True)


def _pg_false():
    return patch("api.services.disaster_recovery.USE_POSTGRES", False)


class TestTestFailover:
    @pytest.mark.asyncio
    async def test_telephony_dispatch(self):
        result = {"status": "passed", "checks": [{"name": "twilio_status", "status": "passed"}]}
        with patch.object(
            DRService,
            "_failover_telephony",
            new_callable=AsyncMock,
            return_value=result,
        ), patch(
            "api.services.disaster_recovery.create_failover_test_db",
            new_callable=AsyncMock,
        ) as mock_create:
            out = await DRService().test_failover(
                "telephony", tenant_id="t1", tested_by="admin"
            )
        assert out["service"] == "telephony"
        assert out["status"] == "passed"
        assert out["result"] == result
        assert isinstance(out["duration_seconds"], float)
        mock_create.assert_awaited_once()
        args = mock_create.call_args[0]
        assert args[0] == "t1"
        assert args[1] == "telephony"
        assert args[2] == result
        assert args[4] == "admin"

    @pytest.mark.asyncio
    async def test_database_dispatch(self):
        with patch.object(
            DRService,
            "_failover_database",
            new_callable=AsyncMock,
            return_value={"status": "degraded", "checks": []},
        ), patch(
            "api.services.disaster_recovery.create_failover_test_db",
            new_callable=AsyncMock,
        ) as mock_create:
            out = await DRService().test_failover("database")
        assert out["status"] == "degraded"
        mock_create.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_llm_dispatch(self):
        with patch.object(
            DRService,
            "_failover_llm",
            new_callable=AsyncMock,
            return_value={"status": "passed", "checks": []},
        ), patch(
            "api.services.disaster_recovery.create_failover_test_db",
            new_callable=AsyncMock,
        ) as mock_create:
            out = await DRService().test_failover("llm")
        assert out["status"] == "passed"
        mock_create.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_unknown_service_skipped(self):
        with patch(
            "api.services.disaster_recovery.create_failover_test_db",
            new_callable=AsyncMock,
        ) as mock_create:
            out = await DRService().test_failover("sms")
        assert out["status"] == "skipped"
        assert out["result"]["checks"] == [
            {"name": "sms", "status": "unknown_service"}
        ]
        mock_create.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_exception_marks_failed(self):
        with patch.object(
            DRService,
            "_failover_telephony",
            new_callable=AsyncMock,
            side_effect=RuntimeError("boom"),
        ), patch(
            "api.services.disaster_recovery.create_failover_test_db",
            new_callable=AsyncMock,
        ):
            out = await DRService().test_failover("telephony")
        assert out["status"] == "failed"
        assert "boom" in out["result"]["error"]

    @pytest.mark.asyncio
    async def test_default_tested_by_system(self):
        with patch.object(
            DRService,
            "_failover_telephony",
            new_callable=AsyncMock,
            return_value={"status": "passed", "checks": []},
        ), patch(
            "api.services.disaster_recovery.create_failover_test_db",
            new_callable=AsyncMock,
        ) as mock_create:
            await DRService().test_failover("telephony")
        args = mock_create.call_args[0]
        assert args[0] is None  # tenant_id default
        assert args[4] == "system"


class TestFailoverTelephony:
    @pytest.mark.asyncio
    async def test_passed_when_200(self):
        http_patch, _client = _patch_http([httpx.Response(200)])
        with http_patch:
            result = await DRService()._failover_telephony()
        assert result["status"] == "passed"
        assert result["checks"][0]["status"] == "passed"

    @pytest.mark.asyncio
    async def test_failed_when_not_200(self):
        http_patch, _client = _patch_http([httpx.Response(503)])
        with http_patch:
            result = await DRService()._failover_telephony()
        assert result["status"] == "degraded"
        assert result["checks"][0]["status"] == "failed"

    @pytest.mark.asyncio
    async def test_failed_on_exception(self):
        http_patch, _client = _patch_http(exc=httpx.ConnectError("unreachable"))
        with http_patch:
            result = await DRService()._failover_telephony()
        assert result["status"] == "degraded"
        assert result["checks"][0]["status"] == "failed"
        assert "unreachable" in result["checks"][0]["error"]


class TestFailoverDatabase:
    @pytest.mark.asyncio
    async def test_pg_and_sqlite_passed(self):
        pool = MagicMock()
        pool.fetchval = AsyncMock(return_value=1)
        with _pg_true(), _patch_pg_pool(pool), _patch_sqlite_conn(FakeConn(row={"1": 1})):
            result = await DRService()._failover_database()
        assert result["status"] == "passed"
        names = [c["name"] for c in result["checks"]]
        assert names == ["pg_connectivity", "sqlite_connectivity"]

    @pytest.mark.asyncio
    async def test_pg_failed_when_val_not_one(self):
        pool = MagicMock()
        pool.fetchval = AsyncMock(return_value=0)
        with _pg_true(), _patch_pg_pool(pool), _patch_sqlite_conn(FakeConn(row={"1": 1})):
            result = await DRService()._failover_database()
        assert result["status"] == "degraded"
        assert result["checks"][0]["status"] == "failed"

    @pytest.mark.asyncio
    async def test_pg_no_pool_only_sqlite(self):
        with _pg_true(), _patch_pg_pool(None), _patch_sqlite_conn(FakeConn(row={"1": 1})):
            result = await DRService()._failover_database()
        assert result["status"] == "passed"
        assert [c["name"] for c in result["checks"]] == ["sqlite_connectivity"]

    @pytest.mark.asyncio
    async def test_sqlite_only_mode(self):
        with _pg_false(), _patch_sqlite_conn(FakeConn(row={"1": 1})):
            result = await DRService()._failover_database()
        assert result["status"] == "passed"
        assert [c["name"] for c in result["checks"]] == ["sqlite_connectivity"]

    @pytest.mark.asyncio
    async def test_sqlite_failed_when_no_row(self):
        with _pg_false(), _patch_sqlite_conn(FakeConn(row=None)):
            result = await DRService()._failover_database()
        assert result["status"] == "degraded"
        assert result["checks"][0]["name"] == "sqlite_connectivity"
        assert result["checks"][0]["status"] == "failed"

    @pytest.mark.asyncio
    async def test_exception_appends_failed_check(self):
        with _pg_false(), _patch_sqlite_conn(FakeConn(exc=RuntimeError("db down"))):
            result = await DRService()._failover_database()
        assert result["status"] == "degraded"
        assert result["checks"][0] == {
            "name": "database",
            "status": "failed",
            "error": "db down",
        }


class TestFailoverLLM:
    @pytest.mark.asyncio
    async def test_all_passed_when_configured(self):
        http_patch, _client = _patch_http([httpx.Response(200), httpx.Response(200)])
        with patch.dict(
            "os.environ",
            {"DEEPSEEK_API_KEY": "key", "DEEPSEEK_BASE_URL": "https://deep.example"},
            clear=False,
        ), http_patch:
            result = await DRService()._failover_llm()
        assert result["status"] == "passed"
        assert [c["name"] for c in result["checks"]] == ["deepseek", "ollama"]

    @pytest.mark.asyncio
    async def test_deepseek_failed_on_500(self):
        http_patch, _client = _patch_http([httpx.Response(500), httpx.Response(200)])
        with patch.dict(
            "os.environ",
            {"DEEPSEEK_API_KEY": "key", "DEEPSEEK_BASE_URL": "https://deep.example"},
            clear=False,
        ), http_patch:
            result = await DRService()._failover_llm()
        assert result["status"] == "degraded"
        assert result["checks"][0]["status"] == "failed"

    @pytest.mark.asyncio
    async def test_deepseek_skipped_when_no_key(self):
        http_patch, _client = _patch_http([httpx.Response(200)])
        with patch.dict("os.environ", {}, clear=True), http_patch:
            result = await DRService()._failover_llm()
        assert result["checks"][0]["name"] == "deepseek"
        assert result["checks"][0]["status"] == "skipped"
        assert result["checks"][0]["reason"] == "not_configured"
        assert result["status"] == "degraded"

    @pytest.mark.asyncio
    async def test_exceptions_mark_both_failed(self):
        http_patch, _client = _patch_http(exc=httpx.ConnectError("timeout"))
        with patch.dict(
            "os.environ",
            {"DEEPSEEK_API_KEY": "key", "DEEPSEEK_BASE_URL": "https://deep.example"},
            clear=False,
        ), http_patch:
            result = await DRService()._failover_llm()
        assert result["status"] == "degraded"
        assert all(c["status"] == "failed" for c in result["checks"])


class TestFailoverList:
    @pytest.mark.asyncio
    async def test_list_failover_tests(self):
        with patch(
            "api.services.disaster_recovery.list_failover_tests_db",
            new_callable=AsyncMock,
            return_value=[{"id": "f1"}],
        ) as m:
            assert await DRService().list_failover_tests("t1") == [{"id": "f1"}]
            m.assert_awaited_once_with("t1")

    @pytest.mark.asyncio
    async def test_get_multi_region_status(self):
        import time

        status = await DRService().get_multi_region_status()
        assert set(status.keys()) == {"primary", "standby"}
        assert status["primary"]["status"] == "healthy"
        assert status["standby"]["region"] == "us-west-2"
        assert isinstance(status["primary"]["last_checked"], float)
        assert isinstance(status["standby"]["last_checked"], float)
        assert time.time() - status["primary"]["last_checked"] < 1

    def test_get_multi_region_status_is_async(self):
        import asyncio

        assert asyncio.iscoroutinefunction(DRService.get_multi_region_status)


class TestChaosExperiments:
    @pytest.mark.asyncio
    async def test_run_schedules_execution(self):
        exp = {"id": "e1", "tenant_id": "t1", "status": "running"}

        def _fake_create_task(coro):
            coro.close()
            return MagicMock()

        with patch(
            "api.services.disaster_recovery.create_chaos_experiment_db",
            new_callable=AsyncMock,
            return_value=exp,
        ), patch(
            "api.services.disaster_recovery.asyncio.create_task",
            side_effect=_fake_create_task,
        ) as mock_task:
            result = await DRService().run_chaos_experiment(
                "api", "latency", 5, "t1"
            )
        assert result == exp
        mock_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_returns_none_when_create_fails(self):
        with patch(
            "api.services.disaster_recovery.create_chaos_experiment_db",
            new_callable=AsyncMock,
            return_value=None,
        ) as mock_create:
            result = await DRService().run_chaos_experiment("api", "latency", 5, "t1")
        assert result is None
        mock_create.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_execute_chaos_updates_completed(self):
        with patch(
            "api.services.disaster_recovery.update_chaos_experiment_db",
            new_callable=AsyncMock,
        ) as mock_update:
            await DRService()._execute_chaos("e1", "api", "latency", 0)
        mock_update.assert_awaited_once_with(
            "e1",
            "completed",
            {
                "target": "api",
                "fault_type": "latency",
                "impact": "simulated",
                "recovery": "automatic",
            },
        )

    @pytest.mark.asyncio
    async def test_list_chaos_experiments(self):
        with patch(
            "api.services.disaster_recovery.list_chaos_experiments_db",
            new_callable=AsyncMock,
            return_value=[{"id": "e1"}],
        ) as m:
            assert await DRService().list_chaos_experiments("t1") == [{"id": "e1"}]
            m.assert_awaited_once_with("t1")


class TestContracts:
    @pytest.mark.asyncio
    async def test_manage_contract(self):
        with patch(
            "api.services.disaster_recovery.create_contract_db",
            new_callable=AsyncMock,
            return_value={"id": "c1"},
        ) as m:
            result = await DRService().manage_contract("t1", "Twilio", "net30", "2026-12-01", cost=100)
        assert result == {"id": "c1"}
        m.assert_awaited_once_with("t1", "Twilio", "net30", "2026-12-01", 100)

    @pytest.mark.asyncio
    async def test_list_contracts(self):
        with patch(
            "api.services.disaster_recovery.list_contracts_db",
            new_callable=AsyncMock,
            return_value=[{"id": "c1"}],
        ) as m:
            assert await DRService().list_contracts("t1") == [{"id": "c1"}]
            m.assert_awaited_once_with("t1")

    @pytest.mark.asyncio
    async def test_get_contract_alerts(self):
        with patch(
            "api.services.disaster_recovery.get_contract_alerts_db",
            new_callable=AsyncMock,
            return_value=[{"id": "c1"}],
        ) as m:
            assert await DRService().get_contract_alerts("t1", days_ahead=15) == [{"id": "c1"}]
            m.assert_awaited_once_with("t1", 15)

    @pytest.mark.asyncio
    async def test_get_contract_alerts_default(self):
        with patch(
            "api.services.disaster_recovery.get_contract_alerts_db",
            new_callable=AsyncMock,
            return_value=[],
        ) as m:
            await DRService().get_contract_alerts("t1")
        m.assert_awaited_once_with("t1", 30)


class TestBackupChannels:
    @pytest.mark.asyncio
    async def test_configure_backup_channel(self):
        with patch(
            "api.services.disaster_recovery.create_backup_channel_db",
            new_callable=AsyncMock,
            return_value={"id": "ch1"},
        ) as m:
            result = await DRService().configure_backup_channel("t1", "email", {"to": "a@b.com"})
        assert result == {"id": "ch1"}
        m.assert_awaited_once_with("t1", "email", {"to": "a@b.com"})

    @pytest.mark.asyncio
    async def test_list_backup_channels(self):
        with patch(
            "api.services.disaster_recovery.list_backup_channels_db",
            new_callable=AsyncMock,
            return_value=[{"id": "ch1"}],
        ) as m:
            assert await DRService().list_backup_channels("t1") == [{"id": "ch1"}]
            m.assert_awaited_once_with("t1")

    @pytest.mark.asyncio
    async def test_test_channel_found(self):
        channels = [{"id": "ch1", "channel_type": "email", "status": "active"}]
        with patch(
            "api.services.disaster_recovery.list_backup_channels_db",
            new_callable=AsyncMock,
            return_value=channels,
        ), patch(
            "api.services.disaster_recovery.update_backup_channel_test_db",
            new_callable=AsyncMock,
        ) as m_update:
            result = await DRService().test_backup_channel("t1", "email")
        assert result == {
            "success": True,
            "channel_id": "ch1",
            "channel_type": "email",
            "message": "Test alert sent via email",
        }
        m_update.assert_awaited_once_with("ch1", "tested")

    @pytest.mark.asyncio
    async def test_test_channel_not_found(self):
        with patch(
            "api.services.disaster_recovery.list_backup_channels_db",
            new_callable=AsyncMock,
            return_value=[],
        ):
            result = await DRService().test_backup_channel("t1", "email")
        assert result == {
            "success": False,
            "message": "No active email channel found",
        }

    @pytest.mark.asyncio
    async def test_test_channel_skips_inactive(self):
        channels = [{"id": "ch1", "channel_type": "email", "status": "inactive"}]
        with patch(
            "api.services.disaster_recovery.list_backup_channels_db",
            new_callable=AsyncMock,
            return_value=channels,
        ), patch(
            "api.services.disaster_recovery.update_backup_channel_test_db",
            new_callable=AsyncMock,
        ) as m_update:
            result = await DRService().test_backup_channel("t1", "email")
        assert result["success"] is False
        m_update.assert_not_called()


def test_module_singleton():
    assert isinstance(dr_service, DRService)
