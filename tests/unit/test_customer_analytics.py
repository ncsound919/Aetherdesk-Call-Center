"""Unit tests for src/api/services/customer_analytics.py.

Covers the ``CustomerAnalyticsService`` business logic (cohort analysis,
customer journey, churn risk, lifetime value, aggregate metrics). All
``api.services.db_cdp`` primitives it calls are mocked; nothing touches a
real database.
"""

import re
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from api.services.customer_analytics import (
    CustomerAnalyticsService,
    customer_analytics_service,
)

NOW = datetime.now(UTC)


def _ago(days=0, hours=0):
    return (NOW - timedelta(days=days, hours=hours)).isoformat()


def _interaction(
    created_at,
    channel="voice",
    sentiment="neutral",
    duration=120,
    itype="call",
):
    return {
        "created_at": created_at,
        "channel": channel,
        "sentiment": sentiment,
        "duration_seconds": duration,
        "interaction_type": itype,
    }


@pytest.fixture
def svc():
    return CustomerAnalyticsService()


@pytest.fixture
def db_mocks():
    search = AsyncMock()
    interactions = AsyncMock()
    with patch(
        "api.services.customer_analytics.search_customers_db",
        new=search,
    ), patch(
        "api.services.customer_analytics.list_customer_interactions_db",
        new=interactions,
    ):
        yield search, interactions


@pytest.fixture
def module_service():
    return customer_analytics_service


class TestGetCohortAnalysis:
    @pytest.mark.asyncio
    async def test_empty_profiles(self, svc, db_mocks):
        search, _ = db_mocks
        search.return_value = []
        out = await svc.get_cohort_analysis("t1")
        assert out == {"cohort_period": "month", "metric": "retention", "cohorts": []}

    @pytest.mark.asyncio
    async def test_skips_profiles_without_interactions(self, svc, db_mocks):
        search, interactions = db_mocks
        search.return_value = [{"id": "c1"}, {"id": "c2"}]
        interactions.side_effect = [[], []]
        out = await svc.get_cohort_analysis("t1")
        assert out["cohorts"] == []

    @pytest.mark.asyncio
    async def test_skips_profiles_with_only_invalid_dates(self, svc, db_mocks):
        search, interactions = db_mocks
        search.return_value = [{"id": "c1"}]
        # "garbage" -> ValueError from fromisoformat; b"garbage" -> TypeError
        interactions.return_value = [
            {"created_at": "garbage"},
            {"created_at": b"garbage"},
        ]
        out = await svc.get_cohort_analysis("t1")
        assert out["cohorts"] == []

    @pytest.mark.asyncio
    async def test_mixed_valid_and_invalid_dates(self, svc, db_mocks):
        search, interactions = db_mocks
        search.return_value = [{"id": "c1"}]
        interactions.return_value = [
            {"created_at": "garbage"},
            _interaction(_ago(days=2)),
        ]
        out = await svc.get_cohort_analysis("t1")
        assert len(out["cohorts"]) == 1
        assert out["cohorts"][0]["total_customers"] == 1
        assert out["cohorts"][0]["active_customers"] == 1

    @pytest.mark.asyncio
    async def test_accepts_z_suffixed_timestamps(self, svc, db_mocks):
        search, interactions = db_mocks
        search.return_value = [{"id": "c1"}]
        created = (NOW - timedelta(days=5)).isoformat().replace("+00:00", "Z")
        interactions.return_value = [{"created_at": created}]
        out = await svc.get_cohort_analysis("t1")
        assert out["cohorts"][0]["total_customers"] == 1

    @pytest.mark.asyncio
    async def test_monthly_cohort_active_and_inactive(self, svc, db_mocks):
        search, interactions = db_mocks
        search.return_value = [{"id": "c1"}, {"id": "c2"}]
        interactions.side_effect = [
            [_interaction(_ago(days=5), sentiment="positive")],
            [_interaction(_ago(days=120))],
        ]
        out = await svc.get_cohort_analysis("t1")
        assert len(out["cohorts"]) == 2
        assert sum(c["total_customers"] for c in out["cohorts"]) == 2
        assert sum(c["active_customers"] for c in out["cohorts"]) == 1
        assert sum(c["retention_pct"] for c in out["cohorts"]) == 100.0

    @pytest.mark.asyncio
    async def test_weekly_cohort_key_format(self, svc, db_mocks):
        search, interactions = db_mocks
        search.return_value = [{"id": "c1"}]
        interactions.return_value = [_interaction(_ago(days=5))]
        out = await svc.get_cohort_analysis("t1", cohort_period="week")
        assert out["cohort_period"] == "week"
        key = out["cohorts"][0]["cohort"]
        assert re.fullmatch(r"\d{4}-W\d{2}", key)

    @pytest.mark.asyncio
    async def test_monthly_cohort_key_format(self, svc, db_mocks):
        search, interactions = db_mocks
        search.return_value = [{"id": "c1"}]
        interactions.return_value = [_interaction(_ago(days=5))]
        out = await svc.get_cohort_analysis("t1", metric="ltv")
        assert out["metric"] == "ltv"
        assert re.fullmatch(r"\d{4}-\d{2}", out["cohorts"][0]["cohort"])

    @pytest.mark.asyncio
    async def test_cohorts_sorted_by_key(self, svc, db_mocks):
        search, interactions = db_mocks
        search.return_value = [{"id": "c1"}, {"id": "c2"}]
        interactions.side_effect = [
            [_interaction(_ago(days=5))],
            [_interaction(_ago(days=150))],
        ]
        out = await svc.get_cohort_analysis("t1")
        keys = [c["cohort"] for c in out["cohorts"]]
        assert keys == sorted(keys)


