"""Unit tests for api.services.qa_scoring.QAScore."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from api.services.qa_scoring import qa_engine


class TestQAScore:
    def test_default_criteria_present(self):
        names = [c["name"] for c in qa_engine.default_criteria]
        assert names == [
            "greeting",
            "listening",
            "knowledge",
            "resolution",
            "closing",
            "compliance",
        ]
        assert sum(c["weight"] for c in qa_engine.default_criteria) == 100

    @pytest.mark.asyncio
    async def test_score_call(self):
        with patch(
            "api.services.db_wfm.create_qa_score_db",
            new_callable=AsyncMock,
            return_value={"id": "qs1"},
        ) as mock_create:
            result = await qa_engine.score_call(
                "t1", "c1", "a1", "r1", "rb1", {"greeting": 5}, "notes"
            )
        mock_create.assert_awaited_once_with(
            "t1", "c1", "a1", "r1", "rb1", {"greeting": 5}, "notes"
        )
        assert result == {"id": "qs1"}

    @pytest.mark.asyncio
    async def test_get_agent_summary(self):
        with patch(
            "api.services.db_wfm.get_agent_qa_summary_db",
            new_callable=AsyncMock,
            return_value={"avg_score": 85.0},
        ) as mock_summary:
            result = await qa_engine.get_agent_summary("a1")
        mock_summary.assert_awaited_once_with("a1")
        assert result["avg_score"] == 85.0

    @pytest.mark.asyncio
    async def test_get_tenant_stats_empty(self):
        with patch(
            "api.services.db_wfm.list_qa_scores_db",
            new_callable=AsyncMock,
            return_value=[],
        ) as mock_list:
            result = await qa_engine.get_tenant_stats("t1")
        mock_list.assert_awaited_once_with("t1", limit=10000)
        assert result == {
            "avg_score": 0.0,
            "total_reviewed": 0,
            "score_distribution": {},
            "top_issues": [],
        }

    @pytest.mark.asyncio
    async def test_get_tenant_stats_with_scores(self):
        scores = [
            {"total_score": 10, "scores_per_criterion": {"greeting": 5, "empathy": 1}},
            {
                "total_score": 30,
                "scores_per_criterion": json.dumps({"greeting": 2, "empathy": 2}),
            },
            {"total_score": 50, "scores_per_criterion": {"empathy": 2}},
            {"total_score": 70, "scores_per_criterion": {"greeting": 5, "empathy": 5}},
            {"total_score": 90, "scores_per_criterion": "bad-json{"},
            {"total_score": 100, "scores_per_criterion": None},
        ]
        with patch(
            "api.services.db_wfm.list_qa_scores_db",
            new_callable=AsyncMock,
            return_value=scores,
        ):
            result = await qa_engine.get_tenant_stats("t1")
        assert result["total_reviewed"] == 6
        assert result["avg_score"] == 58.33
        assert result["score_distribution"] == {
            "0-20": 1,
            "20-40": 1,
            "40-60": 1,
            "60-80": 1,
            "80-100": 2,
        }
        # greeting avg = (5+2+0+5)/4 = 3.0 -> not an issue
        # empathy avg = (1+2+2+5)/4 = 2.5 -> issue
        assert result["top_issues"] == [{"criterion": "empathy", "avg_score": 2.5}]

    @pytest.mark.asyncio
    async def test_get_tenant_stats_issues_sorted_and_limited(self):
        # 6 criteria all weak -> issues sorted ascending, limited to 5
        scores = [
            {
                "total_score": 50,
                "scores_per_criterion": {
                    f"c{i}": 1 for i in range(6)
                },
            }
        ]
        with patch(
            "api.services.db_wfm.list_qa_scores_db",
            new_callable=AsyncMock,
            return_value=scores,
        ):
            result = await qa_engine.get_tenant_stats("t1")
        assert len(result["top_issues"]) == 5
        assert result["top_issues"][0]["avg_score"] <= result["top_issues"][-1][
            "avg_score"
        ]

    @pytest.mark.asyncio
    async def test_get_tenant_stats_scores_per_criterion_type_error(self):
        scores = [{"total_score": 50, "scores_per_criterion": 12345}]
        with patch(
            "api.services.db_wfm.list_qa_scores_db",
            new_callable=AsyncMock,
            return_value=scores,
        ):
            result = await qa_engine.get_tenant_stats("t1")
        assert result["total_reviewed"] == 1
        assert result["top_issues"] == []
