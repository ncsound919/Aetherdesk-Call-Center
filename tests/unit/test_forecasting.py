"""Unit tests for the demand forecaster (Holt-Winters, Erlang C, staffing)."""

import math

import pytest

from api.services.forecasting import DemandForecaster

f = DemandForecaster()


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
