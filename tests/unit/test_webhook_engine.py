"""Tests for src/api/services/webhook_engine.py — payload signing, delivery,
retries, dead-lettering, and the WebhookEngine dispatch queue. All httpx and
db_developer calls are mocked."""

import asyncio
import hashlib
import hmac
import json
import uuid

import httpx
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from api.services.webhook_engine import (
    EVENT_CATALOG,
    WebhookEngine,
    _deliver_webhook,
    _sign_payload,
    webhook_engine,
)


class FakeResp:
    def __init__(self, status_code=200, text=""):
        self.status_code = status_code
        self.text = text


def _patch_httpx_post(monkeypatch, status=200, text="ok", exc=None):
    client = AsyncMock()
    if exc is not None:
        client.post.side_effect = exc
    else:
        client.post.return_value = FakeResp(status, text)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=client)
    ctx.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: ctx)
    return client


# ---------------------------------------------------------------------------
# _sign_payload
# ---------------------------------------------------------------------------


class TestSignPayload:
    def test_signs_with_sha256_hmac(self):
        signature = _sign_payload("body", "secret")
        expected = hmac.new(b"secret", b"body", hashlib.sha256).hexdigest()
        assert signature == expected

    def test_deterministic(self):
        assert _sign_payload("x", "s") == _sign_payload("x", "s")
        assert _sign_payload("x", "s") != _sign_payload("x", "t")


# ---------------------------------------------------------------------------
# _deliver_webhook
# ---------------------------------------------------------------------------


class TestDeliverWebhook:
    @pytest.mark.asyncio
    async def test_success_without_secret(self, monkeypatch):
        client = _patch_httpx_post(monkeypatch, status=200, text="ok")
        with patch("api.services.webhook_engine.update_webhook_delivery_log_db") as update:
            update = AsyncMock()
            with patch("api.services.webhook_engine.update_webhook_delivery_log_db", new=update):
                ok = await _deliver_webhook("http://x", {"a": 1}, None, "L1", "t", "W1")

        assert ok is True
        update.assert_awaited_once_with("L1", "delivered", response_status=200, response_body="ok")
        headers = client.post.call_args.kwargs["headers"]
        assert "X-AetherDesk-Signature" not in headers
        assert client.post.call_args.kwargs["content"] == json.dumps({"a": 1})

    @pytest.mark.asyncio
    async def test_success_with_secret(self, monkeypatch):
        client = _patch_httpx_post(monkeypatch, status=204, text="")
        with patch("api.services.webhook_engine.update_webhook_delivery_log_db") as update:
            update = AsyncMock()
            with patch("api.services.webhook_engine.update_webhook_delivery_log_db", new=update):
                ok = await _deliver_webhook("http://x", {"a": 1}, "sekret", "L1", "t", "W1")

        assert ok is True
        headers = client.post.call_args.kwargs["headers"]
        payload_str = json.dumps({"a": 1})
        assert headers["X-AetherDesk-Signature"] == f"sha256={_sign_payload(payload_str, 'sekret')}"
        assert headers["X-AetherDesk-Timestamp"]

    @pytest.mark.asyncio
    async def test_http_error(self, monkeypatch):
        _patch_httpx_post(monkeypatch, status=500, text="server error")
        update = AsyncMock()
        with patch("api.services.webhook_engine.update_webhook_delivery_log_db", new=update):
            ok = await _deliver_webhook("http://x", {}, None, "L1", "t", "W1")

        assert ok is False
        update.assert_awaited_once_with(
            "L1",
            status="failed",
            response_status=500,
            response_body="server error",
            error_message="HTTP 500",
            retry_count=0,
        )

    @pytest.mark.asyncio
    async def test_timeout_exception(self, monkeypatch):
        _patch_httpx_post(monkeypatch, exc=httpx.TimeoutException("slow"))
        update = AsyncMock()
        with patch("api.services.webhook_engine.update_webhook_delivery_log_db", new=update):
            ok = await _deliver_webhook("http://x", {}, None, "L1", "t", "W1")

        assert ok is False
        call = update.await_args
        assert call.kwargs["error_message"] == "Timeout"
        assert call.kwargs["response_status"] == 0

    @pytest.mark.asyncio
    async def test_generic_exception(self, monkeypatch):
        _patch_httpx_post(monkeypatch, exc=ValueError("dns exploded"))
        update = AsyncMock()
        with patch("api.services.webhook_engine.update_webhook_delivery_log_db", new=update):
            ok = await _deliver_webhook("http://x", {}, None, "L1", "t", "W1")

        assert ok is False
        call = update.await_args
        assert call.kwargs["error_message"] == "dns exploded"
        assert call.kwargs["response_status"] == 0


