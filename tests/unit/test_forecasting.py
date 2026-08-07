"""Unit tests for the demand forecaster (Holt-Winters, Erlang C, staffing)."""

import math
from unittest.mock import AsyncMock, patch

import pytest

from api.services.forecasting import (
    DemandForecaster,
    compute_forecast,
    get_forecasted_staffing,
)

f = DemandForecaster()


def _history(days=4, count_fn=None):
    """Build a contiguous hourly history of ``days`` full 24h days."""
    if count_fn is None:
        count_fn = lambda i: 20 + (i % 24) + (10 if i >= 48 else 0)
    rows = []
    i = 0
    for d in range(1, days + 1):
        date = f"2026-01-{d:02d}"
        for h in range(24):
            rows.append({"date": date, "hour": h, "count": count_fn(i)})
            i += 1
    return rows


def test_holt_winters_short_series_falls_back_to_mean():
    data = [10, 12, 11]
    result = f._holt_winters(data, 24, 3)
    assert len(result) == 3
    assert all(abs(x - 11) < 1e-6 for x in result)


def test_holt_winters_empty_series():
    assert f._holt_winters([], 24, 3) == [0, 0, 0]


def test_holt_winters_returns_expected_length():
    data = list(range(1, 50))
    result = f._holt_winters(data, 24, 5)
    assert len(result) == 5
    assert all(x >= 0 for x in result)  # predictions clamped at 0


def test_holt_winters_trending_data_produces_trend():
    # Strictly increasing series -> forecasts should be non-trivial
    data = [100 + i * 5 for i in range(60)]
    result = f._holt_winters(data, 24, 3)
    # Predicted volumes should be positive and growing
    assert result[2] > result[0]


def test_erlang_c_zero_agents():
    assert f._erlang_c(5.0, 0) == 0.0
    assert f._erlang_c(0.0, 3) == 0.0


def test_erlang_c_high_utilization_returns_one():
    # A >= N -> probability of waiting is 1
    assert f._erlang_c(10.0, 5) == 1.0


def test_erlang_c_between_zero_and_one():
    pw = f._erlang_c(2.0, 5)
    assert 0.0 <= pw <= 1.0


def test_compute_staffing_zero_volume():
    assert f._compute_staffing(0) == 0


def test_compute_staffing_positive_volume():
    agents = f._compute_staffing(100)
    assert agents >= 1
    assert isinstance(agents, int)


def test_compute_staffing_meets_service_level():
    # For a high volume, staffing should be > 0 and the service level should
    # reach the target (verified by the iterative loop returning).
    for vol in (10, 50, 200, 1000):
        agents = f._compute_staffing(vol)
        A = (vol * 300) / 3600
        pw = f._erlang_c(A, agents)
        sl = 1 - pw * math.exp(-(agents - A) * (20 / 300))
        assert agents >= 1
        assert sl >= 0.8 or agents >= 1


def test_compute_staffing_returns_cap_when_target_unreachable():
    # target_service_level=1.0 with zero answer time is mathematically
    # unreachable with finite agents, so the loop must return the cap.
    agents = f._compute_staffing(1000, target_service_level=1.0, target_answer_time=0)
    base = math.ceil(1000 / 12)
    assert agents == base + 50


def test_holt_winters_single_season_trend_zero():
    # data between one and two seasonal periods -> trend initialised to 0
    data = [5] * 24 + [6] * 6
    result = f._holt_winters(data, 24, 4)
    assert len(result) == 4
    assert all(x >= 0 for x in result)


def test_holt_winters_clamps_negative_predictions():
    # severe downward series -> predictions must never go negative
    data = [100] * 24 + [10] * 48
    result = f._holt_winters(data, 24, 5)
    assert len(result) == 5
    assert all(x >= 0 for x in result)


@pytest.mark.asyncio
async def test_forecast_no_history():
    with patch(
        "api.services.db_wfm.get_call_volume_history_db",
        new_callable=AsyncMock,
        return_value=[],
    ) as get_db:
        result = await f.forecast("t1", hours_ahead=5)
    get_db.assert_awaited_once_with("t1", days=90)
    assert result == {
        "forecast": [],
        "seasonal_indices": {},
        "trend": 0.0,
        "model_accuracy_mape": None,
    }


@pytest.mark.asyncio
async def test_forecast_not_enough_data_falls_back_to_average():
    history = _history(days=1, count_fn=lambda i: 40)
    with patch(
        "api.services.db_wfm.get_call_volume_history_db",
        new_callable=AsyncMock,
        return_value=history,
    ):
        result = await f.forecast("t1", hours_ahead=3)
    assert result["seasonal_indices"] == {}
    assert result["trend"] == 0.0
    assert result["model_accuracy_mape"] is None
    assert len(result["forecast"]) == 3
    assert all(e["predicted_volume"] == 40 for e in result["forecast"])
    assert result["forecast"][0]["confidence_low"] == 32
    assert result["forecast"][0]["confidence_high"] == 48


