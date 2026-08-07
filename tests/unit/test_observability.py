"""Unit tests for src/api/services/observability.py."""

import asyncio
import types
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.services import observability
from api.services.observability import (
    CallLogger,
    MetricsCollector,
    SLAMetrics,
    UptimeTracker,
    check_asr_health,
    check_deepseek_health,
    check_ollama_health,
    check_redis_health,
    get_health_status,
    initialized_services,
    log_call,
    mark_initialized,
    redact_pii_processor,
)


@pytest.fixture(autouse=True)
def _reset_collectors():
    observability.metrics.reset()
    for key in list(initialized_services.keys()):
        initialized_services[key] = False
    yield
    observability.metrics.reset()
    for key in list(initialized_services.keys()):
        initialized_services[key] = False


class TestRedactPii:
    def test_redacts_sensitive_keys(self):
        out = redact_pii_processor(None, None, {"email": "a@b.com"})
        assert out["email"] == "[REDACTED]"

    def test_redacts_ssn_pattern(self):
        out = redact_pii_processor(None, None, {"msg": "SSN is 123-45-6789"})
        assert "XXX-XX-XXXX" in out["msg"]
        assert "123-45-6789" not in out["msg"]

    def test_redacts_email_pattern(self):
        out = redact_pii_processor(None, None, {"msg": "contact me@x.com now"})
        assert out["msg"] == "contact [REDACTED_EMAIL] now"

    def test_redacts_phone_pattern(self):
        out = redact_pii_processor(None, None, {"msg": "call 555-123-4567"})
        assert "[REDACTED_PHONE]" in out["msg"]

    def test_non_string_value_untouched(self):
        out = redact_pii_processor(None, None, {"count": 5})
        assert out["count"] == 5


class TestMarkInitialized:
    def test_mark_initialized(self):
        mark_initialized("redis")
        assert initialized_services["redis"] is True


class TestLogCall:
    @pytest.mark.asyncio
    async def test_success_path(self):
        calls = []

        @log_call("my-endpoint")
        async def _work(a, b=2):
            calls.append((a, b))
            return a + b

        assert await _work(1, b=3) == 4
        assert calls == [(1, 3)]

    @pytest.mark.asyncio
    async def test_error_path_reraises(self):
        @log_call("bad-endpoint")
        async def _boom():
            raise RuntimeError("kaboom")

        with pytest.raises(RuntimeError, match="kaboom"):
            await _boom()


class TestCallLogger:
    def test_start_and_end_call(self):
        c = CallLogger()
        c.start_call("call-1", {"tenant": "t1"})
        assert "call-1" in c.active_calls
        assert c.active_calls["call-1"]["events"] == []
        c.end_call("call-1", "completed")
        assert "call-1" not in c.active_calls

    def test_log_event_unknown_call_is_ignored(self):
        c = CallLogger()
        c.log_event("missing", "ringing")  # should not raise

    def test_end_call_unknown_is_ignored(self):
        c = CallLogger()
        c.end_call("missing")  # should not raise

    def test_start_call_default_metadata(self):
        c = CallLogger()
        c.start_call("call-2")
        assert c.active_calls["call-2"]["metadata"] == {}

    def test_log_event_appends_then_raises_source_bug(self):
        # Source bug: logger.info("call_event", ..., event=...) duplicates the
        # positional `event` argument, so the logger raises TypeError AFTER the
        # event is appended to the in-memory log.
        c = CallLogger()
        c.start_call("call-1")
        with pytest.raises(TypeError):
            c.log_event("call-1", "ringing", {"to": "+1"})
        assert len(c.active_calls["call-1"]["events"]) == 1
        assert c.active_calls["call-1"]["events"][0]["event"] == "ringing"


class TestMetricsCollector:
    def test_increment(self):
        m = MetricsCollector()
        m.increment("hits")
        m.increment("hits", 3)
        assert m.counters["counter_hits"] == 4

    def test_record_time_and_get_metrics(self):
        m = MetricsCollector()
        m.record_time("api", 100)
        m.record_time("api", 200)
        m.record_time("db", 50)
        out = m.get_metrics()
        assert out["timers"]["timer_api"] == {
            "count": 2,
            "avg_ms": 150,
            "min_ms": 100,
            "max_ms": 200,
        }
        assert out["timers"]["timer_db"]["count"] == 1

    def test_get_metrics_empty(self):
        m = MetricsCollector()
        out = m.get_metrics()
        assert out["counters"] == {}
        assert out["timers"] == {}

    def test_reset(self):
        m = MetricsCollector()
        m.increment("hits")
        m.record_time("api", 10)
        m.reset()
        assert m.counters == {}
        assert m.timers == {}


