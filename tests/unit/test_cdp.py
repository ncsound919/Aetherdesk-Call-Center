"""Unit tests for src/api/services/cdp.py (the CDP SERVICE).

Covers the ``CDPService`` business logic (customer unification, unified
profiles, tagging, segment evaluation, RFM scoring, interaction timelines).
All ``api.services.db_cdp`` primitives it calls are mocked; nothing touches a
real database.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from api.services.cdp import CDPService


@pytest.fixture
def service():
    return CDPService()


class TestUnifyCustomer:
    @pytest.mark.asyncio
    async def test_creates_customer_when_no_match(self, service):
        with patch(
            "api.services.cdp.find_customers_by_identifier_db",
            new_callable=AsyncMock,
            return_value=[],
        ) as mock_find, patch(
            "api.services.cdp.create_customer_profile_db",
            new_callable=AsyncMock,
            return_value={"id": "c1"},
        ) as mock_create:
            result = await service.unify_customer(
                "t1",
                {
                    "phone": "+1555",
                    "email": "a@b.com",
                    "external_id": "ext1",
                    "name": "Alice",
                    "metadata": {"region": "US"},
                },
            )
        assert result == {"id": "c1"}
        mock_find.assert_called_once_with(
            "t1", {"phone": "+1555", "email": "a@b.com", "external_id": "ext1"}
        )
        mock_create.assert_called_once_with(
            "t1",
            phone="+1555",
            email="a@b.com",
            external_id="ext1",
            name="Alice",
            metadata={"region": "US"},
        )

    @pytest.mark.asyncio
    async def test_creates_with_empty_identifiers(self, service):
        with patch(
            "api.services.cdp.find_customers_by_identifier_db",
            new_callable=AsyncMock,
            return_value=[],
        ), patch(
            "api.services.cdp.create_customer_profile_db",
            new_callable=AsyncMock,
            return_value={"id": "c1"},
        ) as mock_create:
            result = await service.unify_customer("t1", {})
        assert result == {"id": "c1"}
        mock_create.assert_called_once_with(
            "t1",
            phone=None,
            email=None,
            external_id=None,
            name=None,
            metadata={},
        )

    @pytest.mark.asyncio
    async def test_existing_merges_dup_tags_and_fills_missing_phone(self, service):
        primary = {"id": "c1", "tags_json": '["a", "b"]'}
        dup = {"id": "c2", "tags_json": '["b", "c"]'}
        with patch(
            "api.services.cdp.find_customers_by_identifier_db",
            new_callable=AsyncMock,
            return_value=[primary, dup],
        ) as mock_find, patch(
            "api.services.cdp.update_customer_tags_db",
            new_callable=AsyncMock,
        ) as mock_tags, patch(
            "api.services.cdp.upsert_customer_profile_db",
            new_callable=AsyncMock,
        ) as mock_upsert, patch(
            "api.services.cdp.get_customer_profile_db",
            new_callable=AsyncMock,
            return_value={"id": "c1", "tags_json": '["a","b","c"]'},
        ) as mock_get:
            result = await service.unify_customer("t1", {"phone": "+1555"})
        assert result["id"] == "c1"
        mock_find.assert_called_once_with("t1", {"phone": "+1555"})
        mock_tags.assert_called_once()
        assert sorted(mock_tags.call_args.args[1]) == ["a", "b", "c"]
        mock_upsert.assert_called_once()
        kwargs = mock_upsert.call_args.kwargs
        assert kwargs["phone"] == "+1555"
        assert "last_seen_at" in kwargs
        mock_get.assert_called_once_with("c1")

    @pytest.mark.asyncio
    async def test_merges_tags_already_lists(self, service):
        primary = {"id": "c1", "tags_json": ["x"]}
        dup = {"id": "c2", "tags_json": ["y"]}
        with patch(
            "api.services.cdp.find_customers_by_identifier_db",
            new_callable=AsyncMock,
            return_value=[primary, dup],
        ), patch(
            "api.services.cdp.update_customer_tags_db",
            new_callable=AsyncMock,
        ) as mock_tags, patch(
            "api.services.cdp.upsert_customer_profile_db",
            new_callable=AsyncMock,
        ), patch(
            "api.services.cdp.get_customer_profile_db",
            new_callable=AsyncMock,
            return_value={"id": "c1"},
        ):
            await service.unify_customer("t1", {"phone": "+1555"})
        assert sorted(mock_tags.call_args.args[1]) == ["x", "y"]

    @pytest.mark.asyncio
    async def test_dup_without_tags_skips_merge(self, service):
        primary = {"id": "c1", "phone": "+1555", "email": "a@b.com"}
        dup = {"id": "c2"}
        with patch(
            "api.services.cdp.find_customers_by_identifier_db",
            new_callable=AsyncMock,
            return_value=[primary, dup],
        ), patch(
            "api.services.cdp.update_customer_tags_db",
            new_callable=AsyncMock,
        ) as mock_tags, patch(
            "api.services.cdp.upsert_customer_profile_db",
            new_callable=AsyncMock,
        ) as mock_upsert, patch(
            "api.services.cdp.get_customer_profile_db",
            new_callable=AsyncMock,
            return_value={"id": "c1"},
        ):
            await service.unify_customer(
                "t1", {"phone": "+1555", "email": "a@b.com"}
            )
        mock_tags.assert_not_called()
        # primary already has phone+email → only last_seen_at is written
        assert set(mock_upsert.call_args.kwargs.keys()) == {"last_seen_at"}

    @pytest.mark.asyncio
    async def test_existing_single_fills_email(self, service):
        primary = {"id": "c1", "phone": "+1555"}
        with patch(
            "api.services.cdp.find_customers_by_identifier_db",
            new_callable=AsyncMock,
            return_value=[primary],
        ), patch(
            "api.services.cdp.update_customer_tags_db",
            new_callable=AsyncMock,
        ), patch(
            "api.services.cdp.upsert_customer_profile_db",
            new_callable=AsyncMock,
        ) as mock_upsert, patch(
            "api.services.cdp.get_customer_profile_db",
            new_callable=AsyncMock,
            return_value={"id": "c1"},
        ):
            await service.unify_customer("t1", {"email": "a@b.com"})
        assert mock_upsert.call_args.kwargs["email"] == "a@b.com"

    @pytest.mark.asyncio
    async def test_existing_single_fills_external_id(self, service):
        primary = {"id": "c1"}
        with patch(
            "api.services.cdp.find_customers_by_identifier_db",
            new_callable=AsyncMock,
            return_value=[primary],
        ), patch(
            "api.services.cdp.update_customer_tags_db",
            new_callable=AsyncMock,
        ), patch(
            "api.services.cdp.upsert_customer_profile_db",
            new_callable=AsyncMock,
        ) as mock_upsert, patch(
            "api.services.cdp.get_customer_profile_db",
            new_callable=AsyncMock,
            return_value={"id": "c1"},
        ):
            await service.unify_customer("t1", {"external_id": "ext1"})
        assert mock_upsert.call_args.kwargs["external_id"] == "ext1"


class TestGetUnifiedProfile:
    @pytest.mark.asyncio
    async def test_profile_not_found_returns_none(self, service):
        with patch(
            "api.services.cdp.get_customer_profile_db",
            new_callable=AsyncMock,
            return_value=None,
        ) as mock_get, patch(
            "api.services.cdp.list_customer_interactions_db",
            new_callable=AsyncMock,
        ) as mock_ints:
            assert await service.get_unified_profile("t1", "c1") is None
        mock_get.assert_called_once_with("c1")
        mock_ints.assert_not_called()

    @pytest.mark.asyncio
    async def test_full_profile_buckets_channels_and_sentiments(self, service):
        profile = {
            "id": "c1",
            "name": "Alice",
            "tags_json": '["vip"]',
            "metadata_json": '{"region": "US"}',
        }
        interactions = [
            {
                "id": "i1",
                "channel": "voice",
                "sentiment": "positive",
                "created_at": "2026-01-01T00:00:00+00:00",
            },
            {
                "id": "i2",
                "channel": "chat",
                "sentiment": None,
                "created_at": "2026-01-02T00:00:00+00:00",
            },
            {
                "id": "i3",
                "channel": "sms",
                "sentiment": "neutral",
                "created_at": "2026-01-03T00:00:00+00:00",
            },
        ]
        surveys = [{"id": "s1", "rating": 5, "created_at": "2026-01-04"}]
        rfm = {"rfm_segment": "R5F1M1"}
        with patch(
            "api.services.cdp.get_customer_profile_db",
            new_callable=AsyncMock,
            return_value=profile,
        ), patch(
            "api.services.cdp.list_customer_interactions_db",
            new_callable=AsyncMock,
            return_value=interactions,
        ), patch(
            "api.services.cdp.list_csat_surveys_for_customer_db",
            new_callable=AsyncMock,
            return_value=surveys,
        ), patch.object(
            CDPService, "get_rfm_scores", new_callable=AsyncMock, return_value=rfm
        ) as mock_rfm:
            result = await service.get_unified_profile("t1", "c1")
        assert result["profile"]["tags"] == ["vip"]
        assert result["profile"]["metadata"] == {"region": "US"}
        assert [c["id"] for c in result["calls"]] == ["i1"]
        assert [c["id"] for c in result["chat"]] == ["i2"]
        assert [c["id"] for c in result["sms"]] == ["i3"]
        assert result["csat_surveys"] == surveys
        assert result["rfm"] == rfm
        assert len(result["sentiment_timeline"]) == 2
        mock_rfm.assert_called_once_with("t1", "c1")

    @pytest.mark.asyncio
    async def test_profile_already_parsed_fields(self, service):
        profile = {
            "id": "c1",
            "tags_json": ["vip"],
            "metadata_json": {"x": 1},
        }
        with patch(
            "api.services.cdp.get_customer_profile_db",
            new_callable=AsyncMock,
            return_value=profile,
        ), patch(
            "api.services.cdp.list_customer_interactions_db",
            new_callable=AsyncMock,
            return_value=[],
        ), patch(
            "api.services.cdp.list_csat_surveys_for_customer_db",
            new_callable=AsyncMock,
            return_value=[],
        ), patch.object(
            CDPService, "get_rfm_scores", new_callable=AsyncMock, return_value={}
        ):
            result = await service.get_unified_profile("t1", "c1")
        assert result["profile"]["tags"] == ["vip"]
        assert result["profile"]["metadata"] == {"x": 1}
        assert result["calls"] == []
        assert result["sms"] == []
        assert result["chat"] == []
        assert result["sentiment_timeline"] == []


class TestTagCustomer:
    @pytest.mark.asyncio
    async def test_merges_with_existing(self, service):
        with patch(
            "api.services.cdp.get_customer_tags_db",
            new_callable=AsyncMock,
            return_value=["vip"],
        ), patch(
            "api.services.cdp.update_customer_tags_db",
            new_callable=AsyncMock,
        ) as mock_update:
            result = await service.tag_customer("t1", "c1", ["new", "vip"])
        assert sorted(result["tags"]) == ["new", "vip"]
        assert sorted(mock_update.call_args.args[1]) == ["new", "vip"]

    @pytest.mark.asyncio
    async def test_empty_existing(self, service):
        with patch(
            "api.services.cdp.get_customer_tags_db",
            new_callable=AsyncMock,
            return_value=[],
        ), patch(
            "api.services.cdp.update_customer_tags_db",
            new_callable=AsyncMock,
        ) as mock_update:
            result = await service.tag_customer("t1", "c1", ["a"])
        assert result["tags"] == ["a"]
        mock_update.assert_called_once_with("c1", ["a"])


class TestSearchCustomers:
    @pytest.mark.asyncio
    async def test_delegates_to_db(self, service):
        rows = [{"id": "c1"}]
        with patch(
            "api.services.cdp.search_customers_db",
            new_callable=AsyncMock,
            return_value=rows,
        ) as mock_search:
            assert await service.search_customers("t1", "ali") == rows
        mock_search.assert_called_once_with("t1", "ali")


class TestGetSegments:
    @pytest.mark.asyncio
    async def test_parses_criteria_json(self, service):
        segments = [
            {"id": "s1", "criteria_json": '{"a": 1}'},
            {"id": "s2", "criteria_json": {"b": 2}},
            {"id": "s3"},
        ]
        with patch(
            "api.services.cdp.list_segments_db",
            new_callable=AsyncMock,
            return_value=segments,
        ):
            result = await service.get_segments("t1")
        assert result[0]["criteria"] == {"a": 1}
        assert result[1]["criteria"] == {"b": 2}
        assert result[2]["criteria"] == {}


class TestCreateSegment:
    @pytest.mark.asyncio
    async def test_parses_str_criteria(self, service):
        with patch(
            "api.services.cdp.create_segment_db",
            new_callable=AsyncMock,
            return_value={"id": "s1", "criteria_json": '{"a": 1}'},
        ) as mock_create:
            result = await service.create_segment("t1", "VIP", {"a": 1})
        assert result["criteria"] == {"a": 1}
        mock_create.assert_called_once_with("t1", "VIP", {"a": 1})

    @pytest.mark.asyncio
    async def test_dict_criteria_and_missing(self, service):
        with patch(
            "api.services.cdp.create_segment_db",
            new_callable=AsyncMock,
            side_effect=[
                {"id": "s1", "criteria_json": {"a": 1}},
                {"id": "s2"},
            ],
        ):
            assert (await service.create_segment("t1", "A", {}))["criteria"] == {"a": 1}
            assert (await service.create_segment("t1", "B", {}))["criteria"] == {}


class TestEvaluateSegment:
    @pytest.mark.asyncio
    async def test_segment_not_found(self, service):
        with patch(
            "api.services.cdp._get_segment_db",
            new_callable=AsyncMock,
            return_value=None,
        ), patch(
            "api.services.cdp.update_segment_member_count_db",
            new_callable=AsyncMock,
        ) as mock_count:
            assert await service.evaluate_segment("t1", "seg1") == []
        mock_count.assert_not_called()

    @pytest.mark.asyncio
    async def test_filters_by_min_calls(self, service):
        segment = {"criteria_json": '{"min_calls": 2}'}
        profiles = [{"id": "p1"}, {"id": "p2"}]

        def _ints(tenant_id, pid, limit=500):
            if pid == "p1":
                return [{"channel": "voice"}, {"channel": "voice"}]
            return [{"channel": "voice"}]

        with patch(
            "api.services.cdp._get_segment_db",
            new_callable=AsyncMock,
            return_value=segment,
        ), patch(
            "api.services.cdp.search_customers_db",
            new_callable=AsyncMock,
            return_value=profiles,
        ), patch(
            "api.services.cdp.list_customer_interactions_db",
            new_callable=AsyncMock,
            side_effect=_ints,
        ), patch(
            "api.services.cdp.list_csat_surveys_for_customer_db",
            new_callable=AsyncMock,
            return_value=[],
        ), patch(
            "api.services.cdp.update_segment_member_count_db",
            new_callable=AsyncMock,
        ) as mock_count:
            result = await service.evaluate_segment("t1", "seg1")
        assert [p["id"] for p in result] == ["p1"]
        mock_count.assert_called_once_with("seg1", 1)

    @pytest.mark.asyncio
    async def test_filters_by_avg_csat(self, service):
        segment = {"criteria_json": '{"min_calls": 0, "min_csat": 5}'}
        profiles = [{"id": "p1"}, {"id": "p2"}]

        def _surveys(tenant_id, pid):
            if pid == "p1":
                return [{"rating": 4}]
            return [{"rating": 6}]

        with patch(
            "api.services.cdp._get_segment_db",
            new_callable=AsyncMock,
            return_value=segment,
        ), patch(
            "api.services.cdp.search_customers_db",
            new_callable=AsyncMock,
            return_value=profiles,
        ), patch(
            "api.services.cdp.list_customer_interactions_db",
            new_callable=AsyncMock,
            return_value=[{"channel": "voice"}],
        ), patch(
            "api.services.cdp.list_csat_surveys_for_customer_db",
            new_callable=AsyncMock,
            side_effect=_surveys,
        ), patch(
            "api.services.cdp.update_segment_member_count_db",
            new_callable=AsyncMock,
        ) as mock_count:
            result = await service.evaluate_segment("t1", "seg1")
        assert [p["id"] for p in result] == ["p2"]
        mock_count.assert_called_once_with("seg1", 1)

    @pytest.mark.asyncio
    async def test_filters_by_recency_and_tolerates_bad_dates(self, service):
        now = datetime.now(UTC)
        old = (now - timedelta(days=100)).isoformat()
        recent = (now - timedelta(days=5)).isoformat()
        segment = {"criteria_json": '{"min_calls": 0, "max_recency_days": 30}'}
        profiles = [{"id": "p1"}, {"id": "p2"}, {"id": "p3"}]

        def _ints(tenant_id, pid, limit=500):
            return {
                "p1": [{"channel": "voice", "created_at": old}],
                "p2": [{"channel": "voice", "created_at": recent}],
                "p3": [{"channel": "voice", "created_at": "not-a-date"}],
            }[pid]

        with patch(
            "api.services.cdp._get_segment_db",
            new_callable=AsyncMock,
            return_value=segment,
        ), patch(
            "api.services.cdp.search_customers_db",
            new_callable=AsyncMock,
            return_value=profiles,
        ), patch(
            "api.services.cdp.list_customer_interactions_db",
            new_callable=AsyncMock,
            side_effect=_ints,
        ), patch(
            "api.services.cdp.list_csat_surveys_for_customer_db",
            new_callable=AsyncMock,
            return_value=[],
        ), patch(
            "api.services.cdp.update_segment_member_count_db",
            new_callable=AsyncMock,
        ) as mock_count:
            result = await service.evaluate_segment("t1", "seg1")
        assert [p["id"] for p in result] == ["p2", "p3"]
        mock_count.assert_called_once_with("seg1", 2)

    @pytest.mark.asyncio
    async def test_no_matches_updates_zero(self, service):
        segment = {"criteria_json": '{"min_calls": 10}'}
        with patch(
            "api.services.cdp._get_segment_db",
            new_callable=AsyncMock,
            return_value=segment,
        ), patch(
            "api.services.cdp.search_customers_db",
            new_callable=AsyncMock,
            return_value=[],
        ), patch(
            "api.services.cdp.list_customer_interactions_db",
            new_callable=AsyncMock,
        ), patch(
            "api.services.cdp.list_csat_surveys_for_customer_db",
            new_callable=AsyncMock,
        ), patch(
            "api.services.cdp.update_segment_member_count_db",
            new_callable=AsyncMock,
        ) as mock_count:
            assert await service.evaluate_segment("t1", "seg1") == []
        mock_count.assert_called_once_with("seg1", 0)

    @pytest.mark.asyncio
    async def test_dict_criteria(self, service):
        segment = {"criteria_json": {"min_calls": 0}}
        with patch(
            "api.services.cdp._get_segment_db",
            new_callable=AsyncMock,
            return_value=segment,
        ), patch(
            "api.services.cdp.search_customers_db",
            new_callable=AsyncMock,
            return_value=[],
        ), patch(
            "api.services.cdp.list_customer_interactions_db",
            new_callable=AsyncMock,
        ), patch(
            "api.services.cdp.list_csat_surveys_for_customer_db",
            new_callable=AsyncMock,
        ), patch(
            "api.services.cdp.update_segment_member_count_db",
            new_callable=AsyncMock,
        ):
            assert await service.evaluate_segment("t1", "seg1") == []


class TestGetRfmScores:
    @pytest.mark.asyncio
    async def test_no_interactions_returns_defaults(self, service):
        with patch(
            "api.services.cdp.list_customer_interactions_db",
            new_callable=AsyncMock,
            return_value=[],
        ):
            result = await service.get_rfm_scores("t1", "c1")
        assert result["recency_days"] == 999
        assert result["frequency"] == 0
        assert result["monetary_seconds"] == 0
        assert result["rfm_segment"] == "R1F1M1"

    @pytest.mark.asyncio
    async def test_with_interactions_computes_scores(self, service):
        now = datetime.now(UTC)
        old_date = (now - timedelta(days=60)).isoformat()
        interactions = [
            {
                "channel": "voice",
                "created_at": old_date,
                "duration_seconds": 300,
            },
            {
                "channel": "voice",
                "created_at": old_date,
                "duration_seconds": 300,
            },
            {
                "channel": "voice",
                "created_at": old_date,
                "duration_seconds": 300,
            },
        ]
        with patch(
            "api.services.cdp.list_customer_interactions_db",
            new_callable=AsyncMock,
            return_value=interactions,
        ):
            result = await service.get_rfm_scores("t1", "c1")
        assert result["recency_days"] == 60
        assert result["frequency"] == 3
        assert result["monetary_seconds"] == 900
        assert result["r_score"] == 3
        assert result["f_score"] == 1
        assert result["m_score"] == 4
        assert result["rfm_segment"] == "R3F1M4"

    @pytest.mark.asyncio
    async def test_bad_dates_skipped_and_scores_clamped(self, service):
        now = datetime.now(UTC)
        interactions = [
            {"channel": "sms", "created_at": now.isoformat(), "duration_seconds": 10},
            {"channel": "sms", "created_at": "garbage", "duration_seconds": 10},
        ]
        with patch(
            "api.services.cdp.list_customer_interactions_db",
            new_callable=AsyncMock,
            return_value=interactions,
        ):
            result = await service.get_rfm_scores("t1", "c1")
        assert result["frequency"] == 1
        assert result["r_score"] == 5
        assert result["m_score"] == 1


class TestGetInteractionTimeline:
    @pytest.mark.asyncio
    async def test_builds_and_sorts_timeline(self, service):
        interactions = [
            {
                "id": "i1",
                "channel": "voice",
                "interaction_type": "call",
                "sentiment": "positive",
                "summary": "resolved",
                "created_at": "2026-01-02",
            },
            {
                "id": "i2",
                "channel": "chat",
                "interaction_type": "chat",
                "sentiment": None,
                "summary": None,
                "created_at": "2026-01-01",
            },
        ]
        surveys = [{"rating": 5, "feedback": "great", "created_at": "2026-01-03"}]
        with patch(
            "api.services.cdp.list_customer_interactions_db",
            new_callable=AsyncMock,
            return_value=interactions,
        ), patch(
            "api.services.cdp.list_csat_surveys_for_customer_db",
            new_callable=AsyncMock,
            return_value=surveys,
        ):
            timeline = await service.get_interaction_timeline("t1", "c1")
        assert [t["type"] for t in timeline] == ["csat_survey", "interaction", "interaction"]
        assert timeline[0]["rating"] == 5
        assert timeline[1]["channel"] == "voice"
        assert timeline[2]["interaction_type"] == "chat"

    @pytest.mark.asyncio
    async def test_empty(self, service):
        with patch(
            "api.services.cdp.list_customer_interactions_db",
            new_callable=AsyncMock,
            return_value=[],
        ), patch(
            "api.services.cdp.list_csat_surveys_for_customer_db",
            new_callable=AsyncMock,
            return_value=[],
        ):
            assert await service.get_interaction_timeline("t1", "c1") == []
