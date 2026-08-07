"""Unit tests for api.routers.cx."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers.cx import router
from api.services.auth import verify_tenant_access


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router)

    async def _override_verify_tenant_access(tenant_id: str = "TENANT-001"):
        return tenant_id

    app.dependency_overrides[verify_tenant_access] = _override_verify_tenant_access
    with TestClient(app) as c:
        yield c


class TestCreateSurvey:
    def test_success(self, client):
        expected = {"id": "s1", "rating": 5}
        with patch(
            "api.routers.cx.csat_engine.create_survey",
            new_callable=AsyncMock,
            return_value=expected,
        ) as m:
            resp = client.post(
                "/cx/csat/surveys",
                json={
                    "call_id": "C1",
                    "customer_id": "CU1",
                    "rating": 5,
                    "feedback": "Great",
                    "channel": "voice",
                },
            )
        assert resp.status_code == 200
        assert resp.json() == expected
        m.assert_awaited_once_with(
            "TENANT-001",
            call_id="C1",
            customer_id="CU1",
            rating=5,
            feedback="Great",
            channel="voice",
        )

    def test_minimal_survey(self, client):
        with patch(
            "api.routers.cx.csat_engine.create_survey",
            new_callable=AsyncMock,
            return_value={"id": "s2"},
        ) as m:
            resp = client.post("/cx/csat/surveys", json={"rating": 3})
        assert resp.status_code == 200
        m.assert_awaited_once_with(
            "TENANT-001",
            call_id=None,
            customer_id=None,
            rating=3,
            feedback=None,
            channel="voice",
        )

    def test_missing_rating_422(self, client):
        resp = client.post("/cx/csat/surveys", json={"call_id": "C1"})
        assert resp.status_code == 422


class TestListSurveys:
    def test_defaults(self, client):
        with patch(
            "api.routers.cx.list_surveys_db", new_callable=AsyncMock, return_value=[]
        ) as m:
            resp = client.get("/cx/csat/surveys")
        assert resp.status_code == 200
        assert resp.json() == []
        m.assert_awaited_once_with(
            "TENANT-001",
            limit=50,
            offset=0,
            min_rating=None,
            channel=None,
            start_date=None,
            end_date=None,
        )

    def test_with_filters(self, client):
        with patch(
            "api.routers.cx.list_surveys_db",
            new_callable=AsyncMock,
            return_value=[{"id": 1}],
        ) as m:
            resp = client.get(
                "/cx/csat/surveys?limit=20&offset=10&min_rating=4&channel=sms&start_date=2026-01-01&end_date=2026-01-31"
            )
        assert resp.status_code == 200
        m.assert_awaited_once_with(
            "TENANT-001",
            limit=20,
            offset=10,
            min_rating=4,
            channel="sms",
            start_date="2026-01-01",
            end_date="2026-01-31",
        )

    def test_invalid_rating_422(self, client):
        resp = client.get("/cx/csat/surveys?min_rating=6")
        assert resp.status_code == 422


class TestGetCsatScore:
    def test_success(self, client):
        with patch(
            "api.routers.cx.get_csat_score_db",
            new_callable=AsyncMock,
            return_value={"score": 4.2},
        ) as m:
            resp = client.get("/cx/csat/score")
        assert resp.status_code == 200
        assert resp.json() == {"score": 4.2}
        m.assert_awaited_once_with("TENANT-001", start_date=None, end_date=None)


class TestGetResponseRate:
    def test_success(self, client):
        with patch(
            "api.routers.cx.get_response_rate_db",
            new_callable=AsyncMock,
            return_value={"rate": 0.4},
        ) as m:
            resp = client.get("/cx/csat/response-rate")
        assert resp.status_code == 200
        assert resp.json() == {"rate": 0.4}
        m.assert_awaited_once_with("TENANT-001", start_date=None, end_date=None)


class TestGetNps:
    def test_success(self, client):
        with patch(
            "api.routers.cx.get_nps_score_db",
            new_callable=AsyncMock,
            return_value={"nps": 55},
        ) as m:
            resp = client.get("/cx/csat/nps")
        assert resp.status_code == 200
        assert resp.json() == {"nps": 55}
        m.assert_awaited_once_with("TENANT-001", start_date=None, end_date=None)


class TestGetSentimentTrends:
    def test_success(self, client):
        with patch(
            "api.routers.cx.get_sentiment_trends_db",
            new_callable=AsyncMock,
            return_value=[{"sentiment": "positive"}],
        ) as m:
            resp = client.get("/cx/sentiment/trends")
        assert resp.status_code == 200
        assert resp.json() == [{"sentiment": "positive"}]
        m.assert_awaited_once_with(
            "TENANT-001", start_date=None, end_date=None, granularity="day"
        )

    def test_invalid_granularity_422(self, client):
        resp = client.get("/cx/sentiment/trends?granularity=week")
        assert resp.status_code == 422


class TestGetCustomer360:
    def test_success(self, client):
        with patch(
            "api.routers.cx.get_customer_360_db",
            new_callable=AsyncMock,
            return_value={"customer_id": "CU1"},
        ) as m:
            resp = client.get("/cx/customers/CU1/360")
        assert resp.status_code == 200
        assert resp.json() == {"customer_id": "CU1"}
        m.assert_awaited_once_with("TENANT-001", "CU1")


class TestGetCxSummary:
    def test_aggregates_trends(self, client):
        trends = [
            {"sentiment": "positive", "count": 10},
            {"sentiment": "neutral", "count": 5},
            {"sentiment": "negative", "count": 2},
            {"sentiment": "unknown", "count": 3},
            {"count": 1},
        ]
        with patch(
            "api.routers.cx.get_csat_score_db",
            new_callable=AsyncMock,
            return_value=4.5,
        ), patch(
            "api.routers.cx.get_nps_score_db",
            new_callable=AsyncMock,
            return_value=50,
        ), patch(
            "api.routers.cx.get_response_rate_db",
            new_callable=AsyncMock,
            return_value=0.3,
        ), patch(
            "api.routers.cx.get_sentiment_trends_db",
            new_callable=AsyncMock,
            return_value=trends,
        ) as trends_mock:
            resp = client.get("/cx/summary")
        assert resp.status_code == 200
        body = resp.json()
        assert body["csat"] == 4.5
        assert body["nps"] == 50
        assert body["response_rate"] == 0.3
        assert body["sentiment_distribution"] == {
            "positive": 10,
            "neutral": 6,
            "negative": 2,
            "unknown": 3,
        }
        assert body["total_interactions"] == 21
        trends_mock.assert_awaited_once_with(
            "TENANT-001", start_date=None, end_date=None, granularity="day"
        )

    def test_summary_empty_trends(self, client):
        with patch(
            "api.routers.cx.get_csat_score_db", new_callable=AsyncMock, return_value=0
        ), patch(
            "api.routers.cx.get_nps_score_db", new_callable=AsyncMock, return_value=0
        ), patch(
            "api.routers.cx.get_response_rate_db", new_callable=AsyncMock, return_value=0
        ), patch(
            "api.routers.cx.get_sentiment_trends_db", new_callable=AsyncMock, return_value=[]
        ):
            resp = client.get("/cx/summary")
        assert resp.status_code == 200
        body = resp.json()
        assert body["sentiment_distribution"] == {
            "positive": 0,
            "neutral": 0,
            "negative": 0,
        }
        assert body["total_interactions"] == 0
