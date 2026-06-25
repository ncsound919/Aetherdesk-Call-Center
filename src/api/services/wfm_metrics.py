import structlog

from api.services.db_wfm_metrics import (
    create_aht_db,
    create_csat_db,
    create_fcr_db,
    create_nps_db,
    get_aht_stats_db,
    get_csat_trend_db,
    get_fcr_stats_db,
    get_nps_stats_db,
    list_aht_db,
    list_csat_db,
    list_fcr_db,
)

logger = structlog.get_logger()


class WFMMetricsService:
    async def track_aht(self, call_id, agent_id, duration_seconds, tenant_id=None):
        return await create_aht_db(tenant_id, agent_id, call_id, duration_seconds)

    async def track_fcr(self, call_id, customer_id, resolved, tenant_id=None, follow_up_call_id=None):
        return await create_fcr_db(tenant_id, customer_id, call_id, resolved, follow_up_call_id)

    async def track_csat(self, call_id, customer_id, rating, tenant_id=None):
        return await create_csat_db(tenant_id, customer_id, call_id, rating)

    async def track_nps(self, call_id, customer_id, score, tenant_id=None):
        return await create_nps_db(tenant_id, customer_id, call_id, score)

    async def get_aht_stats(self, tenant_id, period="7d"):
        return await get_aht_stats_db(tenant_id, period)

    async def get_fcr_rate(self, tenant_id, period="7d"):
        return await get_fcr_stats_db(tenant_id, period)

    async def get_csat_trend(self, tenant_id, period="7d"):
        return await get_csat_trend_db(tenant_id, period)

    async def get_nps_score(self, tenant_id, period="7d"):
        return await get_nps_stats_db(tenant_id, period)

    async def get_recent_aht(self, tenant_id, limit=50):
        return await list_aht_db(tenant_id, limit)

    async def get_recent_fcr(self, tenant_id, limit=50):
        return await list_fcr_db(tenant_id, limit)

    async def get_recent_csat(self, tenant_id, limit=50):
        return await list_csat_db(tenant_id, limit)


wfm_metrics_service = WFMMetricsService()
