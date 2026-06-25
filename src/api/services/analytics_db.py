"""
ClickHouse analytics database — high-volume call event storage and querying.

Replaces SQLite for call logs, CDR analysis, and real-time metrics.
ClickHouse is purpose-built for analytical workloads — call duration
distributions, agent utilization, SLA tracking at millions of rows.

Graceful degradation: if CLICKHOUSE_HOST is not set, all operations
are no-ops and the system falls back to SQLite/Postgres.
"""

import json
import logging
import os
from datetime import datetime

logger = logging.getLogger(__name__)

_client = None
_initialized = False


def is_clickhouse_enabled() -> bool:
    """Check if ClickHouse is configured."""
    return bool(os.getenv("CLICKHOUSE_HOST"))


def get_clickhouse():
    """Get or create ClickHouse client singleton."""
    global _client, _initialized
    if _client is not None:
        return _client
    if not is_clickhouse_enabled():
        return None
    try:
        import clickhouse_connect
        host = os.getenv("CLICKHOUSE_HOST", "localhost")
        port = int(os.getenv("CLICKHOUSE_PORT", "8123"))
        username = os.getenv("CLICKHOUSE_USER", "default")
        password = os.getenv("CLICKHOUSE_PASSWORD", "")
        database = os.getenv("CLICKHOUSE_DB", "aetherdesk")

        _client = clickhouse_connect.get_client(
            host=host,
            port=port,
            username=username,
            password=password,
            database=database,
        )
        if not _initialized:
            _init_schema(_client, database)
            _initialized = True
        logger.info(f"ClickHouse connected: {host}:{port}/{database}")
        return _client
    except ImportError:
        logger.warning("clickhouse-connect not installed — pip install clickhouse-connect")
        return None
    except Exception as exc:
        logger.warning(f"ClickHouse connection failed: {exc}")
        return None


def _init_schema(client, database: str):
    """Create the call_events table if it doesn't exist."""
    try:
        client.command(f"CREATE DATABASE IF NOT EXISTS {database}")
        client.command("""
            CREATE TABLE IF NOT EXISTS call_events (
                call_id String,
                tenant_id String,
                agent_id String,
                direction Enum8('inbound' = 1, 'outbound' = 2),
                caller String,
                called String,
                started_at DateTime64(3),
                ended_at Nullable(DateTime64(3)),
                duration_seconds Float64 DEFAULT 0,
                intent LowCardinality(String) DEFAULT 'unknown',
                status LowCardinality(String) DEFAULT 'completed',
                satisfaction_score Nullable(Float64),
                tokens_used UInt32 DEFAULT 0,
                cost_cents UInt32 DEFAULT 0,
                metadata String DEFAULT '{}',
                INDEX idx_tenant tenant_id TYPE bloom_filter GRANULARITY 4,
                INDEX idx_agent agent_id TYPE bloom_filter GRANULARITY 4,
                INDEX idx_intent intent TYPE set(100) GRANULARITY 4
            ) ENGINE = MergeTree()
            PARTITION BY toYYYYMM(started_at)
            ORDER BY (tenant_id, started_at)
        """)
        logger.info("ClickHouse schema initialized: call_events table ready")
    except Exception as exc:
        logger.warning(f"ClickHouse schema init failed: {exc}")


def record_call_event(
    call_id: str,
    tenant_id: str,
    agent_id: str,
    direction: str,
    caller: str,
    called: str,
    started_at: datetime,
    ended_at: datetime | None = None,
    duration_seconds: float = 0,
    intent: str = "unknown",
    status: str = "completed",
    satisfaction_score: float | None = None,
    tokens_used: int = 0,
    cost_cents: int = 0,
    metadata: dict | None = None,
):
    """Insert a call event into ClickHouse."""
    ch = get_clickhouse()
    if not ch:
        return False
    event = [
        call_id,
        tenant_id,
        agent_id,
        direction,
        caller,
        called,
        started_at,
        ended_at,
        duration_seconds,
        intent,
        status,
        satisfaction_score,
        tokens_used,
        cost_cents,
        json.dumps(metadata or {}),
    ]
    try:
        ch.insert(
            "call_events",
            [event],
            column_names=[
                "call_id", "tenant_id", "agent_id", "direction",
                "caller", "called", "started_at", "ended_at",
                "duration_seconds", "intent", "status",
                "satisfaction_score", "tokens_used", "cost_cents",
                "metadata",
            ],
        )
        return True
    except Exception as exc:
        logger.warning(f"ClickHouse insert failed: {exc}")
        return False