# ---------------------------------------------------------------------------
# WebhookEngine — CRUD wrappers
# ---------------------------------------------------------------------------


class TestWebhookEngineCrud:
    def test_init(self):
        engine = WebhookEngine()
        assert engine._worker_task is None

    @pytest.mark.asyncio
    async def test_start_and_stop(self):
        engine = WebhookEngine()
        engine.start()
        assert engine._worker_task is not None
        await engine.stop()
        assert engine._worker_task is None

    @pytest.mark.asyncio
    async def test_start_is_idempotent(self):
        engine = WebhookEngine()
        engine.start()
        task = engine._worker_task
        engine.start()
        assert engine._worker_task is task
        await engine.stop()

    @pytest.mark.asyncio
    async def test_register_with_secret(self):
        engine = WebhookEngine()
        register = AsyncMock(return_value={"id": "w1"})
        with patch("api.services.webhook_engine.register_webhook_db", new=register):
            result = await engine.register_webhook("t", "http://x", ["call.completed"], "sekret")

        assert result == {"id": "w1"}
        register.assert_awaited_once_with("t", "http://x", ["call.completed"], "sekret")

    @pytest.mark.asyncio
    async def test_register_generates_secret(self):
        engine = WebhookEngine()
        captured = {}
        async def register(tenant_id, url, events, secret):
            captured["secret"] = secret
            return {"id": "w1"}

        with patch("api.services.webhook_engine.register_webhook_db", new=register):
            await engine.register_webhook("t", "http://x", ["call.completed"])

        assert len(captured["secret"]) == 32
        uuid.UUID(captured["secret"])  # valid hex

    @pytest.mark.asyncio
    async def test_unregister(self):
        engine = WebhookEngine()
        unregister = AsyncMock(return_value=True)
        with patch("api.services.webhook_engine.unregister_webhook_db", new=unregister):
            ok = await engine.unregister_webhook("t", "w1")

        assert ok is True
        unregister.assert_awaited_once_with("t", "w1")

    @pytest.mark.asyncio
    async def test_list_webhooks(self):
        engine = WebhookEngine()
        lst = AsyncMock(return_value=[{"id": "w1"}])
        with patch("api.services.webhook_engine.list_webhooks_db", new=lst):
            result = await engine.list_webhooks("t")

        assert result == [{"id": "w1"}]

    @pytest.mark.asyncio
    async def test_get_webhook(self):
        engine = WebhookEngine()
        getter = AsyncMock(return_value={"id": "w1"})
        with patch("api.services.webhook_engine.get_webhook_by_id_db", new=getter):
            result = await engine.get_webhook("t", "w1")

        assert result == {"id": "w1"}
        getter.assert_awaited_once_with("t", "w1")

    @pytest.mark.asyncio
    async def test_get_delivery_logs(self):
        engine = WebhookEngine()
        logs = AsyncMock(return_value=[{"id": "L1"}])
        with patch("api.services.webhook_engine.get_webhook_delivery_logs_db", new=logs):
            result = await engine.get_delivery_logs("t", "w1", limit=10)

        assert result == [{"id": "L1"}]
        logs.assert_awaited_once_with("t", "w1", 10)

    def test_get_event_catalog(self):
        engine = WebhookEngine()
        catalog = engine.get_event_catalog()
        assert catalog is EVENT_CATALOG
        assert "call.completed" in catalog
        assert "qa.score_created" in catalog


# ---------------------------------------------------------------------------
# WebhookEngine.dispatch_event
# ---------------------------------------------------------------------------


class TestDispatchEvent:
    @pytest.mark.asyncio
    async def test_unknown_event_type(self):
        engine = WebhookEngine()
        with patch("api.services.webhook_engine.get_active_webhooks_for_event_db") as getter:
            getter = AsyncMock()
            with patch("api.services.webhook_engine.get_active_webhooks_for_event_db", new=getter):
                await engine.dispatch_event("t", "not.an.event", {})
        getter.assert_not_called()
        assert engine._dispatch_queue.qsize() == 0

    @pytest.mark.asyncio
    async def test_no_active_webhooks(self):
        engine = WebhookEngine()
        with patch("api.services.webhook_engine.get_active_webhooks_for_event_db") as getter:
            getter = AsyncMock(return_value=[])
            with patch("api.services.webhook_engine.get_active_webhooks_for_event_db", new=getter):
                await engine.dispatch_event("t", "call.completed", {"call_id": "C1"})
        assert engine._dispatch_queue.qsize() == 0

    @pytest.mark.asyncio
    async def test_queues_payloads(self):
        engine = WebhookEngine()
        webhooks = [{"id": "w1"}, {"id": "w2"}]
        with patch("api.services.webhook_engine.get_active_webhooks_for_event_db") as getter:
            getter = AsyncMock(return_value=webhooks)
            with patch("api.services.webhook_engine.get_active_webhooks_for_event_db", new=getter):
                await engine.dispatch_event("t", "call.completed", {"call_id": "C1"})

        assert engine._dispatch_queue.qsize() == 2
        item_wh, payload = engine._dispatch_queue.get_nowait()
        assert item_wh == {"id": "w1"}
        assert payload["event_type"] == "call.completed"
        assert payload["event_id"]
        assert payload["data"] == {"call_id": "C1"}
        assert payload["created_at"]