class TestGetCustomerJourney:
    @pytest.mark.asyncio
    async def test_no_interactions(self, svc, db_mocks):
        _, interactions = db_mocks
        interactions.return_value = []
        out = await svc.get_customer_journey("t1", "c1")
        assert out == {"customer_id": "c1", "stages": [], "total_interactions": 0}

    @pytest.mark.asyncio
    async def test_sorts_and_builds_stages(self, svc, db_mocks):
        _, interactions = db_mocks
        # deliberately out of chronological order
        interactions.return_value = [
            _interaction(_ago(days=3), channel="voice", sentiment="positive"),
            _interaction(_ago(days=100), channel="web", sentiment="negative"),
            _interaction(_ago(days=10), channel="email", sentiment="neutral"),
        ]
        out = await svc.get_customer_journey("t1", "c1")
        assert out["total_interactions"] == 3
        assert out["first_touch"]["channel"] == "web"
        assert out["last_touch"]["channel"] == "voice"
        assert out["conversion_count"] == 1
        assert [s["channel"] for s in out["stages"]] == ["web", "email", "voice"]

    @pytest.mark.asyncio
    async def test_defaults_for_missing_fields(self, svc, db_mocks):
        _, interactions = db_mocks
        interactions.return_value = [{"created_at": _ago(days=1)}]
        out = await svc.get_customer_journey("t1", "c1")
        stage = out["stages"][0]
        assert stage["stage"] == "unknown"
        assert stage["channel"] == "voice"
        assert stage["sentiment"] == "neutral"


