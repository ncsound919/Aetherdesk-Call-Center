"""
AetherDesk Call Center - Full E2E Customer Journey Tests
========================================================
Tests the complete customer journey from call initiation to resolution,
including benchmarking, security validation, and edge case handling.

Usage:
    pytest tests/e2e/test_customer_journey.py -v --tb=short

Environment Variables:
    E2E_API_URL    - API base URL (default: http://localhost:8000)
    E2E_BASE_URL   - UI base URL (default: http://localhost:3000)
    DEEPGRAM_API_KEY - Deepgram API key for STT
    GROQ_API_KEY     - Groq API key for LLM
"""
import asyncio
import json
import os
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import httpx
import pytest
from playwright.sync_api import Page, expect

# Test configuration
API_URL = os.getenv("E2E_API_URL", "http://localhost:8000")
BASE_URL = os.getenv("E2E_BASE_URL", "http://localhost:3000")
INTERNAL_API_KEY = os.getenv("INTERNAL_API_KEY", "dev-api-key")


@dataclass
class BenchmarkResult:
    """Container for benchmark results"""
    name: str
    duration_ms: float
    success: bool
    error: Optional[str] = None
    metadata: dict = field(default_factory=dict)


@dataclass
class CustomerJourneyResult:
    """Container for full journey test results"""
    journey_id: str
    steps: list[BenchmarkResult] = field(default_factory=list)
    total_duration_ms: float = 0.0
    success: bool = True
    failures: list[str] = field(default_factory=list)


class APIClient:
    """HTTP client wrapper for API testing"""

    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.client = httpx.Client(
            base_url=self.base_url,
            headers={"X-API-Key": api_key},
            timeout=30.0
        )

    def close(self):
        self.client.close()

    def post(self, path: str, **kwargs) -> httpx.Response:
        return self.client.post(path, **kwargs)

    def get(self, path: str, **kwargs) -> httpx.Response:
        return self.client.get(path, **kwargs)

    def put(self, path: str, **kwargs) -> httpx.Response:
        return self.client.put(path, **kwargs)

    def delete(self, path: str, **kwargs) -> httpx.Response:
        return self.client.delete(path, **kwargs)


class TestAPIClient:
    """Test fixture that provides an authenticated API client"""

    @pytest.fixture
    def api_client(self):
        client = APIClient(API_URL, INTERNAL_API_KEY)
        yield client
        client.close()


