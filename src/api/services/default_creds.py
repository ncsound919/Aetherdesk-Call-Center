import secrets
import string
from datetime import UTC, datetime

import structlog

from api.services.db_config import USE_POSTGRES
from api.services.db_pool import _get_sqlite_conn, get_pg_pool

logger = structlog.get_logger()

DEFAULT_ADMIN_EMAIL = "admin@aetherdesk.com"
DEFAULT_ADMIN_PASSWORD = "admin123"
WEAK_PASSWORDS = {"password", "password123", "admin", "admin123", "123456", "letmein", "welcome"}


async def check_default_credentials():
    logger.info("checking_default_credentials")
    found = None
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            row = await pool.fetchrow(
                "SELECT id, email FROM users WHERE email = $1",
                DEFAULT_ADMIN_EMAIL,
            )
            if row:
                found = {"user_id": str(row["id"]), "email": row["email"]}
    else:
        conn = _get_sqlite_conn()
        try:
            row = conn.execute(
                "SELECT id, email FROM users WHERE email = ?",
                (DEFAULT_ADMIN_EMAIL,),
            ).fetchone()
            if row:
                found = {"user_id": row["id"], "email": row["email"]}
        finally:
            conn.close()

    if found:
        logger.warning("default_admin_credentials_found", email=DEFAULT_ADMIN_EMAIL)
    else:
        logger.info("no_default_credentials_detected")
    return found


async def force_password_reset(user_id: str):
    logger.info("forcing_password_reset", user_id=user_id)
    reset_token = secrets.token_urlsafe(48)
    expires_at = datetime.now(UTC).isoformat()

    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            await pool.execute(
                "UPDATE users SET reset_token = $1, reset_token_expires = NOW() + INTERVAL '1 hour', password_hash = '' WHERE id = $2",
                reset_token, user_id,
            )
            row = await pool.fetchrow("SELECT id, email FROM users WHERE id = $1", user_id)
            return dict(row) if row else None
    else:
        conn = _get_sqlite_conn()
        try:
            conn.execute(
                "UPDATE users SET reset_token = ?, reset_token_expires = ?, password_hash = '' WHERE id = ?",
                (reset_token, expires_at, user_id),
            )
            conn.commit()
            row = conn.execute("SELECT id, email FROM users WHERE id = ?", (user_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


def generate_secure_password(length: int = 24):
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    while True:
        password = "".join(secrets.choice(alphabet) for _ in range(length))
        if (
            any(c.islower() for c in password)
            and any(c.isupper() for c in password)
            and any(c.isdigit() for c in password)
            and any(c in "!@#$%^&*" for c in password)
        ):
            return password


async def audit_credential_strength():
    logger.info("auditing_credential_strength")
    results = []
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            rows = await pool.fetch("SELECT id, email FROM users")
            for row in rows:
                results.append({
                    "user_id": str(row["id"]),
                    "email": row["email"],
                    "has_default_credential": row["email"] == DEFAULT_ADMIN_EMAIL,
                    "status": "critical" if row["email"] == DEFAULT_ADMIN_EMAIL else "ok",
                })
    else:
        conn = _get_sqlite_conn()
        try:
            rows = conn.execute("SELECT id, email FROM users").fetchall()
            for row in rows:
                results.append({
                    "user_id": row["id"],
                    "email": row["email"],
                    "has_default_credential": row["email"] == DEFAULT_ADMIN_EMAIL,
                    "status": "critical" if row["email"] == DEFAULT_ADMIN_EMAIL else "ok",
                })
        finally:
            conn.close()

    return {
        "total_users": len(results),
        "critical": sum(1 for r in results if r["status"] == "critical"),
        "warning": sum(1 for r in results if r["status"] == "warning"),
        "ok": sum(1 for r in results if r["status"] == "ok"),
        "users": results,
    }
