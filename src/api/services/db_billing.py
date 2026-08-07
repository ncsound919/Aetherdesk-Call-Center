"""Database access for rental billing: rental windows, prepaid minute balances,
and per-tenant billing settings (ai_mode / BYOK keys / ElevenLabs).

Table `tenant_rentals` records each rental (history). Table `tenant_balances`
holds a single row per tenant with the prepaid minute balance, updated
atomically via SQL so concurrent calls cannot overspend.
"""

import json
import uuid
from datetime import UTC, datetime

from api.services.db_pool import USE_POSTGRES, _get_sqlite_conn, get_pg_pool


def _now() -> str:
    return datetime.now(UTC).isoformat()


# ── tenant_balances ────────────────────────────────────────────────────────


async def get_minute_balance_db(tenant_id: str) -> int:
    """Return the tenant's prepaid minute balance (0 if none)."""
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            val = await pool.fetchval(
                "SELECT minute_balance FROM tenant_balances WHERE tenant_id = $1",
                tenant_id,
            )
            return int(val or 0)
    else:
        conn = _get_sqlite_conn()
        try:
            row = conn.execute(
                "SELECT minute_balance FROM tenant_balances WHERE tenant_id = ?",
                (tenant_id,),
            ).fetchone()
            return int(row["minute_balance"]) if row else 0
        finally:
            conn.close()
    return 0


async def credit_minutes_db(tenant_id: str, minutes: int) -> int:
    """Add minutes to the tenant's balance, returning the new balance."""
    if minutes <= 0:
        return await get_minute_balance_db(tenant_id)
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            await pool.execute(
                """INSERT INTO tenant_balances (tenant_id, minute_balance, updated_at)
                   VALUES ($1, $2, NOW())
                   ON CONFLICT (tenant_id) DO UPDATE SET
                     minute_balance = tenant_balances.minute_balance + EXCLUDED.minute_balance,
                     updated_at = NOW()""",
                tenant_id,
                minutes,
            )
            return await get_minute_balance_db(tenant_id)
    else:
        conn = _get_sqlite_conn()
        try:
            now = _now()
            conn.execute(
                """INSERT INTO tenant_balances (tenant_id, minute_balance, updated_at)
                   VALUES (?, ?, ?)
                   ON CONFLICT(tenant_id) DO UPDATE SET
                     minute_balance = tenant_balances.minute_balance + excluded.minute_balance,
                     updated_at = excluded.updated_at""",
                (tenant_id, minutes, now),
            )
            conn.commit()
            row = conn.execute(
                "SELECT minute_balance FROM tenant_balances WHERE tenant_id = ?",
                (tenant_id,),
            ).fetchone()
            return int(row["minute_balance"])
        finally:
            conn.close()
    return await get_minute_balance_db(tenant_id)


async def debit_minutes_db(tenant_id: str, minutes: int) -> bool:
    """Atomically debit minutes. Returns False if balance is insufficient."""
    if minutes <= 0:
        return True
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            result = await pool.execute(
                """UPDATE tenant_balances
                   SET minute_balance = minute_balance - $1, updated_at = NOW()
                   WHERE tenant_id = $2 AND minute_balance >= $1""",
                minutes,
                tenant_id,
            )
            return result == "UPDATE 1"
    else:
        conn = _get_sqlite_conn()
        try:
            cur = conn.execute(
                """UPDATE tenant_balances
                   SET minute_balance = minute_balance - ?, updated_at = ?
                   WHERE tenant_id = ? AND minute_balance >= ?""",
                (minutes, _now(), tenant_id, minutes),
            )
            conn.commit()
            return cur.rowcount == 1
        finally:
            conn.close()
    return False


# ── tenant_rentals ─────────────────────────────────────────────────────────


