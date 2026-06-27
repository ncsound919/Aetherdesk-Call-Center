"""SQLite schema transformation utilities.

Converts the canonical PostgreSQL schema (the source of truth) into a
SQLite-compatible schema at runtime. This is necessary because the legacy
SQLITE_SCHEMA_SQL in db_schema.py was hand-rolled and accumulated dozens
of Postgres-only types that fail when executed against SQLite.

Transformations applied:
- `UUID PRIMARY KEY DEFAULT uuid_generate_v4()` -> `TEXT PRIMARY KEY`
- `TIMESTAMPTZ [DEFAULT NOW()]` -> `TEXT [DEFAULT (datetime('now'))]`
- `JSONB [DEFAULT '{}']` -> `TEXT [DEFAULT '{}']`
- `VARCHAR(n)` -> `TEXT`
- `BOOLEAN` -> `INTEGER`
- `DECIMAL(p,s)` -> `REAL`
- `gen_random_uuid()` / `uuid_generate_v4()` -> `(lower(hex(randomblob(16))))`
- `NOW()` -> `(datetime('now'))`
- `TRUE` -> `1`, `FALSE` -> `0`
- Strip `CREATE EXTENSION`, `ALTER TABLE ... ENABLE ROW LEVEL SECURITY`,
  `CREATE POLICY ... ;`, `GRANT`, `REVOKE` statements (Postgres-only constructs)
"""
from __future__ import annotations

import re


_POSTGRES_TYPE_MAP = [
    (re.compile(r'\bUUID\s+PRIMARY\s+KEY\s+DEFAULT\s+uuid_generate_v4\(\)', re.IGNORECASE), 'TEXT PRIMARY KEY'),
    (re.compile(r'\bUUID\b', re.IGNORECASE), 'TEXT'),
    (re.compile(r'\bTIMESTAMPTZ\b', re.IGNORECASE), 'TEXT'),
    (re.compile(r'\bJSONB\b', re.IGNORECASE), 'TEXT'),
    (re.compile(r'\bVARCHAR\s*\(\s*\d+\s*\)', re.IGNORECASE), 'TEXT'),
    (re.compile(r'\bDECIMAL\s*\(\s*\d+\s*,\s*\d+\s*\)', re.IGNORECASE), 'REAL'),
    (re.compile(r'\bBOOLEAN\s+NOT\s+NULL\s+DEFAULT\s+(\S+)', re.IGNORECASE), r'INTEGER NOT NULL DEFAULT \1'),
    (re.compile(r'\bBOOLEAN\s+DEFAULT\s+(\S+)', re.IGNORECASE), r'INTEGER DEFAULT \1'),
    (re.compile(r'\bBOOLEAN\b', re.IGNORECASE), 'INTEGER'),
]

# Postgres-only statements / clauses to strip.
# NOTE: multi-line blocks (CREATE POLICY, CREATE FUNCTION) must be stripped
# wholesale because their bodies contain Postgres-only syntax.
_POLICY_BLOCK = re.compile(
    r'CREATE\s+POLICY\b[^;]*;',
    re.IGNORECASE | re.DOTALL,
)
_FUNCTION_BLOCK = re.compile(
    r'CREATE\s+(OR\s+REPLACE\s+)?FUNCTION\b.*?\$\$.*?\$\$[^;]*;',
    re.IGNORECASE | re.DOTALL,
)
_FUNCTION_BLOCK_PLAIN = re.compile(
    r'CREATE\s+(OR\s+REPLACE\s+)?FUNCTION\b[^;]*;\s*\n',
    re.IGNORECASE | re.DOTALL,
)
_TRIGGER_BLOCK = re.compile(
    r'CREATE\s+(OR\s+REPLACE\s+)?TRIGGER\b[^;]*;',
    re.IGNORECASE | re.DOTALL,
)
_VIEW_BLOCK = re.compile(
    r'CREATE\s+(OR\s+REPLACE\s+)?VIEW\b[^;]*;',
    re.IGNORECASE | re.DOTALL,
)
# Seed/INSERT statements: strip entirely from the schema (seed data
# belongs in a separate seed.sql, not the schema definition).
_INSERT_BLOCK = re.compile(
    r'INSERT\s+INTO\s+\w+\s*[^;]*;',
    re.IGNORECASE | re.DOTALL,
)

# Line-level stripping for remaining single-line Postgres-only constructs.
_STRIP_LINES = [
    re.compile(r'CREATE\s+EXTENSION\s+IF\s+NOT\s+EXISTS', re.IGNORECASE),
    re.compile(r'CREATE\s+EXTENSION\s+', re.IGNORECASE),
    re.compile(r'\bSET\s+client_min_messages\b', re.IGNORECASE),
    re.compile(r'ALTER\s+TABLE\s+\w+\s+ENABLE\s+ROW\s+LEVEL\s+SECURITY', re.IGNORECASE),
    re.compile(r'ALTER\s+TABLE\s+\w+\s+DISABLE\s+ROW\s+LEVEL\s+SECURITY', re.IGNORECASE),
    re.compile(r'ALTER\s+TABLE\s+\w+\s+(NO\s+)?FORCE\s+ROW\s+LEVEL\s+SECURITY', re.IGNORECASE),
    re.compile(r'^\s*GRANT\s+', re.IGNORECASE),
    re.compile(r'^\s*REVOKE\s+', re.IGNORECASE),
    re.compile(r'^\s*CREATE\s+POLICY\b', re.IGNORECASE),
    re.compile(r'^\s*DROP\s+POLICY\b', re.IGNORECASE),
]


def postgres_to_sqlite(sql: str) -> str:
    """Transform Postgres schema SQL to SQLite-compatible SQL."""
    # Strip CREATE POLICY ... ; blocks first (multi-line)
    sql = _POLICY_BLOCK.sub('', sql)
    sql = _FUNCTION_BLOCK.sub('', sql)
    sql = _FUNCTION_BLOCK_PLAIN.sub('', sql)
    sql = _TRIGGER_BLOCK.sub('', sql)
    sql = _VIEW_BLOCK.sub('', sql)
    sql = _INSERT_BLOCK.sub('', sql)

    # Drop remaining Postgres-only constructs line-by-line
    cleaned_lines = []
    for line in sql.split('\n'):
        if any(p.search(line) for p in _STRIP_LINES):
            continue
        cleaned_lines.append(line)
    sql = '\n'.join(cleaned_lines)

    # Apply type transformations
    for pattern, replacement in _POSTGRES_TYPE_MAP:
        sql = pattern.sub(replacement, sql)

    # Postgres-specific DEFAULT expressions -> SQLite equivalents
    sql = re.sub(r'\bNOW\(\)', "(datetime('now'))", sql, flags=re.IGNORECASE)
    sql = re.sub(r'\bgen_random_uuid\(\)', "(lower(hex(randomblob(16))))", sql, flags=re.IGNORECASE)
    sql = re.sub(r'\buuid_generate_v4\(\)', "(lower(hex(randomblob(16))))", sql, flags=re.IGNORECASE)
    sql = re.sub(r'\bFALSE\b', '0', sql, flags=re.IGNORECASE)
    sql = re.sub(r'\bTRUE\b', '1', sql, flags=re.IGNORECASE)

    return sql
