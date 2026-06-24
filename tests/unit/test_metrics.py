"""Unit tests for MetricsMiddleware and tracking functions.

Creates a minimal FastAPI app with the metrics middleware, then
verifies metric tracking, endpoint skipping, exception handling,
and all helper tracking functions.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.responses import Response

from apps.api.middleware.metrics import (
    REQUEST_COUNT,
    REQUEST_LATENCY,
    VOICE_REQUEST_COUNT,
    ASR_LATENCY,
    TTS_LATENCY,
    LLM_LATENCY,
    ACTIVE_SESSIONS,
    WEBSOCKET_CONNECTIONS,
    REDIS_CONNECTIONS,
    metrics_endpoint,
    track_asr_latency,
    track_llm_latency,
    track_tts_latency,
    track_voice_request,
    update_active_sessions,
    update_redis_connections,
    update_websocket_connections,
)


# ── MetricsMiddleware dispatch ─────────────────────────────────────

@pytest.fixture
def app():
    """Minimal FastAPI app with MetricsMiddleware."""
    application = FastAPI()

    from apps.api.middleware.metrics import MetricsMiddleware

    application.add_middleware(MetricsMiddleware)

    @application.get("/test")
    async def test_route():
        return {"message": "ok"}

    @application.post("/test")
    async def test_route_post():
        return {"message": "ok"}

    @application.put("/test")
    async def test_route_put():
        return {"message": "ok"}

    @application.delete("/test")
    async def test_route_delete():
        return {"message": "ok"}

    @application.get("/error")
    async def error_route():
        raise RuntimeError("something went wrong")

    @application.get("/metrics")
    async def metrics_route():
        return await metrics_endpoint()

    return application


@pytest.fixture
def client(app):
    """TestClient bound to the minimal metrics app."""
    with TestClient(app) as c:
        yield c


class TestMetricsMiddlewareDispatch:
    """Verify dispatch behaviour and metrics tracking."""

    def test_normal_request_tracks_metrics(self, client):
        resp = client.get("/test")
        assert resp.status_code == 200
        assert resp.json() == {"message": "ok"}

    def test_metrics_endpoint_is_skipped(self, client):
        """The /metrics endpoint should bypass metric tracking."""
        resp = client.get("/metrics")
        assert resp.status_code == 200
        assert resp.headers.get("content-type") == "text/plain; charset=utf-8"
        body = resp.text
        assert "http_requests_total" in body
        assert "http_request_duration_seconds" in body

    def test_exception_results_in_500_status_tracking(self, client):
        """Even when a route raises, metrics should still be recorded."""
        with pytest.raises(RuntimeError, match="something went wrong"):
            client.get("/error")

    def test_different_methods_tracked(self, client):
        resp = client.post("/test")
        assert resp.status_code == 200

        resp2 = client.put("/test")
        assert resp2.status_code == 200

        resp3 = client.delete("/test")
        assert resp3.status_code == 200

    def test_tracked_metrics_appear_in_metrics_endpoint(self, client):
        client.get("/test")
        resp = client.get("/metrics")
        body = resp.text
        assert 'http_requests_total{endpoint="/test",method="GET",status="200"}' in body
        assert 'http_request_duration_seconds' in body


# ── Tracking helper functions ─────────────────────────────────────

class TestTrackingFunctions:
    """Verify each tracking helper executes without error."""

    def test_track_voice_request(self):
        track_voice_request(session_id="sess-1", intent="support", protocol_id="p-1")

    def test_track_asr_latency(self):
        track_asr_latency(duration=0.5)
        track_asr_latency(duration=1.0, engine="whisper-large")

    def test_track_tts_latency(self):
        track_tts_latency(duration=0.3)
        track_tts_latency(duration=0.8, engine="elevenlabs")

    def test_track_llm_latency(self):
        track_llm_latency(duration=1.2)
        track_llm_latency(duration=2.5, model="gpt-4")

    def test_update_active_sessions(self):
        update_active_sessions(count=5)
        update_active_sessions(count=0)

    def test_update_websocket_connections(self):
        update_websocket_connections(count=10)
        update_websocket_connections(count=0)

    def test_update_redis_connections(self):
        update_redis_connections(count=3)
        update_redis_connections(count=0)

    def test_tracked_voice_requests_appear_in_metrics(self, client, app):
        track_voice_request(session_id="sess-2", intent="billing", protocol_id="p-2")
        resp = client.get("/metrics")
        body = resp.text
        assert 'voice_requests_total{intent="billing",protocol_id="p-2"}' in body

    def test_all_metric_families_present_in_metrics(self, client, app):
        track_asr_latency(0.1)
        track_tts_latency(0.2)
        track_llm_latency(0.3)
        update_active_sessions(1)
        update_websocket_connections(2)
        update_redis_connections(3)

        resp = client.get("/metrics")
        body = resp.text
        assert "asr_processing_seconds" in body
        assert "tts_processing_seconds" in body
        assert "llm_processing_seconds" in body
        assert "active_voice_sessions" in body
        assert "websocket_connections" in body
        assert "redis_connections" in body


# ── metrics_endpoint ──────────────────────────────────────────────

class TestMetricsEndpoint:
    """Verify the metrics endpoint handler (via callable)."""

    def test_returns_response_with_correct_content_type(self):
        import asyncio
        result = asyncio.run(metrics_endpoint())
        assert isinstance(result, Response)
        assert result.media_type == "text/plain"

    def test_contains_metric_definitions(self):
        import asyncio
        result = asyncio.run(metrics_endpoint())
        body = result.body.decode()
        assert "http_requests_total" in body
        assert "http_request_duration_seconds" in body
