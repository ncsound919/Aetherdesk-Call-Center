import random

import structlog

logger = structlog.get_logger()

STANDARD_RUBRIC = {
    "name": "standard",
    "criteria": [
        {"name": "greeting", "max_score": 10, "weight": 1},
        {"name": "clarity", "max_score": 10, "weight": 1},
        {"name": "empathy", "max_score": 10, "weight": 1},
        {"name": "resolution", "max_score": 10, "weight": 1},
        {"name": "professionalism", "max_score": 10, "weight": 1},
    ],
}

GREETING_KEYWORDS = ["hello", "hi", "good morning", "good afternoon", "good evening", "thank you for calling", "welcome"]
CLARITY_KEYWORDS = ["let me explain", "in other words", "to clarify", "basically", "simply put", "what i mean is"]
EMPATHY_KEYWORDS = ["understand", "sorry", "apologize", "frustrating", "i hear you", "i can imagine", "i understand how"]
RESOLUTION_KEYWORDS = ["let me help", "i will", "let me check", "the solution is", "here is what", "i have resolved"]
PROFESSIONALISM_KEYWORDS = ["please", "thank you", "you are welcome", "sir", "ma'am", "absolutely", "certainly"]

_in_memory_scores = []


class ConversationQualityService:

    def _score_criterion(self, transcript: str, keywords: list[str], max_score: int) -> int:
        transcript_lower = transcript.lower()
        matches = sum(1 for kw in keywords if kw in transcript_lower)
        if matches >= 5:
            return max_score
        if matches >= 3:
            return max(int(max_score * 0.8), 7)
        if matches >= 1:
            return max(int(max_score * 0.5), 5)
        return random.randint(1, 4)

    def score_conversation(self, transcript: str, rubric_name: str = "standard") -> dict:
        logger.info("Scoring conversation", rubric=rubric_name, transcript_length=len(transcript))

        criteria_scores = {
            "greeting": self._score_criterion(transcript, GREETING_KEYWORDS, 10),
            "clarity": self._score_criterion(transcript, CLARITY_KEYWORDS, 10),
            "empathy": self._score_criterion(transcript, EMPATHY_KEYWORDS, 10),
            "resolution": self._score_criterion(transcript, RESOLUTION_KEYWORDS, 10),
            "professionalism": self._score_criterion(transcript, PROFESSIONALISM_KEYWORDS, 10),
        }

        total_score = sum(criteria_scores.values())
        max_possible = 50
        percentage = round((total_score / max_possible) * 100, 1)

        result = {
            "rubric_name": rubric_name,
            "criteria_scores": criteria_scores,
            "total_score": total_score,
            "max_possible": max_possible,
            "percentage": percentage,
            "rating": "excellent" if percentage >= 90 else "good" if percentage >= 75 else "average" if percentage >= 50 else "needs_improvement",
        }

        logger.info("Conversation scored", result=result)
        return result

    async def get_quality_scores(self, tenant_id: str, agent_id: str | None = None, period: str = "30d") -> list[dict]:
        scores = [s for s in _in_memory_scores if s["tenant_id"] == tenant_id]
        if agent_id:
            scores = [s for s in scores if s["agent_id"] == agent_id]
        return scores

    async def get_quality_trends(self, tenant_id: str, period: str = "30d") -> dict:
        scores = [s for s in _in_memory_scores if s["tenant_id"] == tenant_id]
        if not scores:
            return {"trend": [], "avg_percentage": 0, "period": period}

        avg = sum(s.get("percentage", 0) for s in scores) / len(scores)
        return {
            "trend": [
                {"date": s["created_at"], "percentage": s["percentage"]}
                for s in sorted(scores, key=lambda x: x["created_at"])[-30:]
            ],
            "avg_percentage": round(avg, 1),
            "period": period,
        }

    async def identify_coaching_opportunities(self, agent_id: str, period: str = "30d") -> list[dict]:
        agent_scores = [s for s in _in_memory_scores if s["agent_id"] == agent_id]
        if not agent_scores:
            return []

        weakness_map: dict[str, list[int]] = {}
        for s in agent_scores:
            criteria = s.get("criteria_scores", {})
            for criterion, score in criteria.items():
                if criterion not in weakness_map:
                    weakness_map[criterion] = []
                weakness_map[criterion].append(score)

        opportunities = []
        for criterion, scores in weakness_map.items():
            avg = sum(scores) / len(scores)
            opportunities.append({
                "criterion": criterion,
                "average_score": round(avg, 1),
                "max_score": 10,
                "gap": round(10 - avg, 1),
                "priority": "high" if (10 - avg) >= 4 else "medium" if (10 - avg) >= 2 else "low",
            })

        opportunities.sort(key=lambda x: x["gap"], reverse=True)
        return opportunities


conversation_quality_service = ConversationQualityService()
