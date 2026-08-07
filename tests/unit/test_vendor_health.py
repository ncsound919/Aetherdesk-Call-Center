"""Unit tests for api.services.vendor_health."""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import api.services.vendor_health as vh


def _make_async_client_factory(get_side_effect=None):
    """Build a factory that fakes httpx.AsyncClient(...) used in async with."""
    client = AsyncMock()
    if get_side_effect is not None:
        client.get.side_effect = get_side_effect
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=client)
    cm.__aexit__ = AsyncMock(return_value=False)
    factory = MagicMock(return_value=cm)
    return factory, client


def _response(status=200, elapsed_seconds=0.5, text="{}", json_data=None):
    resp = MagicMock()
    resp.status_code = status
    resp.elapsed.total_seconds.return_value = elapsed_seconds
    resp.text = text
    resp.json.return_value = json_data
    return resp


@pytest.fixture(autouse=True)
def _reset_global_state():
    saved_status = vh._vendor_status
    saved_last = vh._last_check
    vh._vendor_status = {}
    vh._last_check = 0
    yield
    vh._vendor_status = saved_status
    vh._last_check = saved_last


class TestCheckAllVendors:
    @pytest.mark.asyncio
    async def test_returns_cached_status_within_interval(self):
        cached = {"twilio": {"status": "healthy"}}
        vh._vendor_status = cached
        vh._last_check = time.time()

        with patch.object(vh.VendorHealthMonitor, "_check_twilio", new_callable=AsyncMock) as m:
            result = await vh.vendor_health_monitor.check_all_vendors()

        assert result == cached
        m.assert_not_called()

    @pytest.mark.asyncio
    async def test_full_check_updates_status_and_last_check(self):
        healthy = {"status": "healthy"}
        with (
            patch.object(
                vh.VendorHealthMonitor, "_check_twilio", new_callable=AsyncMock, return_value=healthy
            ),
            patch.object(
                vh.VendorHealthMonitor, "_check_deepgram", new_callable=AsyncMock, return_value=healthy
            ),
            patch.object(
                vh.VendorHealthMonitor, "_check_groq", new_callable=AsyncMock, return_value=healthy
            ),
            patch.object(
                vh.VendorHealthMonitor, "_check_chatterbox", new_callable=AsyncMock, return_value=healthy
            ),
        ):
            result = await vh.vendor_health_monitor.check_all_vendors()

        assert set(result) == {"twilio", "deepgram", "groq", "chatterbox"}
        assert all(r["status"] == "healthy" for r in result.values())
        assert vh._vendor_status == result
        assert vh._last_check > 0

    @pytest.mark.asyncio
    async def test_degraded_vendors_logged(self):
        healthy = {"status": "healthy"}
        degraded = {"status": "degraded", "status_code": 500}
        with (
            patch.object(
                vh.VendorHealthMonitor, "_check_twilio", new_callable=AsyncMock, return_value=healthy
            ),
            patch.object(
                vh.VendorHealthMonitor, "_check_deepgram", new_callable=AsyncMock, return_value=degraded
            ),
            patch.object(
                vh.VendorHealthMonitor, "_check_groq", new_callable=AsyncMock, return_value=degraded
            ),
            patch.object(
                vh.VendorHealthMonitor, "_check_chatterbox", new_callable=AsyncMock, return_value=healthy
            ),
            patch.object(vh.logger, "warning") as mock_warn,
        ):
            result = await vh.vendor_health_monitor.check_all_vendors()

        assert result["deepgram"]["status"] == "degraded"
        mock_warn.assert_called_once_with("vendor_degradation_detected", vendors=["deepgram", "groq"])