def query_call_stats(
    tenant_id: str,
    start_date: datetime,
    end_date: datetime,
) -> dict:
    """Query call statistics for a tenant in a date range."""
    ch = get_clickhouse()
    if not ch:
        return {"mock": True, "calls": 0, "minutes": 0}
    try:
        result = ch.query(
            """
            SELECT
                count() as total_calls,
                sum(duration_seconds) / 60.0 as total_minutes,
                avg(duration_seconds) as avg_duration,
                countIf(status = 'completed') as completed,
                countIf(status = 'missed') as missed,
                avg(satisfaction_score) as avg_satisfaction,
                sum(tokens_used) as total_tokens,
                sum(cost_cents) as total_cost_cents
            FROM call_events
            WHERE tenant_id = {tid:String}
              AND started_at >= {start:DateTime64(3)}
              AND started_at <= {end:DateTime64(3)}
            """,
            parameters={
                "tid": tenant_id,
                "start": start_date,
                "end": end_date,
            },
        )
        row = result.first_row
        return {
            "total_calls": row[0],
            "total_minutes": round(row[1] or 0, 2),
            "avg_duration": round(row[2] or 0, 2),
            "completed": row[3],
            "missed": row[4],
            "avg_satisfaction": round(row[5] or 0, 2),
            "total_tokens": row[6],
            "total_cost_cents": row[7],
        }
    except Exception as exc:
        logger.warning(f"ClickHouse query failed: {exc}")
        return {"error": str(exc)}


def query_intent_distribution(
    tenant_id: str,
    start_date: datetime,
    end_date: datetime,
) -> list[dict]:
    """Get intent distribution for a tenant."""
    ch = get_clickhouse()
    if not ch:
        return []
    try:
        result = ch.query(
            """
            SELECT intent, count() as cnt
            FROM call_events
            WHERE tenant_id = {tid:String}
              AND started_at >= {start:DateTime64(3)}
              AND started_at <= {end:DateTime64(3)}
            GROUP BY intent
            ORDER BY cnt DESC
            """,
            parameters={
                "tid": tenant_id,
                "start": start_date,
                "end": end_date,
            },
        )
        return [{"intent": r[0], "count": r[1]} for r in result.result_rows]
    except Exception as exc:
        logger.warning(f"ClickHouse intent query failed: {exc}")
        return []


def query_agent_performance(
    tenant_id: str,
    start_date: datetime,
    end_date: datetime,
) -> list[dict]:
    """Get per-agent performance stats."""
    ch = get_clickhouse()
    if not ch:
        return []
    try:
        result = ch.query(
            """
            SELECT
                agent_id,
                count() as total_calls,
                avg(duration_seconds) as avg_duration,
                avg(satisfaction_score) as avg_satisfaction,
                sum(cost_cents) as total_cost_cents
            FROM call_events
            WHERE tenant_id = {tid:String}
              AND started_at >= {start:DateTime64(3)}
              AND started_at <= {end:DateTime64(3)}
            GROUP BY agent_id
            ORDER BY total_calls DESC
            """,
            parameters={
                "tid": tenant_id,
                "start": start_date,
                "end": end_date,
            },
        )
        return [
            {
                "agent_id": r[0],
                "total_calls": r[1],
                "avg_duration": round(r[2] or 0, 2),
                "avg_satisfaction": round(r[3] or 0, 2),
                "total_cost_cents": r[4],
            }
            for r in result.result_rows
        ]
    except Exception as exc:
        logger.warning(f"ClickHouse agent query failed: {exc}")
        return []


def query_hourly_volume(
    tenant_id: str,
    start_date: datetime,
    end_date: datetime,
) -> list[dict]:
    """Get hourly call volume for time-series charts."""
    ch = get_clickhouse()
    if not ch:
        return []
    try:
        result = ch.query(
            """
            SELECT
                toStartOfHour(started_at) as hour,
                count() as calls,
                avg(duration_seconds) as avg_duration
            FROM call_events
            WHERE tenant_id = {tid:String}
              AND started_at >= {start:DateTime64(3)}
              AND started_at <= {end:DateTime64(3)}
            GROUP BY hour
            ORDER BY hour
            """,
            parameters={
                "tid": tenant_id,
                "start": start_date,
                "end": end_date,
            },
        )
        return [
            {
                "hour": r[0].isoformat() if hasattr(r[0], "isoformat") else str(r[0]),
                "calls": r[1],
                "avg_duration": round(r[2] or 0, 2),
            }
            for r in result.result_rows
        ]
    except Exception as exc:
        logger.warning(f"ClickHouse hourly query failed: {exc}")
        return []