# ---------------------------------------------------------------------------
# WebhookEngine.retry_delivery
# ---------------------------------------------------------------------------


class TestRetryDelivery:
    @pytest.mark.asyncio
    async def test_no_log_entry(self):
        engine = WebhookEngine()
        with patch("api.services.webhook_engine.get_webhook_delivery_log_by_id_db") as getter:
            getter = AsyncMock(return_value=None)
            with patch("api.services.webhook_engine.get_webhook_delivery_log_by_id_db", new=getter):
                ok = await engine.retry_delivery("t", "L1")
        assert ok is False

    @pytest.mark.asyncio
    async def test_no_webhook(self):
        engine = WebhookEngine()
        log = {"tenant_id": "t", "webhook_id": "w1", "request_body": "{}", "retry_count": 0}
        with patch("api.services.webhook_engine.get_webhook_delivery_log_by_id_db") as getter, \
             patch("api.services.webhook_engine.get_webhook_by_id_db") as wh_getter:
            getter = AsyncMock(return_value=log)
            wh_getter = AsyncMock(return_value=None)
            with patch("api.services.webhook_engine.get_webhook_delivery_log_by_id_db", new=getter), \
                 patch("api.services.webhook_engine.get_webhook_by_id_db", new=wh_getter):
                ok = await engine.retry_delivery("t", "L1")
        assert ok is False

    @pytest.mark.asyncio
    async def test_success_with_string_body(self):
        engine = WebhookEngine()
        log = {
            "tenant_id": "t",
            "webhook_id": "w1",
            "request_body": json.dumps({"a": 1}),
            "retry_count": 0,
        }
        webhook = {"id": "w1", "url": "http://x", "secret": "s", "tenant_id": "t"}

        with patch("api.services.webhook_engine.get_webhook_delivery_log_by_id_db") as getter, \
             patch("api.services.webhook_engine.get_webhook_by_id_db") as wh_getter, \
             patch("api.services.webhook_engine.update_webhook_delivery_log_db") as updater, \
             patch("api.services.webhook_engine._deliver_webhook") as deliver:
            getter = AsyncMock(return_value=log)
            wh_getter = AsyncMock(return_value=webhook)
            updater = AsyncMock()
            deliver = AsyncMock(return_value=True)
            with patch("api.services.webhook_engine.get_webhook_delivery_log_by_id_db", new=getter), \
                 patch("api.services.webhook_engine.get_webhook_by_id_db", new=wh_getter), \
                 patch("api.services.webhook_engine.update_webhook_delivery_log_db", new=updater), \
                 patch("api.services.webhook_engine._deliver_webhook", new=deliver):
                ok = await engine.retry_delivery("t", "L1")

        assert ok is True
        updater.assert_awaited_with("L1", "retrying", retry_count=1)
        deliver.assert_awaited_once_with("http://x", {"a": 1}, "s", "L1", "t", "w1")

    @pytest.mark.asyncio
    async def test_success_with_dict_body(self):
        engine = WebhookEngine()
        log = {
            "tenant_id": "t",
            "webhook_id": "w1",
            "request_body": {"b": 2},
            "retry_count": 3,
        }
        webhook = {"id": "w1", "url": "http://x", "secret": None, "tenant_id": "t"}

        with patch("api.services.webhook_engine.get_webhook_delivery_log_by_id_db") as getter, \
             patch("api.services.webhook_engine.get_webhook_by_id_db") as wh_getter, \
             patch("api.services.webhook_engine.update_webhook_delivery_log_db") as updater, \
             patch("api.services.webhook_engine._deliver_webhook") as deliver:
            getter = AsyncMock(return_value=log)
            wh_getter = AsyncMock(return_value=webhook)
            updater = AsyncMock()
            deliver = AsyncMock(return_value=True)
            with patch("api.services.webhook_engine.get_webhook_delivery_log_by_id_db", new=getter), \
                 patch("api.services.webhook_engine.get_webhook_by_id_db", new=wh_getter), \
                 patch("api.services.webhook_engine.update_webhook_delivery_log_db", new=updater), \
                 patch("api.services.webhook_engine._deliver_webhook", new=deliver):
                ok = await engine.retry_delivery("t", "L1")

        assert ok is True
        updater.assert_awaited_with("L1", "retrying", retry_count=4)
        deliver.assert_awaited_once_with("http://x", {"b": 2}, None, "L1", "t", "w1")


