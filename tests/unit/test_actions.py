import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call


class TestActionsRun:
    @pytest.mark.asyncio
    async def test_handoff_action(self):
        from api.services.actions import Actions

        mock_redis = MagicMock()
        actions = Actions(mock_redis)

        with patch("api.routers.agent.hub.broadcast", new_callable=AsyncMock) as mock_broadcast:
            result = await actions.run("handoff", {
                "queue": "support",
                "session_id": "SES-001",
                "protocol_id": "PROTO-1",
                "customer_id": "CUST-123"
            })

        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_handoff_escalation(self):
        from api.services.actions import Actions

        mock_redis = MagicMock()
        actions = Actions(mock_redis)

        with patch("api.routers.agent.hub.broadcast", new_callable=AsyncMock) as mock_broadcast:
            result = await actions.run("handoff", {
                "queue": "urgent",
                "session_id": "SES-002",
                "protocol_id": "PROTO-2",
                "is_escalation": True,
                "customer_id": "CUST-456"
            })

        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_handoff_broadcast_error(self):
        from api.services.actions import Actions

        mock_redis = MagicMock()
        actions = Actions(mock_redis)

        with patch("api.routers.agent.hub.broadcast", new_callable=AsyncMock, side_effect=Exception("broadcast failed")):
            result = await actions.run("handoff", {
                "queue": "general",
                "session_id": "SES-003",
                "protocol_id": "PROTO-3"
            })

        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_lookup_invoice_success(self):
        from api.services.actions import Actions

        mock_redis = MagicMock()
        actions = Actions(mock_redis)

        with patch("api.services.actions.lookup_invoice_db", new_callable=AsyncMock) as mock_lookup, \
             patch("api.services.actions.decrypt_val") as mock_decrypt, \
             patch("api.services.actions.get_webhook_url_db", new_callable=AsyncMock, return_value=None):
            mock_lookup.return_value = {
                "status": "encrypted_status",
                "amount": "encrypted_amount",
                "due_date": "2026-07-01"
            }
            mock_decrypt.side_effect = ["paid", "42.00"]

            result = await actions.run("lookup_invoice", {"invoice_id": "INV-001"})

        assert result["success"] is True
        assert result["data"]["status"] == "paid"
        assert result["data"]["amount"] == 42.0
        assert result["data"]["due_date"] == "2026-07-01"

    @pytest.mark.asyncio
    async def test_lookup_invoice_not_found(self):
        from api.services.actions import Actions

        mock_redis = MagicMock()
        actions = Actions(mock_redis)

        with patch("api.services.actions.lookup_invoice_db", new_callable=AsyncMock, return_value=None), \
             patch("api.services.actions.get_webhook_url_db", new_callable=AsyncMock, return_value=None):
            result = await actions.run("lookup_invoice", {"invoice_id": "INV-999"})

        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_lookup_invoice_db_error(self):
        from api.services.actions import Actions

        mock_redis = MagicMock()
        actions = Actions(mock_redis)

        with patch("api.services.actions.lookup_invoice_db", new_callable=AsyncMock, side_effect=Exception("DB down")), \
             patch("api.services.actions.get_webhook_url_db", new_callable=AsyncMock, return_value=None):
            result = await actions.run("lookup_invoice", {"invoice_id": "INV-001"})

        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_get_order_status_success(self):
        from api.services.actions import Actions

        mock_redis = MagicMock()
        actions = Actions(mock_redis)

        with patch("api.services.actions.get_order_status_db", new_callable=AsyncMock) as mock_os, \
             patch("api.services.actions.get_webhook_url_db", new_callable=AsyncMock, return_value=None):
            mock_os.return_value = {"order_id": "ORD-001", "status": "shipped"}

            result = await actions.run("get_order_status", {"order_id": "ORD-001"})

        assert result["success"] is True
        assert result["data"]["status"] == "shipped"

    @pytest.mark.asyncio
    async def test_get_order_status_not_found(self):
        from api.services.actions import Actions

        mock_redis = MagicMock()
        actions = Actions(mock_redis)

        with patch("api.services.actions.get_order_status_db", new_callable=AsyncMock, return_value=None), \
             patch("api.services.actions.get_webhook_url_db", new_callable=AsyncMock, return_value=None):
            result = await actions.run("get_order_status", {"order_id": "ORD-999"})

        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_get_order_status_db_error(self):
        from api.services.actions import Actions

        mock_redis = MagicMock()
        actions = Actions(mock_redis)

        with patch("api.services.actions.get_order_status_db", new_callable=AsyncMock, side_effect=Exception("DB error")), \
             patch("api.services.actions.get_webhook_url_db", new_callable=AsyncMock, return_value=None):
            result = await actions.run("get_order_status", {"order_id": "ORD-001"})

        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_complete_action(self):
        from api.services.actions import Actions

        mock_redis = MagicMock()
        actions = Actions(mock_redis)

        with patch("api.services.actions.get_webhook_url_db", new_callable=AsyncMock, return_value=None):
            result = await actions.run("complete", {})

        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_classify_intent_action(self):
        from api.services.actions import Actions

        mock_redis = MagicMock()
        actions = Actions(mock_redis)

        with patch("api.services.actions.get_webhook_url_db", new_callable=AsyncMock, return_value=None):
            result = await actions.run("classify_intent", {})

        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_route_protocol_action(self):
        from api.services.actions import Actions

        mock_redis = MagicMock()
        actions = Actions(mock_redis)

        with patch("api.services.actions.get_webhook_url_db", new_callable=AsyncMock, return_value=None):
            result = await actions.run("route_protocol", {})

        assert result["success"] is True