class TestGetChurnRisk:
    @pytest.mark.asyncio
    async def test_no_interactions_high_risk(self, svc, db_mocks):
        _, interactions = db_mocks
        interactions.return_value = []
        out = await svc.get_churn_risk("t1", "c1")
        assert out["churn_risk"] == "high"
        assert out["churn_probability"] == 0.8
        assert out["factors"] == ["no_interactions"]

    @pytest.mark.asyncio
    async def test_no_valid_dates_high_risk(self, svc, db_mocks):
        _, interactions = db_mocks
        interactions.return_value = [{"created_at": "garbage"}]
        out = await svc.get_churn_risk("t1", "c1")
        assert out["churn_risk"] == "high"
        assert out["churn_probability"] == 0.7
        assert "no_dates" in out["factors"]

    @pytest.mark.asyncio
    async def test_recent_positive_low_risk(self, svc, db_mocks):
        _, interactions = db_mocks
        interactions.return_value = [
            _interaction(_ago(days=2), sentiment="positive"),
            _interaction(_ago(days=3), sentiment="positive"),
        ]
        out = await svc.get_churn_risk("t1", "c1")
        assert out["churn_risk"] == "low"
        assert out["churn_probability"] == 0.0
        assert out["factors"] == []
        assert out["negative_sentiment_ratio"] == 0.0

    @pytest.mark.asyncio
    async def test_medium_risk_with_frequency_factor(self, svc, db_mocks):
        _, interactions = db_mocks
        interactions.return_value = [_interaction(_ago(days=40))]
        out = await svc.get_churn_risk("t1", "c1")
        assert out["churn_risk"] == "medium"
        assert "inactive_over_30_days" in out["factors"]
        assert "low_interaction_frequency" in out["factors"]
        assert "inactive_over_60_days" not in out["factors"]

    @pytest.mark.asyncio
    async def test_boundary_30_days_no_inactive_factor(self, svc, db_mocks):
        _, interactions = db_mocks
        interactions.return_value = [_interaction(_ago(days=30))]
        out = await svc.get_churn_risk("t1", "c1")
        assert "inactive_over_30_days" not in out["factors"]
        assert "low_interaction_frequency" in out["factors"]
        assert out["churn_probability"] == 0.3

    @pytest.mark.asyncio
    async def test_high_risk_all_factors_and_capped_at_95(self, svc, db_mocks):
        _, interactions = db_mocks
        interactions.return_value = [
            _interaction(_ago(days=200), sentiment="negative"),
            _interaction(_ago(days=201), sentiment="negative"),
        ]
        out = await svc.get_churn_risk("t1", "c1")
        assert out["churn_risk"] == "high"
        assert out["churn_probability"] == 0.95
        assert "inactive_over_60_days" in out["factors"]
        assert "inactive_over_30_days" in out["factors"]
        assert "high_negative_sentiment" in out["factors"]
        assert "low_positive_sentiment" in out["factors"]

    @pytest.mark.asyncio
    async def test_medium_risk_30_to_60_days(self, svc, db_mocks):
        _, interactions = db_mocks
        interactions.return_value = [_interaction(_ago(days=45), sentiment="positive")]
        out = await svc.get_churn_risk("t1", "c1")
        assert out["churn_risk"] == "medium"
        assert "inactive_over_30_days" in out["factors"]
        assert "inactive_over_60_days" not in out["factors"]


class TestGetLifetimeValue:
    @pytest.mark.asyncio
    async def test_no_interactions(self, svc, db_mocks):
        _, interactions = db_mocks
        interactions.return_value = []
        out = await svc.get_lifetime_value("t1", "c1")
        assert out == {"customer_id": "c1", "estimated_ltv": 0, "total_interactions": 0}

    @pytest.mark.asyncio
    async def test_computes_revenue_and_ltv(self, svc, db_mocks):
        _, interactions = db_mocks
        interactions.return_value = [
            _interaction(_ago(days=1), duration=600),
            _interaction(_ago(days=3), duration=300),
        ]
        out = await svc.get_lifetime_value("t1", "c1")
        assert out["total_minutes"] == 15.0
        assert out["estimated_revenue"] == 7.5
        assert out["estimated_ltv"] == 11.25
        # span = 2 days -> (7.5 / 2) * 30
        assert out["monthly_value"] == 112.5

    @pytest.mark.asyncio
    async def test_single_interaction_span_floored_at_one(self, svc, db_mocks):
        _, interactions = db_mocks
        interactions.return_value = [_interaction(_ago(days=2), duration=120)]
        out = await svc.get_lifetime_value("t1", "c1")
        assert out["total_minutes"] == 2.0
        assert out["monthly_value"] == 30.0  # (1.0 / 1) * 30

    @pytest.mark.asyncio
    async def test_no_valid_dates_monthly_value_zero(self, svc, db_mocks):
        _, interactions = db_mocks
        interactions.return_value = [
            {"duration_seconds": 600, "created_at": "garbage"}
        ]
        out = await svc.get_lifetime_value("t1", "c1")
        assert out["total_minutes"] == 10.0
        assert out["estimated_revenue"] == 5.0
        assert out["monthly_value"] == 0


