"""Tests for src/api/services/connection_pool.py — HTTP client pool."""

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import api.services.connection_pool as cp  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_pool():
    cp.HTTPClientPool._instance = None
    cp.http_pool._client = None
    yield
    cp.HTTPClientPool._instance = None
    cp.http_pool._client = None


def run(coro):
    return asyncio.run(coro)


def test_singleton():
    a = cp.HTTPClientPool()
    b = cp.HTTPClientPool()
    assert a is b
    assert isinstance(cp.http_pool, cp.HTTPClientPool)


def test_get_client_creates_and_caches():
    c1 = run(cp.http_pool.get_client())
    assert isinstance(c1, httpx.AsyncClient)
    c2 = run(cp.http_pool.get_client())
    assert c1 is c2


def test_get_client_after_close_recreates():
    c1 = run(cp.http_pool.get_client())
    run(cp.http_pool.close())
    assert c1.is_closed
    c2 = run(cp.http_pool.get_client())
    assert c2 is not c1
    assert not c2.is_closed


def test_get_http_client_context_manager():
    async def _use():
        async with cp.get_http_client() as client:
            assert isinstance(client, httpx.AsyncClient)
            return client

    client = run(_use())
    assert not client.is_closed  # pooled, not closed


def test_close():
    run(cp.http_pool.get_client())
    run(cp.http_pool.close())
    assert cp.http_pool._client is None


def test_get_pool_stats_without_pool(monkeypatch):
    async def _no_pool(*a, **k):
        return None

    monkeypatch.setattr("api.services.db_pool.get_pg_pool", _no_pool)
    assert run(cp.get_pool_stats()) == {"size": 0, "free": 0, "used": 0}


def test_get_pool_stats_with_pool(monkeypatch):
    class _FakePool:
        def __init__(self):
            self._pool = _FakePoolInner()

    class _FakePoolInner:
        def get_size(self):
            return 10

        def get_idle_size(self):
            return 7

    async def _pool(*a, **k):
        return _FakePool()

    monkeypatch.setattr("api.services.db_pool.get_pg_pool", _pool)
    stats = run(cp.get_pool_stats())
    assert stats["size"] == 10
    assert stats["free"] == 7


def test_get_pool_stats_pool_missing_attrs(monkeypatch):
    class _FakePool:
        def __init__(self):
            self._pool = object()  # no get_size / get_idle_size

    async def _pool(*a, **k):
        return _FakePool()

    monkeypatch.setattr("api.services.db_pool.get_pg_pool", _pool)
    stats = run(cp.get_pool_stats())
    assert stats["size"] == -1
    assert stats["free"] == -1


def test_get_pool_stats_exception(monkeypatch):
    async def _boom(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr("api.services.db_pool.get_pg_pool", _boom)
    assert run(cp.get_pool_stats()) == {"size": 0, "free": 0, "used": 0}

