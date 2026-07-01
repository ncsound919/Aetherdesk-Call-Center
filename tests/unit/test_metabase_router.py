"""Tests for Metabase dashboard embedding router."""

import os
import pytest
from unittest.mock import patch, MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def app():
    from api.routers.metabase import router
    from api.services.auth import verify_tenant_access

    application = FastAPI()
    application.include_router(router)
    application.dependency_overrides[verify_tenant_access] = lambda: "tenant-1"
    return application


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c


class TestGetCallStats:
    def test_returns_mock_when_clickhouse_not_enabled(self, client):
        with patch("api.routers.metabase.is_clickhouse_enabled", return_value=False):
            resp = client.get("/metabase/stats")
            assert resp.status_code == 200
            assert resp.json()["source"] == "mock"

    def test_returns_stats_when_enabled(self, client):
        mock_stats = {
            "total_calls": 100,
            "total_minutes": 500.0,
            "avg_duration": 5.0,
            "completed": 90,
            "missed": 10,
            "avg_satisfaction": 0.85,
            "total_tokens": 5000,
            "total_cost_cents": 250,
        }
        with patch("api.routers.metabase.is_clickhouse_enabled", return_value=True), \
             patch("api.routers.metabase.query_call_stats", return_value=mock_stats):
            resp = client.get("/metabase/stats")
            assert resp.status_code == 200
            data = resp.json()
            assert data["source"] == "clickhouse"
            assert data["total_calls"] == 100
            assert data["total_minutes"] == 500.0


class TestGetIntentDistribution:
    def test_returns_mock_when_not_enabled(self, client):
        with patch("api.routers.metabase.is_clickhouse_enabled", return_value=False):
            resp = client.get("/metabase/intents")
            assert resp.status_code == 200
            assert resp.json()["source"] == "mock"

    def test_returns_intents_when_enabled(self, client):
        mock_intents = [{"intent": "billing", "count": 50}]
        with patch("api.routers.metabase.is_clickhouse_enabled", return_value=True), \
             patch("api.routers.metabase.query_intent_distribution", return_value=mock_intents):
            resp = client.get("/metabase/intents")
            assert resp.status_code == 200
            assert resp.json()["intents"] == mock_intents


class TestGetAgentPerformance:
    def test_returns_mock_when_not_enabled(self, client):
        with patch("api.routers.metabase.is_clickhouse_enabled", return_value=False):
            resp = client.get("/metabase/agents")
            assert resp.status_code == 200
            assert resp.json()["source"] == "mock"


class TestGetHourlyVolume:
    def test_returns_mock_when_not_enabled(self, client):
        with patch("api.routers.metabase.is_clickhouse_enabled", return_value=False):
            resp = client.get("/metabase/hourly")
            assert resp.status_code == 200
            assert resp.json()["source"] == "mock"


class TestGetEmbedUrl:
    def test_returns_not_configured_when_no_env(self, client):
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("METABASE_SECRET_KEY", None)
            os.environ.pop("METABASE_SITE_URL", None)
            resp = client.get("/metabase/embed/42")
            assert resp.status_code == 200
            assert resp.json()["configured"] is False

    def test_returns_url_when_configured(self, client):
        with patch.dict(os.environ, {
            "METABASE_SECRET_KEY": "test-secret-key-32chars-long!!!!!",
            "METABASE_SITE_URL": "http://localhost:3002",
        }):
            resp = client.get("/metabase/embed/42")
            assert resp.status_code == 200
            data = resp.json()
            assert data["configured"] is True
            assert data["url"] is not None
            assert "embed/question" in data["url"]


class TestIsMetabaseConfigured:
    def test_returns_false_when_no_env(self):
        from api.routers.metabase import _is_metabase_configured
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("METABASE_SECRET_KEY", None)
            os.environ.pop("METABASE_SITE_URL", None)
            assert _is_metabase_configured() is False

    def test_returns_true_when_both_set(self):
        from api.routers.metabase import _is_metabase_configured
        with patch.dict(os.environ, {
            "METABASE_SECRET_KEY": "key",
            "METABASE_SITE_URL": "http://localhost:3002",
        }):
            assert _is_metabase_configured() is True
