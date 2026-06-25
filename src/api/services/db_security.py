import json
import uuid
from datetime import UTC, datetime

import structlog

from api.services.db_config import USE_POSTGRES
from api.services.db_pool import _get_sqlite_conn, get_pg_pool

logger = structlog.get_logger()


async def create_pen_test_scan_db(tenant_id, target_url, severity="medium"):
    scan_id = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()
    findings = json.dumps([])
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            await pool.execute("""
                INSERT INTO pen_test_scans (id, tenant_id, target_url, status, findings_json, severity, started_at)
                VALUES ($1, $2, $3, 'running', $4, $5, NOW())
            """, scan_id, tenant_id, target_url, findings, severity)
            row = await pool.fetchrow("SELECT * FROM pen_test_scans WHERE id = $1", scan_id)
            return dict(row) if row else None
    else:
        conn = _get_sqlite_conn()
        try:
            conn.execute("""
                INSERT INTO pen_test_scans (id, tenant_id, target_url, status, findings_json, severity, started_at)
                VALUES (?, ?, ?, 'running', ?, ?, ?)
            """, (scan_id, tenant_id, target_url, findings, severity, now))
            conn.commit()
            row = conn.execute("SELECT * FROM pen_test_scans WHERE id = ?", (scan_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


async def update_pen_test_scan_db(scan_id, status, findings, completed_at=None):
    findings_json = json.dumps(findings) if isinstance(findings, list) else findings
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            if completed_at:
                await pool.execute("""
                    UPDATE pen_test_scans SET status = $1, findings_json = $2::jsonb, completed_at = $3 WHERE id = $4
                """, status, findings_json, completed_at, scan_id)
            else:
                await pool.execute("""
                    UPDATE pen_test_scans SET status = $1, findings_json = $2::jsonb WHERE id = $3
                """, status, findings_json, scan_id)
            row = await pool.fetchrow("SELECT * FROM pen_test_scans WHERE id = $1", scan_id)
            return dict(row) if row else None
    else:
        conn = _get_sqlite_conn()
        try:
            if completed_at:
                conn.execute("""
                    UPDATE pen_test_scans SET status = ?, findings_json = ?, completed_at = ? WHERE id = ?
                """, (status, findings_json, completed_at, scan_id))
            else:
                conn.execute("""
                    UPDATE pen_test_scans SET status = ?, findings_json = ? WHERE id = ?
                """, (status, findings_json, scan_id))
            conn.commit()
            row = conn.execute("SELECT * FROM pen_test_scans WHERE id = ?", (scan_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


async def list_pen_test_scans_db(tenant_id):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            rows = await pool.fetch("SELECT * FROM pen_test_scans WHERE tenant_id = $1 ORDER BY started_at DESC", tenant_id)
            return [dict(r) for r in rows]
    else:
        conn = _get_sqlite_conn()
        try:
            rows = conn.execute("SELECT * FROM pen_test_scans WHERE tenant_id = ? ORDER BY started_at DESC", (tenant_id,)).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


async def get_pen_test_scan_db(scan_id):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            row = await pool.fetchrow("SELECT * FROM pen_test_scans WHERE id = $1", scan_id)
            return dict(row) if row else None
    else:
        conn = _get_sqlite_conn()
        try:
            row = conn.execute("SELECT * FROM pen_test_scans WHERE id = ?", (scan_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


async def create_waf_event_db(tenant_id, rule_id, action, source_ip, request_path):
    event_id = str(uuid.uuid4())
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            await pool.execute("""
                INSERT INTO waf_events (id, tenant_id, rule_id, action, source_ip, request_path, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, NOW())
            """, event_id, tenant_id, rule_id, action, source_ip, request_path)
            row = await pool.fetchrow("SELECT * FROM waf_events WHERE id = $1", event_id)
            return dict(row) if row else None
    else:
        conn = _get_sqlite_conn()
        try:
            now = datetime.now(UTC).isoformat()
            conn.execute("""
                INSERT INTO waf_events (id, tenant_id, rule_id, action, source_ip, request_path, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (event_id, tenant_id, rule_id, action, source_ip, request_path, now))
            conn.commit()
            row = conn.execute("SELECT * FROM waf_events WHERE id = ?", (event_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


async def list_waf_events_db(tenant_id, limit=100):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            rows = await pool.fetch("SELECT * FROM waf_events WHERE tenant_id = $1 ORDER BY created_at DESC LIMIT $2", tenant_id, limit)
            return [dict(r) for r in rows]
    else:
        conn = _get_sqlite_conn()
        try:
            rows = conn.execute("SELECT * FROM waf_events WHERE tenant_id = ? ORDER BY created_at DESC LIMIT ?", (tenant_id, limit)).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


async def set_data_classification_db(tenant_id, schema_name, table_name, column_name, sensitivity, description=None):
    class_id = str(uuid.uuid4())
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            await pool.execute("""
                INSERT INTO data_classification (id, tenant_id, schema_name, table_name, column_name, sensitivity, description)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT (tenant_id, schema_name, table_name, column_name)
                DO UPDATE SET sensitivity = $6, description = $7
            """, class_id, tenant_id, schema_name, table_name, column_name, sensitivity, description)
            row = await pool.fetchrow("SELECT * FROM data_classification WHERE id = $1", class_id)
            return dict(row) if row else None
    else:
        conn = _get_sqlite_conn()
        try:
            existing = conn.execute(
                "SELECT id FROM data_classification WHERE tenant_id = ? AND schema_name = ? AND table_name = ? AND column_name = ?",
                (tenant_id, schema_name, table_name, column_name)
            ).fetchone()
            if existing:
                conn.execute(
                    "UPDATE data_classification SET sensitivity = ?, description = ? WHERE id = ?",
                    (sensitivity, description, existing["id"])
                )
                row_id = existing["id"]
            else:
                conn.execute(
                    "INSERT INTO data_classification (id, tenant_id, schema_name, table_name, column_name, sensitivity, description) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (class_id, tenant_id, schema_name, table_name, column_name, sensitivity, description)
                )
                row_id = class_id
            conn.commit()
            row = conn.execute("SELECT * FROM data_classification WHERE id = ?", (row_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


async def get_data_classification_db(tenant_id):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            rows = await pool.fetch("SELECT * FROM data_classification WHERE tenant_id = $1 ORDER BY schema_name, table_name, column_name", tenant_id)
            return [dict(r) for r in rows]
    else:
        conn = _get_sqlite_conn()
        try:
            rows = conn.execute("SELECT * FROM data_classification WHERE tenant_id = ? ORDER BY schema_name, table_name, column_name", (tenant_id,)).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


async def create_rbac_audit_result_db(tenant_id, role, resource, action, expected, actual, passed):
    audit_id = str(uuid.uuid4())
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            await pool.execute("""
                INSERT INTO rbac_audit_results (id, tenant_id, role, resource, action, expected, actual, passed, tested_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW())
            """, audit_id, tenant_id, role, resource, action, expected, actual, passed)
            row = await pool.fetchrow("SELECT * FROM rbac_audit_results WHERE id = $1", audit_id)
            return dict(row) if row else None
    else:
        conn = _get_sqlite_conn()
        try:
            now = datetime.now(UTC).isoformat()
            conn.execute("""
                INSERT INTO rbac_audit_results (id, tenant_id, role, resource, action, expected, actual, passed, tested_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (audit_id, tenant_id, role, resource, action, expected, actual, 1 if passed else 0, now))
            conn.commit()
            row = conn.execute("SELECT * FROM rbac_audit_results WHERE id = ?", (audit_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


async def list_rbac_audit_results_db(tenant_id):
    if USE_POSTGRES:
        pool = await get_pg_pool()
        if pool:
            rows = await pool.fetch("SELECT * FROM rbac_audit_results WHERE tenant_id = $1 ORDER BY tested_at DESC", tenant_id)
            return [dict(r) for r in rows]
    else:
        conn = _get_sqlite_conn()
        try:
            rows = conn.execute("SELECT * FROM rbac_audit_results WHERE tenant_id = ? ORDER BY tested_at DESC", (tenant_id,)).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()
