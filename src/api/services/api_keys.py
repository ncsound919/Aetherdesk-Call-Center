import hashlib
import json
import secrets
import time
from datetime import UTC, datetime, timedelta

import structlog

from api.services.db_developer import (
    create_api_key_db,
    get_api_key_by_id_db,
    get_api_key_by_prefix_db,
    list_api_keys_db,
    revoke_api_key_db,
    update_api_key_last_used_db,
)

logger = structlog.get_logger()

KEY_PREFIX = "ak_"
KEY_BYTES = 32
RATE_LIMIT_WINDOW = 60
RATE_LIMIT_MAX = 100


def _generate_key() -> tuple[str, str, str]:
    raw = secrets.token_hex(KEY_BYTES)
    full_key = f"{KEY_PREFIX}{raw}"
    prefix = full_key[:10]
    key_hash = hashlib.sha256(full_key.encode()).hexdigest()
    return full_key, prefix, key_hash


def _mask_key(full_key: str) -> str:
    if len(full_key) <= 14:
        return full_key[:6] + "****"
    return full_key[:10] + "****" + full_key[-4:]


class APIKeyService:
    def __init__(self):
        self._rate_limits: dict[str, list[float]] = {}

    async def create_key(self, tenant_id: str, name: str, scopes: list[str] | None = None,
                         expires_in_days: int = 365) -> dict:
        full_key, prefix, key_hash = _generate_key()
        scopes = scopes or ["all"]
        expires_at = (datetime.now(UTC) + timedelta(days=expires_in_days)).isoformat()

        record = await create_api_key_db(tenant_id, name, prefix, key_hash, scopes, expires_at)
        if not record:
            raise RuntimeError("Failed to create API key")

        return {
            **record,
            "full_key": full_key,
        }

    async def validate_key(self, api_key: str) -> dict | None:
        if not api_key or not api_key.startswith(KEY_PREFIX):
            return None

        prefix = api_key[:10]
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()

        record = await get_api_key_by_prefix_db(prefix)
        if not record:
            return None

        if not record["is_active"]:
            return None

        if record["key_hash"] != key_hash:
            return None

        if record.get("expires_at"):
            expires = record["expires_at"]
            if isinstance(expires, str):
                expires = datetime.fromisoformat(expires)
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=UTC)
            if expires < datetime.now(UTC):
                logger.info("api_key_expired", key_id=record["id"])
                return None

        await update_api_key_last_used_db(record["id"])

        scopes = record.get("scopes_json", [])
        if isinstance(scopes, str):
            import json
            scopes = json.loads(scopes)
        if isinstance(scopes, dict):
            scopes = scopes.get("scopes", [])

        return {
            "tenant_id": record["tenant_id"],
            "key_id": record["id"],
            "scopes": scopes,
        }

    async def revoke_key(self, tenant_id: str, key_id: str) -> bool:
        return await revoke_api_key_db(tenant_id, key_id)

    async def list_keys(self, tenant_id: str) -> list[dict]:
        records = await list_api_keys_db(tenant_id)
        masked = []
        for r in records:
            scopes = r.get("scopes_json", [])
            if isinstance(scopes, str):
                import json
                scopes = json.loads(scopes)
            masked.append({
                "id": r["id"],
                "name": r["name"],
                "key_prefix": r["key_prefix"],
                "masked_key": r["key_prefix"] + "****" + (r["key_hash"][-4:] if r.get("key_hash") else "****"),
                "scopes": scopes,
                "created_at": r.get("created_at"),
                "last_used_at": r.get("last_used_at"),
                "expires_at": r.get("expires_at"),
                "is_active": bool(r.get("is_active")),
            })
        return masked

    async def rotate_key(self, tenant_id: str, key_id: str) -> dict | None:
        record = await get_api_key_by_id_db(tenant_id, key_id)
        if not record:
            return None

        await revoke_api_key_db(tenant_id, key_id)

        return await self.create_key(
            tenant_id,
            record["name"] + " (rotated)",
            json.loads(record["scopes_json"]) if isinstance(record.get("scopes_json"), str) else record.get("scopes_json", ["all"]),
        )

    async def get_key_usage(self, tenant_id: str, key_id: str, period: str = "7d") -> dict:
        record = await get_api_key_by_id_db(tenant_id, key_id)
        if not record:
            return None

        return {
            "key_id": key_id,
            "name": record["name"],
            "created_at": record.get("created_at"),
            "last_used_at": record.get("last_used_at"),
            "is_active": bool(record.get("is_active")),
            "period": period,
            "call_count": 0,
        }

    def check_rate_limit(self, api_key: str) -> bool:
        now = time.time()
        window_start = now - RATE_LIMIT_WINDOW

        if api_key not in self._rate_limits:
            self._rate_limits[api_key] = []

        timestamps = self._rate_limits[api_key]
        timestamps = [t for t in timestamps if t > window_start]

        if len(timestamps) >= RATE_LIMIT_MAX:
            return False

        timestamps.append(now)
        self._rate_limits[api_key] = timestamps
        return True


api_key_service = APIKeyService()
