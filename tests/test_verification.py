"""
AetherDesk Call Center Platform - Verification Tests
Run these to confirm all components are working correctly.
"""

import pytest
from playwright.sync_api import sync_playwright
import os
import tempfile
import shutil

# Configuration
PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "aetherdesk")
PROJECT_NAME = os.environ.get("GCP_PROJECT_NAME", "AetherDesk")


class TestInfrastructure:
    """Tests for the core infrastructure setup"""

    def test_fonoster_voice_server_running(self):
        """Verify Fonoster Voice Server is running on port 50061"""
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        result = sock.connect_ex(('localhost', 50061))
        sock.close()
        assert result == 0, "Fonoster Voice Server not running on port 50061"

    def test_freeswitch_sip_running(self):
        """Verify FreeSWITCH SIP server is running on port 5060"""
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        result = sock.connect_ex(('localhost', 5060))
        sock.close()
        assert result == 0, "FreeSWITCH SIP not running on port 5060"

    def test_api_server_running(self):
        """Verify API Server is running on port 3000"""
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        result = sock.connect_ex(('localhost', 3000))
        sock.close()
        assert result == 0, "API Server not running on port 3000"

    def test_redis_running(self):
        """Verify Redis is running on port 6379"""
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        result = sock.connect_ex(('localhost', 6379))
        sock.close()
        assert result == 0, "Redis not running on port 6379"

    def test_postgres_running(self):
        """Verify PostgreSQL is running on port 5432"""
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        result = sock.connect_ex(('localhost', 5432))
        sock.close()
        assert result == 0, "PostgreSQL not running on port 5432"


class TestAPIBasics:
    """Tests for the core API functionality"""

    def test_health_endpoint(self):
        """Test the /health endpoint"""
        import httpx
        response = httpx.get("http://localhost:3000/health", timeout=10)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "services" in data

    def test_database_schema(self):
        """Test that the database schema is loaded"""
        import asyncpg
        import asyncio

        async def check_schema():
            conn = await asyncpg.connect(
                host="localhost",
                port=5432,
                database="aetherdesk",
                user="aetherdesk_admin"
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


class TestCallFlow:
    """Tests for call flow functionality"""

    def test_agent_registration(self):
        """Test agent registration and SIP extension assignment"""
        import httpx

        # Create a test agent
        response = httpx.post(
            "http://localhost:3000/api/v1/tenants/test/agents",
            json={
                "name": "Test Agent",
                "type": "ai",
                "skills": ["support"],
                "config": {"model": "gpt-4"}
            },
            timeout=10
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
            "http://localhost:3000/api/v1/calls",
            json={
                "agent_id": "test-agent-id",
                "caller_number": "+15551234567",
                "call_direction": "inbound"
            },
            timeout=10
        )
        assert response.status_code == 201
        data = response.json()
        assert data["call_status"] == "initiated"


class TestCompliance:
    """Tests for HIPAA/GDPR compliance features"""

    def test_encryption_functions(self):
        """Test database encryption functions"""
        import asyncpg
        import asyncio

        async def test_encryption():
            conn = await asyncpg.connect(
                host="localhost",
                port=5432,
                database="aetherdesk",
                user="aetherdesk_admin"
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
                    encrypted
                )
                assert decrypted == "test data"
            finally:
                await conn.close()

        asyncio.run(test_encryption())

    def test_rls_enabled(self):
        """Test that Row Level Security is enabled on tenant tables"""
        import asyncpg
        import asyncio

        async def check_rls():
            conn = await asyncpg.connect(
                host="localhost",
                port=5432,
                database="aetherdesk",
                user="aetherdesk_admin"
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


class TestCostTracking:
    """Tests for cost tracking and billing functionality"""

    def test_agent_activity_tracking(self):
        """Test that agent activity is properly tracked for billing"""
        import httpx

        response = httpx.get(
            "http://localhost:3000/api/v1/usage",
            params={
                "tenant_id": "test-tenant",
                "period_start": "2024-01-01T00:00:00",
                "period_end": "2024-12-31T23:59:59"
            },
            timeout=10
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
            "http://localhost:3000/api/v1/billing",
            params={
                "period_start": "2024-01-01T00:00:00",
                "period_end": "2024-12-31T23:59:59"
            },
            timeout=10
        )
        assert response.status_code == 200
        data = response.json()
        assert "total_calls" in data
        assert "total_cost" in data
        assert "breakdown" in data


if __name__ == "__main__":
    pytest.main([__file__, "-v"])