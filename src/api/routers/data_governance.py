import structlog
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query

from api.models.dto import LineageEntryCreate
from api.services.auth import verify_tenant_access
from api.services.data_lineage import lineage_service
from api.services.db_calls import log_audit_event
from api.services.db_config import USE_POSTGRES
from api.services.db_pool import db_context, encrypt_val
from api.services.db_tenants import get_user_by_id_db
from api.services.security_guard import mask_email

logger = structlog.get_logger()

router = APIRouter(prefix="/data-governance", tags=["data-governance"])


@router.get("/lineage/record")
async def get_record_lineage(
    table: str = Query(..., description="Source or target table name"),
    record_id: str = Query(..., description="Record ID"),
    tenant_id: str = Depends(verify_tenant_access),
):
    result = await lineage_service.get_lineage_for_record(tenant_id, table, record_id)
    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("error", "Lineage not found"))
    return result


@router.get("/lineage/graph")
async def get_lineage_graph(
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    tenant_id: str = Depends(verify_tenant_access),
):
    return await lineage_service.get_lineage_graph(tenant_id, start_date=start_date, end_date=end_date)


@router.get("/lineage/column")
async def get_column_lineage(
    table: str = Query(..., description="Table name"),
    column: str = Query(..., description="Column name"),
    tenant_id: str = Depends(verify_tenant_access),
):
    return await lineage_service.get_column_lineage(tenant_id, table, column)