class TestGetAggregateMetrics:
    @pytest.mark.asyncio
    async def test_empty(self, svc, db_mocks):
        search, _ = db_mocks
        search.return_value = []
        out = await svc.get_aggregate_metrics("t1")
        assert out["total_customers"] == 0
        assert out["avg_lifetime_calls"] == 0.0
        assert out["total_lifetime_calls"] == 0
        assert out["period"] == "30d"

    @pytest.mark.asyncio
    async def test_default_30d_period(self, svc, db_mocks):
        search, interactions = db_mocks
        search.return_value = [{"id": "c1"}, {"id": "c2"}]
        interactions.side_effect = [
            [
                _interaction(_ago(days=3), channel="voice"),
                _interaction(_ago(days=4), channel="email"),
            ],
            [_interaction(_ago(days=40), channel="voice")],
        ]
        out = await svc.get_aggregate_metrics("t1")
        assert out["total_customers"] == 2
        assert out["active_customers"] == 1
        assert out["new_customers"] == 1
        assert out["returning_customers"] == 0
        assert out["total_lifetime_calls"] == 2  # c1: 1 voice + c2: 1 voice
        assert out["avg_lifetime_calls"] == 1.0

    @pytest.mark.asyncio
    async def test_7d_period_counts_only_recent(self, svc, db_mocks):
        search, interactions = db_mocks
        search.return_value = [{"id": "c1"}, {"id": "c2"}]
        interactions.side_effect = [
            [_interaction(_ago(days=3), channel="voice")],
            [_interaction(_ago(days=60), channel="voice")],
        ]
        out = await svc.get_aggregate_metrics("t1", period="7d")
        assert out["active_customers"] == 1
        assert out["new_customers"] == 1
        assert out["total_lifetime_calls"] == 2

    @pytest.mark.asyncio
    async def test_90d_period_returning_customers(self, svc, db_mocks):
        search, interactions = db_mocks
        # c1: recent (active + new), c2: first seen 100d ago but active in 90d
        search.return_value = [{"id": "c1"}, {"id": "c2"}]
        interactions.side_effect = [
            [_interaction(_ago(days=3), channel="voice")],
            [
                _interaction(_ago(days=40), channel="voice"),
                _interaction(_ago(days=100), channel="web"),
            ],
        ]
        out = await svc.get_aggregate_metrics("t1", period="90d")
        assert out["active_customers"] == 2
        assert out["new_customers"] == 1
        assert out["returning_customers"] == 1

    @pytest.mark.asyncio
    async def test_skips_profiles_without_interactions(self, svc, db_mocks):
        search, interactions = db_mocks
        search.return_value = [{"id": "c1"}]
        interactions.return_value = []
        out = await svc.get_aggregate_metrics("t1")
        assert out["active_customers"] == 0
        assert out["total_lifetime_calls"] == 0

    @pytest.mark.asyncio
    async def test_bad_dates_skipped(self, svc, db_mocks):
        search, interactions = db_mocks
        search.return_value = [{"id": "c1"}]
        interactions.return_value = [{"created_at": "garbage", "channel": "voice"}]
        out = await svc.get_aggregate_metrics("t1")
        assert out["active_customers"] == 0
        # voice channel still counted even when dates are unparseable
        assert out["total_lifetime_calls"] == 1

    @pytest.mark.asyncio
    async def test_module_singleton_is_instance(self, module_service):
        assert isinstance(module_service, CustomerAnalyticsService)
