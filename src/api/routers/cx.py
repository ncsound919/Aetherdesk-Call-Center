
import structlog
from fastapi import APIRouter, Depends, Query

from api.models.dto import CSATSurveyCreate
from api.services.auth import verify_tenant_access
from api.services.csat import csat_engine
from api.services.db_cx import (
    get_csat_score_db,
    get_customer_360_db,
    get_nps_score_db,
    get_response_rate_db,
    get_sentiment_trends_db,
    list_surveys_db,
)

logger = structlog.get_logger()

router = APIRouter(prefix="/cx", tags=["cx"])


@router.post("/csat/surveys")
async def create_survey(
    data: CSATSurveyCreate,
    tenant_id: str = Depends(verify_tenant_access),
):
    result = await csat_engine.create_survey(
        tenant_id,
        call_id=data.call_id,
        customer_id=data.customer_id,
        rating=data.rating,
        feedback=data.feedback,
        channel=data.channel,
    )
    logger.info("csat_survey_created", tenant_id=tenant_id, rating=data.rating)
    return result


@router.get("/csat/surveys")
async def list_surveys(
    tenant_id: str = Depends(verify_tenant_access),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    min_rating: int | None = Query(None, ge=1, le=5),
    channel: str | None = Query(None),
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
):
    return await list_surveys_db(
        tenant_id,
        limit=limit,
        offset=offset,
        min_rating=min_rating,
        channel=channel,
        start_date=start_date,
        end_date=end_date,
    )


@router.get("/csat/score")
async def get_csat_score(
    tenant_id: str = Depends(verify_tenant_access),
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
):
    return await get_csat_score_db(tenant_id, start_date=start_date, end_date=end_date)


@router.get("/csat/response-rate")
async def get_response_rate(
    tenant_id: str = Depends(verify_tenant_access),
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
):
    return await get_response_rate_db(tenant_id, start_date=start_date, end_date=end_date)


@router.get("/csat/nps")
async def get_nps(
    tenant_id: str = Depends(verify_tenant_access),
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
):
    return await get_nps_score_db(tenant_id, start_date=start_date, end_date=end_date)


@router.get("/sentiment/trends")
async def get_sentiment_trends(
    tenant_id: str = Depends(verify_tenant_access),
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    granularity: str = Query("day", regex="^(hour|day)$"),
):
    return await get_sentiment_trends_db(tenant_id, start_date=start_date, end_date=end_date, granularity=granularity)


@router.get("/customers/{customer_id}/360")
async def get_customer_360(
    customer_id: str,
    tenant_id: str = Depends(verify_tenant_access),
):
    return await get_customer_360_db(tenant_id, customer_id)


@router.get("/summary")
async def get_cx_summary(
    tenant_id: str = Depends(verify_tenant_access),
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
):
    csat = await get_csat_score_db(tenant_id, start_date=start_date, end_date=end_date)
    nps = await get_nps_score_db(tenant_id, start_date=start_date, end_date=end_date)
    response_rate = await get_response_rate_db(tenant_id, start_date=start_date, end_date=end_date)
    trends = await get_sentiment_trends_db(tenant_id, start_date=start_date, end_date=end_date, granularity="day")

    sentiment_dist = {"positive": 0, "neutral": 0, "negative": 0}
    for row in trends:
        sentiment = row.get("sentiment", "neutral")
        sentiment_dist[sentiment] = sentiment_dist.get(sentiment, 0) + row.get("count", 0)

    return {
        "csat": csat,
        "nps": nps,
        "response_rate": response_rate,
        "sentiment_distribution": sentiment_dist,
        "total_interactions": sum(sentiment_dist.values()),
    }
