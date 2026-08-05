"""Unit tests for CSAT / NPS / sentiment pure logic."""

import pytest

from api.services.csat import csat_engine


def test_nps_score_mixed_ratings():
    counts = {10: 5, 9: 5, 8: 2, 7: 2, 6: 2, 5: 1}
    result = csat_engine.nps_score(counts)
    assert result["promoters"] == 10
    assert result["detractors"] == 3
    assert result["passives"] == 4
    assert result["total"] == 17
    assert result["nps"] == round((10 - 3) / 17 * 100, 1)


def test_nps_score_all_detractors():
    result = csat_engine.nps_score({1: 5, 2: 3})
    assert result["nps"] == -100.0
    assert result["promoters"] == 0


def test_nps_score_empty_is_zero():
    result = csat_engine.nps_score({})
    assert result["nps"] == 0
    assert result["promoters"] == 0
    assert result["detractors"] == 0


def test_nps_score_all_promoters():
    result = csat_engine.nps_score({10: 10})
    assert result["nps"] == 100.0
    assert result["detractors"] == 0


def test_calculate_response_rate():
    assert csat_engine.calculate_response_rate(5, 10) == 50.0
    assert csat_engine.calculate_response_rate(0, 10) == 0.0


def test_calculate_response_rate_zero_total():
    assert csat_engine.calculate_response_rate(5, 0) == 0.0


def test_aggregate_sentiment_empty():
    result = csat_engine.aggregate_sentiment([])
    assert result["dominant"] == "neutral"
    assert result["distribution"] == {}


def test_aggregate_sentiment_dominant():
    result = csat_engine.aggregate_sentiment(["positive", "positive", "negative", "positive"])
    assert result["dominant"] == "positive"
    assert result["total"] == 4
    assert result["distribution"] == {"positive": 3, "negative": 1}


def test_aggregate_sentiment_tie_picks_most_common():
    result = csat_engine.aggregate_sentiment(["positive", "negative"])
    assert result["dominant"] in ("positive", "negative")
    assert result["total"] == 2
