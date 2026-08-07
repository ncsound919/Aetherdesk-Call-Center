"""Unit tests for src/api/services/db_ai_assist.py.

Uses the established fake-sqlite / fake-asyncpg pattern from
test_db_platform_ops.py: FakeConn for the SQLite branch, FakePool for the
Postgres branch, and patch() of the module-level USE_POSTGRES / _get_sqlite_conn
/ get_pg_pool globals.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import api.services.db_ai_assist as module
from api.services.db_ai_assist import (
    create_knowledge_snippet_db,
    delete_knowledge_snippet_db,
    list_knowledge_snippets_db,
    search_knowledge_snippets_db,
)

ROW = {"id": "s1", "tenant_id": "t1", "title": "Refund policy", "content": "Body"}


class FakeCursor:
    def __init__(self, rowcount=1):
        self.rowcount = rowcount
        self.executed = []

    def execute(self, sql, params=None):
        self.executed.append((sql, params))
        return self


class FakeConn:
    def __init__(self, fetchone=None, fetchall=None, rowcount=1):
        self._one = fetchone
        self._all = fetchall
        self.rowcount = rowcount
        self.closed = False
        self.committed = False
        self.last_sql = None
        self.last_params = None
        self.executed_sqls = []
        self.executed_params = []
        self.last_cursor = None

    def execute(self, sql, params=None):
        self.last_sql = sql
        self.last_params = params
        self.executed_sqls.append(sql)
        self.executed_params.append(params)
        return self

    def fetchone(self):
        return self._one

    def fetchall(self):
        return self._all

    def commit(self):
        self.committed = True

    def close(self):
        self.closed = True

    def cursor(self):
        self.last_cursor = FakeCursor(rowcount=self.rowcount)
        return self.last_cursor


class FakePool:
    def __init__(self, fetchrow=None, fetch=None, execute_result="OK"):
        self._row = fetchrow
        self._rows = fetch or []
        self._execute_result = execute_result
        self.executed = []
        self.fetched = []

    async def fetchrow(self, sql, *params):
        self.fetched.append((sql, params))
        return self._row

    async def fetch(self, sql, *params):
        self.fetched.append((sql, params))
        return self._rows

    async def execute(self, sql, *params):
        self.executed.append((sql, params))
        return self._execute_result


def _patch_conn(conn):
    return patch(
        "api.services.db_ai_assist._get_sqlite_conn",
        MagicMock(return_value=conn),
    )


def _patch_pg(pool):
    return patch(
        "api.services.db_ai_assist.get_pg_pool",
        new_callable=AsyncMock,
        return_value=pool,
    )


def _pg_true():
    return patch("api.services.db_ai_assist.USE_POSTGRES", True)


def _pg_false():
    return patch("api.services.db_ai_assist.USE_POSTGRES", False)


class TestCreateKnowledgeSnippet:
    @pytest.mark.asyncio
    async def test_sqlite_found(self):
        conn = FakeConn(fetchone=ROW)
        with _pg_false(), _patch_conn(conn):
            result = await create_knowledge_snippet_db(
                "t1", "Refund policy", "Body", tags=["refund"], category="policy"
            )
        assert result == ROW
        assert "INSERT INTO knowledge_snippets" in conn.executed_sqls[0]
        assert conn.executed_params[0][5] == "policy"
        assert '"refund"' in conn.executed_params[0][4]
        assert conn.committed is True
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_default_tags_and_category(self):
        conn = FakeConn(fetchone=ROW)
        with _pg_false(), _patch_conn(conn):
            result = await create_knowledge_snippet_db("t1", "Title", "Body")
        assert result == ROW
        assert conn.executed_params[0][4] == "[]"
        assert conn.executed_params[0][5] == "general"

    @pytest.mark.asyncio
    async def test_sqlite_not_found(self):
        conn = FakeConn(fetchone=None)
        with _pg_false(), _patch_conn(conn):
            assert (
                await create_knowledge_snippet_db("t1", "T", "B") is None
            )

    @pytest.mark.asyncio
    async def test_pg_found(self):
        pool = FakePool(fetchrow=ROW)
        with _pg_true(), _patch_pg(pool):
            result = await create_knowledge_snippet_db(
                "t1", "Refund policy", "Body", tags=["refund"]
            )
        assert result == ROW
        assert "INSERT INTO knowledge_snippets" in pool.executed[0][0]
        assert '"refund"' in pool.executed[0][1][4]

    @pytest.mark.asyncio
    async def test_pg_not_found(self):
        pool = FakePool(fetchrow=None)
        with _pg_true(), _patch_pg(pool):
            assert await create_knowledge_snippet_db("t1", "T", "B") is None

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await create_knowledge_snippet_db("t1", "T", "B") is None


class TestSearchKnowledgeSnippets:
    @pytest.mark.asyncio
    async def test_sqlite_returns_rows(self):
        conn = FakeConn(fetchall=[ROW])
        with _pg_false(), _patch_conn(conn):
            result = await search_knowledge_snippets_db("t1", "refund", limit=5)
        assert result == [ROW]
        assert "title LIKE ? OR content LIKE ?" in conn.last_sql
        assert conn.last_params == ("t1", "%refund%", "%refund%", 5)
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_empty(self):
        conn = FakeConn(fetchall=[])
        with _pg_false(), _patch_conn(conn):
            assert await search_knowledge_snippets_db("t1", "x") == []

    @pytest.mark.asyncio
    async def test_pg_returns_rows(self):
        pool = FakePool(fetch=[ROW])
        with _pg_true(), _patch_pg(pool):
            result = await search_knowledge_snippets_db("t1", "refund", limit=3)
        assert result == [ROW]
        sql, params = pool.fetched[0]
        assert "ILIKE $2" in sql
        assert params == ("t1", "%refund%", 3)

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await search_knowledge_snippets_db("t1", "refund") == []


class TestListKnowledgeSnippets:
    @pytest.mark.asyncio
    async def test_sqlite_with_category(self):
        conn = FakeConn(fetchall=[ROW])
        with _pg_false(), _patch_conn(conn):
            result = await list_knowledge_snippets_db(
                "t1", category="policy", limit=10, offset=5
            )
        assert result == [ROW]
        assert "category = ?" in conn.last_sql
        assert conn.last_params == ("t1", "policy", 10, 5)

    @pytest.mark.asyncio
    async def test_sqlite_without_category(self):
        conn = FakeConn(fetchall=[ROW])
        with _pg_false(), _patch_conn(conn):
            result = await list_knowledge_snippets_db("t1", limit=50, offset=0)
        assert result == [ROW]
        assert "category" not in conn.last_sql
        assert conn.last_params == ("t1", 50, 0)

    @pytest.mark.asyncio
    async def test_sqlite_empty(self):
        conn = FakeConn(fetchall=[])
        with _pg_false(), _patch_conn(conn):
            assert await list_knowledge_snippets_db("t1") == []

    @pytest.mark.asyncio
    async def test_pg_with_category(self):
        pool = FakePool(fetch=[ROW])
        with _pg_true(), _patch_pg(pool):
            result = await list_knowledge_snippets_db("t1", category="policy")
        assert result == [ROW]
        sql, params = pool.fetched[0]
        assert "category = $2" in sql
        assert params == ("t1", "policy", 50, 0)

    @pytest.mark.asyncio
    async def test_pg_without_category(self):
        pool = FakePool(fetch=[ROW])
        with _pg_true(), _patch_pg(pool):
            result = await list_knowledge_snippets_db("t1", limit=10, offset=2)
        assert result == [ROW]
        sql, params = pool.fetched[0]
        assert "category" not in sql
        assert params == ("t1", 10, 2)

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await list_knowledge_snippets_db("t1") == []


class TestDeleteKnowledgeSnippet:
    @pytest.mark.asyncio
    async def test_sqlite_deleted(self):
        conn = FakeConn(rowcount=1)
        with _pg_false(), _patch_conn(conn):
            assert await delete_knowledge_snippet_db("t1", "s1") is True
        assert "DELETE FROM knowledge_snippets" in conn.last_cursor.executed[0][0]
        assert conn.committed is True
        assert conn.closed is True

    @pytest.mark.asyncio
    async def test_sqlite_not_found(self):
        conn = FakeConn(rowcount=0)
        with _pg_false(), _patch_conn(conn):
            assert await delete_knowledge_snippet_db("t1", "ghost") is False

    @pytest.mark.asyncio
    async def test_pg_deleted(self):
        pool = FakePool(execute_result="DELETE 1")
        with _pg_true(), _patch_pg(pool):
            assert await delete_knowledge_snippet_db("t1", "s1") is True
        sql, params = pool.executed[0]
        assert "DELETE FROM knowledge_snippets" in sql
        assert params == ("s1", "t1")

    @pytest.mark.asyncio
    async def test_pg_no_delete(self):
        pool = FakePool(execute_result="UPDATE 0")
        with _pg_true(), _patch_pg(pool):
            assert await delete_knowledge_snippet_db("t1", "s1") is False

    @pytest.mark.asyncio
    async def test_pg_no_pool(self):
        with _pg_true(), _patch_pg(None):
            assert await delete_knowledge_snippet_db("t1", "s1") is False