class TestCheckTwilio:
    @pytest.mark.asyncio
    async def test_not_configured(self, monkeypatch):
        monkeypatch.setenv("TWILIO_ACCOUNT_SID", "")
        monkeypatch.setenv("TWILIO_AUTH_TOKEN", "")
        result = await vh.vendor_health_monitor._check_twilio()
        assert result == {"status": "not_configured", "message": "No Twilio credentials"}

    @pytest.mark.asyncio
    async def test_healthy(self, monkeypatch):
        monkeypatch.setenv("TWILIO_ACCOUNT_SID", "sid")
        monkeypatch.setenv("TWILIO_AUTH_TOKEN", "tok")
        factory, client = _make_async_client_factory(get_side_effect=lambda *a, **k: _response(200, 1.25))
        with patch.object(vh.httpx, "AsyncClient", factory):
            result = await vh.vendor_health_monitor._check_twilio()
        assert result["status"] == "healthy"
        assert result["latency_ms"] == 1250

    @pytest.mark.asyncio
    async def test_degraded(self, monkeypatch):
        monkeypatch.setenv("TWILIO_ACCOUNT_SID", "sid")
        monkeypatch.setenv("TWILIO_AUTH_TOKEN", "tok")
        factory, _ = _make_async_client_factory(get_side_effect=lambda *a, **k: _response(401))
        with patch.object(vh.httpx, "AsyncClient", factory):
            result = await vh.vendor_health_monitor._check_twilio()
        assert result == {"status": "degraded", "status_code": 401}

    @pytest.mark.asyncio
    async def test_unhealthy_on_exception(self, monkeypatch):
        monkeypatch.setenv("TWILIO_ACCOUNT_SID", "sid")
        monkeypatch.setenv("TWILIO_AUTH_TOKEN", "tok")
        factory, _ = _make_async_client_factory(
            get_side_effect=lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
        )
        with patch.object(vh.httpx, "AsyncClient", factory):
            result = await vh.vendor_health_monitor._check_twilio()
        assert result["status"] == "unhealthy"
        assert "boom" in result["error"]


class TestCheckDeepgram:
    @pytest.mark.asyncio
    async def test_not_configured(self, monkeypatch):
        monkeypatch.setenv("DEEPGRAM_API_KEY", "")
        result = await vh.vendor_health_monitor._check_deepgram()
        assert result == {"status": "not_configured", "message": "No Deepgram API key"}

    @pytest.mark.asyncio
    @pytest.mark.parametrize("status", [200, 401])
    async def test_healthy_statuses(self, monkeypatch, status):
        monkeypatch.setenv("DEEPGRAM_API_KEY", "key")
        factory, _ = _make_async_client_factory(get_side_effect=lambda *a, **k: _response(status))
        with patch.object(vh.httpx, "AsyncClient", factory):
            result = await vh.vendor_health_monitor._check_deepgram()
        assert result == {"status": "healthy"}

    @pytest.mark.asyncio
    async def test_degraded(self, monkeypatch):
        monkeypatch.setenv("DEEPGRAM_API_KEY", "key")
        factory, _ = _make_async_client_factory(get_side_effect=lambda *a, **k: _response(500))
        with patch.object(vh.httpx, "AsyncClient", factory):
            result = await vh.vendor_health_monitor._check_deepgram()
        assert result == {"status": "degraded", "status_code": 500}

    @pytest.mark.asyncio
    async def test_unhealthy_on_exception(self, monkeypatch):
        monkeypatch.setenv("DEEPGRAM_API_KEY", "key")
        factory, _ = _make_async_client_factory(
            get_side_effect=lambda *a, **k: (_ for _ in ()).throw(OSError("down"))
        )
        with patch.object(vh.httpx, "AsyncClient", factory):
            result = await vh.vendor_health_monitor._check_deepgram()
        assert result["status"] == "unhealthy"
        assert "down" in result["error"]


