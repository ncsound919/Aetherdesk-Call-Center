"""Tests for src/api/main.py — FastAPI app factory, lifespan, handlers, helpers.

Covers the module-level setup (env guard, logging, app, middleware, routers),
the exception handlers, get_voice_client branches, safe_redis_publish, and the
startup/shutdown lifespan with a mocked Redis + background loops.
"""

import asyncio
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import api.main as main  # noqa: E402
from api.services.db_errors import DatabaseError, NotFoundError, PoolNotAvailableError  # noqa: E402


def _fake_loop_task(*args):
    async def _loop():
        # Wait forever on an event (cancelled on shutdown) rather than sleeping,
        # so tests that patch asyncio.sleep aren't disrupted.
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


class TestAppConstruction:
    def test_app_exists_with_expected_config(self):
        assert main.app.title == "AetherDesk Call Center API"
        assert main.app.version == "1.0.0"
        assert main.app.docs_url == "/docs"

    def test_router_includes_register_routes(self):
        # The app registers a large set of routers (covered at import time);
        # assert the route table is populated.
        assert len(main.app.routes) >= 30

    def test_middleware_registered(self):
        mw = {m.cls.__name__ for m in main.app.user_middleware}
        assert "CORSMiddleware" in mw
        assert "RateLimitMiddleware" in mw
        assert "AuditMiddleware" in mw
        assert "SecurityHeadersMiddleware" in mw
        assert "RBACMiddleware" in mw


class TestExceptionHandlers:
    async def _invoke(self, exc):
        handler = main.app.exception_handlers[type(exc)]
        return await handler(None, exc)

    def test_not_found_handler_returns_404(self):
        resp = asyncio.run(self._invoke(NotFoundError("user", "u-1")))
        assert resp.status_code == 404
        body = resp.body.decode()
        assert '"code":"not_found"' in body

    def test_pool_error_handler_returns_503(self):
        resp = asyncio.run(self._invoke(PoolNotAvailableError()))
        assert resp.status_code == 503
        assert '"code":"service_unavailable"' in resp.body.decode()

    def test_database_error_handler_returns_500(self):
        resp = asyncio.run(self._invoke(DatabaseError("boom")))
        assert resp.status_code == 500
        assert '"code":"database_error"' in resp.body.decode()


class TestHelpers:
    def test_create_access_token_returns_jwt(self):
        token = main.create_access_token({"sub": "user-1"})
        assert isinstance(token, str)
        assert token.count(".") == 2

    def test_create_access_token_with_expiry(self):
        import datetime as dt

        token = main.create_access_token(
            {"sub": "user-1"}, dt.timedelta(minutes=5)
        )
        assert token.count(".") == 2


class TestGetVoiceClient:
    def test_mock_client_when_no_keys(self, monkeypatch):
        monkeypatch.delenv("FONOSTER_API_KEY", raising=False)
        monkeypatch.delenv("TWILIO_ACCOUNT_SID", raising=False)
        monkeypatch.setattr("api.mock_voice_client.MockVoiceClient", object)
        client = main.get_voice_client()
        assert client is not None

    def test_fonoster_client_when_key_present(self, monkeypatch):
        monkeypatch.setenv("FONOSTER_API_KEY", "real-key")
        monkeypatch.setenv("FONOSTER_URL", "http://fonoster:50062")
        monkeypatch.setenv("FONOSTER_API_SECRET", "sec")
        monkeypatch.delenv("TWILIO_ACCOUNT_SID", raising=False)
        monkeypatch.setattr(
            "api.fonoster_client.FonosterHTTPClient", lambda *a, **k: "fonoster-client"
        )
        assert main.get_voice_client() == "fonoster-client"

    def test_twilio_client_when_sid_present(self, monkeypatch):
        monkeypatch.delenv("FONOSTER_API_KEY", raising=False)
        monkeypatch.setenv("TWILIO_ACCOUNT_SID", "ACxxx")
        monkeypatch.setattr(
            "api.twilio_client.TwilioVoiceClient", lambda: "twilio-client"
        )
        assert main.get_voice_client() == "twilio-client"

    def test_none_when_mock_unavailable(self, monkeypatch):
        monkeypatch.delenv("FONOSTER_API_KEY", raising=False)
        monkeypatch.delenv("TWILIO_ACCOUNT_SID", raising=False)

        class _Boom:
            def __init__(self):
                raise RuntimeError("mock unavailable")

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
        client = main.get_voice_client()
        assert client is not None

    def test_twilio_failure_falls_back_to_mock(self, monkeypatch):
        monkeypatch.delenv("FONOSTER_API_KEY", raising=False)
        monkeypatch.setenv("TWILIO_ACCOUNT_SID", "ACx")
        monkeypatch.setattr(
            "api.twilio_client.TwilioVoiceClient",
            lambda: (_ for _ in ()).throw(RuntimeError("no twilio")),
        )
        monkeypatch.setattr("api.mock_voice_client.MockVoiceClient", object)
        client = main.get_voice_client()
        assert client is not None