async def get_active_rental_db(tenant_id: str) -> dict | None:
    """Return the active (non-expired) rental for a tenant, or None."""
    now = _now()
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            return await pool.fetchrow(
                """SELECT * FROM tenant_rentals
                   WHERE tenant_id = $1 AND status = 'active' AND rental_end > $2
                   ORDER BY created_at DESC LIMIT 1""",
                tenant_id,
                now,
            )
    else:
        conn = _get_sqlite_conn()
        try:
            return conn.execute(
                """SELECT * FROM tenant_rentals
                   WHERE tenant_id = ? AND status = 'active' AND rental_end > ?
                   ORDER BY created_at DESC LIMIT 1""",
                (tenant_id, now),
            ).fetchone()
        finally:
            conn.close()
    return None


async def has_call_capacity_db(tenant_id: str) -> tuple[bool, dict]:
    """Return (ok, info) — whether the tenant can place a call right now.

    Requires an active rental (capacity) and a positive prepaid minute balance.
    """
    rental = await get_active_rental_db(tenant_id)
    balance = await get_minute_balance_db(tenant_id)
    ok = rental is not None and balance > 0
    info = {
        "active_rental": rental is not None,
        "minute_balance": balance,
        "reason": (
            None
            if ok
            else ("no_active_rental" if rental is None else "insufficient_minutes")
        ),
    }
    return ok, info


