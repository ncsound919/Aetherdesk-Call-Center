"""Unit tests for the conversation quality scoring service."""

from unittest.mock import patch

import pytest

from api.services.conversation_quality import ConversationQualityService

svc = ConversationQualityService()


def test_score_conversation_all_keywords_max():
    transcript = (
        "hello good morning good afternoon thank you for calling welcome welcome welcome "
        "let me explain in other words to clarify basically simply put what i mean is "
        "understand sorry apologize frustrating i hear you i can imagine i understand how "
        "let me help i will let me check the solution is here is what i have resolved "
        "please thank you you are welcome sir ma'am absolutely certainly certainly"
    )
    result = svc.score_conversation(transcript)
    assert result["total_score"] == 50
    assert result["percentage"] == 100.0
    assert result["rating"] == "excellent"
    assert all(v == 10 for v in result["criteria_scores"].values())


def test_score_conversation_empty_transcript_low_score():
    with patch("random.randint", return_value=1):
        result = svc.score_conversation("")
    assert result["total_score"] <= 20
    assert result["rating"] == "needs_improvement"


def test_score_conversation_partial_matches():
    transcript = "Hello there. I understand. Let me help you with that. Thank you."
    result = svc.score_conversation(transcript)
    assert result["percentage"] > 0
    assert result["rating"] in ("needs_improvement", "average", "good", "excellent")
    assert result["max_possible"] == 50
    assert result["rubric_name"] == "standard"


def test_score_criterion_matches_thresholds():
    # 5+ keyword matches -> max score
    kw = ["a", "b", "c", "d", "e", "f", "g"]
    assert svc._score_criterion("a b c d e f g", kw, 10) == 10
    # 3-4 matches -> 80% (8)
    assert svc._score_criterion("a b c d", kw, 10) == 8
    # 1-2 matches -> 50% (5)
    assert svc._score_criterion("a b", kw, 10) == 5


def test_score_criterion_no_matches_uses_random():
    with patch("random.randint", return_value=3):
        score = svc._score_criterion("zzz yyy", ["a", "b"], 10)
    assert score == 3


@pytest.mark.asyncio
async def test_get_quality_scores_filters_by_tenant():
    _inject_score({"tenant_id": "T1", "agent_id": "A1", "percentage": 80, "created_at": "2026-01-01"})
    _inject_score({"tenant_id": "T2", "agent_id": "A1", "percentage": 50, "created_at": "2026-01-01"})

    all_t1 = await svc.get_quality_scores("T1")
    assert len(all_t1) == 1
    filtered = await svc.get_quality_scores("T2", agent_id="A1")
    assert len(filtered) == 1
    _clear_scores()


@pytest.mark.asyncio
async def test_get_quality_trends_empty():
    _clear_scores()
    trend = await svc.get_quality_trends("NOPE")
    assert trend["trend"] == []
    assert trend["avg_percentage"] == 0


@pytest.mark.asyncio
async def test_get_quality_trends_averages():
    _clear_scores()
    _inject_score({"tenant_id": "T1", "agent_id": "A1", "percentage": 60, "created_at": "2026-01-01"})
    _inject_score({"tenant_id": "T1", "agent_id": "A1", "percentage": 80, "created_at": "2026-01-02"})
    trend = await svc.get_quality_trends("T1")
    assert trend["avg_percentage"] == 70.0
    assert len(trend["trend"]) == 2
    _clear_scores()


@pytest.mark.asyncio
async def test_coaching_opportunities_prioritises_gaps():
    _clear_scores()
    _inject_score({
        "tenant_id": "T1", "agent_id": "A1", "percentage": 70, "created_at": "2026-01-01",
        "criteria_scores": {"greeting": 10, "empathy": 2, "clarity": 6},
    })
    opps = await svc.identify_coaching_opportunities("A1")
    # Empathy has the largest gap -> sorted first
    assert opps[0]["criterion"] == "empathy"
    assert opps[0]["priority"] == "high"
    assert opps[2]["criterion"] == "greeting"
    assert opps[2]["priority"] == "low"
    _clear_scores()


@pytest.mark.asyncio
async def test_coaching_opportunities_empty_agent():
    _clear_scores()
    assert await svc.identify_coaching_opportunities("NOBODY") == []


# ── Helpers to seed/clear the in-memory score store ──────────────────────────

def _inject_score(record: dict):
    from api.services import conversation_quality as mod
    mod._in_memory_scores.append(record)


def _clear_scores():
    from api.services import conversation_quality as mod
    mod._in_memory_scores.clear()