class TestSafeRedisPublish:
    def test_publish_success(self, monkeypatch):
        fake = FakeRedis()
        monkeypatch.setattr(main, "redis_client", fake)
        assert asyncio.run(main.safe_redis_publish("ch", "msg")) is True

    def test_reconnect_then_success(self, monkeypatch):
        failing = FakeRedis(publish_ok=False)
        monkeypatch.setattr(main, "redis_client", failing)
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

    def test_publish_with_no_existing_client(self, monkeypatch):
        monkeypatch.setattr(main, "redis_client", None)
        monkeypatch.setattr(
            main.redis, "from_url", lambda *a, **k: FakeRedis()
        )
        assert asyncio.run(main.safe_redis_publish("ch", "msg")) is True


class TestLifespan:
    def test_startup_and_shutdown(self, monkeypatch):
        monkeypatch.setattr(main.redis, "from_url", lambda *a, **k: FakeRedis())
        monkeypatch.setattr(
            main.agent_cache, "start_cleanup_loop", _fake_loop_task
        )
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
                assert main.app.state.fonster_client is not None
                assert main.app.state.transcript_store is not None
                assert main.app.state.voice_profile_store is not None
            # After exit, state objects are still set; verify no exception thrown.
            assert hasattr(main.app, "state")

        asyncio.run(_run())

    def test_lifespan_without_voice_client(self, monkeypatch):
        monkeypatch.setattr(main.redis, "from_url", lambda *a, **k: FakeRedis())
        monkeypatch.setattr(
            main.agent_cache, "start_cleanup_loop", _fake_loop_task
        )
        monkeypatch.setattr(
            "api.services.transcript_store.TranscriptStore.cleanup_stale_loop",
            _fake_loop_task,
        )
        monkeypatch.setattr(main, "get_voice_client", lambda: None)
        monkeypatch.setattr(
            "api.services.database.init_sqlite_schema", lambda: None
        )

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

        monkeypatch.setattr(
            main.redis, "from_url", lambda *a, **k: _RetryRedis()
        )
        monkeypatch.setattr(
            main.agent_cache, "start_cleanup_loop", _fake_loop_task
        )
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

    def test_lifespan_survives_db_init_failure(self, monkeypatch):
        def _boom_schema(*a, **k):
            raise RuntimeError("schema init failed")

        monkeypatch.setattr(main.redis, "from_url", lambda *a, **k: FakeRedis())
        monkeypatch.setattr(
            main.agent_cache, "start_cleanup_loop", _fake_loop_task
        )
        monkeypatch.setattr(
            "api.services.transcript_store.TranscriptStore.cleanup_stale_loop",
            _fake_loop_task,
        )
        monkeypatch.setattr(main, "get_voice_client", lambda: FakeVoiceClient())
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
                class _R:
                    rowcount = 1

                return _R()

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

        monkeypatch.setattr(main.asyncio, "sleep", _short_sleep)
        monkeypatch.setattr(
            "api.services.database._get_sqlite_conn", lambda: FakeConn()
        )
        monkeypatch.setattr(main.redis, "from_url", lambda *a, **k: FakeRedis())
        monkeypatch.setattr(
            main.agent_cache, "start_cleanup_loop", _fake_loop_task
        )
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
                await real_sleep(0.05)

        asyncio.run(_run())
        # The retention loop ran at least one iteration (sleep was short-circuited).
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

        monkeypatch.setattr(main.asyncio, "sleep", _short_sleep)
        monkeypatch.setattr(
            "api.services.database._get_sqlite_conn", lambda: _FailingConn()
        )
        monkeypatch.setattr(main.redis, "from_url", lambda *a, **k: FakeRedis())
        monkeypatch.setattr(
            main.agent_cache, "start_cleanup_loop", _fake_loop_task
        )
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
                await real_sleep(0.05)

        asyncio.run(_run())

    def test_lifespan_flushes_observability_backends(self, monkeypatch):
        import types as _types

        # Patch flush/shutdown on the real modules so shutdown calls them.
        import api.services.langfuse_client as _lf

        monkeypatch.setattr(_lf, "flush", lambda: None)
        try:
            import api.services.analytics_client as _an
        except Exception:
            _an = _types.ModuleType("api.services.analytics_client")
            _an.shutdown = lambda: None
            monkeypatch.setitem(sys.modules, "api.services.analytics_client", _an)
        else:
            monkeypatch.setattr(_an, "shutdown", lambda: None)

        fake_sentry = _types.ModuleType("sentry_sdk")
        fake_sentry.flush = lambda: None
        monkeypatch.setitem(sys.modules, "sentry_sdk", fake_sentry)

        monkeypatch.setattr(main.redis, "from_url", lambda *a, **k: FakeRedis())
        monkeypatch.setattr(
            main.agent_cache, "start_cleanup_loop", _fake_loop_task
        )
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
                pass

        asyncio.run(_run())

    def test_lifespan_survives_redis_connect_error(self, monkeypatch):
        def _boom_from_url(*a, **k):
            raise ConnectionError("cannot reach redis")

        monkeypatch.setattr(main.redis, "from_url", _boom_from_url)
        monkeypatch.setattr(
            main.agent_cache, "start_cleanup_loop", _fake_loop_task
        )
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
                assert main.app.state.fonster_client is not None

        asyncio.run(_run())


