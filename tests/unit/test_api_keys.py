"""Unit tests for src/api/services/api_keys.py.

Covers key generation/masking, create/validate/revoke/list/rotate/usage flows,
scope handling, expiry validation and the in-process rate limiter. All
``api.services.db_developer`` primitives are mocked; nothing touches a real
database.
"""

import hashlib
import json
import time
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from api.services.api_keys import (
    APIKeyService,
    KEY_PREFIX,
    _generate_key,
    _mask_key,
    api_key_service,
)


@pytest.fixture
def svc():
    return APIKeyService()


@pytest.fixture
def module_service():
    return api_key_service


class TestGenerateAndMask:
    def test_generate_key_structure(self):
        full_key, prefix, key_hash = _generate_key()
        assert full_key.startswith(KEY_PREFIX)
        assert len(full_key) == len(KEY_PREFIX) + 64
        assert prefix == full_key[:10]
        assert key_hash == hashlib.sha256(full_key.encode()).hexdigest()

    def test_generate_key_uses_secrets(self):
        with patch("api.services.api_keys.secrets.token_hex", return_value="ab" * 32):
            full_key, prefix, key_hash = _generate_key()
        assert full_key == "ak_" + "ab" * 32
        assert prefix == full_key[:10]

    def test_mask_key_short(self):
        assert _mask_key("ak_12345678") == "ak_123" + "****"

    def test_mask_key_long(self):
        full = "ak_" + "x" * 32
        assert _mask_key(full) == full[:10] + "****" + full[-4:]


class TestCreateKey:
    @pytest.mark.asyncio
    async def test_create_key_with_default_scopes(self, svc):
        with patch(
            "api.services.api_keys._generate_key",
            return_value=("ak_full", "ak_prefix", "hash123"),
        ), patch(
            "api.services.api_keys.create_api_key_db",
            new_callable=AsyncMock,
            return_value={"id": "k1", "name": "n"},
        ) as create_db:
            result = await svc.create_key("t1", "key name")
        assert result == {"id": "k1", "name": "n", "full_key": "ak_full"}
        assert create_db.await_args.args[:4] == ("t1", "key name", "ak_prefix", "hash123")
        assert create_db.await_args.args[4] == ["all"]
        expires_at = create_db.await_args.args[5]
        parsed = datetime.fromisoformat(expires_at)
        assert parsed.tzinfo is not None

    @pytest.mark.asyncio
    async def test_create_key_with_custom_scopes_and_expiry(self, svc):
        with patch(
            "api.services.api_keys._generate_key",
            return_value=("ak_full", "ak_prefix", "hash123"),
        ), patch(
            "api.services.api_keys.create_api_key_db",
            new_callable=AsyncMock,
            return_value={"id": "k1"},
        ) as create_db:
            result = await svc.create_key(
                "t1", "key name", scopes=["read", "write"], expires_in_days=30
            )
        assert result["full_key"] == "ak_full"
        assert create_db.await_args.args[4] == ["read", "write"]
        expires = datetime.fromisoformat(create_db.await_args.args[5])
        delta = expires - datetime.now(UTC)
        assert timedelta(days=29) <= delta <= timedelta(days=31)

    @pytest.mark.asyncio
    async def test_create_key_empty_scopes_list_defaults(self, svc):
        with patch(
            "api.services.api_keys._generate_key",
            return_value=("ak_full", "ak_prefix", "hash123"),
        ), patch(
            "api.services.api_keys.create_api_key_db",
            new_callable=AsyncMock,
            return_value={"id": "k1"},
        ) as create_db:
            await svc.create_key("t1", "key name", scopes=[])
        assert create_db.await_args.args[4] == ["all"]

    @pytest.mark.asyncio
    async def test_create_key_db_failure_raises(self, svc):
        with patch(
            "api.services.api_keys._generate_key",
            return_value=("ak_full", "ak_prefix", "hash123"),
        ), patch(
            "api.services.api_keys.create_api_key_db",
            new_callable=AsyncMock,
            return_value=None,
        ):
            with pytest.raises(RuntimeError, match="Failed to create API key"):
                await svc.create_key("t1", "key name")


