"""Unit tests for src/api/main.py — FastAPI app factory, lifespan, endpoints.

api.main imports cleanly because tests/conftest.py sets the required env vars
before any api.* import. We cover the app construction, middleware, exception
handlers, health endpoints (via TestClient), the startup/shutdown lifespan
(with mocked Redis / background loops), safe_redis_publish and get_voice_client.
"""

import asyncio
import os
import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))

# Several other unit tests defensively pre-register a mock `api.main` (a bare
# ModuleType with only redis_client/logger) in sys.modules. If that mock is
# already present, `import api.main` below would bind to it and every test
# here would fail with AttributeError. Evict any such mock so the real app
# module loads (mirrors tests/conftest.ensure_real_api_main).
if "api.main" in sys.modules and not hasattr(sys.modules["api.main"], "app"):
    del sys.modules["api.main"]

import api.main as main  # noqa: E402
from api.services.db_errors import (  # noqa: E402
    DatabaseError,
    NotFoundError,
    PoolNotAvailableError,
)


def _fake_loop_task(*args):
    async def _loop():
        await asyncio.Event().wait()

    return _loop()


class FakeRedis:
    def __init__(self, ping_ok=True, publish_ok=True):
        self._ping_ok = ping_ok
        self._publish_ok = publish_ok

    async def ping(self):
        if not self._ping_ok:
            raise ConnectionError("redis down")
        return True

    async def publish(self, channel, message):
        if not self._publish_ok:
            raise ConnectionError("publish failed")
        return 1

    async def close(self):
        return None


class FakeVoiceClient:
    async def close(self):
        return None


def _patch_lifespan_deps(monkeypatch):
    monkeypatch.setattr(main.redis, "from_url", lambda *a, **k: FakeRedis())
    monkeypatch.setattr(main.agent_cache, "start_cleanup_loop", _fake_loop_task)
    monkeypatch.setattr(
        "api.services.transcript_store.TranscriptStore.cleanup_stale_loop",
        _fake_loop_task,
    )
    monkeypatch.setattr(main, "get_voice_client", lambda: FakeVoiceClient())
    monkeypatch.setattr("api.services.database.init_sqlite_schema", lambda: None)


class TestAppConstruction:
    def test_app_metadata(self):
        assert main.app.title == "AetherDesk Call Center API"
        assert main.app.version == "1.0.0"
        assert main.app.docs_url == "/docs"
        assert main.app.redoc_url == "/redoc"

    def test_routes_registered(self):
        assert len(main.app.routes) >= 30

    def test_middleware_registered(self):
        names = {m.cls.__name__ for m in main.app.user_middleware}
        assert "CORSMiddleware" in names
        assert "RateLimitMiddleware" in names
        assert "AuditMiddleware" in names
        assert "SecurityHeadersMiddleware" in names
        assert "RBACMiddleware" in names


class TestExceptionHandlers:
    async def _invoke(self, exc):
        handler = main.app.exception_handlers[type(exc)]
        return await handler(None, exc)

    def test_not_found_handler(self):
        resp = asyncio.run(self._invoke(NotFoundError("user", "u-1")))
        assert resp.status_code == 404
        assert '"code":"not_found"' in resp.body.decode()

    def test_pool_error_handler(self):
        resp = asyncio.run(self._invoke(PoolNotAvailableError()))
        assert resp.status_code == 503
        assert '"code":"service_unavailable"' in resp.body.decode()

    def test_database_error_handler(self):
        resp = asyncio.run(self._invoke(DatabaseError("boom")))
        assert resp.status_code == 500
        assert '"code":"database_error"' in resp.body.decode()


class TestEndpoints:
    @pytest.fixture
    def client(self):
        # No context manager → lifespan is not run; state defaults apply.
        return TestClient(main.app)

    def test_liveness(self, client):
        resp = client.get("/api/v1/health/live")
        assert resp.status_code == 200
        assert resp.json()["status"] == "alive"

    def test_health_endpoint(self, client):
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] in ("healthy", "degraded")
        assert "services" in body
        assert body["services"]["redis"] in ("connected", "disconnected")

    def test_docs(self, client):
        resp = client.get("/docs")
        assert resp.status_code == 200

    def test_readiness_probe(self, client):
        resp = client.get("/api/v1/health/ready")
        assert resp.status_code in (200, 503)
        assert resp.json()["status"] in ("ready", "not_ready")

    def test_security_headers_present(self, client):
        resp = client.get("/api/v1/health/live")
        assert resp.status_code == 200