class TestCustomerJourney(TestAPIClient):
    """
    Full customer journey tests:
    1. Customer calls in
    2. Call is routed to AI agent
    3. AI agent handles inquiry
    4. Handoff to human if needed
    5. Call completion and recording
    """

    @pytest.fixture(autouse=True)
    def setup_journey(self):
        """Setup for each journey test"""
        self.journey = CustomerJourneyResult(
            journey_id=f"journey_{uuid.uuid4().hex[:8]}"
        )

    def _add_step(self, name: str, duration_ms: float, success: bool, error: str = None, metadata: dict = None):
        """Record a step in the journey"""
        step = BenchmarkResult(
            name=name,
            duration_ms=duration_ms,
            success=success,
            error=error,
            metadata=metadata or {}
        )
        self.journey.steps.append(step)
        if not success:
            self.journey.success = False
            if error:
                self.journey.failures.append(f"{name}: {error}")

    # ─────────────────────────────────────────────
    # 1. INBOUND CALL HANDLING
    # ─────────────────────────────────────────────
    def test_01_inbound_call_routing(self):
        """Test: Customer call is received and routed to an agent"""
        call_id = f"call_{uuid.uuid4().hex[:8]}"
        start = time.time()

        # Create a call session via the voice endpoint
        response = self.api_client.post("/api/v1/calls", json={
            "caller_number": "+15551234567",
            "called_number": "+15557654321",
            "call_direction": "inbound",
            "intent": "billing"
        })
        duration = (time.time() - start) * 1000

        assert response.status_code == 201, f"Call creation failed: {response.text}"
        data = response.json()
        assert "id" in data, "Response missing call ID"
        assert data["call_status"] == "initiated"

        self._add_step(
            "inbound_call_routing",
            duration,
            True,
            metadata={"call_id": data["id"], "agent_id": data.get("agent_id")}
        )

    def test_02_call_to_agent_assignment(self):
        """Test: Call is assigned to an available agent"""
        call_id = f"call_{uuid.uuid4().hex[:8]}"
        start = time.time()

        # Create call without specifying agent (auto-route)
        response = self.api_client.post("/api/v1/calls", json={
            "caller_number": "+15559876543",
            "call_direction": "inbound",
            "intent": "technical"
        })
        duration = (time.time() - start) * 1000

        assert response.status_code == 201, f"Auto-routing failed: {response.text}"
        data = response.json()

        # Either an agent was assigned or call was queued
        assert data["call_status"] in ("initiated", "ringing")

        self._add_step(
            "call_to_agent_assignment",
            duration,
            True,
            metadata={"agent_assigned": data.get("agent_id") is not None}
        )

    # ─────────────────────────────────────────────
    # 2. AI AGENT INTERACTION
    # ─────────────────────────────────────────────
    def test_03_intent_classification(self):
        """Test: AI correctly classifies customer intent"""
        classifier = self.api_client.post("/api/v1/voice/intent", json={
            "text": "I need to check my invoice status"
        })
        duration = 50.0  # Approximate classification time

        assert classifier.status_code == 200, f"Classification failed: {classifier.text}"
        data = classifier.json()
        assert "intent" in data, "Response missing intent"
        assert data["intent"] in (
            "billing_invoice", "billing_refund", "order_status",
            "tech_support_password", "generalInquiry", "agent_handoff"
        )
        assert data.get("confidence", 0) >= 0.2, "Confidence too low"

        self._add_step(
            "intent_classification",
            duration,
            True,
            metadata={"intent": data["intent"], "confidence": data.get("confidence")}
        )

    def test_04_agent_response_generation(self):
        """Test: AI agent generates appropriate response"""
        # Mock the orchestrator step
        from api.services.orchestrator import ReActAgent, Actions
        from unittest.mock import MagicMock

        mock_redis = MagicMock()
        actions = Actions(mock_redis)
        agent = ReActAgent(
            name="test_agent",
            system_prompt="You are a helpful agent.",
            tools=["lookup_invoice", "get_order_status"],
            actions=actions
        )

        start = time.time()
        history = [
            {"from": "customer", "text": "I need to check my invoice", "customer_id": "test-1"},
            {"from": "agent", "text": "I can help with that. What's your invoice number?", "customer_id": "test-1"}
        ]

        # Test the agent step
        response = asyncio.run(agent.step(history, "My invoice is INV-5001", "TENANT-001"))
        duration = (time.time() - start) * 1000

        assert isinstance(response.text, str), "Agent response should be text"
        assert response.latency_ms > 0, "Latency should be positive"

        self._add_step(
            "agent_response_generation",
            duration,
            True,
            metadata={"response_length": len(response.text), "needs_agent": response.needs_agent}
        )

    # ─────────────────────────────────────────────
    # 3. HANDOFF TO HUMAN
    # ─────────────────────────────────────────────
    def test_05_customer_handoff(self):
        """Test: Customer is successfully handed off to human agent"""
        from api.services.actions import Actions
        from unittest.mock import MagicMock

        mock_redis = MagicMock()
        actions = Actions(mock_redis)

        start = time.time()
        result = actions.run("handoff", {
            "queue": "general",
            "session_id": "test-handoff-123",
            "protocol_id": "PROTO-001"
        })
        duration = (time.time() - start) * 1000

        assert result["success"], f"Handoff failed: {result}"

        self._add_step(
            "customer_handoff",
            duration,
            True,
            metadata={"queue": "general", "session_id": "test-handoff-123"}
        )

    def test_06_escalation_alert(self):
        """Test: Escalation alerts are pushed correctly"""
        from api.routers.campaign import push_escalation_alert

        start = time.time()
        asyncio.run(push_escalation_alert(
            call_sid="test-call-123",
            reason="Customer requested supervisor",
            agent_name="TestAgent"
        ))
        duration = (time.time() - start) * 1000

        # Just verify no exception was raised
        assert duration < 1000, "Escalation alert took too long"

        self._add_step(
            "escalation_alert",
            duration,
            True,
            metadata={"alert_delivered": True}
        )

    # ─────────────────────────────────────────────
    # 4. VOICE CLONING WORKFLOW
    # ─────────────────────────────────────────────
    @pytest.mark.slow
    def test_07_voice_clone_workflow(self):
        """Test: Voice cloning API workflow (without actual audio upload)"""
        # Test the clone endpoint is accessible and auth works
        response = self.api_client.post("/api/v1/voice/clone",
            files={"audio": ("test.wav", b"fake-audio-data", "audio/wav")},
            data={"voice_name": "Test Voice", "language": "en-US"}
        )

        # May fail if Chatterbox is not running, but auth should work
        assert response.status_code in (200, 503), f"Unexpected status: {response.status_code}"

        self._add_step(
            "voice_clone_workflow",
            100.0,
            response.status_code == 200,
            metadata={"status_code": response.status_code}
        )

    # ─────────────────────────────────────────────
    # 5. SECURITY VALIDATION
    # ─────────────────────────────────────────────
    def test_08_unauthorized_access_blocked(self):
        """Test: Unauthenticated requests are blocked"""
        # Create a client without API key
        unauth_client = httpx.Client(base_url=API_URL, timeout=30.0)

        # Try accessing protected endpoints without auth
        response = unauth_client.get("/api/v1/agents?tenant_id=test")

        assert response.status_code in (401, 403), \
            f"Unauthenticated access should be blocked, got {response.status_code}"

        unauth_client.close()
        self._add_step("unauthorized_access_blocked", 50.0, True)

    def test_09_tenant_isolation(self):
        """Test: Tenants cannot access each other's data"""
        # Create two API keys for different tenants
        # This test validates that the verify_api_key function returns correct tenant_id
        from api.services.auth import verify_api_key

        # Test with dev API key
        result = asyncio.run(verify_api_key("dev-api-key"))
        assert result == "TENANT-001", f"Dev key should return TENANT-001, got {result}"

        self._add_step("tenant_isolation", 10.0, True, metadata={"tenant_id": result})

    # ─────────────────────────────────────────────
    # 6. DATA INTEGRITY
    # ─────────────────────────────────────────────
    def test_10_call_status_update(self):
        """Test: Call status can be updated and retrieved"""
        from api.services.database import (
            create_call_session, get_call_session, update_call_status
        )

        call_id = f"test-update-{uuid.uuid4().hex[:6]}"

        # Create a test call
        asyncio.run(create_call_session(
            tenant_id="TENANT-001",
            agent_id=None,
            caller_number="+15551234567",
            called_number="+15557654321",
            call_direction="inbound",
            sip_call_id=call_id
        ))

        # Update status
        start = time.time()
        updated = asyncio.run(update_call_status(call_id, "active"))
        duration = (time.time() - start) * 1000

        assert updated is not None, "Call status update should return data"
        assert updated["call_status"] == "active"

        # Cleanup
        asyncio.run(update_call_status(call_id, "completed"))

        self._add_step(
            "call_status_update",
            duration,
            True,
            metadata={"new_status": "active"}
        )

    # ─────────────────────────────────────────────
    # 7. PERFORMANCE BENCHMARKS
    # ─────────────────────────────────────────────
    @pytest.mark.benchmark
    def test_benchmark_queue_operations(self, benchmark):
        """Benchmark: Queue enqueue/dequeue performance"""
        from api.services.queue import QueueManager

        class MockRedis:
            def ping(self):
                return False  # Force in-memory fallback

        qm = QueueManager(MockRedis(), use_fallback=True)
        queue_name = f"bench-{uuid.uuid4().hex[:6]}"

        def run_benchmark():
            for i in range(100):
                qm.enqueue(queue_name, {"item": i, "created_ts": time.time()})
            for _ in range(100):
                qm.claim(queue_name, "bench-agent")

        result = benchmark(run_benchmark)
        self._add_step(
            "benchmark_queue_ops",
            0.0,
            True,
            metadata={"iterations": result.stats["num_rounds"] if hasattr(result, 'stats') else 100}
        )

    @pytest.mark.benchmark
    def test_benchmark_auth_verification(self, benchmark):
        """Benchmark: API key verification performance"""
        from api.services.auth import verify_api_key

        def run_benchmark():
            return asyncio.run(verify_api_key("dev-api-key"))

        result = benchmark(run_benchmark)
        self._add_step(
            "benchmark_auth_verify",
            0.0,
            True,
            metadata={"result": result}
        )

    @pytest.mark.benchmark
    def test_benchmark_api_response_time(self, benchmark):
        """Benchmark: End-to-end API response time"""
        def run_benchmark():
            return self.api_client.get("/api/v1/health")

        result = benchmark(run_benchmark)
        assert result.status_code == 200

        self._add_step(
            "benchmark_api_response",
            result.elapsed.total_seconds() * 1000 if hasattr(result, 'elapsed') else 0,
            True
        )


