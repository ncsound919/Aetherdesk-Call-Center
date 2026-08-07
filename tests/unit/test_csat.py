"""Unit tests for CSAT / NPS / sentiment pure logic."""

import pytest
from unittest.mock import AsyncMock, patch

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


@pytest.mark.asyncio
async def test_create_survey_delegates_to_db():
    with patch(
        "api.services.db_cx.create_survey_db", new_callable=AsyncMock, return_value={"id": 1}
    ) as mock_db:
        result = await csat_engine.create_survey(
            "T-1", call_id="C-1", customer_id="CU-1", rating=4, feedback="good", channel="chat"
        )
    mock_db.assert_awaited_once_with(
        "T-1", call_id="C-1", customer_id="CU-1", rating=4, feedback="good", channel="chat"
    )
    assert result == {"id": 1}


@pytest.mark.asyncio
async def test_get_survey_response_rate_delegates_to_db():
    with patch(
        "api.services.db_cx.get_response_rate_db", new_callable=AsyncMock, return_value={"rate": 0.4}
    ) as mock_db:
        result = await csat_engine.get_survey_response_rate("T-1", start_date="2026-01-01", end_date="2026-01-31")
    mock_db.assert_awaited_once_with("T-1", start_date="2026-01-01", end_date="2026-01-31")
    assert result == {"rate": 0.4}


@pytest.mark.asyncio
async def test_get_csat_score_delegates_to_db():
    with patch(
        "api.services.db_cx.get_csat_score_db", new_callable=AsyncMock, return_value={"score": 4.5}
    ) as mock_db:
        result = await csat_engine.get_csat_score("T-1")
    mock_db.assert_awaited_once_with("T-1", start_date=None, end_date=None)
    assert result == {"score": 4.5}


@pytest.mark.asyncio
async def test_get_sentiment_trends_delegates_to_db():
    with patch(
        "api.services.db_cx.get_sentiment_trends_db", new_callable=AsyncMock, return_value=[{"day": "d1"}]
    ) as mock_db:
        result = await csat_engine.get_sentiment_trends("T-1", granularity="week")
    mock_db.assert_awaited_once_with("T-1", start_date=None, end_date=None, granularity="week")
    assert result == [{"day": "d1"}]


@pytest.mark.asyncio
async def test_get_nps_score_delegates_to_db():
    with patch(
        "api.services.db_cx.get_nps_score_db", new_callable=AsyncMock, return_value={"nps": 55}
    ) as mock_db:
        result = await csat_engine.get_nps_score("T-1")
    mock_db.assert_awaited_once_with("T-1", start_date=None, end_date=None)
    assert result == {"nps": 55}


@pytest.mark.asyncio
async def test_get_customer_360_delegates_to_db():
    with patch(
        "api.services.db_cx.get_customer_360_db", new_callable=AsyncMock, return_value={"customer_id": "CU-1"}
    ) as mock_db:
        result = await csat_engine.get_customer_360("T-1", "CU-1")
    mock_db.assert_awaited_once_with("T-1", "CU-1")
    assert result == {"customer_id": "CU-1"}
