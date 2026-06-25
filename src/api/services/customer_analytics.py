from collections import defaultdict
from datetime import UTC, datetime, timedelta

import structlog

from api.services.db_cdp import (
    list_customer_interactions_db,
    search_customers_db,
)

logger = structlog.get_logger()


class CustomerAnalyticsService:

    async def get_cohort_analysis(self, tenant_id, cohort_period="month", metric="retention"):
        all_profiles = await search_customers_db(tenant_id, "")
        cohorts = defaultdict(lambda: {"total": 0, "active": 0, "retention": 0})
        now = datetime.now(UTC)

        for p in all_profiles:
            pid = p["id"]
            interactions = await list_customer_interactions_db(tenant_id, pid, limit=500)
            if not interactions:
                continue
            dates = []
            for i in interactions:
                try:
                    d = datetime.fromisoformat(i.get("created_at", "").replace("Z", "+00:00"))
                    dates.append(d)
                except (ValueError, TypeError):
                    pass
            if not dates:
                continue
            first = min(dates)
            if cohort_period == "week":
                cohort_key = first.strftime("%Y-W%W")
            else:
                cohort_key = first.strftime("%Y-%m")
            cohorts[cohort_key]["total"] += 1
            if (now - max(dates)).days <= 30:
                cohorts[cohort_key]["active"] += 1

        result = []
        for key in sorted(cohorts.keys()):
            c = cohorts[key]
            retention_pct = round((c["active"] / c["total"] * 100), 1) if c["total"] > 0 else 0
            result.append({
                "cohort": key,
                "total_customers": c["total"],
                "active_customers": c["active"],
                "retention_pct": retention_pct,
            })

        return {"cohort_period": cohort_period, "metric": metric, "cohorts": result}

    async def get_customer_journey(self, tenant_id, customer_id):
        interactions = await list_customer_interactions_db(tenant_id, customer_id, limit=500)
        if not interactions:
            return {"customer_id": customer_id, "stages": [], "total_interactions": 0}

        stages = []
        for i in sorted(interactions, key=lambda x: x.get("created_at", "")):
            stages.append({
                "stage": i.get("interaction_type", "unknown"),
                "channel": i.get("channel", "voice"),
                "sentiment": i.get("sentiment", "neutral"),
                "timestamp": i.get("created_at"),
            })

        first_touch = stages[0] if stages else None
        last_touch = stages[-1] if stages else None
        voice_stages = [s for s in stages if s["channel"] == "voice"]
        conversion_count = len(voice_stages)

        return {
            "customer_id": customer_id,
            "first_touch": first_touch,
            "last_touch": last_touch,
            "total_interactions": len(stages),
            "conversion_count": conversion_count,
            "stages": stages,
        }

    async def get_churn_risk(self, tenant_id, customer_id):
        interactions = await list_customer_interactions_db(tenant_id, customer_id, limit=500)
        now = datetime.now(UTC)
        if not interactions:
            return {"customer_id": customer_id, "churn_risk": "high", "churn_probability": 0.8, "factors": ["no_interactions"]}

        dates = []
        sentiments = []
        for i in interactions:
            try:
                d = datetime.fromisoformat(i.get("created_at", "").replace("Z", "+00:00"))
                dates.append(d)
            except (ValueError, TypeError):
                pass
            s = i.get("sentiment", "neutral")
            sentiments.append(s)

        if not dates:
            return {"customer_id": customer_id, "churn_risk": "high", "churn_probability": 0.7, "factors": ["no_dates"]}

        days_since_last = (now - max(dates)).days
        interaction_frequency = len(dates) / max((now - min(dates)).days, 1)

        negative_ratio = sentiments.count("negative") / max(len(sentiments), 1)
        positive_ratio = sentiments.count("positive") / max(len(sentiments), 1)

        risk_score = 0.0
        factors = []
        if days_since_last > 60:
            risk_score += 0.3
            factors.append("inactive_over_60_days")
        if days_since_last > 30:
            risk_score += 0.15
            factors.append("inactive_over_30_days")
        if interaction_frequency < 0.05:
            risk_score += 0.2
            factors.append("low_interaction_frequency")
        if negative_ratio > 0.5:
            risk_score += 0.25
            factors.append("high_negative_sentiment")
        if positive_ratio < 0.1:
            risk_score += 0.1
            factors.append("low_positive_sentiment")

        risk_score = min(risk_score, 0.95)
        if risk_score >= 0.6:
            risk_level = "high"
        elif risk_score >= 0.3:
            risk_level = "medium"
        else:
            risk_level = "low"

        return {
            "customer_id": customer_id,
            "churn_risk": risk_level,
            "churn_probability": round(risk_score, 2),
            "factors": factors,
            "days_since_last_interaction": days_since_last,
            "interaction_frequency": round(interaction_frequency, 4),
            "negative_sentiment_ratio": round(negative_ratio, 2),
        }

    async def get_lifetime_value(self, tenant_id, customer_id):
        interactions = await list_customer_interactions_db(tenant_id, customer_id, limit=500)
        if not interactions:
            return {"customer_id": customer_id, "estimated_ltv": 0, "total_interactions": 0}

        total_duration = sum(i.get("duration_seconds", 0) for i in interactions)
        total_minutes = total_duration / 60
        estimated_revenue = total_minutes * 0.50

        dates = []
        for i in interactions:
            try:
                d = datetime.fromisoformat(i.get("created_at", "").replace("Z", "+00:00"))
                dates.append(d)
            except (ValueError, TypeError):
                pass

        if dates:
            days_span = max((max(dates) - min(dates)).days, 1)
            monthly_value = (estimated_revenue / days_span) * 30
        else:
            monthly_value = 0

        ltv = estimated_revenue * 1.5
        return {
            "customer_id": customer_id,
            "estimated_ltv": round(ltv, 2),
            "total_interactions": len(interactions),
            "total_minutes": round(total_minutes, 2),
            "estimated_revenue": round(estimated_revenue, 2),
            "monthly_value": round(monthly_value, 2),
        }

    async def get_aggregate_metrics(self, tenant_id, period="30d"):
        all_profiles = await search_customers_db(tenant_id, "")
        total_customers = len(all_profiles)
        now = datetime.now(UTC)

        if period == "7d":
            cutoff = now - timedelta(days=7)
        elif period == "90d":
            cutoff = now - timedelta(days=90)
        else:
            cutoff = now - timedelta(days=30)

        active_customers = 0
        new_customers = 0
        total_lifetime_calls = 0

        for p in all_profiles:
            pid = p["id"]
            interactions = await list_customer_interactions_db(tenant_id, pid, limit=500)
            if not interactions:
                continue
            voice = [i for i in interactions if i.get("channel") == "voice"]
            total_lifetime_calls += len(voice)
            dates = []
            for i in interactions:
                try:
                    d = datetime.fromisoformat(i.get("created_at", "").replace("Z", "+00:00"))
                    dates.append(d)
                except (ValueError, TypeError):
                    pass
            if not dates:
                continue
            latest = max(dates)
            if latest >= cutoff:
                active_customers += 1
            first = min(dates)
            if first >= cutoff:
                new_customers += 1

        returning = max(0, active_customers - new_customers)
        avg_lifetime_calls = round(total_lifetime_calls / max(total_customers, 1), 1)

        return {
            "period": period,
            "total_customers": total_customers,
            "active_customers": active_customers,
            "new_customers": new_customers,
            "returning_customers": returning,
            "avg_lifetime_calls": avg_lifetime_calls,
            "total_lifetime_calls": total_lifetime_calls,
        }


customer_analytics_service = CustomerAnalyticsService()
