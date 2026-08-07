"""Unit tests for src/api/services/db_admin_ops.py.

Covers SEO content, donors, coupons, contact notes, and flyer saves under both
SQLite (fake conn) and PostgreSQL (fake asyncpg pool) paths. Unlike the
guarded pattern in other db modules, these helpers fall back to SQLite when
``USE_POSTGRES`` is True but the pool is unavailable.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.services.db_admin_ops import (
    _now,
    _row_to_dict,
    add_contact_note_db,
    create_coupon_db,
    create_donor_db,
    create_flyer_save_db,
    get_seo_content_db,
    list_contact_notes_db,
    list_coupons_db,
    list_donors_db,
    list_flyer_saves_db,
    list_seo_content_db,
    set_coupon_status_db,
    upsert_seo_content_db,
)


class FakeConn:
    """Minimal sqlite3-like connection (single-value or sequential fetchone)."""

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
    """Minimal asyncpg-like pool."""

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
        self.fetchrow_calls = []
        self.last_fetch_sql = None

    async def fetchrow(self, sql, *params):
        self.fetchrow_calls.append((sql, params))
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
        "api.services.db_admin_ops._get_sqlite_conn",
        MagicMock(return_value=conn),
    )


def _patch_pg(pool):
    return patch(
        "api.services.db_admin_ops.get_pg_pool",
        new_callable=AsyncMock,
        return_value=pool,
    )


def _pg_true():
    return patch("api.services.db_admin_ops.USE_POSTGRES", True)


def _pg_false():
    return patch("api.services.db_admin_ops.USE_POSTGRES", False)


class TestHelpers:
    def test_now_returns_iso(self):
        assert "T" in _now()

    def test_row_to_dict_none(self):
        assert _row_to_dict(None, ("a",)) is None

    def test_row_to_dict_dict_passthrough(self):
        assert _row_to_dict({"a": 1}, ("a",)) == {"a": 1}

    def test_row_to_dict_tuple_zips(self):
        assert _row_to_dict((1, "x"), ("id", "name")) == {"id": 1, "name": "x"}


class TestListSeoContent:
    @pytest.mark.asyncio
    async def test_sqlite_no_status(self):
        rows = [{"slug": "a", "status": "published"}]
        conn = FakeConn(fetchall=rows)
        with _pg_false(), _patch_conn(conn):
            result = await list_seo_content_db()
        assert result == rows
        assert "WHERE status" not in conn.last_sql

    @pytest.mark.asyncio
    async def test_sqlite_with_status(self):
        conn = FakeConn(fetchall=[{"slug": "a"}])
        with _pg_false(), _patch_conn(conn):
            result = await list_seo_content_db(status="draft")
        assert result == [{"slug": "a"}]
        assert conn.last_params == ("draft",)

    @pytest.mark.asyncio
    async def test_sqlite_tuple_rows(self):
        conn = FakeConn(fetchall=[("id1", "slug-a")])
        with _pg_false(), _patch_conn(conn):
            result = await list_seo_content_db()
        assert result[0]["id"] == "id1"
        assert result[0]["slug"] == "slug-a"

    @pytest.mark.asyncio
    async def test_pg_no_status(self):
        pool = FakePool(fetch=[{"slug": "a"}])
        with _pg_true(), _patch_pg(pool):
            result = await list_seo_content_db()
        assert result == [{"slug": "a"}]
        assert "WHERE status" not in pool.last_fetch_sql

    @pytest.mark.asyncio
    async def test_pg_with_status(self):
        pool = FakePool(fetch=[{"slug": "a"}])
        with _pg_true(), _patch_pg(pool):
            result = await list_seo_content_db(status="published")
        assert result == [{"slug": "a"}]
        assert "status = $1" in pool.last_fetch_sql

    @pytest.mark.asyncio
    async def test_pg_no_pool_falls_back_to_sqlite(self):
        conn = FakeConn(fetchall=[{"slug": "a"}])
        with _pg_true(), _patch_pg(None), _patch_conn(conn):
            result = await list_seo_content_db()
        assert result == [{"slug": "a"}]


class TestGetSeoContent:
    @pytest.mark.asyncio
    async def test_sqlite_found(self):
        conn = FakeConn(fetchone={"slug": "a", "status": "draft"})
        with _pg_false(), _patch_conn(conn):
            assert await get_seo_content_db("a") == {"slug": "a", "status": "draft"}
        assert conn.last_params == ("a",)

    @pytest.mark.asyncio
    async def test_sqlite_not_found(self):
        conn = FakeConn(fetchone=None)
        with _pg_false(), _patch_conn(conn):
            assert await get_seo_content_db("a") is None

    @pytest.mark.asyncio
    async def test_sqlite_tuple_row(self):
        conn = FakeConn(fetchone=("id1", "slug-a"))
        with _pg_false(), _patch_conn(conn):
            result = await get_seo_content_db("slug-a")
        assert result["id"] == "id1"
        assert result["slug"] == "slug-a"

    @pytest.mark.asyncio
    async def test_pg_found(self):
        pool = FakePool(fetchrow={"slug": "a"})
        with _pg_true(), _patch_pg(pool):
            assert await get_seo_content_db("a") == {"slug": "a"}

    @pytest.mark.asyncio
    async def test_pg_not_found(self):
        pool = FakePool(fetchrow=None)
        with _pg_true(), _patch_pg(pool):
            assert await get_seo_content_db("a") is None

    @pytest.mark.asyncio
    async def test_pg_no_pool_falls_back(self):
        conn = FakeConn(fetchone={"slug": "a"})
        with _pg_true(), _patch_pg(None), _patch_conn(conn):
            assert await get_seo_content_db("a") == {"slug": "a"}


class TestUpsertSeoContent:
    data = {
        "meta_title": "T",
        "meta_description": "D",
        "og_title": "OT",
        "og_description": "OD",
        "og_image": "img.png",
        "keywords": ["k"],
        "body": "<p>Hi</p>",
    }

    @pytest.mark.asyncio
    async def test_sqlite_existing_updates(self):
        row = {"slug": "a", "status": "published"}
        conn = FakeConn(fetchone=[{"id": "c1"}, row])
        with _pg_false(), _patch_conn(conn):
            result = await upsert_seo_content_db("a", self.data)
        assert result == row
        assert any("UPDATE seo_content" in s for s in conn.executed_sqls)
        assert conn.committed is True

    @pytest.mark.asyncio
    async def test_sqlite_missing_inserts(self):
        row = {"slug": "a", "status": "draft"}
        conn = FakeConn(fetchone=[None, row])
        with _pg_false(), _patch_conn(conn):
            result = await upsert_seo_content_db("a", self.data)
        assert result == row
        assert any("INSERT INTO seo_content" in s for s in conn.executed_sqls)
        assert conn.committed is True

    @pytest.mark.asyncio
    async def test_pg(self):
        pool = FakePool(fetchrow={"slug": "a", "status": "draft"})
        with _pg_true(), _patch_pg(pool):
            result = await upsert_seo_content_db("a", self.data)
        assert result == {"slug": "a", "status": "draft"}
        sql, params = pool.fetchrow_calls[0]
        assert "ON CONFLICT (slug)" in sql
        assert params[1] == "a"
        assert params[9] == "draft"

    @pytest.mark.asyncio
    async def test_pg_no_pool_falls_back(self):
        row = {"slug": "a"}
        conn = FakeConn(fetchone=[None, row])
        with _pg_true(), _patch_pg(None), _patch_conn(conn):
            result = await upsert_seo_content_db("a", self.data)
        assert result == row


class TestDonors:
    @pytest.mark.asyncio
    async def test_list_sqlite(self):
        rows = [{"id": "d1", "name": "Bob"}]
        conn = FakeConn(fetchall=rows)
        with _pg_false(), _patch_conn(conn):
            assert await list_donors_db() == rows

    @pytest.mark.asyncio
    async def test_list_pg(self):
        pool = FakePool(fetch=[{"id": "d1"}])
        with _pg_true(), _patch_pg(pool):
            assert await list_donors_db() == [{"id": "d1"}]

    @pytest.mark.asyncio
    async def test_list_pg_no_pool_falls_back(self):
        conn = FakeConn(fetchall=[{"id": "d1"}])
        with _pg_true(), _patch_pg(None), _patch_conn(conn):
            assert await list_donors_db() == [{"id": "d1"}]

    @pytest.mark.asyncio
    async def test_create_sqlite(self):
        row = {"id": "d1", "name": "Bob"}
        conn = FakeConn(fetchone=row)
        with _pg_false(), _patch_conn(conn):
            result = await create_donor_db(
                "Bob", "b@b.com", "+1", 100.0, "USD", "gold", "note", "2026-01-01"
            )
        assert result == row
        insert_sql, insert_params = conn.executed_calls[0]
        assert "INSERT INTO donors" in insert_sql
        assert insert_params[1] == "Bob"
        assert conn.committed is True

    @pytest.mark.asyncio
    async def test_create_pg(self):
        pool = FakePool(fetchrow={"id": "d1"})
        with _pg_true(), _patch_pg(pool):
            result = await create_donor_db(
                "Bob", "b@b.com", "+1", 100.0, "USD", "gold", "note", "2026-01-01"
            )
        assert result == {"id": "d1"}
        sql, params = pool.executed[0]
        assert "INSERT INTO donors" in sql
        assert params[1] == "Bob"


class TestCoupons:
    @pytest.mark.asyncio
    async def test_list_sqlite(self):
        rows = [{"id": "c1", "code": "SAVE10"}]
        conn = FakeConn(fetchall=rows)
        with _pg_false(), _patch_conn(conn):
            assert await list_coupons_db() == rows

    @pytest.mark.asyncio
    async def test_list_pg(self):
        pool = FakePool(fetch=[{"id": "c1"}])
        with _pg_true(), _patch_pg(pool):
            assert await list_coupons_db() == [{"id": "c1"}]

    @pytest.mark.asyncio
    async def test_create_sqlite(self):
        row = {"id": "c1", "code": "SAVE10"}
        conn = FakeConn(fetchone=row)
        with _pg_false(), _patch_conn(conn):
            result = await create_coupon_db(
                "SAVE10", "percent", 10, 50, 100, "2026-01-01", "2026-12-31", "sc", "active"
            )
        assert result == row
        insert_sql, insert_params = conn.executed_calls[0]
        assert "INSERT INTO coupons" in insert_sql
        assert insert_params[1] == "SAVE10"
        assert insert_params[2] == "percent"
        assert conn.committed is True

    @pytest.mark.asyncio
    async def test_create_pg(self):
        pool = FakePool(fetchrow={"id": "c1"})
        with _pg_true(), _patch_pg(pool):
            result = await create_coupon_db(
                "SAVE10", "percent", 10, 50, 100, "2026-01-01", "2026-12-31", "sc", "active"
            )
        assert result == {"id": "c1"}
        sql, params = pool.executed[0]
        assert "INSERT INTO coupons" in sql
        assert params[1] == "SAVE10"

    @pytest.mark.asyncio
    async def test_set_status_sqlite(self):
        conn = FakeConn()
        with _pg_false(), _patch_conn(conn):
            await set_coupon_status_db("c1", "disabled")
        assert "UPDATE coupons SET status=?" in conn.last_sql
        assert conn.last_params == ("disabled", "c1")
        assert conn.committed is True

    @pytest.mark.asyncio
    async def test_set_status_pg(self):
        pool = FakePool()
        with _pg_true(), _patch_pg(pool):
            await set_coupon_status_db("c1", "disabled")
        sql, params = pool.executed[0]
        assert "UPDATE coupons SET status=$2 WHERE id=$1" in sql
        assert params == ("c1", "disabled")

    @pytest.mark.asyncio
    async def test_set_status_pg_no_pool_falls_back(self):
        conn = FakeConn()
        with _pg_true(), _patch_pg(None), _patch_conn(conn):
            await set_coupon_status_db("c1", "disabled")
        assert conn.committed is True


class TestContactNotes:
    @pytest.mark.asyncio
    async def test_add_sqlite(self):
        conn = FakeConn()
        with _pg_false(), _patch_conn(conn):
            await add_contact_note_db("call", "c1", "note text")
        assert "INSERT INTO contact_notes" in conn.last_sql
        assert conn.last_params[1] == "call"
        assert conn.last_params[3] == "note text"
        assert conn.committed is True

    @pytest.mark.asyncio
    async def test_add_pg(self):
        pool = FakePool()
        with _pg_true(), _patch_pg(pool):
            await add_contact_note_db("call", "c1", "note text")
        sql, params = pool.executed[0]
        assert "INSERT INTO contact_notes" in sql
        assert params[1] == "call"

    @pytest.mark.asyncio
    async def test_list_sqlite(self):
        rows = [{"id": "n1", "source": "call"}]
        conn = FakeConn(fetchall=rows)
        with _pg_false(), _patch_conn(conn):
            result = await list_contact_notes_db("call", "c1")
        assert result == rows
        assert conn.last_params == ("call", "c1")

    @pytest.mark.asyncio
    async def test_list_pg(self):
        pool = FakePool(fetch=[{"id": "n1"}])
        with _pg_true(), _patch_pg(pool):
            result = await list_contact_notes_db("call", "c1")
        assert result == [{"id": "n1"}]
        assert "ORDER BY created_at DESC" in pool.last_fetch_sql

    @pytest.mark.asyncio
    async def test_list_pg_no_pool_falls_back(self):
        conn = FakeConn(fetchall=[{"id": "n1"}])
        with _pg_true(), _patch_pg(None), _patch_conn(conn):
            assert await list_contact_notes_db("call", "c1") == [{"id": "n1"}]


class TestFlyerSaves:
    @pytest.mark.asyncio
    async def test_list_sqlite_parses_config_json(self):
        rows = [
            {"id": "f1", "config_json": '{"theme": "dark"}'},
            {"id": "f2", "config_json": {"theme": "light"}},
            {"id": "f3", "config_json": "not-json"},
        ]
        conn = FakeConn(fetchall=rows)
        with _pg_false(), _patch_conn(conn):
            result = await list_flyer_saves_db()
        assert result[0]["config_json"] == {"theme": "dark"}
        assert result[1]["config_json"] == {"theme": "light"}
        assert result[2]["config_json"] == {}

    @pytest.mark.asyncio
    async def test_list_pg(self):
        pool = FakePool(fetch=[{"id": "f1"}])
        with _pg_true(), _patch_pg(pool):
            assert await list_flyer_saves_db() == [{"id": "f1"}]

    @pytest.mark.asyncio
    async def test_create_sqlite(self):
        row = {"id": "f1", "config_json": '{"theme": "dark"}'}
        conn = FakeConn(fetchone=row)
        with _pg_false(), _patch_conn(conn):
            result = await create_flyer_save_db(
                "t1", "Title", "Sub", "CTA", "https://x.com", "dark", "logo.png", {"x": 1}
            )
        assert result == row
        insert_sql, insert_params = conn.executed_calls[0]
        assert "INSERT INTO flyer_saves" in insert_sql
        assert insert_params[8] == '{"x": 1}'
        assert conn.committed is True

    @pytest.mark.asyncio
    async def test_create_sqlite_config_none(self):
        conn = FakeConn(fetchone={"id": "f1"})
        with _pg_false(), _patch_conn(conn):
            await create_flyer_save_db("t1", "Title", "", "", "", "", "", None)
        assert conn.executed_calls[0][1][8] == "{}"

    @pytest.mark.asyncio
    async def test_create_pg(self):
        pool = FakePool(fetchrow={"id": "f1"})
        with _pg_true(), _patch_pg(pool):
            result = await create_flyer_save_db(
                "t1", "Title", "", "", "", "dark", "", {"a": 1}
            )
        assert result == {"id": "f1"}
        sql, params = pool.executed[0]
        assert "INSERT INTO flyer_saves" in sql
        assert params[8] == '{"a": 1}'