class TestActionsWebhook:
    @pytest.mark.asyncio
    async def test_trigger_webhook_with_url(self):
        from api.services.actions import Actions

        mock_redis = MagicMock()
        actions = Actions(mock_redis)

        mock_post = AsyncMock()
        mock_post.return_value.status_code = 200
        mock_client = MagicMock()
        mock_client.post = mock_post
        mock_client.__aenter__.return_value = mock_client

        with patch("api.services.actions.get_webhook_url_db", new_callable=AsyncMock, return_value="https://example.com/webhook"), \
             patch("api.services.actions.Actions._is_url_safe", new_callable=AsyncMock, return_value=True), \
             patch("httpx.AsyncClient", return_value=mock_client), \
             patch("httpx.Limits"):
            await actions._trigger_webhook("TENANT-001", "complete", {"key": "val"})

            mock_post.assert_called_once()

    @pytest.mark.asyncio
    async def test_trigger_webhook_no_url(self):
        from api.services.actions import Actions

        mock_redis = MagicMock()
        actions = Actions(mock_redis)

        with patch("api.services.actions.get_webhook_url_db", new_callable=AsyncMock, return_value=None):
            await actions._trigger_webhook("TENANT-001", "complete", {})

    @pytest.mark.asyncio
    async def test_trigger_webhook_ssrf_blocked(self):
        from api.services.actions import Actions

        mock_redis = MagicMock()
        actions = Actions(mock_redis)

        with patch("api.services.actions.get_webhook_url_db", new_callable=AsyncMock, return_value="http://169.254.169.254/latest/meta-data/"), \
             patch("api.services.actions.Actions._is_url_safe", new_callable=AsyncMock, return_value=False):
            await actions._trigger_webhook("TENANT-001", "complete", {})

    @pytest.mark.asyncio
    async def test_trigger_webhook_http_error(self):
        from api.services.actions import Actions

        mock_redis = MagicMock()
        actions = Actions(mock_redis)

        with patch("api.services.actions.get_webhook_url_db", new_callable=AsyncMock, return_value="https://example.com/webhook"), \
             patch("api.services.actions.Actions._is_url_safe", new_callable=AsyncMock, return_value=True), \
             patch("httpx.AsyncClient") as mock_client:
            mock_client_instance = AsyncMock()
            mock_client_instance.__aenter__.return_value = mock_client_instance
            mock_client.return_value = mock_client_instance
            mock_client_instance.post = AsyncMock(side_effect=Exception("Connection error"))

            await actions._trigger_webhook("TENANT-001", "complete", {})

    @pytest.mark.asyncio
    async def test_is_url_safe_https(self):
        from api.services.actions import Actions

        mock_redis = MagicMock()
        actions = Actions(mock_redis)

        with patch("socket.getaddrinfo") as mock_gai:
            import socket
            mock_gai.side_effect = [
                [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 80))],
                [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 80))],
            ]
            result = await actions._is_url_safe("https://example.com")
            assert result is True

    @pytest.mark.asyncio
    async def test_is_url_safe_invalid_scheme(self):
        from api.services.actions import Actions

        mock_redis = MagicMock()
        actions = Actions(mock_redis)

        result = await actions._is_url_safe("ftp://example.com")
        assert result is False

    @pytest.mark.asyncio
    async def test_is_url_safe_private_ip(self):
        from api.services.actions import Actions

        mock_redis = MagicMock()
        actions = Actions(mock_redis)

        with patch("socket.getaddrinfo") as mock_gai:
            import socket
            mock_gai.side_effect = [
                [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.1.1", 80))],
                [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.1.1", 80))],
            ]
            result = await actions._is_url_safe("http://192.168.1.1")
            assert result is False

    @pytest.mark.asyncio
    async def test_is_url_safe_metadata_endpoint(self):
        from api.services.actions import Actions

        mock_redis = MagicMock()
        actions = Actions(mock_redis)

        with patch("socket.getaddrinfo") as mock_gai:
            import socket
            mock_gai.side_effect = [
                [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", 80))],
                [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", 80))],
            ]
            result = await actions._is_url_safe("http://169.254.169.254")
            assert result is False

    @pytest.mark.asyncio
    async def test_is_url_safe_dns_rebinding_detected(self):
        from api.services.actions import Actions

        mock_redis = MagicMock()
        actions = Actions(mock_redis)

        with patch("socket.getaddrinfo") as mock_gai:
            import socket
            mock_gai.side_effect = [
                [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 80))],
                [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.1.1", 80))],
            ]
            result = await actions._is_url_safe("http://example.com")
            assert result is False

    @pytest.mark.asyncio
    async def test_is_url_safe_dns_resolution_failure(self):
        from api.services.actions import Actions
        import socket

        mock_redis = MagicMock()
        actions = Actions(mock_redis)

        with patch("socket.getaddrinfo", side_effect=socket.gaierror("Name or service not known")):
            result = await actions._is_url_safe("http://nonexistent.example.com")
            assert result is False

    @pytest.mark.asyncio
    async def test_is_url_safe_empty_hostname(self):
        from api.services.actions import Actions

        mock_redis = MagicMock()
        actions = Actions(mock_redis)

        result = await actions._is_url_safe("http:///path")
        assert result is False


class TestActionsPreview:
    def test_preview_with_keys(self):
        from api.services.actions import Actions

        mock_redis = MagicMock()
        actions = Actions(mock_redis)

        result = actions._preview({"customer_id": "CUST-1", "invoice_id": "INV-001", "order_id": "ORD-001"})
        assert "customer_id:CUST-1" in result
        assert "invoice_id:INV-001" in result
        assert "order_id:ORD-001" in result

    def test_preview_empty(self):
        from api.services.actions import Actions

        mock_redis = MagicMock()
        actions = Actions(mock_redis)

        result = actions._preview({"unrelated": "value"})
        assert result == "New customer"

    def test_preview_partial_keys(self):
        from api.services.actions import Actions

        mock_redis = MagicMock()
        actions = Actions(mock_redis)

        result = actions._preview({"customer_id": "CUST-1", "zip": "12345"})
        assert result == "customer_id:CUST-1, zip:12345"
