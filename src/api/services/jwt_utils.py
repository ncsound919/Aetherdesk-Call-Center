"""JWT utilities using RS256 asymmetric signing.

RS256 (RSA-SHA256) is more secure than HS256 because:
- Private key stays only on the issuing server
- Multiple services can verify tokens with just the public key
- Key rotation is simpler (distribute new public key)

Configuration (in order of precedence):
1. JWT_PRIVATE_KEY / JWT_PUBLIC_KEY — inline PEM keys
2. JWT_PRIVATE_KEY_PATH / JWT_PUBLIC_KEY_PATH — file paths to PEM keys
3. Auto-generated dev keys (APP_ENV=development only)
"""

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import jwt
import structlog

logger = structlog.get_logger()

_private_key: str | None = None
_public_key: str | None = None
_algorithm = "RS256"


def _load_key(key_name: str, path_name: str, fallback_gen: object = None) -> str | None:
    """Load a key from env var or file path, with optional dev fallback."""
    inline = os.getenv(key_name)
    if inline:
        return inline

    path = os.getenv(path_name)
    if path:
        p = Path(path)
        if p.exists():
            return p.read_text().strip()
        logger.warning("JWT key file not found", path=str(path))

    return None


def _ensure_dev_keys():
    """Auto-generate RSA key pair for development."""
    global _private_key, _public_key

    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    _private_key = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()

    _public_key = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()

    logger.info("Auto-generated dev RSA key pair for JWT")


def get_private_key() -> str:
    global _private_key
    if _private_key:
        return _private_key

    _private_key = _load_key("JWT_PRIVATE_KEY", "JWT_PRIVATE_KEY_PATH")
    if _private_key:
        return _private_key

    env = os.getenv("APP_ENV", "development")
    if env == "production":
        raise RuntimeError(
            "JWT_PRIVATE_KEY or JWT_PRIVATE_KEY_PATH must be set in production"
        )

    _ensure_dev_keys()
    return _private_key  # type: ignore


def get_public_key() -> str:
    global _public_key
    if _public_key:
        return _public_key

    _public_key = _load_key("JWT_PUBLIC_KEY", "JWT_PUBLIC_KEY_PATH")
    if _public_key:
        return _public_key

    env = os.getenv("APP_ENV", "development")
    if env == "production":
        raise RuntimeError(
            "JWT_PUBLIC_KEY or JWT_PUBLIC_KEY_PATH must be set in production"
        )

    _ensure_dev_keys()
    return _public_key  # type: ignore


# ── Token Creation & Verification ────────────────────────────────


def create_access_token(
    data: dict,
    expires_delta: timedelta | None = None,
) -> str:
    """Create a JWT access token signed with RS256."""
    import uuid
    to_encode = data.copy()
    expire = datetime.now(UTC) + (expires_delta or timedelta(hours=24))
    to_encode.update({
        "exp": expire,
        "iat": datetime.now(UTC),
        "jti": str(uuid.uuid4())
    })
    return jwt.encode(to_encode, get_private_key(), algorithm=_algorithm)


def verify_access_token(token: str) -> dict | None:
    """Verify a JWT access token signed with RS256.

    The `algorithms=` parameter is always passed explicitly. PyJWT 2.10+
    rejects the `alg=none` confusion attack (CVE-2025-61152) and refuses
    to decode without an explicit algorithm list.
    """
    try:
        return jwt.decode(
            token,
            get_public_key(),
            algorithms=[_algorithm],
        )
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def generate_dev_key_pair() -> dict:
    """Generate and print a new RSA key pair for production setup.

    Usage: python -c "from api.services.jwt_utils import generate_dev_key_pair; print(generate_dev_key_pair())"
    """
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=4096)
    private_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()

    public_pem = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()

    return {
        "private_key": private_pem,
        "public_key": public_pem,
    }


