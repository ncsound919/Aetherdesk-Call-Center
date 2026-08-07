"""Unit tests for src/api/services/db_cdp.py.

Covers the CDP `*_db` functions (customer profiles, interactions, segments)
under both the SQLite and PostgreSQL (mocked pool) paths.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.services.db_cdp import (
    create_customer_interaction_db,
    create_customer_profile_db,
    create_segment_db,
    find_customers_by_identifier_db,
    get_customer_profile_db,
    get_customer_tags_db,
    get_segment_db,
    list_csat_surveys_for_customer_db,
    list_customer_interactions_db,
    list_segments_db,
    search_customers_db,
    update_customer_tags_db,
    update_segment_member_count_db,
    upsert_customer_profile_db,
)


class FakeConn:
    """Minimal sqlite3-like connection.

    - fetchone/fetchall may be a single value OR a list of values to return
      in sequence (for multi-query functions).
    """

    def __init__(self, fetchone=None, fetchall=None, rowcount=1):
        if isinstance(fetchone, list):
            self._one = list(fetchone)
        else:
            self._one = [fetchone]
        if isinstance(fetchall, list) and fetchall and isinstance(fetchall[0], list):
            self._all = list(fetchall)
        else:
            self._all = [fetchall]
        self.rowcount = rowcount
        self.closed = False
        self.committed = False
        self.last_sql = None
        self.last_params = None
        self.executed_sqls = []
        self.executed_calls = []

    def execute(self, sql, params=None):
        self.last_sql = sql
        self.last_params = params
        self.executed_sqls.append(sql)
        self.executed_calls.append((sql, params))
        return self

    def fetchone(self):
        if self._one:
            return self._one.pop(0)
        return None

    def fetchall(self):
        if self._all:
            return self._all.pop(0)
        return None

    def commit(self):
        self.committed = True

    def close(self):
        self.closed = True


class FakePool:
    """Minimal asyncpg-like pool.

    - fetchrow/fetchval may be a single value OR a list of values to return
      in sequence.
    - fetch expects lists of rows; a single list is a single result, and a
      list-of-lists is a sequence of results.
    """

    def __init__(self, fetchrow=None, fetch=None, fetchval=None):
        if isinstance(fetchrow, list):
            self._row = list(fetchrow)
        else:
            self._row = [fetchrow]
        if isinstance(fetch, list) and fetch and isinstance(fetch[0], list):
            self._rows = list(fetch)
        else:
            self._rows = [fetch]
        if isinstance(fetchval, list):
            self._vals = [fetchval]
        else:
            self._vals = [fetchval]
        self.executed = []
        self.last_fetch_sql = None

    async def fetchrow(self, sql, *params):
        if self._row:
            return self._row.pop(0)
        return None

    async def fetchval(self, sql, *params):
        if self._vals:
            return self._vals.pop(0)
        return None

    async def fetch(self, sql, *params):
        self.last_fetch_sql = sql
        if self._rows:
            return self._rows.pop(0)
        return []

    async def execute(self, sql, *params):
        self.executed.append((sql, params))
        return "OK"


def _patch_conn(conn):
    return patch(
        "api.services.db_cdp._get_sqlite_conn",
        MagicMock(return_value=conn),
    )


def _patch_pg(pool):
    return patch(
        "api.services.db_cdp.get_pg_pool",
        new_callable=AsyncMock,
        return_value=pool,
    )


def _pg_true():
    return patch("api.services.db_cdp.USE_POSTGRES", True)


def _pg_false():
    return patch("api.services.db_cdp.USE_POSTGRES", False)


class TestUpsertCustomerProfile:
    @pytest.mark.asyncio
    async def test_no_updates_delegates_to_get(self):
        with _pg_false(), patch(
            "api.services.db_cdp.get_customer_profile_db",
            new_callable=AsyncMock,
            return_value={"id": "c1", "name": "Existing"},
        ) as mock_get:
            result = await upsert_customer_profile_db(
                "t1", "c1", external_id=None, unknown_field="x"
            )
        assert result == {"id": "c1", "name": "Existing"}
        mock_get.assert_called_once_with("c1")

    @pytest.mark.asyncio
    async def test_sqlite_updates(self):
        conn = FakeConn(fetchone={"id": "c1", "name": "Alice"})
        with _pg_false(), _patch_conn(conn):
            result = await upsert_customer_profile_db(
                "t1", "c1", name="Alice", email="a@b.com", phone=None
            )
        assert result == {"id": "c1", "name": "Alice"}
        update_sql, update_params = conn.executed_calls[0]
        assert "UPDATE customer_profiles SET name = ?, email = ?, updated_at = ?" in update_sql
        assert update_params[-1] == "c1"
        assert conn.committed is True
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_row_none(self):
        conn = FakeConn(fetchone=None)
        with _pg_false(), _patch_conn(conn):
            assert await upsert_customer_profile_db("t1", "c1", name="Alice") is None

    @pytest.mark.asyncio
    async def test_pg_updates(self):
        pool = FakePool(fetchrow={"id": "c1", "email": "a@b.com"})
        with _pg_true(), _patch_pg(pool):
            result = await upsert_customer_profile_db(
                "t1", "c1", email="a@b.com", tags_json='["vip"]'
            )
        assert result == {"id": "c1", "email": "a@b.com"}
        sql, params = pool.executed[0]
        assert "UPDATE customer_profiles SET email = $1, tags_json = $2, updated_at = NOW()" in sql
        assert params == ("a@b.com", '["vip"]', "c1")

    @pytest.mark.asyncio
    async def test_pg_row_none(self):
        pool = FakePool(fetchrow=None)
        with _pg_true(), _patch_pg(pool):
            assert await upsert_customer_profile_db("t1", "c1", email="x@y.z") is None

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await upsert_customer_profile_db("t1", "c1", email="x@y.z") is None


class TestCreateCustomerProfile:
    @pytest.mark.asyncio
    async def test_sqlite_full(self):
        conn = FakeConn(fetchone={"id": "c1", "name": "Alice"})
        with _pg_false(), _patch_conn(conn):
            result = await create_customer_profile_db(
                "t1",
                name="Alice",
                phone="+1555",
                email="a@b.com",
                external_id="ext1",
                tags=["vip", "new"],
                metadata={"region": "US"},
            )
        assert result == {"id": "c1", "name": "Alice"}
        insert_sql, insert_params = conn.executed_calls[0]
        assert "INSERT INTO customer_profiles" in insert_sql
        assert insert_params[2] == "ext1"
        assert insert_params[6] == '["vip", "new"]'
        assert conn.committed is True
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_row_none(self):
        conn = FakeConn(fetchone=None)
        with _pg_false(), _patch_conn(conn):
            assert await create_customer_profile_db("t1") is None

    @pytest.mark.asyncio
    async def test_pg_full(self):
        pool = FakePool(fetchrow={"id": "c1", "name": "Alice"})
        with _pg_true(), _patch_pg(pool):
            result = await create_customer_profile_db(
                "t1", name="Alice", tags=["vip"]
            )
        assert result == {"id": "c1", "name": "Alice"}
        sql, params = pool.executed[0]
        assert "INSERT INTO customer_profiles" in sql
        assert params[1] == "t1"
        assert params[5] == "Alice"
        assert params[6] == '["vip"]'

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await create_customer_profile_db("t1", name="Alice") is None


class TestGetCustomerProfile:
    @pytest.mark.asyncio
    async def test_sqlite_found(self):
        conn = FakeConn(fetchone={"id": "c1", "name": "Alice"})
        with _pg_false(), _patch_conn(conn):
            result = await get_customer_profile_db("c1")
        assert result == {"id": "c1", "name": "Alice"}
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_not_found(self):
        conn = FakeConn(fetchone=None)
        with _pg_false(), _patch_conn(conn):
            assert await get_customer_profile_db("c1") is None

    @pytest.mark.asyncio
    async def test_pg_found(self):
        pool = FakePool(fetchrow={"id": "c1"})
        with _pg_true(), _patch_pg(pool):
            assert await get_customer_profile_db("c1") == {"id": "c1"}

    @pytest.mark.asyncio
    async def test_pg_not_found(self):
        pool = FakePool(fetchrow=None)
        with _pg_true(), _patch_pg(pool):
            assert await get_customer_profile_db("c1") is None

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await get_customer_profile_db("c1") is None


class TestFindCustomersByIdentifier:
    @pytest.mark.asyncio
    async def test_sqlite_with_identifiers(self):
        conn = FakeConn(fetchall=[[{"id": "c1", "email": "a@b.com"}]])
        with _pg_false(), _patch_conn(conn):
            result = await find_customers_by_identifier_db(
                "t1", {"email": "a@b.com", "phone": None}
            )
        assert result == [{"id": "c1", "email": "a@b.com"}]
        assert "(email = ?)" in conn.last_sql
        assert conn.last_params == ["t1", "a@b.com"]
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_no_identifiers(self):
        conn = FakeConn(fetchall=[])
        with _pg_false(), _patch_conn(conn):
            assert await find_customers_by_identifier_db("t1", {}) == []
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_pg_with_identifiers(self):
        pool = FakePool(fetch=[[{"id": "c1", "phone": "+1555"}]])
        with _pg_true(), _patch_pg(pool):
            result = await find_customers_by_identifier_db(
                "t1", {"email": None, "phone": "+1555"}
            )
        assert result == [{"id": "c1", "phone": "+1555"}]
        assert "phone = $2" in pool.last_fetch_sql

    @pytest.mark.asyncio
    async def test_pg_no_identifiers(self):
        pool = FakePool()
        with _pg_true(), _patch_pg(pool):
            assert await find_customers_by_identifier_db("t1", {}) == []
        assert pool.executed == []

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await find_customers_by_identifier_db(
                "t1", {"email": "a@b.com"}
            ) == []


class TestSearchCustomers:
    @pytest.mark.asyncio
    async def test_sqlite_returns_rows(self):
        conn = FakeConn(fetchall=[[{"id": "c1", "name": "Alice"}]])
        with _pg_false(), _patch_conn(conn):
            result = await search_customers_db("t1", "ali")
        assert result == [{"id": "c1", "name": "Alice"}]
        assert conn.last_params == ("t1", "%ali%", "%ali%", "%ali%")
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_empty(self):
        conn = FakeConn(fetchall=[])
        with _pg_false(), _patch_conn(conn):
            assert await search_customers_db("t1", "zzz") == []

    @pytest.mark.asyncio
    async def test_pg_returns_rows(self):
        pool = FakePool(fetch=[[{"id": "c1"}]])
        with _pg_true(), _patch_pg(pool):
            result = await search_customers_db("t1", "ali")
        assert result == [{"id": "c1"}]
        assert "ILIKE $2" in pool.last_fetch_sql

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await search_customers_db("t1", "ali") == []


class TestUpdateCustomerTags:
    @pytest.mark.asyncio
    async def test_sqlite(self):
        conn = FakeConn()
        with _pg_false(), _patch_conn(conn):
            await update_customer_tags_db("c1", ["vip"])
        assert "UPDATE customer_profiles SET tags_json = ?" in conn.last_sql
        assert conn.last_params[0] == '["vip"]'
        assert conn.committed is True
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_pg(self):
        pool = FakePool()
        with _pg_true(), _patch_pg(pool):
            await update_customer_tags_db("c1", ["vip"])
        sql, params = pool.executed[0]
        assert "tags_json = $1::jsonb" in sql
        assert params == ('["vip"]', "c1")

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            await update_customer_tags_db("c1", ["vip"])


class TestGetCustomerTags:
    @pytest.mark.asyncio
    async def test_sqlite_row(self):
        conn = FakeConn(fetchone={"tags_json": '["a", "b"]'})
        with _pg_false(), _patch_conn(conn):
            assert await get_customer_tags_db("c1") == ["a", "b"]
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_row_none(self):
        conn = FakeConn(fetchone=None)
        with _pg_false(), _patch_conn(conn):
            assert await get_customer_tags_db("c1") == []

    @pytest.mark.asyncio
    async def test_pg_row_str(self):
        pool = FakePool(fetchval='["x"]')
        with _pg_true(), _patch_pg(pool):
            assert await get_customer_tags_db("c1") == ["x"]

    @pytest.mark.asyncio
    async def test_pg_row_already_parsed(self):
        pool = FakePool(fetchval=["y", "z"])
        with _pg_true(), _patch_pg(pool):
            assert await get_customer_tags_db("c1") == ["y", "z"]

    @pytest.mark.asyncio
    async def test_pg_row_none(self):
        pool = FakePool(fetchval=None)
        with _pg_true(), _patch_pg(pool):
            assert await get_customer_tags_db("c1") == []

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await get_customer_tags_db("c1") == []


class TestListCustomerInteractions:
    @pytest.mark.asyncio
    async def test_sqlite_returns_rows(self):
        conn = FakeConn(fetchall=[[{"id": "i1", "interaction_type": "call"}]])
        with _pg_false(), _patch_conn(conn):
            result = await list_customer_interactions_db("t1", "c1", limit=10)
        assert result == [{"id": "i1", "interaction_type": "call"}]
        assert conn.last_params == ("t1", "c1", 10)
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_empty(self):
        conn = FakeConn(fetchall=[])
        with _pg_false(), _patch_conn(conn):
            assert await list_customer_interactions_db("t1", "c1") == []

    @pytest.mark.asyncio
    async def test_pg_returns_rows(self):
        pool = FakePool(fetch=[[{"id": "i1"}]])
        with _pg_true(), _patch_pg(pool):
            result = await list_customer_interactions_db("t1", "c1")
        assert result == [{"id": "i1"}]
        assert "LIMIT $3" in pool.last_fetch_sql

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await list_customer_interactions_db("t1", "c1") is None


class TestListCsatSurveysForCustomer:
    @pytest.mark.asyncio
    async def test_sqlite_returns_rows(self):
        conn = FakeConn(fetchall=[[{"id": "s1", "rating": 5}]])
        with _pg_false(), _patch_conn(conn):
            result = await list_csat_surveys_for_customer_db("t1", "c1")
        assert result == [{"id": "s1", "rating": 5}]
        assert "FROM csat_surveys" in conn.last_sql
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_empty(self):
        conn = FakeConn(fetchall=[])
        with _pg_false(), _patch_conn(conn):
            assert await list_csat_surveys_for_customer_db("t1", "c1") == []

    @pytest.mark.asyncio
    async def test_pg_returns_rows(self):
        pool = FakePool(fetch=[[{"id": "s1"}]])
        with _pg_true(), _patch_pg(pool):
            result = await list_csat_surveys_for_customer_db("t1", "c1")
        assert result == [{"id": "s1"}]
        assert "FROM csat_surveys" in pool.last_fetch_sql

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await list_csat_surveys_for_customer_db("t1", "c1") is None


class TestCreateCustomerInteraction:
    @pytest.mark.asyncio
    async def test_sqlite_returns_row(self):
        conn = FakeConn(fetchone={"id": "i1", "interaction_type": "call"})
        with _pg_false(), _patch_conn(conn):
            result = await create_customer_interaction_db(
                "t1",
                "c1",
                "call",
                channel="voice",
                call_id="call1",
                agent_id="a1",
                sentiment="positive",
                summary="resolved",
                duration_seconds=42,
            )
        assert result == {"id": "i1", "interaction_type": "call"}
        insert_sql, insert_params = conn.executed_calls[0]
        assert "INSERT INTO customer_interactions" in insert_sql
        assert insert_params[5] == "call1"
        assert insert_params[7] == "positive"
        assert insert_params[9] == 42
        assert conn.committed is True
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_row_none(self):
        conn = FakeConn(fetchone=None)
        with _pg_false(), _patch_conn(conn):
            assert await create_customer_interaction_db("t1", "c1", "call") is None

    @pytest.mark.asyncio
    async def test_pg_returns_row(self):
        pool = FakePool(fetchrow={"id": "i1"})
        with _pg_true(), _patch_pg(pool):
            result = await create_customer_interaction_db("t1", "c1", "call")
        assert result == {"id": "i1"}
        sql, params = pool.executed[0]
        assert "INSERT INTO customer_interactions" in sql
        assert params[2] == "c1"
        assert params[4] == "voice"

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await create_customer_interaction_db("t1", "c1", "call") is None


class TestCreateSegment:
    @pytest.mark.asyncio
    async def test_sqlite_criteria_dict(self):
        conn = FakeConn(fetchone={"id": "seg1", "name": "VIP"})
        with _pg_false(), _patch_conn(conn):
            result = await create_segment_db(
                "t1", "VIP", {"min_rating": 9}
            )
        assert result == {"id": "seg1", "name": "VIP"}
        insert_sql, insert_params = conn.executed_calls[0]
        assert "INSERT INTO customer_segments" in insert_sql
        assert insert_params[3] == '{"min_rating": 9}'
        assert conn.committed is True
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_criteria_str(self):
        conn = FakeConn(fetchone={"id": "seg1"})
        with _pg_false(), _patch_conn(conn):
            result = await create_segment_db("t1", "VIP", '{"min_rating": 9}')
        assert result == {"id": "seg1"}
        insert_sql, insert_params = conn.executed_calls[0]
        assert "INSERT INTO customer_segments" in insert_sql
        assert insert_params[3] == '{"min_rating": 9}'

    @pytest.mark.asyncio
    async def test_sqlite_row_none(self):
        conn = FakeConn(fetchone=None)
        with _pg_false(), _patch_conn(conn):
            assert await create_segment_db("t1", "VIP", {"a": 1}) is None

    @pytest.mark.asyncio
    async def test_pg_criteria_dict(self):
        pool = FakePool(fetchrow={"id": "seg1"})
        with _pg_true(), _patch_pg(pool):
            result = await create_segment_db("t1", "VIP", {"a": 1})
        assert result == {"id": "seg1"}
        sql, params = pool.executed[0]
        assert "INSERT INTO customer_segments" in sql
        assert params[3] == '{"a": 1}'

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await create_segment_db("t1", "VIP", {"a": 1}) is None


class TestListSegments:
    @pytest.mark.asyncio
    async def test_sqlite_returns_rows(self):
        conn = FakeConn(fetchall=[[{"id": "seg1", "name": "VIP"}]])
        with _pg_false(), _patch_conn(conn):
            result = await list_segments_db("t1")
        assert result == [{"id": "seg1", "name": "VIP"}]
        assert conn.last_params == ("t1",)
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_empty(self):
        conn = FakeConn(fetchall=[])
        with _pg_false(), _patch_conn(conn):
            assert await list_segments_db("t1") == []

    @pytest.mark.asyncio
    async def test_pg_returns_rows(self):
        pool = FakePool(fetch=[[{"id": "seg1"}]])
        with _pg_true(), _patch_pg(pool):
            result = await list_segments_db("t1")
        assert result == [{"id": "seg1"}]
        assert "FROM customer_segments" in pool.last_fetch_sql

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await list_segments_db("t1") is None


class TestGetSegment:
    @pytest.mark.asyncio
    async def test_sqlite_found(self):
        conn = FakeConn(fetchone={"id": "seg1", "name": "VIP"})
        with _pg_false(), _patch_conn(conn):
            result = await get_segment_db("seg1")
        assert result == {"id": "seg1", "name": "VIP"}
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_not_found(self):
        conn = FakeConn(fetchone=None)
        with _pg_false(), _patch_conn(conn):
            assert await get_segment_db("seg1") is None

    @pytest.mark.asyncio
    async def test_pg_found(self):
        pool = FakePool(fetchrow={"id": "seg1"})
        with _pg_true(), _patch_pg(pool):
            assert await get_segment_db("seg1") == {"id": "seg1"}

    @pytest.mark.asyncio
    async def test_pg_not_found(self):
        pool = FakePool(fetchrow=None)
        with _pg_true(), _patch_pg(pool):
            assert await get_segment_db("seg1") is None

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await get_segment_db("seg1") is None


class TestUpdateSegmentMemberCount:
    @pytest.mark.asyncio
    async def test_sqlite(self):
        conn = FakeConn()
        with _pg_false(), _patch_conn(conn):
            await update_segment_member_count_db("seg1", 42)
        assert "UPDATE customer_segments SET member_count = ?" in conn.last_sql
        assert conn.last_params == (42, "seg1")
        assert conn.committed is True
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_pg(self):
        pool = FakePool()
        with _pg_true(), _patch_pg(pool):
            await update_segment_member_count_db("seg1", 42)
        sql, params = pool.executed[0]
        assert "member_count = $1" in sql
        assert params == (42, "seg1")

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            await update_segment_member_count_db("seg1", 42)