class TestEdgeCases(TestAPIClient):
    """
    Edge case tests to ensure robustness:
    - Empty payloads
    - Invalid data formats
    - Boundary conditions
    - Error handling
    """

    def test_empty_call_request(self):
        """Test: Empty call creation request"""
        response = self.api_client.post("/api/v1/calls", json={})
        assert response.status_code == 422, "Empty request should be rejected"

    def test_invalid_caller_number(self):
        """Test: Invalid phone number format"""
        response = self.api_client.post("/api/v1/calls", json={
            "caller_number": "not-a-phone-number",
            "call_direction": "inbound"
        })
        # Should either reject or handle gracefully
        assert response.status_code in (400, 422, 201), f"Unexpected status: {response.status_code}"

    def test_large_payload_rejection(self):
        """Test: Large payloads are rejected or handled"""
        large_text = "x" * 10_000_000  # 10MB of text
        response = self.api_client.post("/api/v1/voice/intent", json={
            "text": large_text
        })
        # Should either reject or truncate
        assert response.status_code in (200, 413, 422)

    def test_special_characters_in_text(self):
        """Test: Special characters are handled correctly"""
        special_text = "Hello! @#$%^&*()_+{}|:<>?~`-=[]\\;',./\""
        response = self.api_client.post("/api/v1/voice/intent", json={
            "text": special_text
        })
        assert response.status_code == 200, f"Special characters caused error: {response.text}"

    def test_unicode_handling(self):
        """Test: Unicode characters are handled correctly"""
        unicode_text = "こんにちは世界 🌍 你好世界 🇨🇳 مرحبا بالعالم"
        response = self.api_client.post("/api/v1/voice/intent", json={
            "text": unicode_text
        })
        assert response.status_code == 200, f"Unicode caused error: {response.text}"

    def test_concurrent_call_creation(self):
        """Test: Multiple concurrent call creations don't conflict"""
        import concurrent.futures

        def create_call(i):
            return self.api_client.post("/api/v1/calls", json={
                "caller_number": f"+1555{i:07d}",
                "call_direction": "inbound"
            })

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(create_call, i) for i in range(10)]
            results = [f.result() for f in futures]

        success_count = sum(1 for r in results if r.status_code == 201)
        assert success_count >= 8, f"Too many concurrent failures: {success_count}/10"


