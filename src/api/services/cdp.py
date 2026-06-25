import json
from datetime import UTC, datetime

import structlog

from api.services.db_cdp import (
    create_customer_profile_db,
    create_segment_db,
    find_customers_by_identifier_db,
    get_customer_profile_db,
    get_customer_tags_db,
    list_csat_surveys_for_customer_db,
    list_customer_interactions_db,
    list_segments_db,
    search_customers_db,
    update_customer_tags_db,
    update_segment_member_count_db,
    upsert_customer_profile_db,
)
from api.services.db_cdp import get_segment_db as _get_segment_db

logger = structlog.get_logger()


class CDPService:

    async def unify_customer(self, tenant_id, identifiers):
        phone = identifiers.get("phone")
        email = identifiers.get("email")
        external_id = identifiers.get("external_id")

        lookup = {}
        if phone:
            lookup["phone"] = phone
        if email:
            lookup["email"] = email
        if external_id:
            lookup["external_id"] = external_id

        existing = await find_customers_by_identifier_db(tenant_id, lookup)

        if existing:
            primary = existing[0]
            pid = primary["id"]
            for dup in existing[1:]:
                if dup.get("tags_json"):
                    ptags = json.loads(primary.get("tags_json", "[]")) if isinstance(primary.get("tags_json"), str) else primary.get("tags_json", [])
                    dtags = json.loads(dup.get("tags_json", "[]")) if isinstance(dup.get("tags_json"), str) else dup.get("tags_json", [])
                    merged_tags = list(set(ptags + dtags))
                    await update_customer_tags_db(pid, merged_tags)

            update_fields = {"last_seen_at": datetime.now(UTC).isoformat()}
            if phone and not primary.get("phone"):
                update_fields["phone"] = phone
            if email and not primary.get("email"):
                update_fields["email"] = email
            if external_id and not primary.get("external_id"):
                update_fields["external_id"] = external_id
            if update_fields:
                await upsert_customer_profile_db(tenant_id, pid, **update_fields)

            return await get_customer_profile_db(pid)

        customer = await create_customer_profile_db(
            tenant_id,
            phone=phone,
            email=email,
            external_id=external_id,
            name=identifiers.get("name"),
            metadata=identifiers.get("metadata", {}),
        )
        logger.info("customer_created", tenant_id=tenant_id, customer_id=customer["id"])
        return customer

    async def get_unified_profile(self, tenant_id, customer_id):
        profile = await get_customer_profile_db(customer_id)
        if not profile:
            return None
        if isinstance(profile.get("tags_json"), str):
            profile["tags"] = json.loads(profile["tags_json"])
        else:
            profile["tags"] = profile.get("tags_json", [])
        if isinstance(profile.get("metadata_json"), str):
            profile["metadata"] = json.loads(profile["metadata_json"])
        else:
            profile["metadata"] = profile.get("metadata_json", {})

        calls = await list_customer_interactions_db(tenant_id, customer_id)
        sms = await list_customer_interactions_db(tenant_id, customer_id)
        sms = [c for c in sms if c.get("channel") == "sms"]
        chats = [c for c in calls if c.get("channel") == "chat"]
        calls_only = [c for c in calls if c.get("channel") == "voice"]

        surveys = await list_csat_surveys_for_customer_db(tenant_id, customer_id)

        sentiments = []
        for c in calls:
            if c.get("sentiment"):
                sentiments.append({"date": c.get("created_at"), "sentiment": c.get("sentiment")})

        rfm = await self.get_rfm_scores(tenant_id, customer_id)

        return {
            "profile": profile,
            "calls": calls_only,
            "sms": sms,
            "chat": chats,
            "csat_surveys": surveys,
            "sentiment_timeline": sentiments,
            "rfm": rfm,
        }

    async def tag_customer(self, tenant_id, customer_id, tags):
        existing = await get_customer_tags_db(customer_id)
        merged = list(set(existing + tags))
        await update_customer_tags_db(customer_id, merged)
        logger.info("customer_tagged", tenant_id=tenant_id, customer_id=customer_id, tags=tags)
        return {"tags": merged}

    async def search_customers(self, tenant_id, query):
        return await search_customers_db(tenant_id, query)

    async def get_segments(self, tenant_id):
        segments = await list_segments_db(tenant_id)
        for s in segments:
            if isinstance(s.get("criteria_json"), str):
                s["criteria"] = json.loads(s["criteria_json"])
            else:
                s["criteria"] = s.get("criteria_json", {})
        return segments

    async def create_segment(self, tenant_id, name, criteria):
        segment = await create_segment_db(tenant_id, name, criteria)
        if segment and isinstance(segment.get("criteria_json"), str):
            segment["criteria"] = json.loads(segment["criteria_json"])
        else:
            segment["criteria"] = segment.get("criteria_json", {})
        logger.info("segment_created", tenant_id=tenant_id, name=name)
        return segment

    async def evaluate_segment(self, tenant_id, segment_id):
        segment = await _get_segment_db(segment_id)
        if not segment:
            return []
        criteria_raw = segment.get("criteria_json", "{}")
        if isinstance(criteria_raw, str):
            criteria = json.loads(criteria_raw)
        else:
            criteria = criteria_raw
        min_calls = criteria.get("min_calls", 0)
        min_csat = criteria.get("min_csat", 0)
        max_recency_days = criteria.get("max_recency_days", 9999)


        all_profiles = await search_customers_db(tenant_id, "")
        matching = []
        for p in all_profiles:
            pid = p["id"]
            interactions = await list_customer_interactions_db(tenant_id, pid, limit=500)
            voice_interactions = [i for i in interactions if i.get("channel") == "voice"]
            if len(voice_interactions) < min_calls:
                continue
            surveys = await list_csat_surveys_for_customer_db(tenant_id, pid)
            if surveys:
                avg_csat = sum(s.get("rating", 0) for s in surveys) / len(surveys)
                if avg_csat < min_csat:
                    continue
            if interactions:
                latest = max(i.get("created_at", "") for i in interactions)
                try:
                    latest_dt = datetime.fromisoformat(latest.replace("Z", "+00:00"))
                    days_since = (datetime.now(UTC) - latest_dt).days
                    if days_since > max_recency_days:
                        continue
                except (ValueError, TypeError):
                    pass
            matching.append(p)

        await update_segment_member_count_db(segment_id, len(matching))
        return matching

    async def get_rfm_scores(self, tenant_id, customer_id):
        interactions = await list_customer_interactions_db(tenant_id, customer_id, limit=500)
        now = datetime.now(UTC)
        recency_days = 999
        frequency = 0
        monetary = 0
        if interactions:
            dates = []
            for i in interactions:
                try:
                    d = datetime.fromisoformat(i.get("created_at", "").replace("Z", "+00:00"))
                    dates.append(d)
                except (ValueError, TypeError):
                    pass
            if dates:
                recency_days = (now - max(dates)).days
                frequency = len(dates)
                monetary = sum(i.get("duration_seconds", 0) for i in interactions)

        r_score = max(1, min(5, 5 - recency_days // 30))
        f_score = max(1, min(5, frequency // 5 + 1))
        m_score = max(1, min(5, monetary // 300 + 1))

        return {
            "recency_days": recency_days,
            "frequency": frequency,
            "monetary_seconds": monetary,
            "r_score": r_score,
            "f_score": f_score,
            "m_score": m_score,
            "rfm_segment": f"R{r_score}F{f_score}M{m_score}",
        }

    async def get_interaction_timeline(self, tenant_id, customer_id):
        interactions = await list_customer_interactions_db(tenant_id, customer_id, limit=200)
        surveys = await list_csat_surveys_for_customer_db(tenant_id, customer_id)
        timeline = []
        for i in interactions:
            timeline.append({
                "type": "interaction",
                "channel": i.get("channel"),
                "interaction_type": i.get("interaction_type"),
                "sentiment": i.get("sentiment"),
                "summary": i.get("summary"),
                "timestamp": i.get("created_at"),
            })
        for s in surveys:
            timeline.append({
                "type": "csat_survey",
                "rating": s.get("rating"),
                "feedback": s.get("feedback"),
                "timestamp": s.get("created_at"),
            })
        timeline.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        return timeline


cdp_service = CDPService()