class TestValidateKey:
    @pytest.mark.asyncio
    async def test_empty_key_returns_none(self, svc):
        with patch("api.services.api_keys.get_api_key_by_prefix_db") as get_db:
            assert await svc.validate_key("") is None
            assert await svc.validate_key(None) is None
            get_db.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_wrong_prefix_returns_none(self, svc):
        with patch("api.services.api_keys.get_api_key_by_prefix_db") as get_db:
            assert await svc.validate_key("not_ak_1234567890") is None
            get_db.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_record_returns_none(self, svc):
        with patch(
            "api.services.api_keys.get_api_key_by_prefix_db",
            new_callable=AsyncMock,
            return_value=None,
        ) as get_db:
            assert await svc.validate_key("ak_1234567890") is None
        assert get_db.await_args.args[0] == "ak_1234567890"[:10]

    @pytest.mark.asyncio
    async def test_inactive_key_returns_none(self, svc):
        record = {"id": "k1", "is_active": False, "key_hash": "x"}
        with patch(
            "api.services.api_keys.get_api_key_by_prefix_db",
            new_callable=AsyncMock,
            return_value=record,
        ):
            assert await svc.validate_key("ak_1234567890") is None

    @pytest.mark.asyncio
    async def test_hash_mismatch_returns_none(self, svc):
        record = {"id": "k1", "is_active": True, "key_hash": "different"}
        with patch(
            "api.services.api_keys.get_api_key_by_prefix_db",
            new_callable=AsyncMock,
            return_value=record,
        ):
            assert await svc.validate_key("ak_1234567890") is None

    @pytest.mark.asyncio
    async def test_expired_string_expiry_returns_none(self, svc):
        api_key = "ak_1234567890abcdef"
        record = {
            "id": "k1",
            "is_active": True,
            "key_hash": hashlib.sha256(api_key.encode()).hexdigest(),
            "expires_at": (datetime.now(UTC) - timedelta(days=1)).isoformat(),
        }
        with patch(
            "api.services.api_keys.get_api_key_by_prefix_db",
            new_callable=AsyncMock,
            return_value=record,
        ):
            assert await svc.validate_key(api_key) is None

    @pytest.mark.asyncio
    async def test_expired_naive_datetime_returns_none(self, svc):
        api_key = "ak_1234567890abcdef"
        record = {
            "id": "k1",
            "is_active": True,
            "key_hash": hashlib.sha256(api_key.encode()).hexdigest(),
            "expires_at": datetime.now() - timedelta(days=1),
        }
        with patch(
            "api.services.api_keys.get_api_key_by_prefix_db",
            new_callable=AsyncMock,
            return_value=record,
        ):
            assert await svc.validate_key(api_key) is None

    @pytest.mark.asyncio
    async def test_valid_key_with_list_scopes(self, svc):
        api_key = "ak_1234567890abcdef"
        record = {
            "id": "k1",
            "tenant_id": "t1",
            "is_active": True,
            "key_hash": hashlib.sha256(api_key.encode()).hexdigest(),
            "expires_at": (datetime.now(UTC) + timedelta(days=10)).isoformat(),
            "scopes_json": ["read", "write"],
        }
        with patch(
            "api.services.api_keys.get_api_key_by_prefix_db",
            new_callable=AsyncMock,
            return_value=record,
        ), patch(
            "api.services.api_keys.update_api_key_last_used_db",
            new_callable=AsyncMock,
        ) as update_db:
            result = await svc.validate_key(api_key)
        assert result == {"tenant_id": "t1", "key_id": "k1", "scopes": ["read", "write"]}
        update_db.assert_awaited_once_with("k1")

    @pytest.mark.asyncio
    async def test_valid_key_with_string_scopes(self, svc):
        api_key = "ak_1234567890abcdef"
        record = {
            "id": "k1",
            "tenant_id": "t1",
            "is_active": True,
            "key_hash": hashlib.sha256(api_key.encode()).hexdigest(),
            "scopes_json": json.dumps(["admin"]),
        }
        with patch(
            "api.services.api_keys.get_api_key_by_prefix_db",
            new_callable=AsyncMock,
            return_value=record,
        ), patch(
            "api.services.api_keys.update_api_key_last_used_db",
            new_callable=AsyncMock,
        ):
            result = await svc.validate_key(api_key)
        assert result["scopes"] == ["admin"]

    @pytest.mark.asyncio
    async def test_valid_key_with_dict_scopes(self, svc):
        api_key = "ak_1234567890abcdef"
        record = {
            "id": "k1",
            "tenant_id": "t1",
            "is_active": True,
            "key_hash": hashlib.sha256(api_key.encode()).hexdigest(),
            "scopes_json": {"scopes": ["read"]},
        }
        with patch(
            "api.services.api_keys.get_api_key_by_prefix_db",
            new_callable=AsyncMock,
            return_value=record,
        ), patch(
            "api.services.api_keys.update_api_key_last_used_db",
            new_callable=AsyncMock,
        ):
            result = await svc.validate_key(api_key)
        assert result["scopes"] == ["read"]

    @pytest.mark.asyncio
    async def test_valid_key_dict_scopes_missing_key_defaults(self, svc):
        api_key = "ak_1234567890abcdef"
        record = {
            "id": "k1",
            "tenant_id": "t1",
            "is_active": True,
            "key_hash": hashlib.sha256(api_key.encode()).hexdigest(),
            "scopes_json": {"other": 1},
        }
        with patch(
            "api.services.api_keys.get_api_key_by_prefix_db",
            new_callable=AsyncMock,
            return_value=record,
        ), patch(
            "api.services.api_keys.update_api_key_last_used_db",
            new_callable=AsyncMock,
        ):
            result = await svc.validate_key(api_key)
        assert result["scopes"] == []

    @pytest.mark.asyncio
    async def test_valid_key_without_expiry(self, svc):
        api_key = "ak_1234567890abcdef"
        record = {
            "id": "k1",
            "tenant_id": "t1",
            "is_active": True,
            "key_hash": hashlib.sha256(api_key.encode()).hexdigest(),
        }
        with patch(
            "api.services.api_keys.get_api_key_by_prefix_db",
            new_callable=AsyncMock,
            return_value=record,
        ), patch(
            "api.services.api_keys.update_api_key_last_used_db",
            new_callable=AsyncMock,
        ):
            result = await svc.validate_key(api_key)
        assert result["key_id"] == "k1"