class TestRedisHealth:
    def _fake_main(self, redis):
        mod = types.ModuleType("api.main")
        mod.app = SimpleNamespace(state=SimpleNamespace(redis=redis))
        return mod

    @pytest.mark.asyncio
    async def test_healthy_when_redis_pings(self):
        fake_redis = MagicMock()
        fake_redis.ping.return_value = True
        with patch.dict(
            "sys.modules", {"api.main": self._fake_main(fake_redis)}
        ):
            assert await check_redis_health() is True

    @pytest.mark.asyncio
    async def test_unhealthy_when_no_redis_attr(self):
        mod = types.ModuleType("api.main")
        mod.app = SimpleNamespace(state=SimpleNamespace())
        with patch.dict("sys.modules", {"api.main": mod}):
            assert await check_redis_health() is False

    @pytest.mark.asyncio
    async def test_unhealthy_when_ping_raises(self):
        class _Boom:
            def ping(self):
                raise ConnectionError("down")

        with patch.dict(
            "sys.modules", {"api.main": self._fake_main(_Boom())}
        ):
            assert await check_redis_health() is False


class TestAsrHealth:
    def _fake_asr(self, model):
        mod = types.ModuleType("api.services.asr")
        mod.asr_service = SimpleNamespace(_model=model)
        return mod

    @pytest.mark.asyncio
    async def test_healthy_when_model_loaded(self):
        with patch.dict(
            "sys.modules", {"api.services.asr": self._fake_asr("model")}
        ):
            assert await check_asr_health() is True

    @pytest.mark.asyncio
    async def test_unhealthy_when_model_none(self):
        with patch.dict(
            "sys.modules", {"api.services.asr": self._fake_asr(None)}
        ):
            assert await check_asr_health() is False

    @pytest.mark.asyncio
    async def test_error_caught(self):
        with patch.dict(
            "sys.modules", {"api.services.asr": SimpleNamespace()}
        ):
            assert await check_asr_health() is False


class FakeResponse:
    def __init__(self, status_code=200):
        self.status_code = status_code


class FakeClient:
    def __init__(self, status_code=200, raises=None):
        self._status = status_code
        self._raises = raises

    async def get(self, url, **kwargs):
        if self._raises:
            raise self._raises
        return FakeResponse(self._status)


class TestOllamaHealth:
    @pytest.mark.asyncio
    async def test_healthy(self, monkeypatch):
        monkeypatch.setenv("OLLAMA_HOST", "http://ollama:11434")
        with patch(
            "api.services.observability.http_pool.get_client",
            new_callable=AsyncMock,
            return_value=FakeClient(200),
        ) as mock_get:
            assert await check_ollama_health() is True
        mock_get.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_unhealthy_status(self):
        with patch(
            "api.services.observability.http_pool.get_client",
            new_callable=AsyncMock,
            return_value=FakeClient(500),
        ):
            assert await check_ollama_health() is False

    @pytest.mark.asyncio
    async def test_error_returns_false(self):
        with patch(
            "api.services.observability.http_pool.get_client",
            new_callable=AsyncMock,
            return_value=FakeClient(raises=ConnectionError("nope")),
        ):
            assert await check_ollama_health() is False


class TestDeepseekHealth:
    @pytest.mark.asyncio
    async def test_no_key_returns_false(self, monkeypatch):
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        assert await check_deepseek_health() is False

    @pytest.mark.asyncio
    async def test_healthy(self, monkeypatch):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-123")
        monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
        with patch(
            "api.services.observability.http_pool.get_client",
            new_callable=AsyncMock,
            return_value=FakeClient(200),
        ):
            assert await check_deepseek_health() is True

    @pytest.mark.asyncio
    async def test_unhealthy_status(self, monkeypatch):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-123")
        with patch(
            "api.services.observability.http_pool.get_client",
            new_callable=AsyncMock,
            return_value=FakeClient(401),
        ):
            assert await check_deepseek_health() is False

    @pytest.mark.asyncio
    async def test_error_returns_false(self, monkeypatch):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-123")
        with patch(
            "api.services.observability.http_pool.get_client",
            new_callable=AsyncMock,
            return_value=FakeClient(raises=ConnectionError("nope")),
        ):
            assert await check_deepseek_health() is False


