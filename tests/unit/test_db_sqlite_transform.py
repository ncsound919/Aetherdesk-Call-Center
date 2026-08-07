"""Unit tests for src/api/services/db_sqlite_transform.py."""

import sqlite3

from api.services.db_sqlite_transform import postgres_to_sqlite


class TestTypeTransformations:
    def test_uuid_primary_key_with_uuid_generate_v4(self):
        sql = "id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),"
        out = postgres_to_sqlite(sql)
        assert "id TEXT PRIMARY KEY" in out
        assert "uuid_generate_v4" not in out

    def test_uuid_primary_key_with_gen_random_uuid(self):
        sql = "id UUID PRIMARY KEY DEFAULT gen_random_uuid(),"
        out = postgres_to_sqlite(sql)
        assert "id TEXT PRIMARY KEY" in out
        assert "gen_random_uuid" not in out

    def test_plain_uuid(self):
        sql = "ref UUID REFERENCES tenants(id),"
        out = postgres_to_sqlite(sql)
        assert "ref TEXT" in out
        assert "REFERENCES tenants(id)" in out

    def test_timestamptz(self):
        assert postgres_to_sqlite("created_at TIMESTAMPTZ NOT NULL,") == (
            "created_at TEXT NOT NULL,"
        )

    def test_jsonb(self):
        assert postgres_to_sqlite("settings JSONB DEFAULT '{}',") == (
            "settings TEXT DEFAULT '{}',"
        )

    def test_varchar(self):
        assert postgres_to_sqlite("name VARCHAR(100) NOT NULL,") == (
            "name TEXT NOT NULL,"
        )
        assert postgres_to_sqlite("code VARCHAR(255),") == "code TEXT,"

    def test_decimal(self):
        assert postgres_to_sqlite("price DECIMAL(10, 2) DEFAULT 0,") == (
            "price REAL DEFAULT 0,"
        )

    def test_boolean_with_default(self):
        assert postgres_to_sqlite("active BOOLEAN DEFAULT TRUE,") == (
            "active INTEGER DEFAULT 1,"
        )
        assert postgres_to_sqlite("flag BOOLEAN DEFAULT FALSE,") == (
            "flag INTEGER DEFAULT 0,"
        )

    def test_boolean_not_null_default(self):
        assert postgres_to_sqlite(
            "is_active BOOLEAN NOT NULL DEFAULT FALSE,"
        ) == ("is_active INTEGER NOT NULL DEFAULT 0,")

    def test_plain_boolean(self):
        assert postgres_to_sqlite("is_ok BOOLEAN,") == "is_ok INTEGER,"


class TestExpressionTransformations:
    def test_now(self):
        assert postgres_to_sqlite("created_at TIMESTAMP DEFAULT NOW()") == (
            "created_at TIMESTAMP DEFAULT (datetime('now'))"
        )

    def test_gen_random_uuid_expression(self):
        assert postgres_to_sqlite(
            "DEFAULT gen_random_uuid()"
        ) == "DEFAULT (lower(hex(randomblob(16))))"

    def test_uuid_generate_v4_expression(self):
        assert postgres_to_sqlite(
            "DEFAULT uuid_generate_v4()"
        ) == "DEFAULT (lower(hex(randomblob(16))))"

    def test_true_false_literals(self):
        assert postgres_to_sqlite("WHERE is_active = TRUE AND deleted = FALSE") == (
            "WHERE is_active = 1 AND deleted = 0"
        )


