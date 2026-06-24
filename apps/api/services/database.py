"""Database layer — re-exports from focused modules."""
from contextlib import contextmanager

from apps.api.services.db_calls import (
    create_call_session,
    dequeue_call,
    enqueue_call,
    get_billing_summary,
    get_call_session,
    get_order_status_db,
    get_pending_approvals_db,
    get_saas_dashboard_db,
    get_session_recordings_db,
    get_usage_stats,
    get_webhook_url_db,
    list_calls,
    log_audit_event,
    lookup_invoice_db,
    process_approval_db,
    rent_agent_db,
    update_call_status,
)
from apps.api.services.db_config import (
    DATABASE_URL,
    SQLITE_PATH,
    SQLITE_POOL_SIZE,
    SQLITE_TIMEOUT,
    USE_POSTGRES,
)
from apps.api.services.db_errors import (
    DatabaseError,
    NotFoundError,
    PoolNotAvailableError,
)
from apps.api.services.db_pool import (
    _get_sqlite_conn,
    close_pg_pool,
    db_context,
    decrypt_val,
    encrypt_val,
    get_pg_pool,
)
from apps.api.services.db_schema import (
    SCHEMA_SQL,
    SQLITE_SCHEMA_SQL,
    init_pg_schema,
    init_sqlite_schema,
)
from apps.api.services.db_tenants import (
    create_agent,
    create_agent_profile_db,
    create_tenant,
    delete_agent_db,
    get_agent_db,
    get_available_agents,
    get_tenant_by_api_key,
    get_tenant_db,
    get_tenant_settings_db,
    get_user_by_email_db,
    list_agents,
    list_tenants_db,
    update_agent_db,
    update_agent_status,
    update_tenant_settings_db,
    verify_tenant_api_key,
)


@contextmanager
def db_context_sync():
    if USE_POSTGRES:
        raise RuntimeError("db_context_sync not supported for PostgreSQL. Use async db_context instead.")
    conn = _get_sqlite_conn()
    try:
        yield conn
    finally:
        conn.close()


async def db_run_sync(db_func):
    """Run a synchronous DB function in a thread to avoid blocking the event loop."""
    import asyncio
    return await asyncio.to_thread(db_func)


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