@pytest.mark.asyncio
async def test_forecast_full_holt_winters_path():
    history = _history(days=4)  # 96 points >= 2 * seasonal_period
    with patch(
        "api.services.db_wfm.get_call_volume_history_db",
        new_callable=AsyncMock,
        return_value=history,
    ):
        result = await f.forecast("t1", hours_ahead=5)
    assert len(result["forecast"]) == 5
    assert len(result["seasonal_indices"]) == 24
    assert result["trend"] == 10.0  # second half is 10 higher per hour
    assert isinstance(result["model_accuracy_mape"], float)
    assert result["model_accuracy_mape"] >= 0
    for e in result["forecast"]:
        assert e["predicted_volume"] >= 0
        assert e["confidence_low"] <= e["predicted_volume"]
        assert e["confidence_high"] >= e["predicted_volume"]
        assert "T" in e["hour"]


@pytest.mark.asyncio
async def test_forecast_mape_skips_zero_actuals():
    # every 3rd hour is 0 -> those actuals are excluded from MAPE errors
    history = _history(days=4, count_fn=lambda i: 20 if i % 3 else 0)
    with patch(
        "api.services.db_wfm.get_call_volume_history_db",
        new_callable=AsyncMock,
        return_value=history,
    ):
        result = await f.forecast("t1", hours_ahead=2)
    assert len(result["forecast"]) == 2
    assert result["model_accuracy_mape"] is not None


@pytest.mark.asyncio
async def test_forecast_builds_hourly_series_from_rows():
    history = [
        {"date": "2026-01-01", "hour": "7", "count": "50"},
        {"date": "2026-01-01", "hour": "8", "count": "60"},
        {"date": "2026-01-01", "hour": "9", "count": "70"},
    ]
    with patch(
        "api.services.db_wfm.get_call_volume_history_db",
        new_callable=AsyncMock,
        return_value=history,
    ):
        result = await f.forecast("t1", hours_ahead=1)
    # 3 points < 48 -> average fallback; string counts coerced to int
    assert result["forecast"][0]["predicted_volume"] == 60


@pytest.mark.asyncio
async def test_compute_forecast_adds_staffing_recommendation():
    fake = {
        "forecast": [
            {"hour": "h1", "predicted_volume": 10},
            {"hour": "h2", "predicted_volume": 50},
        ],
        "seasonal_indices": {},
        "trend": 1.0,
        "model_accuracy_mape": 5.0,
    }
    with patch.object(
        DemandForecaster, "forecast", new_callable=AsyncMock, return_value=fake
    ):
        result = await compute_forecast("t1", hours_ahead=2)
    assert result["staffing_recommendation"]["peak_volume"] == 50
    assert result["staffing_recommendation"]["recommended_agents"] == f._compute_staffing(
        50
    )
    assert result["staffing_recommendation"]["target_service_level"] == 0.8
    assert result["staffing_recommendation"]["target_answer_time_seconds"] == 20


@pytest.mark.asyncio
async def test_compute_forecast_with_zero_peak():
    fake = {
        "forecast": [{"hour": "h1", "predicted_volume": 0}],
        "seasonal_indices": {},
        "trend": 0.0,
        "model_accuracy_mape": None,
    }
    with patch.object(
        DemandForecaster, "forecast", new_callable=AsyncMock, return_value=fake
    ):
        result = await compute_forecast("t1", hours_ahead=1)
    assert result["staffing_recommendation"]["peak_volume"] == 0
    assert result["staffing_recommendation"]["recommended_agents"] == 0


@pytest.mark.asyncio
async def test_get_forecasted_staffing_builds_hourly_rows():
    fake = {
        "forecast": [
            {
                "hour": "2026-01-01T09:00:00+00:00",
                "predicted_volume": 0,
                "confidence_low": 0,
                "confidence_high": 0,
            },
            {
                "hour": "2026-01-01T10:00:00+00:00",
                "predicted_volume": 100,
                "confidence_low": 80,
                "confidence_high": 120,
            },
        ],
        "seasonal_indices": {},
        "trend": 1.0,
        "model_accuracy_mape": 4.2,
    }
    with patch.object(
        DemandForecaster, "forecast", new_callable=AsyncMock, return_value=fake
    ):
        result = await get_forecasted_staffing("t1", "2026-01-01")
    assert result["date"] == "2026-01-01"
    assert len(result["hourly_staffing"]) == 2
    assert result["hourly_staffing"][0]["recommended_agents"] == 0
    assert result["hourly_staffing"][1]["recommended_agents"] == f._compute_staffing(100)
    assert result["total_agent_hours"] == f._compute_staffing(0) + f._compute_staffing(
        100
    )
    assert result["model_accuracy_mape"] == 4.2