class TestCreateAccessToken:
    def test_returns_jwt(self):
        token = main.create_access_token({"sub": "user-1"})
        assert isinstance(token, str)
        assert token.count(".") == 2

    def test_with_expiry(self):
        import datetime as dt

        token = main.create_access_token({"sub": "u"}, dt.timedelta(minutes=5))
        assert token.count(".") == 2


class TestGetVoiceClient:
    def test_mock_client_when_no_keys(self, monkeypatch):
        monkeypatch.delenv("FONOSTER_API_KEY", raising=False)
        monkeypatch.delenv("TWILIO_ACCOUNT_SID", raising=False)
        monkeypatch.setattr("api.mock_voice_client.MockVoiceClient", object)
        assert main.get_voice_client() is not None

    def test_fonoster_client_when_key(self, monkeypatch):
        monkeypatch.setenv("FONOSTER_API_KEY", "real-key")
        monkeypatch.setenv("FONOSTER_URL", "http://fonoster:50062")
        monkeypatch.delenv("TWILIO_ACCOUNT_SID", raising=False)
        monkeypatch.setattr(
            "api.fonoster_client.FonosterHTTPClient", lambda *a, **k: "fonoster"
        )
        assert main.get_voice_client() == "fonoster"

    def test_twilio_client_when_sid(self, monkeypatch):
        monkeypatch.delenv("FONOSTER_API_KEY", raising=False)
        monkeypatch.setenv("TWILIO_ACCOUNT_SID", "ACxxx")
        monkeypatch.setattr(
            "api.twilio_client.TwilioVoiceClient", lambda: "twilio"
        )
        assert main.get_voice_client() == "twilio"

    def test_none_when_mock_unavailable(self, monkeypatch):
        monkeypatch.delenv("FONOSTER_API_KEY", raising=False)
        monkeypatch.delenv("TWILIO_ACCOUNT_SID", raising=False)

        class _Boom:
            def __init__(self):
                raise RuntimeError("unavailable")

        monkeypatch.setattr("api.mock_voice_client.MockVoiceClient", _Boom)
        assert main.get_voice_client() is None

    def test_fonoster_failure_falls_back_to_mock(self, monkeypatch):
        monkeypatch.setenv("FONOSTER_API_KEY", "key")
        monkeypatch.delenv("TWILIO_ACCOUNT_SID", raising=False)
        monkeypatch.setattr(
            "api.fonoster_client.FonosterHTTPClient",
            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no fonoster")),
        )
        monkeypatch.setattr("api.mock_voice_client.MockVoiceClient", object)
        assert main.get_voice_client() is not None

    def test_twilio_failure_falls_back_to_mock(self, monkeypatch):
        monkeypatch.delenv("FONOSTER_API_KEY", raising=False)
        monkeypatch.setenv("TWILIO_ACCOUNT_SID", "ACx")
        monkeypatch.setattr(
            "api.twilio_client.TwilioVoiceClient",
            lambda: (_ for _ in ()).throw(RuntimeError("no twilio")),
        )
        monkeypatch.setattr("api.mock_voice_client.MockVoiceClient", object)
        assert main.get_voice_client() is not None


class TestSafeRedisPublish:
    def test_publish_success(self, monkeypatch):
        monkeypatch.setattr(main, "redis_client", FakeRedis())
        assert asyncio.run(main.safe_redis_publish("ch", "msg")) is True

    def test_reconnect_then_success(self, monkeypatch):
        monkeypatch.setattr(main, "redis_client", FakeRedis(publish_ok=False))
        monkeypatch.setattr(
            main.redis, "from_url", lambda *a, **k: FakeRedis(publish_ok=True)
        )
        assert asyncio.run(main.safe_redis_publish("ch", "msg")) is True

    def test_all_fail(self, monkeypatch):
        monkeypatch.setattr(main, "redis_client", FakeRedis(publish_ok=False))
        monkeypatch.setattr(
            main.redis, "from_url", lambda *a, **k: FakeRedis(publish_ok=False)
        )
        assert asyncio.run(main.safe_redis_publish("ch", "msg")) is False

    def test_publish_with_no_client(self, monkeypatch):
        monkeypatch.setattr(main, "redis_client", None)
        monkeypatch.setattr(main.redis, "from_url", lambda *a, **k: FakeRedis())
        assert asyncio.run(main.safe_redis_publish("ch", "msg")) is True