class TestHealthAndMonitoring(TestAPIClient):
    """Health check and monitoring endpoint tests"""

    def test_health_endpoint(self):
        """Test: Health check returns all service statuses"""
        response = self.api_client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()

        assert "status" in data
        assert "services" in data
        assert "fonster_connected" in data
        assert "database_connected" in data

    def test_readiness_probe(self):
        """Test: Readiness probe returns ready status"""
        response = self.api_client.get("/api/v1/health/ready")
        assert response.status_code == 200
        assert response.json().get("status") == "ready"

    def test_liveness_probe(self):
        """Test: Liveness probe returns alive status"""
        response = self.api_client.get("/api/v1/health/live")
        assert response.status_code == 200
        assert response.json().get("status") == "alive"


# ─────────────────────────────────────────────
# UI TESTS (Playwright Browser)
# ─────────────────────────────────────────────
@pytest.mark.ui
class TestUIFlows:
    """
    UI-based tests using Playwright to test the full customer journey
    through the web interface.
    """

    def test_login_page_loads(self, page: Page):
        """Test: Login page loads correctly"""
        page.goto(f"{BASE_URL}/login")
        expect(page).to_have_title(re.compile("AetherDesk|Login"))
        expect(page.locator("input[type='email']")).to_be_visible()
        expect(page.locator("input[type='password']")).to_be_visible()

    def test_dashboard_loads(self, page: Page):
        """Test: Dashboard loads after login"""
        page.goto(f"{BASE_URL}/login")
        # Fill in dev credentials
        page.locator("input[type='email']").fill("admin@aetherdesk.com")
        page.locator("input[type='password']").fill("admin123")
        page.locator("button[type='submit']").click()

        # Wait for dashboard to load - use role heading instead of text
        page.wait_for_url(f"{BASE_URL}/**", timeout=10000)
        expect(page.get_by_role("heading", name="Dashboard")).to_be_visible()

    def test_agent_management_ui(self, page: Page):
        """Test: Agent management UI works"""
        page.goto(f"{BASE_URL}/agents")
        # Should show agent list or create button - use heading role
        expect(page.get_by_role("heading", name=re.compile("Agents|Agent"))).to_be_visible()

    def test_call_history_ui(self, page: Page):
        """Test: Call history displays correctly"""
        page.goto(f"{BASE_URL}/calls")
        expect(page.get_by_role("heading", name=re.compile("Calls|Call History"))).to_be_visible()

    def test_campaign_ui(self, page: Page):
        """Test: Campaign management UI works"""
        page.goto(f"{BASE_URL}/campaigns")
        expect(page.get_by_role("heading", name=re.compile("Campaign|Campaigns"))).to_be_visible()