# ---------------------------------------------------------------------------
# WebhookEngine._deliver_with_retry
# ---------------------------------------------------------------------------


class TestDeliverWithRetry:
    @pytest.mark.asyncio
    async def test_no_log_created(self):
        engine = WebhookEngine()
        creator = AsyncMock(return_value=None)
        deliver = AsyncMock()
        with patch("api.services.webhook_engine.create_webhook_delivery_log_db", new=creator), \
             patch("api.services.webhook_engine._deliver_webhook", new=deliver):
            await engine._deliver_with_retry(
                {"tenant_id": "t", "id": "w1", "url": "http://x"},
                {"event_type": "call.completed"},
            )
        deliver.assert_not_called()

    @pytest.mark.asyncio
    async def test_success_first_try(self):
        engine = WebhookEngine()
        webhook = {"tenant_id": "t", "id": "w1", "url": "http://x", "secret": "s"}
        payload = {"event_type": "call.completed", "data": {}}
        creator = AsyncMock(return_value={"id": "L1"})
        updater = AsyncMock()
        deliver = AsyncMock(return_value=True)
        with patch("api.services.webhook_engine.create_webhook_delivery_log_db", new=creator), \
             patch("api.services.webhook_engine.update_webhook_delivery_log_db", new=updater), \
             patch("api.services.webhook_engine._deliver_webhook", new=deliver):
            await engine._deliver_with_retry(webhook, payload)

        creator.assert_awaited_once_with(
            "t", "w1", "call.completed", json.dumps(payload)
        )
        updater.assert_not_called()
        deliver.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_dead_letter_after_retries(self):
        engine = WebhookEngine()
        webhook = {"tenant_id": "t", "id": "w1", "url": "http://x", "secret": None}
        payload = {"event_type": "call.failed"}
        creator = AsyncMock(return_value={"id": "L1"})
        updater = AsyncMock()
        deliver = AsyncMock(return_value=False)
        sleep = AsyncMock()
        with patch("api.services.webhook_engine.create_webhook_delivery_log_db", new=creator), \
             patch("api.services.webhook_engine.update_webhook_delivery_log_db", new=updater), \
             patch("api.services.webhook_engine._deliver_webhook", new=deliver), \
             patch("asyncio.sleep", new=sleep):
            await engine._deliver_with_retry(webhook, payload)

        assert deliver.await_count == 3
        assert sleep.await_count == 2
        assert ("L1", "retrying", {"retry_count": 1}) in [
            (c.args[0], c.args[1], c.kwargs) for c in updater.await_args_list
        ]
        assert ("L1", "retrying", {"retry_count": 2}) in [
            (c.args[0], c.args[1], c.kwargs) for c in updater.await_args_list
        ]
        updater.assert_awaited_with(
            "L1", "dead_letter", error_message="Max retries exceeded", retry_count=3
        )


# ---------------------------------------------------------------------------
# WebhookEngine._worker_loop
# ---------------------------------------------------------------------------


class TestWorkerLoop:
    @pytest.mark.asyncio
    async def test_dispatches_and_breaks_on_cancel(self):
        engine = WebhookEngine()
        with patch.object(engine, "_deliver_with_retry") as deliver:
            deliver = AsyncMock()
            with patch.object(engine, "_deliver_with_retry", new=deliver):
                engine._dispatch_queue.get = AsyncMock(
                    side_effect=[({"id": "w1"}, {"event_type": "x"}), asyncio.CancelledError()]
                )
                await engine._worker_loop()
                await asyncio.sleep(0)
        deliver.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_logs_error_and_continues(self):
        engine = WebhookEngine()
        with patch.object(engine, "_deliver_with_retry") as deliver:
            deliver = AsyncMock()
            with patch.object(engine, "_deliver_with_retry", new=deliver):
                engine._dispatch_queue.get = AsyncMock(
                    side_effect=[Exception("worker exploded"), asyncio.CancelledError()]
                )
                await engine._worker_loop()
        deliver.assert_not_called()
