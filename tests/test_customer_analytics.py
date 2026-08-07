"""Tests for src/api/services/customer_analytics.py — CustomerAnalyticsService."""

import asyncio
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import api.services.customer_analytics as ca  # noqa: E402

NOW = datetime.now(UTC)
RECENT = (NOW - timedelta(days=3)).isoformat()
OLD = (NOW - timedelta(days=120)).isoformat()


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def svc():
    return ca.CustomerAnalyticsService()


def _interaction(created_at=RECENT, channel="voice", sentiment="neutral", duration=120):
    return {
        "created_at": created_at,
        "channel": channel,
        "sentiment": sentiment,
        "duration_seconds": duration,
        "interaction_type": "call",
    }


@pytest.fixture
def mocks(monkeypatch):
    search = AsyncMock()
    interactions = AsyncMock()
    monkeypatch.setattr(ca, "search_customers_db", search)
    monkeypatch.setattr(ca, "list_customer_interactions_db", interactions)
    return search, interactions


class TestCohortAnalysis:
    def test_empty_profiles(self, svc, mocks):
        search, _ = mocks
        search.return_value = []
        out = run(svc.get_cohort_analysis("t1"))
        assert out["cohorts"] == []
        assert out["cohort_period"] == "month"

    def test_monthly_cohort_with_active_and_inactive(self, svc, mocks):
        search, interactions = mocks
        search.return_value = [{"id": "c1"}, {"id": "c2"}]
        interactions.side_effect = [
            [_interaction(RECENT, sentiment="positive")],
            [_interaction(OLD)],
        ]
        out = run(svc.get_cohort_analysis("t1"))
        assert len(out["cohorts"]) == 2
        assert sum(c["total_customers"] for c in out["cohorts"]) == 2
        assert sum(c["active_customers"] for c in out["cohorts"]) == 1

    def test_weekly_cohort_and_bad_dates(self, svc, mocks):
        search, interactions = mocks
        search.return_value = [{"id": "c1"}]
        interactions.return_value = [_interaction("not-a-date"), _interaction(RECENT)]
        out = run(svc.get_cohort_analysis("t1", cohort_period="week"))
        assert len(out["cohorts"]) == 1
        assert out["cohorts"][0]["total_customers"] == 1

    def test_skips_customers_without_dates(self, svc, mocks):
        search, interactions = mocks
        search.return_value = [{"id": "c1"}]
        interactions.return_value = [{"created_at": "garbage"}]
        out = run(svc.get_cohort_analysis("t1"))
        assert out["cohorts"] == []

    def test_skips_profiles_without_interactions(self, svc, mocks):
        search, interactions = mocks
        search.return_value = [{"id": "c1"}]
        interactions.return_value = []
        out = run(svc.get_cohort_analysis("t1"))
        assert out["cohorts"] == []


class TestCustomerJourney:
    def test_no_interactions(self, svc, mocks):
        _, interactions = mocks
        interactions.return_value = []
        out = run(svc.get_customer_journey("t1", "c1"))
        assert out["stages"] == []
        assert out["total_interactions"] == 0

    def test_journey_builds_stages(self, svc, mocks):
        _, interactions = mocks
        interactions.return_value = [
            _interaction(RECENT, channel="voice", sentiment="positive"),
            _interaction(OLD, channel="web", sentiment="negative"),
        ]
        out = run(svc.get_customer_journey("t1", "c1"))
        assert out["total_interactions"] == 2
        assert out["conversion_count"] == 1  # one voice stage
        assert out["first_touch"]["channel"] == "web"
        assert out["last_touch"]["channel"] == "voice"