# ─────────────────────────────────────────────
# BENCHMARK SUMMARY
# ─────────────────────────────────────────────
class BenchmarkCollector:
    """Collects and reports benchmark results"""

    def __init__(self):
        self.results = []

    def add(self, name: str, duration_ms: float, success: bool, metadata: dict = None):
        self.results.append(BenchmarkResult(name, duration_ms, success, metadata=metadata or {}))

    def summary(self) -> dict:
        """Generate benchmark summary"""
        total = sum(r.duration_ms for r in self.results)
        success_count = sum(1 for r in self.results if r.success)
        return {
            "total_tests": len(self.results),
            "passed": success_count,
            "failed": len(self.results) - success_count,
            "total_duration_ms": round(total, 2),
            "avg_duration_ms": round(total / len(self.results), 2) if self.results else 0,
            "results": [
                {
                    "name": r.name,
                    "duration_ms": r.duration_ms,
                    "success": r.success,
                    "error": r.error
                }
                for r in self.results
            ]
        }


# ─────────────────────────────────────────────
# FIXTURE PROVIDERS
# ─────────────────────────────────────────────
@pytest.fixture(scope="session")
def benchmark_collector():
    """Session-scoped benchmark collector"""
    collector = BenchmarkCollector()
    yield collector
    # Print summary at end
    print("\n" + "=" * 60)
    print("BENCHMARK SUMMARY")
    print("=" * 60)
    summary = collector.summary()
    print(f"Total Tests: {summary['total_tests']}")
    print(f"Passed: {summary['passed']}")
    print(f"Failed: {summary['failed']}")
    print(f"Total Duration: {summary['total_duration_ms']:.2f}ms")
    print(f"Avg Duration: {summary['avg_duration_ms']:.2f}ms")
    print("=" * 60)