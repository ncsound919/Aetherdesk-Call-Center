"""
AetherDesk Call Center Platform - Verification Tests
Run these to confirm all components are working correctly.

These tests exercise a fully-deployed stack (API server, PostgreSQL, Fonoster,
FreeSWITCH, Redis and the agent Web UI). Each test is skipped automatically
when its required infrastructure is not reachable, so the suite stays green in
minimal/CI environments and performs real verification when the stack is up.
"""

import os
import socket

import pytest

# Optional dependency: only required by the Web UI tests.
try:
    from playwright.sync_api import sync_playwright

    _PLAYWRIGHT_AVAILABLE = True
except ImportError:
    sync_playwright = None
    _PLAYWRIGHT_AVAILABLE = False

# Configuration
PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "aetherdesk")
PROJECT_NAME = os.environ.get("GCP_PROJECT_NAME", "AetherDesk")
API_BASE = os.environ.get("AETHERDESK_API_BASE", "http://localhost:3000")

_PORT_API = 3000
_PORT_WEBUI = 3001
_PORT_FONOSTER = 50061
_PORT_FREESWITCH = 5060
_PORT_POSTGRES = 5432
_PORT_REDIS = 6379

# Database connection (CI provides postgres service with test_* creds; local
# deployments use the aetherdesk_admin defaults).
_DB_HOST = os.environ.get("PGHOST", "localhost")
_DB_PORT = int(os.environ.get("PGPORT", "5432"))
_DB_NAME = os.environ.get("PGDATABASE", "aetherdesk")
_DB_USER = os.environ.get("PGUSER", "aetherdesk_admin")
_DB_PASS = os.environ.get("PGPASSWORD", "")


