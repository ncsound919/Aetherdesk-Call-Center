from collections import Counter

import structlog

logger = structlog.get_logger()


class CSATService:
    """CSAT & CX Service — pure Python implementations."""

    async def create_survey(self, tenant_id, call_id=None, customer_id=None, rating=5, feedback=None, channel="voice"):
        from api.services.db_cx import create_survey_db
        return await create_survey_db(tenant_id, call_id=call_id, customer_id=customer_id, rating=rating, feedback=feedback, channel=channel)

    async def get_survey_response_rate(self, tenant_id, start_date=None, end_date=None):
        from api.services.db_cx import get_response_rate_db
        return await get_response_rate_db(tenant_id, start_date=start_date, end_date=end_date)

    async def get_csat_score(self, tenant_id, start_date=None, end_date=None):
        from api.services.db_cx import get_csat_score_db
        return await get_csat_score_db(tenant_id, start_date=start_date, end_date=end_date)

    async def get_sentiment_trends(self, tenant_id, start_date=None, end_date=None, granularity="day"):
        from api.services.db_cx import get_sentiment_trends_db
        return await get_sentiment_trends_db(tenant_id, start_date=start_date, end_date=end_date, granularity=granularity)

    async def get_nps_score(self, tenant_id, start_date=None, end_date=None):
        from api.services.db_cx import get_nps_score_db
        return await get_nps_score_db(tenant_id, start_date=start_date, end_date=end_date)

    async def get_customer_360(self, tenant_id, customer_id):
        from api.services.db_cx import get_customer_360_db
        return await get_customer_360_db(tenant_id, customer_id)

    def nps_score(self, rating_counts: dict) -> dict:
        total = sum(rating_counts.values())
        if total == 0:
            return {"nps": 0, "promoters": 0, "passives": 0, "detractors": 0}
        promoters = sum(rating_counts.get(r, 0) for r in range(9, 11))
        detractors = sum(rating_counts.get(r, 0) for r in range(0, 7))
        passives = total - promoters - detractors
        nps = ((promoters - detractors) / total) * 100
        return {
            "nps": round(nps, 1),
            "promoters": promoters,
            "passives": passives,
            "detractors": detractors,
            "total": total,
        }

    def calculate_response_rate(self, responded: int, total: int) -> float:
        if total <= 0:
            return 0.0
        return round((responded / total) * 100, 2)

    def aggregate_sentiment(self, sentiments: list[str]) -> dict:
        if not sentiments:
            return {"dominant": "neutral", "distribution": {}}
        counts = Counter(sentiments)
        dominant = counts.most_common(1)[0][0]
        return {
            "dominant": dominant,
            "distribution": dict(counts),
            "total": len(sentiments),
        }


csat_engine = CSATService()