class TestChurnRisk:
    def test_no_interactions_high_risk(self, svc, mocks):
        _, interactions = mocks
        interactions.return_value = []
        out = run(svc.get_churn_risk("t1", "c1"))
        assert out["churn_risk"] == "high"
        assert out["churn_probability"] == 0.8

    def test_bad_dates_high_risk(self, svc, mocks):
        _, interactions = mocks
        interactions.return_value = [{"created_at": "garbage"}]
        out = run(svc.get_churn_risk("t1", "c1"))
        assert out["churn_risk"] == "high"
        assert "no_dates" in out["factors"]

    def test_recent_positive_low_risk(self, svc, mocks):
        _, interactions = mocks
        interactions.return_value = [
            _interaction(RECENT, sentiment="positive"),
            _interaction(RECENT, sentiment="positive"),
        ]
        out = run(svc.get_churn_risk("t1", "c1"))
        assert out["churn_risk"] == "low"

    def test_old_negative_high_risk(self, svc, mocks):
        _, interactions = mocks
        interactions.return_value = [
            _interaction(OLD, sentiment="negative"),
            _interaction(OLD, sentiment="negative"),
        ]
        out = run(svc.get_churn_risk("t1", "c1"))
        assert out["churn_risk"] == "high"
        assert "inactive_over_60_days" in out["factors"]
        assert "high_negative_sentiment" in out["factors"]

    def test_medium_risk(self, svc, mocks):
        from datetime import timedelta

        _, interactions = mocks
        forty_days = (NOW - timedelta(days=40)).isoformat()
        interactions.return_value = [_interaction(forty_days)]
        out = run(svc.get_churn_risk("t1", "c1"))
        assert out["churn_risk"] == "medium"
        assert "inactive_over_30_days" in out["factors"]
        assert "low_interaction_frequency" in out["factors"]


class TestLifetimeValue:
    def test_no_interactions(self, svc, mocks):
        _, interactions = mocks
        interactions.return_value = []
        out = run(svc.get_lifetime_value("t1", "c1"))
        assert out["estimated_ltv"] == 0

    def test_with_durations(self, svc, mocks):
        _, interactions = mocks
        interactions.return_value = [
            _interaction(RECENT, duration=600),  # 10 minutes
            _interaction((NOW - timedelta(days=1)).isoformat(), duration=300),  # 5 min
        ]
        out = run(svc.get_lifetime_value("t1", "c1"))
        assert out["total_minutes"] == 15.0
        assert out["estimated_revenue"] == 7.5
        assert out["estimated_ltv"] == 11.25

    def test_no_valid_dates(self, svc, mocks):
        _, interactions = mocks
        interactions.return_value = [{"duration_seconds": 600, "created_at": "garbage"}]
        out = run(svc.get_lifetime_value("t1", "c1"))
        assert out["total_minutes"] == 10.0
        assert out["monthly_value"] == 0


class TestAggregateMetrics:
    def test_empty(self, svc, mocks):
        search, _ = mocks
        search.return_value = []
        out = run(svc.get_aggregate_metrics("t1"))
        assert out["total_customers"] == 0
        assert out["avg_lifetime_calls"] == 0.0

    def test_periods_and_counts(self, svc, mocks):
        search, interactions = mocks
        search.return_value = [{"id": "c1"}, {"id": "c2"}, {"id": "c3"}]
        interactions.side_effect = [
            [_interaction(RECENT, channel="voice")],  # c1 active+new, 1 call
            [_interaction(OLD, channel="web")],  # c2 old, no voice
            [],  # c3 no interactions
        ]
        out = run(svc.get_aggregate_metrics("t1", period="30d"))
        assert out["total_customers"] == 3
        assert out["active_customers"] == 1
        assert out["new_customers"] == 1
        assert out["returning_customers"] == 0
        assert out["total_lifetime_calls"] == 1

    def test_90d_period(self, svc, mocks):
        search, interactions = mocks
        search.return_value = [{"id": "c1"}]
        interactions.return_value = [_interaction(RECENT)]
        out = run(svc.get_aggregate_metrics("t1", period="90d"))
        assert out["active_customers"] == 1

    def test_7d_period(self, svc, mocks):
        search, interactions = mocks
        search.return_value = [{"id": "c1"}]
        interactions.return_value = [_interaction(RECENT)]
        out = run(svc.get_aggregate_metrics("t1", period="7d"))
        assert out["active_customers"] == 1

    def test_profile_with_bad_dates(self, svc, mocks):
        search, interactions = mocks
        search.return_value = [{"id": "c1"}]
        interactions.return_value = [{"created_at": "garbage", "channel": "voice"}]
        out = run(svc.get_aggregate_metrics("t1"))
        assert out["active_customers"] == 0