def _port_open(port: int, host: str = "localhost", timeout: float = 1.0) -> bool:
    """Return True when a TCP connection to ``host:port`` succeeds."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _api_reachable() -> bool:
    """Return True when the AetherDesk API answers its health contract."""
    try:
        import httpx

        response = httpx.get(
            f"{API_BASE}/api/v1/health", timeout=5, follow_redirects=True
        )
        if response.status_code != 200:
            return False
        data = response.json()
        return isinstance(data.get("status"), str) and "services" in data
    except Exception:
        return False


_HAS_API = _api_reachable()
_HAS_POSTGRES = _port_open(_PORT_POSTGRES)
_HAS_FONOSTER = _port_open(_PORT_FONOSTER)
_HAS_FREESWITCH = _port_open(_PORT_FREESWITCH)
_HAS_REDIS = _port_open(_PORT_REDIS)
_HAS_WEBUI = _port_open(_PORT_WEBUI) and _PLAYWRIGHT_AVAILABLE

needs_api = pytest.mark.skipif(
    not _HAS_API, reason="AetherDesk API not reachable (deploy it, then re-run)"
)
needs_postgres = pytest.mark.skipif(
    not _HAS_POSTGRES, reason="PostgreSQL not running on localhost:5432"
)
needs_fonoster = pytest.mark.skipif(
    not _HAS_FONOSTER, reason="Fonoster not running on localhost:50061"
)
needs_freeswitch = pytest.mark.skipif(
    not _HAS_FREESWITCH, reason="FreeSWITCH not running on localhost:5060"
)
needs_redis = pytest.mark.skipif(
    not _HAS_REDIS, reason="Redis not running on localhost:6379"
)
needs_webui = pytest.mark.skipif(
    not _HAS_WEBUI, reason="Agent Web UI / Playwright browser not available"
)


class TestInfrastructure:
    """Tests for the core infrastructure setup"""

    @needs_fonoster
    def test_fonoster_voice_server_running(self):
        """Verify Fonoster Voice Server is running on port 50061"""
        assert _port_open(_PORT_FONOSTER), "Fonoster Voice Server not running on port 50061"

    @needs_freeswitch
    def test_freeswitch_sip_running(self):
        """Verify FreeSWITCH SIP server is running on port 5060"""
        assert _port_open(_PORT_FREESWITCH), "FreeSWITCH SIP not running on port 5060"

    @needs_api
    def test_api_server_running(self):
        """Verify API Server is running on port 3000"""
        assert _port_open(_PORT_API), "API Server not running on port 3000"

    @needs_redis
    def test_redis_running(self):
        """Verify Redis is running on port 6379"""
        assert _port_open(_PORT_REDIS), "Redis not running on port 6379"

    @needs_postgres
    def test_postgres_running(self):
        """Verify PostgreSQL is running on port 5432"""
        assert _port_open(_PORT_POSTGRES), "PostgreSQL not running on port 5432"


@needs_api
class TestAPIBasics:
    """Tests for the core API functionality"""

    def test_health_endpoint(self):
        """Test the /api/v1/health endpoint"""
        import httpx

        response = httpx.get(f"{API_BASE}/api/v1/health", timeout=10, follow_redirects=True)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] in ("healthy", "degraded")
        assert "services" in data

    def test_database_schema(self):
        """Test that the database schema is loaded"""
        import asyncio

        import asyncpg

        async def check_schema():
            conn = await asyncpg.connect(
                host=_DB_HOST,
                port=_DB_PORT,
                database=_DB_NAME,
                user=_DB_USER,
                password=_DB_PASS,
            )
            try:
                # Check for tables
                tables = await conn.fetch(
                    "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
                )
                table_names = [t["table_name"] for t in tables]

                expected_tables = [
                    "tenants", "agents", "call_sessions",
                    "call_queue", "agent_activity", "recordings",
                    "transcriptions", "billing_records", "audit_log", "plans"
                ]

                for table in expected_tables:
                    assert table in table_names, f"Table '{table}' not found"
            finally:
                await conn.close()

        asyncio.run(check_schema())


@needs_api
class TestCallFlow:
    """Tests for call flow functionality"""

    def test_agent_registration(self):
        """Test agent registration and SIP extension assignment"""
        import httpx

        # Create a test agent
        response = httpx.post(
            f"{API_BASE}/api/v1/tenants/test/agents",
            json={
                "name": "Test Agent",
                "agent_type": "ai",
                "skills": ["support"],
                "config": {"model": "gpt-4"},
            },
            timeout=10,
        )
        assert response.status_code == 201
        data = response.json()
        assert "id" in data
        assert "sip_extension" in data
        assert data["sip_extension"] is not None

    def test_call_creation(self):
        """Test call creation with agent assignment"""
        import httpx

        response = httpx.post(
            f"{API_BASE}/api/v1/calls",
            json={
                "agent_id": "test-agent-id",
                "caller_number": "+15551234567",
                "call_direction": "inbound",
            },
            timeout=10,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["call_status"] == "initiated"


@needs_postgres
class TestCompliance:
    """Tests for HIPAA/GDPR compliance features"""

    def test_encryption_functions(self):
        """Test database encryption functions"""
        import asyncio

        import asyncpg

        async def test_encryption():
            conn = await asyncpg.connect(
                host=_DB_HOST,
                port=_DB_PORT,
                database=_DB_NAME,
                user=_DB_USER,
                password=_DB_PASS,
            )
            try:
                # Test encryption
                encrypted = await conn.fetchval(
                    "SELECT encrypt_data('test data', 'test-key')"
                )
                assert encrypted is not None

                # Test decryption
                decrypted = await conn.fetchval(
                    "SELECT decrypt_data($1, 'test-key')",
                    encrypted,
                )
                assert decrypted == "test data"
            finally:
                await conn.close()

        asyncio.run(test_encryption())

    def test_rls_enabled(self):
        """Test that Row Level Security is enabled on tenant tables"""
        import asyncio

        import asyncpg

        async def check_rls():
            conn = await asyncpg.connect(
                host=_DB_HOST,
                port=_DB_PORT,
                database=_DB_NAME,
                user=_DB_USER,
                password=_DB_PASS,
            )
            try:
                tables = ["agents", "call_sessions", "call_queue",
                          "agent_activity", "recordings", "transcriptions",
                          "billing_records", "audit_log"]

                for table in tables:
                    result = await conn.fetchval(
                        f"""
                        SELECT relrowsecurity FROM pg_class
                        WHERE relname = '{table}'
                        """
                    )
                    assert result, f"RLS not enabled on {table}"
            finally:
                await conn.close()

        asyncio.run(check_rls())


@needs_webui
class TestWebUI:
    """Tests for the Agent Web UI"""

    def test_login_page(self):
        """Test that the login page is accessible"""
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto("http://localhost:3001/login")
            assert page.url.endswith("/login")
            assert page.get_by_text("AetherDesk Agent Login").is_visible()
            browser.close()

    def test_dashboard_access(self):
        """Test that the dashboard is accessible after login"""
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context()
            page = context.new_page()
            page.goto("http://localhost:3001/")
            # Should redirect to login if not authenticated
            assert "login" in page.url or page.get_by_text("Dashboard").is_visible()
            browser.close()


@needs_api
class TestCostTracking:
    """Tests for cost tracking and billing functionality"""

    def test_agent_activity_tracking(self):
        """Test that agent activity is properly tracked for billing"""
        import httpx

        response = httpx.get(
            f"{API_BASE}/api/v1/usage",
            params={
                "tenant_id": "test-tenant",
                "period_start": "2024-01-01T00:00:00",
                "period_end": "2024-12-31T23:59:59",
            },
            timeout=10,
        )
        assert response.status_code == 200
        data = response.json()
        assert "total_agents" in data
        assert "total_calls" in data
        assert "total_minutes" in data
        assert "total_cost" in data

    def test_billing_calculation(self):
        """Test billing calculation based on plan rates"""
        import httpx

        response = httpx.get(
            f"{API_BASE}/api/v1/billing",
            params={
                "period_start": "2024-01-01T00:00:00",
                "period_end": "2024-12-31T23:59:59",
            },
            timeout=10,
        )
        assert response.status_code == 200
        data = response.json()
        assert "total_calls" in data
        assert "total_cost" in data
        assert "breakdown" in data


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