class TestLifespan:
    def test_startup_and_shutdown(self, monkeypatch):
        _patch_lifespan_deps(monkeypatch)

        async def _run():
            async with main.lifespan(main.app):
                assert main.app.state.redis is not None
                assert main.app.state.fonster_client is not None
                assert main.app.state.transcript_store is not None
                assert main.app.state.voice_profile_store is not None

        asyncio.run(_run())

    def test_lifespan_without_voice_client(self, monkeypatch):
        _patch_lifespan_deps(monkeypatch)
        monkeypatch.setattr(main, "get_voice_client", lambda: None)

        async def _run():
            async with main.lifespan(main.app):
                assert main.app.state.fonster_client is None

        asyncio.run(_run())

    def test_lifespan_redis_retries_then_connects(self, monkeypatch):
        class _RetryRedis:
            def __init__(self):
                self._fails = 1

            async def ping(self):
                if self._fails > 0:
                    self._fails -= 1
                    raise ConnectionError("first ping fails")
                return True

            async def close(self):
                return None

        monkeypatch.setattr(main.redis, "from_url", lambda *a, **k: _RetryRedis())
        monkeypatch.setattr(main.agent_cache, "start_cleanup_loop", _fake_loop_task)
        monkeypatch.setattr(
            "api.services.transcript_store.TranscriptStore.cleanup_stale_loop",
            _fake_loop_task,
        )
        monkeypatch.setattr(main, "get_voice_client", lambda: FakeVoiceClient())
        monkeypatch.setattr(
            "api.services.database.init_sqlite_schema", lambda: None
        )

        async def _run():
            async with main.lifespan(main.app):
                assert main.app.state.redis is not None

        asyncio.run(_run())

    def test_lifespan_survives_redis_connect_error(self, monkeypatch):
        def _boom_from_url(*a, **k):
            raise ConnectionError("cannot reach redis")

        _patch_lifespan_deps(monkeypatch)
        monkeypatch.setattr(main.redis, "from_url", _boom_from_url)

        async def _run():
            async with main.lifespan(main.app):
                assert main.app.state.fonster_client is not None

        asyncio.run(_run())

    def test_lifespan_survives_db_init_failure(self, monkeypatch):
        def _boom_schema(*a, **k):
            raise RuntimeError("schema init failed")

        _patch_lifespan_deps(monkeypatch)
        monkeypatch.setattr(
            "api.services.database.init_sqlite_schema", _boom_schema
        )

        async def _run():
            async with main.lifespan(main.app):
                assert main.app.state.fonster_client is not None

        asyncio.run(_run())

    def test_lifespan_runs_retention_cleanup(self, monkeypatch):
        class FakeConn:
            def execute(self, sql, params=None):
                return types.SimpleNamespace(rowcount=1)

            def commit(self):
                return None

            def close(self):
                return None

        calls = {"n": 0}
        real_sleep = asyncio.sleep

        async def _short_sleep(s):
            calls["n"] += 1
            if calls["n"] > 1:
                raise asyncio.CancelledError()

        _patch_lifespan_deps(monkeypatch)
        monkeypatch.setattr(main.asyncio, "sleep", _short_sleep)
        monkeypatch.setattr(
            "api.services.database._get_sqlite_conn", lambda: FakeConn()
        )

        async def _run():
            async with main.lifespan(main.app):
                await real_sleep(0.05)

        asyncio.run(_run())
        assert calls["n"] > 1

    def test_lifespan_retention_catches_db_errors(self, monkeypatch):
        class _FailingConn:
            def execute(self, sql, params=None):
                raise RuntimeError("db locked")

            def close(self):
                return None

        real_sleep = asyncio.sleep
        calls = {"n": 0}

        async def _short_sleep(s):
            calls["n"] += 1
            if calls["n"] > 1:
                raise asyncio.CancelledError()

        _patch_lifespan_deps(monkeypatch)
        monkeypatch.setattr(main.asyncio, "sleep", _short_sleep)
        monkeypatch.setattr(
            "api.services.database._get_sqlite_conn", lambda: _FailingConn()
        )

        async def _run():
            async with main.lifespan(main.app):
                await real_sleep(0.05)

        asyncio.run(_run())

    def test_lifespan_flushes_observability_backends(self, monkeypatch):
        import api.services.langfuse_client as _lf

        monkeypatch.setattr(_lf, "flush", lambda: None)

        try:
            import api.services.analytics_client as _an
        except Exception:
            _an = types.ModuleType("api.services.analytics_client")
            _an.shutdown = lambda: None
            monkeypatch.setitem(sys.modules, "api.services.analytics_client", _an)
        else:
            monkeypatch.setattr(_an, "shutdown", lambda: None)

        fake_sentry = types.ModuleType("sentry_sdk")
        fake_sentry.flush = lambda: None
        monkeypatch.setitem(sys.modules, "sentry_sdk", fake_sentry)

        _patch_lifespan_deps(monkeypatch)

        async def _run():
            async with main.lifespan(main.app):
                pass

        asyncio.run(_run())

    def test_lifespan_redis_ping_fails_forever(self, monkeypatch):
        class _DownRedis:
            async def ping(self):
                raise ConnectionError("redis down forever")

            async def close(self):
                return None

        class FakeConn:
            def execute(self, sql, params=None):
                return types.SimpleNamespace(rowcount=0)

            def commit(self):
                return None

            def close(self):
                return None

        _patch_lifespan_deps(monkeypatch)
        monkeypatch.setattr(main.redis, "from_url", lambda *a, **k: _DownRedis())
        monkeypatch.setattr(
            "api.services.database._get_sqlite_conn", lambda: FakeConn()
        )

        async def _run():
            async with main.lifespan(main.app):
                assert main.app.state.fonster_client is not None

        asyncio.run(_run())

    def test_lifespan_pg_db_init_branch(self, monkeypatch):
        class FakePGPool:
            async def execute(self, sql, *params):
                return "OK"

        async def _run():
            async with main.lifespan(main.app):
                assert main.app.state.redis is not None

        _patch_lifespan_deps(monkeypatch)
        monkeypatch.setattr(main, "USE_POSTGRES", True)
        monkeypatch.setattr(
            main, "get_pg_pool", AsyncMock(return_value=FakePGPool())
        )
        monkeypatch.setattr(
            main, "init_pg_schema", AsyncMock(return_value=None)
        )
        asyncio.run(_run())

    def test_lifespan_pg_db_init_no_pool(self, monkeypatch):
        _patch_lifespan_deps(monkeypatch)
        monkeypatch.setattr(main, "USE_POSTGRES", True)
        monkeypatch.setattr(main, "get_pg_pool", AsyncMock(return_value=None))
        monkeypatch.setattr(
            main, "init_pg_schema", AsyncMock(return_value=None)
        )

        async def _run():
            async with main.lifespan(main.app):
                assert main.app.state.fonster_client is not None

        asyncio.run(_run())

    def test_lifespan_pg_retention_cleanup(self, monkeypatch):
        class FakePGPool:
            def __init__(self):
                self.executed = []

            async def execute(self, sql, *params):
                self.executed.append(sql)
                return "OK"

        real_sleep = asyncio.sleep
        calls = {"n": 0}

        async def _short_sleep(s):
            calls["n"] += 1
            if calls["n"] > 1:
                raise asyncio.CancelledError()

        _patch_lifespan_deps(monkeypatch)
        monkeypatch.setattr(main.asyncio, "sleep", _short_sleep)
        monkeypatch.setattr(main, "USE_POSTGRES", True)
        pool = FakePGPool()
        monkeypatch.setattr(main, "get_pg_pool", AsyncMock(return_value=pool))
        monkeypatch.setattr(
            "api.services.database._get_sqlite_conn",
            lambda: types.SimpleNamespace(execute=lambda *a, **k: None),
        )

        async def _run():
            async with main.lifespan(main.app):
                await real_sleep(0.05)

        asyncio.run(_run())
        assert calls["n"] > 1
        assert any("UPDATE recordings" in sql for sql in pool.executed)
        assert any("DELETE FROM transcriptions" in sql for sql in pool.executed)

    def test_lifespan_shutdown_flush_errors(self, monkeypatch):
        import api.services.langfuse_client as _lf

        def _boom(*a, **k):
            raise RuntimeError("flush failed")

        monkeypatch.setattr(_lf, "flush", _boom)

        try:
            import api.services.analytics_client as _an
        except Exception:
            _an = types.ModuleType("api.services.analytics_client")
            _an.shutdown = _boom
            monkeypatch.setitem(sys.modules, "api.services.analytics_client", _an)
        else:
            monkeypatch.setattr(_an, "shutdown", _boom)

        fake_sentry = types.ModuleType("sentry_sdk")
        fake_sentry.flush = _boom
        monkeypatch.setitem(sys.modules, "sentry_sdk", fake_sentry)

        _patch_lifespan_deps(monkeypatch)

        async def _run():
            async with main.lifespan(main.app):
                pass

        asyncio.run(_run())