async def activate_rental_db(
    tenant_id: str,
    period: str,
    ai_mode: str,
    quantity: int,
    included_minutes: int,
    rental_start: str,
    rental_end: str,
    stripe_session_id: str | None = None,
    payment_intent_id: str | None = None,
) -> dict:
    """Open a rental window and credit included minutes to the balance."""
    rental_id = str(uuid.uuid4())
    created = _now()
    values = (
        rental_id,
        tenant_id,
        period,
        ai_mode,
        quantity,
        included_minutes,
        rental_start,
        rental_end,
        stripe_session_id,
        payment_intent_id,
        "active",
        created,
    )
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            await pool.execute(
                """INSERT INTO tenant_rentals
                   (id, tenant_id, period, ai_mode, quantity, included_minutes,
                    rental_start, rental_end, stripe_session_id, payment_intent_id,
                    status, created_at)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)""",
                *values,
            )
            await credit_minutes_db(tenant_id, included_minutes)
            return await get_active_rental_db(tenant_id) or {}
    else:
        conn = _get_sqlite_conn()
        try:
            conn.execute(
                """INSERT INTO tenant_rentals
                   (id, tenant_id, period, ai_mode, quantity, included_minutes,
                    rental_start, rental_end, stripe_session_id, payment_intent_id,
                    status, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                values,
            )
            conn.commit()
        finally:
            conn.close()
        await credit_minutes_db(tenant_id, included_minutes)
        return await get_active_rental_db(tenant_id) or {}
    return {}


async def end_rental_db(rental_id: str) -> bool:
    """Mark a rental as ended (idempotent)."""
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            result = await pool.execute(
                "UPDATE tenant_rentals SET status = 'ended' WHERE id = $1 AND status = 'active'",
                rental_id,
            )
            return result == "UPDATE 1"
    else:
        conn = _get_sqlite_conn()
        try:
            cur = conn.execute(
                "UPDATE tenant_rentals SET status = 'ended' WHERE id = ? AND status = 'active'",
                (rental_id,),
            )
            conn.commit()
            return cur.rowcount == 1
        finally:
            conn.close()
    return False


async def get_rental_history_db(tenant_id: str) -> list[dict]:
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            return await pool.fetch(
                "SELECT * FROM tenant_rentals WHERE tenant_id = $1 ORDER BY created_at DESC",
                tenant_id,
            )
    else:
        conn = _get_sqlite_conn()
        try:
            return conn.execute(
                "SELECT * FROM tenant_rentals WHERE tenant_id = ? ORDER BY created_at DESC",
                (tenant_id,),
            ).fetchall()
        finally:
            conn.close()
    return []


async def get_rental_by_session_db(stripe_session_id: str) -> dict | None:
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            return await pool.fetchrow(
                "SELECT * FROM tenant_rentals WHERE stripe_session_id = $1 LIMIT 1",
                stripe_session_id,
            )
    else:
        conn = _get_sqlite_conn()
        try:
            return conn.execute(
                "SELECT * FROM tenant_rentals WHERE stripe_session_id = ? LIMIT 1",
                (stripe_session_id,),
            ).fetchone()
        finally:
            conn.close()
    return None


async def _tenant_id_for_sip_call(call_sid: str) -> str | None:
    """Find the tenant that owns a call by its SIP/Twilio call SID."""
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            row = await pool.fetchrow(
                "SELECT tenant_id FROM call_sessions WHERE sip_call_id = $1 LIMIT 1",
                call_sid,
            )
            return row["tenant_id"] if row else None
    else:
        conn = _get_sqlite_conn()
        try:
            row = conn.execute(
                "SELECT tenant_id FROM call_sessions WHERE sip_call_id = ? LIMIT 1",
                (call_sid,),
            ).fetchone()
            return row["tenant_id"] if row else None
        finally:
            conn.close()
    return None


async def settle_call_minutes_db(call_sid: str, duration_seconds: int) -> dict:
    """Debit a completed call's minutes (ceil, min 1) from the tenant balance.

    Returns ``{"debit": bool, "tenant_id": str|None, "minutes": int}``. When the
    call SID cannot be mapped to a tenant, no debit is applied (logged upstream).
    """
    tenant_id = await _tenant_id_for_sip_call(call_sid)
    if not tenant_id:
        return {"debit": False, "tenant_id": None, "minutes": 0, "reason": "call_not_found"}
    minutes = max(1, (int(duration_seconds) + 59) // 60)
    ok = await debit_minutes_db(tenant_id, minutes)
    return {"debit": ok, "tenant_id": tenant_id, "minutes": minutes}


# ── tenants.settings helpers ───────────────────────────────────────────────


def _load_settings(settings) -> dict:
    if not settings:
        return {}
    if isinstance(settings, dict):
        return dict(settings)
    if isinstance(settings, str):
        try:
            parsed = json.loads(settings)
            return parsed if isinstance(parsed, dict) else {}
        except (json.JSONDecodeError, TypeError):
            return {}
    return {}


async def get_tenant_billing_settings_db(tenant_id: str) -> dict:
    """Return {ai_mode, byok_keys, elevenlabs_api_key, elevenlabs_voice_id, ...}."""
    from api.services.db_tenants import get_tenant_db

    tenant = await get_tenant_db(tenant_id)
    settings = _load_settings(tenant["settings"] if tenant else None)
    return {
        "ai_mode": settings.get("ai_mode", "deepseek"),
        "byok_keys": settings.get("byok_keys", {}),
        "elevenlabs_api_key": settings.get("elevenlabs_api_key"),
        "elevenlabs_voice_id": settings.get("elevenlabs_voice_id"),
    }


async def set_tenant_billing_settings_db(tenant_id: str, updates: dict) -> dict:
    """Merge ``updates`` into the tenant's settings JSON and persist."""
    from api.services.db_tenants import get_tenant_db

    tenant = await get_tenant_db(tenant_id)
    if not tenant:
        return {}
    settings = _load_settings(tenant["settings"])
    settings.update(updates)
    serialized = json.dumps(settings)

    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            await pool.execute(
                "UPDATE tenants SET settings = $1, updated_at = NOW() WHERE id = $2",
                serialized,
                tenant_id,
            )
    else:
        conn = _get_sqlite_conn()
        try:
            conn.execute(
                "UPDATE tenants SET settings = ?, updated_at = ? WHERE id = ?",
                (serialized, _now(), tenant_id),
            )
            conn.commit()
        finally:
            conn.close()
    return await get_tenant_billing_settings_db(tenant_id)