class TestStatementStripping:
    def test_create_extension_stripped(self):
        sql = 'CREATE EXTENSION IF NOT EXISTS "uuid-ossp";\nCREATE TABLE t (id TEXT);'
        out = postgres_to_sqlite(sql)
        assert "CREATE EXTENSION" not in out
        assert "CREATE TABLE t (id TEXT);" in out

    def test_create_extension_plain_stripped(self):
        sql = "CREATE EXTENSION pgcrypto;\nCREATE TABLE t (id TEXT);"
        out = postgres_to_sqlite(sql)
        assert "CREATE EXTENSION" not in out

    def test_row_level_security_stripped(self):
        for directive in ("ENABLE", "DISABLE", "FORCE", "NO FORCE"):
            sql = (
                f"ALTER TABLE agents {directive} ROW LEVEL SECURITY;\n"
                "CREATE TABLE t (id TEXT);"
            )
            out = postgres_to_sqlite(sql)
            assert "ROW LEVEL SECURITY" not in out
            assert "CREATE TABLE t (id TEXT);" in out

    def test_set_client_min_messages_stripped(self):
        sql = "SET client_min_messages = warning;\nCREATE TABLE t (id TEXT);"
        out = postgres_to_sqlite(sql)
        assert "client_min_messages" not in out

    def test_grant_stripped(self):
        sql = "GRANT SELECT ON agents TO app_role;\nCREATE TABLE t (id TEXT);"
        out = postgres_to_sqlite(sql)
        assert "GRANT" not in out

    def test_revoke_stripped(self):
        sql = "REVOKE ALL ON agents FROM app_role;\nCREATE TABLE t (id TEXT);"
        out = postgres_to_sqlite(sql)
        assert "REVOKE" not in out

    def test_multiline_policy_stripped(self):
        sql = (
            "CREATE POLICY tenant_isolation_agents ON agents\n"
            "    USING (tenant_id = current_setting('app.current_tenant_id')::uuid);\n"
            "CREATE TABLE t (id TEXT);"
        )
        out = postgres_to_sqlite(sql)
        assert "CREATE POLICY" not in out
        assert "current_setting" not in out
        assert "CREATE TABLE t (id TEXT);" in out

    def test_drop_policy_stripped(self):
        sql = "DROP POLICY tenant_isolation_agents ON agents;\nCREATE TABLE t (id TEXT);"
        out = postgres_to_sqlite(sql)
        assert "DROP POLICY" not in out

    def test_dollar_quoted_function_stripped(self):
        sql = (
            "CREATE OR REPLACE FUNCTION encrypt_data(plaintext TEXT, key TEXT)\n"
            "RETURNS TEXT AS $$\n"
            "BEGIN\n"
            "    RETURN pgp_sym_encrypt(plaintext, key);\n"
            "END;\n"
            "$$ LANGUAGE plpgsql;\n"
            "CREATE TABLE t (id TEXT);"
        )
        out = postgres_to_sqlite(sql)
        assert "CREATE OR REPLACE FUNCTION" not in out
        assert "pgp_sym_encrypt" not in out
        assert "CREATE TABLE t (id TEXT);" in out

    def test_single_line_function_stripped(self):
        sql = (
            "CREATE FUNCTION add_one(x int) RETURNS int AS 'SELECT x + 1' "
            "LANGUAGE sql;\nCREATE TABLE t (id TEXT);"
        )
        out = postgres_to_sqlite(sql)
        assert "CREATE FUNCTION" not in out
        assert "CREATE TABLE t (id TEXT);" in out

    def test_trigger_stripped(self):
        sql = (
            "CREATE TRIGGER trg_tenants_updated BEFORE UPDATE ON tenants "
            "FOR EACH ROW EXECUTE FUNCTION update_updated_at();\n"
            "CREATE TABLE t (id TEXT);"
        )
        out = postgres_to_sqlite(sql)
        assert "CREATE TRIGGER" not in out
        assert "CREATE TABLE t (id TEXT);" in out

    def test_view_stripped(self):
        sql = (
            "CREATE OR REPLACE VIEW agent_performance AS\n"
            "SELECT a.id, a.name FROM agents a;\n"
            "CREATE TABLE t (id TEXT);"
        )
        out = postgres_to_sqlite(sql)
        assert "CREATE OR REPLACE VIEW" not in out
        assert "CREATE TABLE t (id TEXT);" in out

    def test_insert_block_stripped(self):
        sql = (
            "INSERT INTO plans (name) VALUES\n"
            "('Starter'),\n"
            "('Pro')\n"
            "ON CONFLICT (name) DO NOTHING;\n"
            "CREATE TABLE t (id TEXT);"
        )
        out = postgres_to_sqlite(sql)
        assert "INSERT INTO plans" not in out
        assert "CREATE TABLE t (id TEXT);" in out


class TestFullTableTransformation:
    def test_table_becomes_sqlite_compatible(self):
        sql = """
        CREATE TABLE IF NOT EXISTS plans (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            ref UUID,
            name VARCHAR(100) NOT NULL,
            description TEXT,
            price_per_hour DECIMAL(10, 2) NOT NULL DEFAULT 0,
            features JSONB DEFAULT '[]',
            is_active BOOLEAN DEFAULT TRUE,
            email_verified BOOLEAN DEFAULT FALSE,
            flag BOOLEAN,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        );
        """
        out = postgres_to_sqlite(sql)
        assert "id TEXT PRIMARY KEY" in out
        assert "ref TEXT" in out
        assert "name TEXT NOT NULL" in out
        assert "price_per_hour REAL NOT NULL DEFAULT 0" in out
        assert "features TEXT DEFAULT '[]'" in out
        assert "is_active INTEGER DEFAULT 1" in out
        assert "email_verified INTEGER DEFAULT 0" in out
        assert "flag INTEGER" in out
        assert "created_at TEXT DEFAULT (datetime('now'))" in out
        assert "updated_at TIMESTAMP DEFAULT (datetime('now'))" in out
        assert "UUID" not in out
        assert "JSONB" not in out
        assert "TIMESTAMPTZ" not in out
        assert "VARCHAR" not in out
        assert "DECIMAL" not in out
        assert "BOOLEAN" not in out

    def test_transformation_is_idempotent(self):
        sql = (
            "CREATE TABLE foo (\n"
            "    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),\n"
            "    active BOOLEAN DEFAULT TRUE,\n"
            "    created_at TIMESTAMPTZ DEFAULT NOW()\n"
            ");\n"
        )
        once = postgres_to_sqlite(sql)
        twice = postgres_to_sqlite(once)
        assert once == twice

    def test_executes_in_sqlite(self):
        from api.services.db_schema import SCHEMA_SQL

        conn = sqlite3.connect(":memory:")
        try:
            conn.executescript(postgres_to_sqlite(SCHEMA_SQL))
            conn.commit()
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            assert "tenants" in tables
            assert "users" in tables
            assert "agents" in tables
            assert "failover_tests" in tables
        finally:
            conn.close()
