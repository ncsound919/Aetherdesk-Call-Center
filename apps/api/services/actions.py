import asyncio
import ipaddress
import socket
import urllib.parse

import httpx
import structlog

from apps.api.services.database import (
    get_webhook_url_db,
    lookup_invoice_db,
    get_order_status_db,
    decrypt_val,
)
from .queue import QueueManager

logger = structlog.get_logger()

# C5/C10 fix: metadata endpoints and private networks defined once at module level
_METADATA_ENDPOINTS = {
    ipaddress.ip_address("169.254.169.254"),  # AWS/GCP/Azure metadata
    ipaddress.ip_address("100.100.100.200"),  # Aliyun metadata
    ipaddress.ip_address("169.254.169.253"),  # Some Azure metadata
}
_PRIVATE_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),  # Link-local
    ipaddress.ip_network("fc00::/7"),         # IPv6 unique local
    ipaddress.ip_network("::1/128"),          # IPv6 loopback
    ipaddress.ip_network("fe80::/10"),        # IPv6 link-local
]


def _is_ip_safe(ip_str: str) -> bool:
    """Return True if the resolved IP address is safe for outbound requests."""
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    if ip in _METADATA_ENDPOINTS:
        return False
    for network in _PRIVATE_NETWORKS:
        if ip in network:
            return False
    return True


class Actions:
    def __init__(self, redis_client):
        self.qm = QueueManager(redis_client)

    async def _trigger_webhook(self, tenant_id: str, action: str, data: dict):
        """Automate data sync to tenant's CRM/External systems."""
        url = await get_webhook_url_db(tenant_id)
        if not url:
            return

        # C5/C10 fix: validate URL once, then request with no redirects
        if not self._is_url_safe(url):
            logger.error("ssrf_blocked", url=url, error="URL failed safety check")
            return

        try:
            async with httpx.AsyncClient(
                timeout=5.0,
                follow_redirects=False,  # C10 fix: never follow redirects
            ) as client:
                response = await client.post(url, json={
                    "event": "agent_action",
                    "action": action,
                    "data": data,
                    "tenant_id": tenant_id,
                    "is_escalation": data.get("is_escalation", False)
                })
                logger.info("webhook_triggered", url=url, action=action,
                            status=response.status_code)
        except Exception as e:
            logger.error("webhook_failed", url=url, error=str(e))

    def _is_url_safe(self, url: str) -> bool:
        """SSRF protection: validate URL scheme and resolve IP once.

        C5 fix: removed double-DNS-resolution race condition (time.sleep pattern).
        Resolve once, check every returned IP. Never follow redirects on the
        actual request so a redirect cannot escape the check.
        """
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
                    parsed.port or (443 if parsed.scheme == "https" else 80),
                    socket.AF_UNSPEC,
                    socket.SOCK_STREAM,
                )
            except socket.gaierror:
                return False

            if not addrinfos:
                return False

            # 3. Check every resolved IP against blocklists
            for family, _, _, _, sockaddr in addrinfos:
                ip_str = sockaddr[0]
                if not _is_ip_safe(ip_str):
                    logger.warning("ssrf_blocked_ip", hostname=hostname, ip=ip_str)
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
                from apps.api.routers.agent import hub
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

        # Trigger automation for all successful actions
        if result["success"]:
            asyncio.create_task(
                self._trigger_webhook(tenant_id, action, result.get("data", fields))
            )
        return result

    def _preview(self, fields: dict) -> str:
        keys = [k for k in ("customer_id", "invoice_id", "order_id", "zip", "rx_number") if k in fields]
        return ", ".join(f"{k}:{fields[k]}" for k in keys) or "New customer"
