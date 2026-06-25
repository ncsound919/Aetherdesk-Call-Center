"""Unit tests for JWT utility functions (create_access_token, verify_access_token)."""

import sys
import types
from unittest.mock import patch, MagicMock

import pytest

# Pre-register a mock module for api.main to avoid import errors
# if jwt_utils.py or its dependencies ever import it.
_sentinel = types.ModuleType("api.main")
_sentinel.redis_client = None
_sentinel.logger = MagicMock()
sys.modules.setdefault("api.main", _sentinel)


class TestCreateAccessToken:
    """Tests for create_access_token()."""

    def test_returns_encoded_string(self):
        from api.services.jwt_utils import create_access_token

        with patch("api.services.jwt_utils.jwt.encode") as mock_encode:
            mock_encode.return_value = "encoded.jwt.token"

            result = create_access_token(data={"sub": "user-1", "tenant_id": "T-1"})
            assert result == "encoded.jwt.token"

    def test_includes_exp_and_jti(self):
        from api.services.jwt_utils import create_access_token

        with patch("api.services.jwt_utils.jwt.encode") as mock_encode:
            mock_encode.return_value = "encoded.jwt.token"

            create_access_token(data={"sub": "user-1"})
            called_data = mock_encode.call_args[0][0]
            assert called_data["sub"] == "user-1"
            assert "exp" in called_data
            assert "iat" in called_data
            assert "jti" in called_data

    def test_custom_expires_delta(self):
        from datetime import timedelta

        from api.services.jwt_utils import create_access_token

        with patch("api.services.jwt_utils.jwt.encode") as mock_encode:
            mock_encode.return_value = "encoded.jwt.token"

            create_access_token(data={"sub": "user-1"}, expires_delta=timedelta(hours=1))
            called_data = mock_encode.call_args[0][0]
            assert called_data["sub"] == "user-1"


class TestVerifyAccessToken:
    """Tests for verify_access_token()."""

    def test_valid_token_returns_payload(self):
        from api.services.jwt_utils import verify_access_token

        with patch("api.services.jwt_utils.jwt.decode") as mock_decode:
            mock_decode.return_value = {"sub": "user-1", "tenant_id": "T-1"}

            result = verify_access_token("valid.jwt.token")
            assert result == {"sub": "user-1", "tenant_id": "T-1"}

    def test_expired_token_returns_none(self):
        from api.services.jwt_utils import verify_access_token

        with patch("api.services.jwt_utils.jwt.decode") as mock_decode:
            from jwt import ExpiredSignatureError

            mock_decode.side_effect = ExpiredSignatureError("Token expired")

            result = verify_access_token("expired.jwt.token")
            assert result is None

    def test_invalid_token_tries_hs256_fallback(self):
        from api.services.jwt_utils import verify_access_token

        with patch("api.services.jwt_utils.jwt.decode") as mock_decode:
            from jwt import InvalidTokenError

            # First call (RS256) raises InvalidTokenError, second (HS256) succeeds
            mock_decode.side_effect = [
                InvalidTokenError("RS256 failed"),
                {"sub": "user-1", "tenant_id": "T-1"},
            ]

            with patch("api.services.jwt_utils.os.getenv", return_value="hs256-secret"):
                result = verify_access_token("mixed.jwt.token")
                assert result == {"sub": "user-1", "tenant_id": "T-1"}

    def test_invalid_token_no_hs256_fallback_returns_none(self):
        from api.services.jwt_utils import verify_access_token

        with patch("api.services.jwt_utils.jwt.decode") as mock_decode:
            from jwt import InvalidTokenError

            mock_decode.side_effect = InvalidTokenError("RS256 failed")

            with patch("api.services.jwt_utils.os.getenv", return_value=None):
                result = verify_access_token("invalid.jwt.token")
                assert result is None

    def test_both_algorithms_fail_returns_none(self):
        from api.services.jwt_utils import verify_access_token

        with patch("api.services.jwt_utils.jwt.decode") as mock_decode:
            from jwt import InvalidTokenError

            mock_decode.side_effect = InvalidTokenError("nope")

            with patch("api.services.jwt_utils.os.getenv", return_value="hs256-secret"):
                result = verify_access_token("totally.bogus.token")
                assert result is None


