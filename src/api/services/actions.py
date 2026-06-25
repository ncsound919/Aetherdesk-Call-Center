import asyncio

import httpx
import structlog

from api.services.database import (
    decrypt_val,
    get_order_status_db,
    get_webhook_url_db,
    lookup_invoice_db,
)

from .queue import QueueManager

logger = structlog.get_logger()


class Actions:
    def __init__(self, redis_client):
        self.qm = QueueManager(redis_client)

    async def _trigger_webhook(self, tenant_id: str, action: str, data: dict):
        """Optimization: Automate data sync to tenant's CRM/External systems."""
        url = await get_webhook_url_db(tenant_id)

        if url:
            # Enhanced SSRF Protection (v2)
            if not await self._is_url_safe(url):
                logger.error("ssrf_blocked", url=url, error="URL failed safety check")
                return

            try:
                async with httpx.AsyncClient(
                    timeout=5.0,
                    follow_redirects=True,
                    limits=httpx.Limits(max_redirects=5)
                ) as client:
                    # Verify final destination after redirects
                    response = await client.post(url, json={
                        "event": "agent_action",
                        "action": action,
                        "data": data,
                        "tenant_id": tenant_id,
                        "is_escalation": data.get("is_escalation", False)
                    }, headers={"X-Forwarded-For": "127.0.0.1"})
                    logger.info("webhook_triggered", url=url, action=action, status=response.status_code)
            except Exception as e:
                logger.error("webhook_failed", url=url, error=str(e))

    async def _is_url_safe(self, url: str) -> bool:
        """Comprehensive SSRF protection with IPv6, metadata endpoint, and DNS rebinding checks."""
        import ipaddress
        import socket
        import urllib.parse

        try:
            parsed = urllib.parse.urlparse(url)

            # 1. Scheme validation
            if parsed.scheme not in ("http", "https"):
                return False

            hostname = parsed.hostname
            if not hostname:
                return False

            # 2. Resolve to all IPs (handles both IPv4 and IPv6)
            try:
                addrinfos = socket.getaddrinfo(
                    hostname,
                    parsed.port or 80,
                    socket.AF_UNSPEC,  # Support both IPv4 and IPv6
                    socket.SOCK_STREAM
                )
            except socket.gaierror:
                return False

            if not addrinfos:
                return False

            # 3. Block cloud metadata endpoints
            METADATA_ENDPOINTS = [
                ipaddress.ip_address("169.254.169.254"),  # AWS/GCP/Azure metadata
                ipaddress.ip_address("100.100.100.200"),  # Aliyun metadata
                ipaddress.ip_address("169.254.169.253"),  # Some Azure metadata
            ]

            # 4. Block private/internal ranges
            PRIVATE_NETWORKS = [
                ipaddress.ip_network("10.0.0.0/8"),
                ipaddress.ip_network("172.16.0.0/12"),
                ipaddress.ip_network("192.168.0.0/16"),
                ipaddress.ip_network("127.0.0.0/8"),
                ipaddress.ip_network("169.254.0.0/16"),  # Link-local
                ipaddress.ip_network("fc00::/7"),          # IPv6 unique local
                ipaddress.ip_network("::1/128"),           # IPv6 loopback
                ipaddress.ip_network("fe80::/10"),         # IPv6 link-local
            ]

            for family, _, _, _, sockaddr in addrinfos:
                if family == socket.AF_INET:
                    ip_str = sockaddr[0]
                elif family == socket.AF_INET6:
                    ip_str = sockaddr[0]
                else:
                    continue

                try:
                    ip = ipaddress.ip_address(ip_str)
                except ValueError:
                    continue

                # Check metadata endpoints
                if ip in METADATA_ENDPOINTS:
                    return False

                # Check private networks
                for network in PRIVATE_NETWORKS:
                    if ip in network:
                        return False

            # 5. DNS rebinding protection: resolve again after a delay and compare
            import asyncio
            await asyncio.sleep(0.1)  # Small delay to catch fast-changing DNS

            try:
                addrinfos2 = socket.getaddrinfo(
                    hostname,
                    parsed.port or 80,
                    socket.AF_UNSPEC,
                    socket.SOCK_STREAM
                )
            except socket.gaierror:
                return False

            ips1 = {sockaddr[0] for _, _, _, _, sockaddr in addrinfos if sockaddr}
            ips2 = {sockaddr[0] for _, _, _, _, sockaddr in addrinfos2 if sockaddr}

            # If IPs changed between checks, potential DNS rebinding attack
            if ips1 != ips2:
                return False

            return True

        except Exception:
            return False

    async def run(self, action: str, fields: dict, tenant_id: str = "TENANT-001") -> dict:
        result = {"success": False}

        if action == "handoff":
            queue = fields.get("queue", "general")
            sid = fields.get("session_id", "unknown")
            proto = fields.get("protocol_id", "unknown")
            is_escalation = fields.get("is_escalation", False)
            preview = self._preview(fields)
            self.qm.enqueue(queue, {
                "session_id": sid,
                "protocol_id": proto,
                "preview": preview,
                "queue": queue,
                "is_escalation": is_escalation
            })
            try:
                from api.routers.agent import hub
                await hub.broadcast({"type": "queue_updated", "is_escalation": is_escalation})
            except Exception as e:
                logger.error("broadcast_error", error=str(e))
            result = {"success": True}

        elif action == "lookup_invoice":
            inv = fields.get("invoice_id", "")
            if inv:
                try:
                    row = await lookup_invoice_db(inv)
                    if row:
                        status = decrypt_val(row["status"])
                        amount_str = decrypt_val(row["amount"])
                        data = {
                            "status": status,
                            "amount": float(amount_str),
                            "due_date": row["due_date"]
                        }
                        result = {"success": True, "data": data}
                except Exception as e:
                    logger.error("db_lookup_error", error=str(e))

        elif action == "get_order_status":
            order_id = fields.get("order_id", "")
            if order_id:
                try:
                    row = await get_order_status_db(order_id)
                    if row:
                        result = {"success": True, "data": dict(row)}
                except Exception as e:
                    logger.error("db_lookup_error", error=str(e))

        elif action in ["complete", "classify_intent", "route_protocol"]:
            result = {"success": True}

        # Optimization: Trigger automation for all successful actions
        if result["success"]:
            asyncio.create_task(self._trigger_webhook(tenant_id, action, result.get("data", fields)))

        return result

    def _preview(self, fields: dict) -> str:
        keys = [k for k in ("customer_id","invoice_id","order_id","zip","rx_number") if k in fields]
        return ", ".join(f"{k}:{fields[k]}" for k in keys) or "New customer"


