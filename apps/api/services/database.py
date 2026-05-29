"""Database layer — re-exports from focused modules."""
from apps.api.services.db_pool import (
    encrypt_val, decrypt_val, get_pg_pool, close_pg_pool, db_context,
    _get_sqlite_conn, _release_sqlite_conn, _get_sqlite_conn_async,
)
from apps.api.services.db_schema import (
    USE_POSTGRES, DATABASE_URL, SQLITE_PATH, SQLITE_POOL_SIZE, SQLITE_TIMEOUT,
    SCHEMA_SQL, SQLITE_SCHEMA_SQL,
    init_pg_schema, init_sqlite_schema,
)
from apps.api.services.db_tenants import (
    create_tenant, get_tenant_db, list_tenants_db,
    get_tenant_by_api_key, verify_tenant_api_key,
    get_user_by_email_db,
    get_tenant_settings_db, update_tenant_settings_db,
    create_agent, get_agent_db, list_agents,
    update_agent_status, update_agent_db, delete_agent_db,
    get_available_agents, create_agent_profile_db,
    _parse_skills,
)
from apps.api.services.db_calls import (
    create_call_session, get_call_session, update_call_status, list_calls,
    enqueue_call, dequeue_call,
    get_usage_stats, get_billing_summary,
    log_audit_event,
    get_saas_dashboard_db, rent_agent_db,
    get_session_recordings_db, get_pending_approvals_db,
    process_approval_db,
    get_webhook_url_db, lookup_invoice_db, get_order_status_db,
)
from apps.api.services.db_errors import (
    DatabaseError, NotFoundError, PoolNotAvailableError,
)

from contextlib import contextmanager


@contextmanager
def db_context_sync():
    if USE_POSTGRES:
        raise RuntimeError("db_context_sync not supported for PostgreSQL. Use async db_context instead.")
    conn = _get_sqlite_conn()
    try:
        yield conn
    finally:
        conn.close()


__all__ = [
    "db_context", "db_context_sync",
    "get_pg_pool", "close_pg_pool",
    "encrypt_val", "decrypt_val",
    "USE_POSTGRES", "DATABASE_URL", "SQLITE_PATH", "SQLITE_POOL_SIZE", "SQLITE_TIMEOUT",
    "SCHEMA_SQL", "SQLITE_SCHEMA_SQL",
    "init_pg_schema", "init_sqlite_schema",
    "create_tenant", "get_tenant_db", "list_tenants_db",
    "get_tenant_by_api_key", "verify_tenant_api_key",
    "get_user_by_email_db",
    "get_tenant_settings_db", "update_tenant_settings_db",
    "create_agent", "get_agent_db", "list_agents",
    "update_agent_status", "update_agent_db", "delete_agent_db",
    "get_available_agents", "create_agent_profile_db",
    "create_call_session", "get_call_session", "update_call_status", "list_calls",
    "enqueue_call", "dequeue_call",
    "get_usage_stats", "get_billing_summary",
    "log_audit_event",
    "get_saas_dashboard_db", "rent_agent_db",
    "get_session_recordings_db", "get_pending_approvals_db",
    "process_approval_db",
    "get_webhook_url_db", "lookup_invoice_db", "get_order_status_db",
    "DatabaseError", "NotFoundError", "PoolNotAvailableError",
]