class TestUptimeTracker:
    def test_get_uptime_seconds(self):
        assert UptimeTracker().get_uptime_seconds() >= 0

    def test_get_uptime_percentage(self):
        assert UptimeTracker().get_uptime_percentage() == 99.9
        assert UptimeTracker().get_uptime_percentage(99.5) == 99.5


class TestSLAMetrics:
    def test_record_request_success(self):
        sla = SLAMetrics()
        sla.record_request("/x", 200, 10.0)
        assert sla._request_counts["/x"] == 1
        assert sla._error_counts == {}

    def test_record_request_error(self):
        sla = SLAMetrics()
        sla.record_request("/x", 503, 10.0)
        assert sla._error_counts["/x"] == 1

    def test_summary_empty(self):
        sla = SLAMetrics()
        summary = sla.get_sla_summary()
        assert summary["total_requests"] == 0
        assert summary["error_rate_pct"] == 0
        assert summary["latency"] == {
            "avg_ms": 0,
            "p50_ms": 0,
            "p95_ms": 0,
            "p99_ms": 0,
        }

    def test_summary_with_data(self):
        sla = SLAMetrics()
        sla.record_request("/a", 200, 100)
        sla.record_request("/a", 200, 200)
        sla.record_request("/a", 500, 300)
        summary = sla.get_sla_summary()
        assert summary["total_requests"] == 3
        assert summary["error_rate_pct"] == round(1 / 3 * 100, 2)
        assert summary["latency"]["p50_ms"] == 200.0
        assert summary["latency"]["avg_ms"] == 200.0

    def test_latency_buckets_truncated(self):
        sla = SLAMetrics()
        for i in range(1100):
            sla.record_request("/bulk", 200, float(i))
        assert len(sla._latency_buckets["/bulk"]) == 1000

    def test_reset(self):
        sla = SLAMetrics()
        sla.record_request("/x", 500, 1.0)
        sla.reset()
        summary = sla.get_sla_summary()
        assert summary["total_requests"] == 0


class TestGetHealthStatus:
    @pytest.mark.asyncio
    async def test_all_healthy(self, monkeypatch):
        async def _ok():
            return True

        with patch.object(
            observability, "HEALTH_CHECKS", {"redis": _ok}
        ), patch.object(
            observability.psutil, "cpu_percent", return_value=10.0
        ), patch.object(
            observability.psutil,
            "virtual_memory",
            return_value=SimpleNamespace(percent=50.0, available=1024 * 1024 * 512),
        ):
            result = await get_health_status()
        assert result["status"] == "healthy"
        assert result["services"]["redis"]["status"] == "healthy"
        assert result["system_metrics"]["cpu_percent"] == 10.0
        assert result["system_metrics"]["memory_available_mb"] == 512

    @pytest.mark.asyncio
    async def test_one_unhealthy(self, monkeypatch):
        async def _bad():
            return False

        async def _good():
            return True

        with patch.object(
            observability, "HEALTH_CHECKS", {"a": _good, "b": _bad}
        ), patch.object(
            observability.psutil, "cpu_percent", return_value=0.0
        ), patch.object(
            observability.psutil,
            "virtual_memory",
            return_value=SimpleNamespace(percent=0.0, available=0),
        ):
            result = await get_health_status()
        assert result["status"] == "degraded"
        assert result["services"]["b"]["status"] == "unhealthy"

    @pytest.mark.asyncio
    async def test_check_raising_exception(self, monkeypatch):
        async def _boom():
            raise RuntimeError("broken")

        with patch.object(
            observability, "HEALTH_CHECKS", {"a": _boom}
        ), patch.object(
            observability.psutil, "cpu_percent", return_value=0.0
        ), patch.object(
            observability.psutil,
            "virtual_memory",
            return_value=SimpleNamespace(percent=0.0, available=0),
        ):
            result = await get_health_status()
        assert result["status"] == "degraded"
        assert result["services"]["a"]["status"] == "error"
        assert result["services"]["a"]["error"] == "broken"