@router.delete("/users/{user_id}/data")
async def delete_user_data(
    user_id: str,
    tenant_id: str = Depends(verify_tenant_access),
):
    user = await get_user_by_id_db(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.get("tenant_id") != tenant_id:
        raise HTTPException(status_code=403, detail="User does not belong to this tenant")

    logger.info(
        "gdpr_delete_user_data",
        user_id=user_id,
        email=mask_email(user.get("email")),
        tenant_id=tenant_id,
    )

    now = datetime.now(UTC).isoformat()
    deleted_email = f"deleted-{uuid4().hex[:12]}@anonymous.invalid"
    summary = {"calls_anonymized": 0, "leads_anonymized": 0, "profiles_anonymized": 0}

    phone = None

    async with db_context() as conn:
        if USE_POSTGRES:
            await conn.execute(
                """UPDATE users SET
                   email = $1, full_name = 'Deleted User',
                   password_hash = $2, avatar_url = NULL,
                   verification_token = NULL, reset_token = NULL,
                   reset_token_expires = NULL, updated_at = NOW()
                   WHERE id = $3""",
                deleted_email, encrypt_val("REDACTED"), user_id,
            )
            row = await conn.fetchrow(
                "SELECT phone, email FROM users WHERE id = $1", user_id,
            )
        else:
            conn.execute(
                """UPDATE users SET
                   email = ?, full_name = 'Deleted User',
                   password_hash = ?, avatar_url = NULL,
                   verification_token = NULL, reset_token = NULL,
                   reset_token_expires = NULL, updated_at = ?
                   WHERE id = ?""",
                (deleted_email, encrypt_val("REDACTED"), now, user_id),
            )
            row = conn.execute(
                "SELECT phone, email FROM users WHERE id = ?", (user_id,),
            ).fetchone()

        if row:
            phone = row.get("phone") if isinstance(row, dict) else row["phone"]

        old_email = user.get("email")
        if old_email or phone:
            if USE_POSTGRES:
                if phone:
                    result = await conn.execute(
                        "UPDATE call_sessions SET caller_number = 'REDACTED', caller_name = 'Deleted', pii_redacted = TRUE WHERE caller_number = $1 AND tenant_id = $2",
                        phone, tenant_id,
                    )
                    summary["calls_anonymized"] += int(result.split()[-1]) if result else 0
                    result2 = await conn.execute(
                        "UPDATE call_sessions SET called_number = 'REDACTED', pii_redacted = TRUE WHERE called_number = $1 AND tenant_id = $2",
                        phone, tenant_id,
                    )
                    summary["calls_anonymized"] += int(result2.split()[-1]) if result2 else 0

                await conn.execute(
                    "UPDATE leads SET email = 'REDACTED', phone = 'REDACTED', first_name = 'Deleted', last_name = 'Deleted', contact_name = 'Deleted', company_name = 'REDACTED', notes = NULL WHERE (email = $1 OR phone = $2) AND tenant_id = $3",
                    old_email or "", phone or "", tenant_id,
                )
                summary["leads_anonymized"] = 1

                await conn.execute(
                    "UPDATE customer_profiles SET email = 'REDACTED', phone = 'REDACTED', name = 'Deleted User', tags_json = '[]', metadata_json = '{}' WHERE (email = $1 OR phone = $2) AND tenant_id = $3",
                    old_email or "", phone or "", tenant_id,
                )
                summary["profiles_anonymized"] = 1
            else:
                if phone:
                    c = conn.execute(
                        "UPDATE call_sessions SET caller_number = 'REDACTED', caller_name = 'Deleted', pii_redacted = 1 WHERE caller_number = ? AND tenant_id = ?",
                        (phone, tenant_id),
                    )
                    summary["calls_anonymized"] += c.rowcount
                    c = conn.execute(
                        "UPDATE call_sessions SET called_number = 'REDACTED', pii_redacted = 1 WHERE called_number = ? AND tenant_id = ?",
                        (phone, tenant_id),
                    )
                    summary["calls_anonymized"] += c.rowcount

                conn.execute(
                    "UPDATE leads SET email = 'REDACTED', phone = 'REDACTED', first_name = 'Deleted', last_name = 'Deleted', contact_name = 'Deleted', company_name = 'REDACTED', notes = NULL WHERE (email = ? OR phone = ?) AND tenant_id = ?",
                    (old_email or "", phone or "", tenant_id),
                )
                summary["leads_anonymized"] = 1

                conn.execute(
                    "UPDATE customer_profiles SET email = 'REDACTED', phone = 'REDACTED', name = 'Deleted User', tags_json = '[]', metadata_json = '{}' WHERE (email = ? OR phone = ?) AND tenant_id = ?",
                    (old_email or "", phone or "", tenant_id),
                )
                summary["profiles_anonymized"] = 1

    await log_audit_event(
        tenant_id, user_id, "gdpr_delete",
        "user", user_id,
        old_values={"email": mask_email(user.get("email"))},
        new_values={"email": "REDACTED", "status": "anonymized"},
    )

    return {
        "success": True,
        "message": "User data anonymized successfully (right to be forgotten)",
        "user_id": user_id,
        "details": summary,
        "timestamp": now,
    }


@router.get("/users/{user_id}/export")
async def export_user_data(
    user_id: str,
    tenant_id: str = Depends(verify_tenant_access),
):
    user = await get_user_by_id_db(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.get("tenant_id") != tenant_id:
        raise HTTPException(status_code=403, detail="User does not belong to this tenant")

    logger.info(
        "gdpr_export_user_data",
        user_id=user_id,
        email=mask_email(user.get("email")),
        tenant_id=tenant_id,
    )

    export_data = {
        "profile": {
            "id": user.get("id"),
            "email": user.get("email"),
            "full_name": user.get("full_name"),
            "role": user.get("role"),
            "email_verified": user.get("email_verified"),
            "onboarding_completed": user.get("onboarding_completed"),
            "onboarding_step": user.get("onboarding_step"),
            "created_at": user.get("created_at"),
            "updated_at": user.get("updated_at"),
        },
        "calls": [],
        "recordings": [],
        "transcriptions": [],
        "customer_profiles": [],
        "leads": [],
    }

    async with db_context() as conn:
        if USE_POSTGRES:
            calls_rows = await conn.fetch(
                "SELECT id, agent_id, caller_number, caller_name, called_number, call_direction, call_status, call_type, start_time, end_time, duration_seconds, talk_time_seconds, sentiment_score, intent_detected, ai_summary, created_at FROM call_sessions WHERE tenant_id = $1 ORDER BY created_at DESC LIMIT 1000",
                tenant_id,
            )
            export_data["calls"] = [dict(r) for r in calls_rows]

            recordings_rows = await conn.fetch(
                "SELECT id, call_id, agent_id, file_path, file_size_bytes, duration_seconds, format, created_at FROM recordings WHERE tenant_id = $1 ORDER BY created_at DESC LIMIT 1000",
                tenant_id,
            )
            export_data["recordings"] = [dict(r) for r in recordings_rows]

            transcriptions_rows = await conn.fetch(
                "SELECT id, call_id, stt_engine, language_code, confidence_score, created_at FROM transcriptions WHERE tenant_id = $1 ORDER BY created_at DESC LIMIT 1000",
                tenant_id,
            )
            export_data["transcriptions"] = [dict(r) for r in transcriptions_rows]

            profiles_rows = await conn.fetch(
                "SELECT id, external_id, phone, email, name, tags_json, created_at FROM customer_profiles WHERE tenant_id = $1 ORDER BY created_at DESC LIMIT 1000",
                tenant_id,
            )
            export_data["customer_profiles"] = [dict(r) for r in profiles_rows]

            leads_rows = await conn.fetch(
                "SELECT id, company_name, contact_name, first_name, last_name, phone, email, status, score, source, created_at FROM leads WHERE tenant_id = $1 ORDER BY created_at DESC LIMIT 1000",
                tenant_id,
            )
            export_data["leads"] = [dict(r) for r in leads_rows]
        else:
            export_data["calls"] = [
                dict(r) for r in conn.execute(
                    "SELECT id, agent_id, caller_number, caller_name, called_number, call_direction, call_status, call_type, start_time, end_time, duration_seconds, talk_time_seconds, sentiment_score, intent_detected, ai_summary, created_at FROM call_sessions WHERE tenant_id = ? ORDER BY created_at DESC LIMIT 1000",
                    (tenant_id,),
                ).fetchall()
            ]
            export_data["recordings"] = [
                dict(r) for r in conn.execute(
                    "SELECT id, call_id, agent_id, file_path, file_size_bytes, duration_seconds, format, created_at FROM recordings WHERE tenant_id = ? ORDER BY created_at DESC LIMIT 1000",
                    (tenant_id,),
                ).fetchall()
            ]
            export_data["transcriptions"] = [
                dict(r) for r in conn.execute(
                    "SELECT id, call_id, stt_engine, language_code, confidence_score, created_at FROM transcriptions WHERE tenant_id = ? ORDER BY created_at DESC LIMIT 1000",
                    (tenant_id,),
                ).fetchall()
            ]
            export_data["customer_profiles"] = [
                dict(r) for r in conn.execute(
                    "SELECT id, external_id, phone, email, name, tags_json, created_at FROM customer_profiles WHERE tenant_id = ? ORDER BY created_at DESC LIMIT 1000",
                    (tenant_id,),
                ).fetchall()
            ]
            export_data["leads"] = [
                dict(r) for r in conn.execute(
                    "SELECT id, company_name, contact_name, first_name, last_name, phone, email, status, score, source, created_at FROM leads WHERE tenant_id = ? ORDER BY created_at DESC LIMIT 1000",
                    (tenant_id,),
                ).fetchall()
            ]

    record_count = sum(
        len(export_data.get(k, []))
        for k in ("calls", "recordings", "transcriptions", "customer_profiles", "leads")
    )

    return {
        "success": True,
        "user_id": user_id,
        "exported_at": datetime.now(UTC).isoformat(),
        "record_count": record_count,
        "data": export_data,
    }


@router.get("/health-score")
async def get_health_score(
    tenant_id: str = Depends(verify_tenant_access),
):
    return await lineage_service.get_data_health_score(tenant_id)


@router.post("/lineage")
async def record_lineage(
    data: LineageEntryCreate,
    tenant_id: str = Depends(verify_tenant_access),
):
    result = await lineage_service.record_lineage(
        tenant_id,
        source_table=data.source_table,
        source_id=data.source_id,
        target_table=data.target_table,
        target_id=data.target_id,
        operation=data.operation,
        metadata=data.metadata,
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Failed to record lineage"))
    return result
