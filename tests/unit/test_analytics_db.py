"""Tests for ClickHouse analytics database service."""

import os
import json
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta


@pytest.fixture(autouse=True)
def reset_clickhouse():
    """Reset singleton state before each test."""
    import api.services.analytics_db as mod
    mod._client = None
    mod._initialized = False
    yield
    mod._client = None
    mod._initialized = False


class TestIsClickhouseEnabled:
    def test_returns_false_when_not_set(self):
        from api.services.analytics_db import is_clickhouse_enabled
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("CLICKHOUSE_HOST", None)
            assert is_clickhouse_enabled() is False

    def test_returns_true_when_set(self):
        from api.services.analytics_db import is_clickhouse_enabled
        with patch.dict(os.environ, {"CLICKHOUSE_HOST": "localhost"}):
            assert is_clickhouse_enabled() is True


class TestGetClickhouse:
    def test_returns_none_when_not_enabled(self):
        from api.services.analytics_db import get_clickhouse
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("CLICKHOUSE_HOST", None)
            assert get_clickhouse() is None

    def test_returns_none_when_import_fails(self):
        from api.services.analytics_db import get_clickhouse
        with patch.dict(os.environ, {"CLICKHOUSE_HOST": "localhost"}):
            with patch("builtins.__import__", side_effect=ImportError("no module")):
                assert get_clickhouse() is None

    def test_returns_none_on_connection_error(self):
        from api.services.analytics_db import get_clickhouse
        with patch.dict(os.environ, {"CLICKHOUSE_HOST": "localhost"}):
            mock_ch = MagicMock()
            mock_ch.get_client.side_effect = Exception("conn refused")
            with patch.dict("sys.modules", {"clickhouse_connect": mock_ch}):
                assert get_clickhouse() is None

    def test_caches_client(self):
        from api.services.analytics_db import get_clickhouse
        mock_client = MagicMock()
        import api.services.analytics_db as mod
        mod._client = mock_client
        # Should return the cached client without trying to connect
        assert get_clickhouse() is mock_client


class TestRecordCallEvent:
    def test_returns_false_when_not_enabled(self):
        from api.services.analytics_db import record_call_event
        result = record_call_event(
            call_id="call-1",
            tenant_id="tenant-1",
            agent_id="agent-1",
            direction="inbound",
            caller="+1234567890",
            called="+0987654321",
            started_at=datetime.utcnow(),
        )
        assert result is False

    def test_inserts_when_enabled(self):
        from api.services.analytics_db import record_call_event
        mock_client = MagicMock()
        import api.services.analytics_db as mod
        mod._client = mock_client

        result = record_call_event(
            call_id="call-1",
            tenant_id="tenant-1",
            agent_id="agent-1",
            direction="inbound",
            caller="+1234567890",
            called="+0987654321",
            started_at=datetime.utcnow(),
            duration_seconds=120.5,
            intent="billing",
            status="completed",
            satisfaction_score=0.9,
            tokens_used=150,
            cost_cents=5,
            metadata={"key": "value"},
        )
        assert result is True
        mock_client.insert.assert_called_once()
        # Verify the metadata is JSON-encoded
        call_args = mock_client.insert.call_args
        event_data = call_args[0][1][0]  # First row of data
        assert json.loads(event_data[14]) == {"key": "value"}  # metadata column


class TestQueryCallStats:
    def test_returns_mock_when_not_enabled(self):
        from api.services.analytics_db import query_call_stats
        now = datetime.utcnow()
        result = query_call_stats("tenant-1", now - timedelta(days=30), now)
        assert result["mock"] is True
        assert result["calls"] == 0

    def test_queries_when_enabled(self):
        from api.services.analytics_db import query_call_stats
        mock_client = MagicMock()
        mock_result = MagicMock()
        mock_result.first_row = (10, 10.0, 60.0, 8, 2, 0.85, 1500, 50)
        mock_client.query.return_value = mock_result

        import api.services.analytics_db as mod
        mod._client = mock_client

        now = datetime.utcnow()
        result = query_call_stats("tenant-1", now - timedelta(days=30), now)
        assert result["total_calls"] == 10
        assert result["total_minutes"] == 10.0
        assert result["completed"] == 8
        assert result["missed"] == 2


class TestQueryIntentDistribution:
    def test_returns_empty_when_not_enabled(self):
        from api.services.analytics_db import query_intent_distribution
        now = datetime.utcnow()
        result = query_intent_distribution("tenant-1", now - timedelta(days=30), now)
        assert result == []

    def test_queries_when_enabled(self):
        from api.services.analytics_db import query_intent_distribution
        mock_client = MagicMock()
        mock_result = MagicMock()
        mock_result.result_rows = [("billing", 50), ("support", 30), ("sales", 20)]
        mock_client.query.return_value = mock_result

        import api.services.analytics_db as mod
        mod._client = mock_client

        now = datetime.utcnow()
        result = query_intent_distribution("tenant-1", now - timedelta(days=30), now)
        assert len(result) == 3
        assert result[0]["intent"] == "billing"
        assert result[0]["count"] == 50


class TestQueryAgentPerformance:
    def test_returns_empty_when_not_enabled(self):
        from api.services.analytics_db import query_agent_performance
        now = datetime.utcnow()
        result = query_agent_performance("tenant-1", now - timedelta(days=30), now)
        assert result == []


class TestQueryHourlyVolume:
    def test_returns_empty_when_not_enabled(self):
        from api.services.analytics_db import query_hourly_volume
        now = datetime.utcnow()
        result = query_hourly_volume("tenant-1", now - timedelta(days=7), now)
        assert result == []

    def test_queries_when_enabled(self):
        from api.services.analytics_db import query_hourly_volume
        mock_client = MagicMock()
        mock_result = MagicMock()
        mock_result.result_rows = [
            (datetime(2024, 1, 1, 0, 0, 0), 5, 45.0),
            (datetime(2024, 1, 1, 1, 0, 0), 8, 52.3),
        ]
        mock_client.query.return_value = mock_result

        import api.services.analytics_db as mod
        mod._client = mock_client

        now = datetime.utcnow()
        result = query_hourly_volume("tenant-1", now - timedelta(days=7), now)
        assert len(result) == 2
        assert result[0]["calls"] == 5
        assert result[0]["avg_duration"] == 45.0