class TestCheckGroq:
    @pytest.mark.asyncio
    async def test_not_configured(self, monkeypatch):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "")
        result = await vh.vendor_health_monitor._check_groq()
        assert result == {"status": "not_configured", "message": "No DeepSeek API key"}

    @pytest.mark.asyncio
    async def test_healthy(self, monkeypatch):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "key")
        factory, client = _make_async_client_factory(get_side_effect=lambda *a, **k: _response(200))
        with patch.object(vh.httpx, "AsyncClient", factory):
            result = await vh.vendor_health_monitor._check_groq()
        assert result == {"status": "healthy"}
        client.get.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_uses_custom_base_url(self, monkeypatch):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "key")
        monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://custom.example")
        factory, client = _make_async_client_factory(get_side_effect=lambda *a, **k: _response(200))
        with patch.object(vh.httpx, "AsyncClient", factory):
            await vh.vendor_health_monitor._check_groq()
        assert "https://custom.example/models" in str(client.get.await_args)

    @pytest.mark.asyncio
    async def test_degraded(self, monkeypatch):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "key")
        factory, _ = _make_async_client_factory(get_side_effect=lambda *a, **k: _response(503))
        with patch.object(vh.httpx, "AsyncClient", factory):
            result = await vh.vendor_health_monitor._check_groq()
        assert result == {"status": "degraded", "status_code": 503}

    @pytest.mark.asyncio
    async def test_unhealthy_on_exception(self, monkeypatch):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "key")
        factory, _ = _make_async_client_factory(
            get_side_effect=lambda *a, **k: (_ for _ in ()).throw(TimeoutError())
        )
        with patch.object(vh.httpx, "AsyncClient", factory):
            result = await vh.vendor_health_monitor._check_groq()
        assert result["status"] == "unhealthy"


class TestCheckChatterbox:
    @pytest.mark.asyncio
    async def test_healthy(self):
        factory, _ = _make_async_client_factory(get_side_effect=lambda *a, **k: _response(200))
        with patch.object(vh.httpx, "AsyncClient", factory):
            result = await vh.vendor_health_monitor._check_chatterbox()
        assert result == {"status": "healthy"}

    @pytest.mark.asyncio
    async def test_uses_custom_url(self, monkeypatch):
        monkeypatch.setenv("CHATTERBOX_API_URL", "http://chatterbox-dev:6000")
        factory, client = _make_async_client_factory(get_side_effect=lambda *a, **k: _response(200))
        with patch.object(vh.httpx, "AsyncClient", factory):
            await vh.vendor_health_monitor._check_chatterbox()
        assert "http://chatterbox-dev:6000/health" in str(client.get.await_args)

    @pytest.mark.asyncio
    async def test_degraded(self):
        factory, _ = _make_async_client_factory(get_side_effect=lambda *a, **k: _response(502))
        with patch.object(vh.httpx, "AsyncClient", factory):
            result = await vh.vendor_health_monitor._check_chatterbox()
        assert result == {"status": "degraded", "status_code": 502}

    @pytest.mark.asyncio
    async def test_unhealthy_on_exception(self):
        factory, _ = _make_async_client_factory(
            get_side_effect=lambda *a, **k: (_ for _ in ()).throw(ConnectionError("refused"))
        )
        with patch.object(vh.httpx, "AsyncClient", factory):
            result = await vh.vendor_health_monitor._check_chatterbox()
        assert result["status"] == "unhealthy"


class TestStatusHelpers:
    def test_get_vendor_status_returns_copy(self):
        vh._vendor_status = {"twilio": {"status": "healthy"}}
        result = vh.vendor_health_monitor.get_vendor_status()
        assert result == {"twilio": {"status": "healthy"}}
        # dict() is shallow: top-level mutation must not leak back
        result["new_vendor"] = {"status": "healthy"}
        assert "new_vendor" not in vh._vendor_status

    def test_get_degraded_vendors(self):
        vh._vendor_status = {
            "twilio": {"status": "healthy"},
            "deepgram": {"status": "degraded"},
            "groq": {"status": "unhealthy"},
        }
        result = vh.vendor_health_monitor.get_degraded_vendors()
        assert result == ["deepgram", "groq"]

    def test_get_degraded_vendors_empty(self):
        vh._vendor_status = {"twilio": {"status": "healthy"}}
        assert vh.vendor_health_monitor.get_degraded_vendors() == []