class TestRevokeListRotateUsage:
    @pytest.mark.asyncio
    async def test_revoke_key(self, svc):
        with patch(
            "api.services.api_keys.revoke_api_key_db",
            new_callable=AsyncMock,
            return_value=True,
        ) as revoke_db:
            assert await svc.revoke_key("t1", "k1") is True
        revoke_db.assert_awaited_once_with("t1", "k1")

    @pytest.mark.asyncio
    async def test_list_keys_masks_and_parses_scopes(self, svc):
        records = [
            {
                "id": "k1",
                "name": "a",
                "key_prefix": "ak_123456",
                "key_hash": "hash1234",
                "scopes_json": json.dumps(["read"]),
                "created_at": "2026-01-01",
                "last_used_at": "2026-02-01",
                "expires_at": None,
                "is_active": 1,
            },
            {
                "id": "k2",
                "name": "b",
                "key_prefix": "ak_abcdef",
                "key_hash": None,
                "scopes_json": ["write"],
                "is_active": 0,
            },
        ]
        with patch(
            "api.services.api_keys.list_api_keys_db",
            new_callable=AsyncMock,
            return_value=records,
        ) as list_db:
            out = await svc.list_keys("t1")
        list_db.assert_awaited_once_with("t1")
        assert out[0]["masked_key"] == "ak_123456****1234"
        assert out[0]["scopes"] == ["read"]
        assert out[0]["is_active"] is True
        assert out[1]["masked_key"] == "ak_abcdef********"
        assert out[1]["scopes"] == ["write"]
        assert out[1]["is_active"] is False

    @pytest.mark.asyncio
    async def test_list_keys_empty(self, svc):
        with patch(
            "api.services.api_keys.list_api_keys_db",
            new_callable=AsyncMock,
            return_value=[],
        ) as list_db:
            assert await svc.list_keys("t1") == []
        list_db.assert_awaited_once_with("t1")

    @pytest.mark.asyncio
    async def test_rotate_key_missing_record_returns_none(self, svc):
        with patch(
            "api.services.api_keys.get_api_key_by_id_db",
            new_callable=AsyncMock,
            return_value=None,
        ) as get_db:
            assert await svc.rotate_key("t1", "k1") is None
        get_db.assert_awaited_once_with("t1", "k1")

    @pytest.mark.asyncio
    async def test_rotate_key_revokes_and_creates(self, svc):
        record = {
            "id": "k1",
            "name": "my key",
            "scopes_json": json.dumps(["read", "write"]),
        }
        with patch(
            "api.services.api_keys.get_api_key_by_id_db",
            new_callable=AsyncMock,
            return_value=record,
        ), patch(
            "api.services.api_keys.revoke_api_key_db",
            new_callable=AsyncMock,
            return_value=True,
        ) as revoke_db, patch.object(
            svc, "create_key", new_callable=AsyncMock, return_value={"full_key": "new"}
        ) as create_key:
            result = await svc.rotate_key("t1", "k1")
        assert result == {"full_key": "new"}
        revoke_db.assert_awaited_once_with("t1", "k1")
        create_key.assert_awaited_once_with("t1", "my key (rotated)", ["read", "write"])

    @pytest.mark.asyncio
    async def test_rotate_key_scopes_from_list(self, svc):
        record = {"id": "k1", "name": "my key", "scopes_json": ["read"]}
        with patch(
            "api.services.api_keys.get_api_key_by_id_db",
            new_callable=AsyncMock,
            return_value=record,
        ), patch(
            "api.services.api_keys.revoke_api_key_db",
            new_callable=AsyncMock,
            return_value=True,
        ), patch.object(
            svc, "create_key", new_callable=AsyncMock, return_value={"full_key": "new"}
        ) as create_key:
            await svc.rotate_key("t1", "k1")
        create_key.assert_awaited_once_with("t1", "my key (rotated)", ["read"])

    @pytest.mark.asyncio
    async def test_get_key_usage(self, svc):
        record = {
            "id": "k1",
            "name": "a",
            "created_at": "2026-01-01",
            "last_used_at": "2026-02-01",
            "is_active": True,
        }
        with patch(
            "api.services.api_keys.get_api_key_by_id_db",
            new_callable=AsyncMock,
            return_value=record,
        ) as get_db:
            out = await svc.get_key_usage("t1", "k1", period="30d")
        get_db.assert_awaited_once_with("t1", "k1")
        assert out["period"] == "30d"
        assert out["call_count"] == 0
        assert out["is_active"] is True

    @pytest.mark.asyncio
    async def test_get_key_usage_missing_record(self, svc):
        with patch(
            "api.services.api_keys.get_api_key_by_id_db",
            new_callable=AsyncMock,
            return_value=None,
        ):
            assert await svc.get_key_usage("t1", "k1") is None


class TestRateLimit:
    def test_rate_limit_allows_until_max(self, svc):
        with patch("api.services.api_keys.RATE_LIMIT_MAX", 3):
            assert svc.check_rate_limit("ak_key1") is True
            assert svc.check_rate_limit("ak_key1") is True
            assert svc.check_rate_limit("ak_key1") is True
            assert svc.check_rate_limit("ak_key1") is False

    def test_rate_limit_per_key(self, svc):
        with patch("api.services.api_keys.RATE_LIMIT_MAX", 2):
            assert svc.check_rate_limit("ak_key1") is True
            assert svc.check_rate_limit("ak_key2") is True
            assert svc.check_rate_limit("ak_key1") is True
            assert svc.check_rate_limit("ak_key1") is False
            assert svc.check_rate_limit("ak_key2") is True

    def test_rate_limit_expires_old_timestamps(self, svc):
        old = time.time() - 120
        svc._rate_limits["ak_key1"] = [old, old]
        with patch("api.services.api_keys.RATE_LIMIT_MAX", 2):
            assert svc.check_rate_limit("ak_key1") is True

    def test_module_singleton_is_instance(self, module_service):
        assert isinstance(module_service, APIKeyService)