class TestGenerateDevKeyPair:
    """Tests for generate_dev_key_pair()."""

    def test_returns_rsa_key_pair(self):
        from api.services.jwt_utils import generate_dev_key_pair

        result = generate_dev_key_pair()
        assert "private_key" in result
        assert "public_key" in result
        assert result["private_key"].startswith("-----BEGIN PRIVATE KEY-----")
        assert result["public_key"].startswith("-----BEGIN PUBLIC KEY-----")


class TestGetPrivateKey:
    """Tests for get_private_key()."""

    def test_returns_cached_key(self):
        from api.services.jwt_utils import get_private_key

        with patch(
            "api.services.jwt_utils._private_key", "cached-private-key"
        ), patch("api.services.jwt_utils._load_key") as mock_load:
            result = get_private_key()
            assert result == "cached-private-key"
            mock_load.assert_not_called()

    def test_loads_from_env_when_not_cached(self):
        from api.services.jwt_utils import get_private_key

        with patch("api.services.jwt_utils._private_key", None), patch(
            "api.services.jwt_utils._load_key", return_value="env-private-key"
        ):
            result = get_private_key()
            assert result == "env-private-key"

    def test_raises_in_production_without_key(self):
        from api.services.jwt_utils import get_private_key

        with patch("api.services.jwt_utils._private_key", None), patch(
            "api.services.jwt_utils._load_key", return_value=None
        ), patch("api.services.jwt_utils.os.getenv", return_value="production"):
            with pytest.raises(RuntimeError, match="JWT_PRIVATE_KEY"):
                get_private_key()

    def test_generates_dev_keys_in_development(self):
        import api.services.jwt_utils as jwt_utils

        from api.services.jwt_utils import get_private_key

        with patch.object(jwt_utils, "_private_key", None), patch(
            "api.services.jwt_utils._load_key", return_value=None
        ), patch("api.services.jwt_utils.os.getenv", return_value="development"), patch.object(
            jwt_utils, "_ensure_dev_keys"
        ) as mock_ensure:
            # Make _ensure_dev_keys actually set the global variable
            def _fake_ensure():
                jwt_utils._private_key = "dev-generated-key"

            mock_ensure.side_effect = _fake_ensure

            result = get_private_key()
            mock_ensure.assert_called_once()
            assert result == "dev-generated-key"


class TestGetPublicKey:
    """Tests for get_public_key()."""

    def test_returns_cached_key(self):
        from api.services.jwt_utils import get_public_key

        with patch("api.services.jwt_utils._public_key", "cached-public-key"), patch(
            "api.services.jwt_utils._load_key"
        ) as mock_load:
            result = get_public_key()
            assert result == "cached-public-key"
            mock_load.assert_not_called()

    def test_loads_from_env_when_not_cached(self):
        from api.services.jwt_utils import get_public_key

        with patch("api.services.jwt_utils._public_key", None), patch(
            "api.services.jwt_utils._load_key", return_value="env-public-key"
        ):
            result = get_public_key()
            assert result == "env-public-key"

    def test_raises_in_production_without_key(self):
        from api.services.jwt_utils import get_public_key

        with patch("api.services.jwt_utils._public_key", None), patch(
            "api.services.jwt_utils._load_key", return_value=None
        ), patch("api.services.jwt_utils.os.getenv", return_value="production"):
            with pytest.raises(RuntimeError, match="JWT_PUBLIC_KEY"):
                get_public_key()

    def test_generates_dev_keys_in_development(self):
        import api.services.jwt_utils as jwt_utils

        from api.services.jwt_utils import get_public_key

        with patch.object(jwt_utils, "_public_key", None), patch(
            "api.services.jwt_utils._load_key", return_value=None
        ), patch("api.services.jwt_utils.os.getenv", return_value="development"), patch.object(
            jwt_utils, "_ensure_dev_keys"
        ) as mock_ensure:
            def _fake_ensure():
                jwt_utils._public_key = "dev-generated-public-key"

            mock_ensure.side_effect = _fake_ensure

            result = get_public_key()
            mock_ensure.assert_called_once()
            assert result == "dev-generated-public-key"