class TestImportTimeConfig:
    """Module-level env guards are only reachable at import time, so these
    spawn subprocesses that import api.main under different environment
    configurations and assert the resulting behaviour."""

    @staticmethod
    def _run(code: str, env_set: dict, env_del: list):
        import subprocess
        import sys

        env = dict(os.environ)
        env.update(env_set)
        for k in env_del:
            env.pop(k, None)
        proc = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            timeout=120,
            env=env,
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

    def test_import_with_sentry_dsn(self):
        code = (
            "import os,sys; sys.path.insert(0,'src'); "
            "os.environ['SENTRY_DSN']='http://x@sentry.local/1'; "
            "import api.main; print('IMPORT_OK')"
        )
        proc = self._run(code, {}, [])
        assert proc.returncode == 0
        assert "IMPORT_OK" in proc.stdout

    def test_lifespan_survives_redis_failure(self, monkeypatch):
        class _DownRedis:
            async def ping(self):
                raise ConnectionError("redis down forever")

            async def close(self):
                return None

        monkeypatch.setattr(main.redis, "from_url", lambda *a, **k: _DownRedis())
        monkeypatch.setattr(
            main.agent_cache, "start_cleanup_loop", _fake_loop_task
        )
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
                assert main.app.state.fonster_client is not None

        asyncio.run(_run())