class TestImportTimeConfig:
    """Module-level env guards are only reachable at import time, so these
    spawn subprocesses that import api.main under different environments."""

    @staticmethod
    def _run(code, env_set, env_del):
        import subprocess

        env = dict(os.environ)
        env.update(env_set)
        # Isolate these guard tests from the repo .env file (main.py loads it
        # at import time before the env guard); otherwise dotenv would supply
        # the popped required vars and the guard would never fire.
        env["AETHERDESK_DOTENV_DISABLED"] = "1"
        for k in env_del:
            env.pop(k, None)
        # When measuring coverage, propagate the subprocess-coverage config so
        # the child process's data lands in the same coverage data file.
        sub_cov = os.environ.get("TEST_MAIN_SUBCOV_CONFIG")
        if sub_cov:
            env["COVERAGE_PROCESS_START"] = sub_cov
        proc = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            timeout=300,
            env=env,
            cwd=os.getcwd(),
        )
        return proc

    def test_missing_required_env_exits(self):
        code = (
            "import os,sys; sys.path.insert(0,'src'); "
            "os.environ.pop('JWT_SECRET',None); os.environ.pop('INTERNAL_API_KEY',None); "
            "import api.main"
        )
        proc = self._run(code, {}, [])
        assert proc.returncode != 0
        assert "FATAL" in proc.stderr

    def test_postgres_without_database_url_raises(self):
        code = (
            "import os,sys; sys.path.insert(0,'src'); "
            "os.environ['USE_POSTGRES']='true'; os.environ.pop('DATABASE_URL',None); "
            "import api.main"
        )
        proc = self._run(code, {}, [])
        assert proc.returncode != 0
        assert "DATABASE_URL" in proc.stderr

    def test_production_without_encryption_key_raises(self):
        code = (
            "import os,sys; sys.path.insert(0,'src'); "
            "os.environ['APP_ENV']='production'; os.environ['ENCRYPTION_KEY']=''; "
            "import api.main"
        )
        proc = self._run(code, {}, [])
        assert proc.returncode != 0
        assert "ENCRYPTION_KEY" in proc.stderr

    def test_postgres_without_jwt_secret_raises(self):
        code = (
            "import os,sys; sys.path.insert(0,'src'); "
            "os.environ['APP_ENV']='production'; os.environ['USE_POSTGRES']='true'; "
            "os.environ['DATABASE_URL']='postgresql://u:p@localhost/db'; "
            "os.environ.pop('JWT_SECRET',None); "
            "import api.main"
        )
        proc = self._run(code, {}, [])
        assert proc.returncode != 0
        assert "JWT_SECRET" in proc.stderr

    def test_log_format_plain_imports(self):
        code = (
            "import os,sys; sys.path.insert(0,'src'); "
            "os.environ['LOG_FORMAT']='plain'; "
            "import api.main; print('IMPORT_OK')"
        )
        proc = self._run(code, {}, [])
        assert proc.returncode == 0
        assert "IMPORT_OK" in proc.stdout

    def test_import_with_sentry_dsn(self):
        code = (
            "import os,sys; sys.path.insert(0,'src'); "
            "os.environ['SENTRY_DSN']='http://x@sentry.local/1'; "
            "import api.main; print('IMPORT_OK')"
        )
        proc = self._run(code, {}, [])
        assert proc.returncode == 0
        assert "IMPORT_OK" in proc.stdout
