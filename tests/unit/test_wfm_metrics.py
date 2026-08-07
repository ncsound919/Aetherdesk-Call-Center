"""Unit tests for api.services.wfm_metrics."""

from unittest.mock import AsyncMock, patch

import pytest

from api.services.wfm_metrics import WFMMetricsService, wfm_metrics_service

SERVICE = "api.services.wfm_metrics"


@pytest.fixture(autouse=True)
def _service():
    return WFMMetricsService()


@pytest.mark.asyncio
async def test_track_aht():
    with patch(f"{SERVICE}.create_aht_db", new_callable=AsyncMock) as m:
        m.return_value = {"id": "m1"}
        result = await wfm_metrics_service.track_aht(
            call_id="C1", agent_id="A1", duration_seconds=120, tenant_id="T1"
        )
    assert result == {"id": "m1"}
    m.assert_awaited_once_with("T1", "A1", "C1", 120)


@pytest.mark.asyncio
async def test_track_aht_default_tenant():
    with patch(f"{SERVICE}.create_aht_db", new_callable=AsyncMock) as m:
        await wfm_metrics_service.track_aht("C1", "A1", 60)
    m.assert_awaited_once_with(None, "A1", "C1", 60)


@pytest.mark.asyncio
async def test_track_fcr():
    with patch(f"{SERVICE}.create_fcr_db", new_callable=AsyncMock) as m:
        m.return_value = {"id": "f1"}
        result = await wfm_metrics_service.track_fcr(
            call_id="C1",
            customer_id="CU1",
            resolved=True,
            tenant_id="T1",
            follow_up_call_id="C2",
        )
    assert result == {"id": "f1"}
    m.assert_awaited_once_with("T1", "CU1", "C1", True, "C2")


@pytest.mark.asyncio
async def test_track_fcr_defaults():
    with patch(f"{SERVICE}.create_fcr_db", new_callable=AsyncMock) as m:
        await wfm_metrics_service.track_fcr("C1", "CU1", False)
    m.assert_awaited_once_with(None, "CU1", "C1", False, None)


@pytest.mark.asyncio
async def test_track_csat():
    with patch(f"{SERVICE}.create_csat_db", new_callable=AsyncMock) as m:
        m.return_value = {"id": "c1"}
        result = await wfm_metrics_service.track_csat(
            call_id="C1", customer_id="CU1", rating=5, tenant_id="T1"
        )
    assert result == {"id": "c1"}
    m.assert_awaited_once_with("T1", "CU1", "C1", 5)


@pytest.mark.asyncio
async def test_track_nps():
    with patch(f"{SERVICE}.create_nps_db", new_callable=AsyncMock) as m:
        m.return_value = {"id": "n1"}
        result = await wfm_metrics_service.track_nps(
            call_id="C1", customer_id="CU1", score=9, tenant_id="T1"
        )
    assert result == {"id": "n1"}
    m.assert_awaited_once_with("T1", "CU1", "C1", 9)


@pytest.mark.asyncio
async def test_get_aht_stats_default_period():
    with patch(f"{SERVICE}.get_aht_stats_db", new_callable=AsyncMock) as m:
        m.return_value = {"avg": 120}
        result = await wfm_metrics_service.get_aht_stats("T1")
    assert result == {"avg": 120}
    m.assert_awaited_once_with("T1", "7d")


@pytest.mark.asyncio
async def test_get_aht_stats_custom_period():
    with patch(f"{SERVICE}.get_aht_stats_db", new_callable=AsyncMock) as m:
        await wfm_metrics_service.get_aht_stats("T1", "30d")
    m.assert_awaited_once_with("T1", "30d")


@pytest.mark.asyncio
async def test_get_fcr_rate():
    with patch(f"{SERVICE}.get_fcr_stats_db", new_callable=AsyncMock) as m:
        m.return_value = {"fcr": 0.75}
        result = await wfm_metrics_service.get_fcr_rate("T1")
    assert result == {"fcr": 0.75}
    m.assert_awaited_once_with("T1", "7d")


@pytest.mark.asyncio
async def test_get_csat_trend():
    with patch(f"{SERVICE}.get_csat_trend_db", new_callable=AsyncMock) as m:
        m.return_value = [{"date": "d1", "csat": 4.5}]
        result = await wfm_metrics_service.get_csat_trend("T1", "30d")
    assert result == [{"date": "d1", "csat": 4.5}]
    m.assert_awaited_once_with("T1", "30d")


@pytest.mark.asyncio
async def test_get_nps_score():
    with patch(f"{SERVICE}.get_nps_stats_db", new_callable=AsyncMock) as m:
        m.return_value = {"nps": 55}
        result = await wfm_metrics_service.get_nps_score("T1")
    assert result == {"nps": 55}
    m.assert_awaited_once_with("T1", "7d")


@pytest.mark.asyncio
async def test_get_recent_aht():
    with patch(f"{SERVICE}.list_aht_db", new_callable=AsyncMock) as m:
        m.return_value = [{"call_id": "C1"}]
        result = await wfm_metrics_service.get_recent_aht("T1", limit=10)
    assert result == [{"call_id": "C1"}]
    m.assert_awaited_once_with("T1", 10)


@pytest.mark.asyncio
async def test_get_recent_aht_default_limit():
    with patch(f"{SERVICE}.list_aht_db", new_callable=AsyncMock) as m:
        await wfm_metrics_service.get_recent_aht("T1")
    m.assert_awaited_once_with("T1", 50)


@pytest.mark.asyncio
async def test_get_recent_fcr():
    with patch(f"{SERVICE}.list_fcr_db", new_callable=AsyncMock) as m:
        m.return_value = [{"call_id": "C1"}]
        result = await wfm_metrics_service.get_recent_fcr("T1", limit=5)
    assert result == [{"call_id": "C1"}]
    m.assert_awaited_once_with("T1", 5)


@pytest.mark.asyncio
async def test_get_recent_csat():
    with patch(f"{SERVICE}.list_csat_db", new_callable=AsyncMock) as m:
        m.return_value = [{"call_id": "C1"}]
        result = await wfm_metrics_service.get_recent_csat("T1", limit=3)
    assert result == [{"call_id": "C1"}]
    m.assert_awaited_once_with("T1", 3)


@pytest.mark.asyncio
async def test_db_error_propagates():
    with patch(f"{SERVICE}.get_aht_stats_db", new_callable=AsyncMock) as m:
        m.side_effect = RuntimeError("db down")
        with pytest.raises(RuntimeError):
            await wfm_metrics_service.get_aht_stats("T1")
