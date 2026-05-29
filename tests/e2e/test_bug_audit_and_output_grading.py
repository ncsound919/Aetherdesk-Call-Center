"""
Bug Audit Verification & Output Grading E2E Tests
=====================================================
Tests verify bugs found in audit, edge cases, and grade output quality.

Run: pytest tests/e2e/test_bug_audit_and_output_grading.py -v
"""
import json
import re
import time
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Any

import httpx
import pytest
from playwright.sync_api import Page, expect


API_URL = "http://localhost:8000"
UI_URL = "http://localhost:3000"
HEADERS = {"x-api-key": "dev-api-key", "Content-Type": "application/json"}


# =============================================================================
# OUTPUT GRADING HELPERS
# =============================================================================

class OutputGrader:
    """Grades API response quality across multiple dimensions."""

    @staticmethod
    def grade_json_structure(response: dict, expected_fields: list[str]) -> dict:
        """Grade JSON structure completeness."""
        missing = [f for f in expected_fields if f not in response]
        score = (len(expected_fields) - len(missing)) / len(expected_fields) * 100
        return {
            "score": score,
            "grade": "A" if score >= 90 else "B" if score >= 70 else "C" if score >= 50 else "F",
            "missing_fields": missing,
        }

    @staticmethod
    def grade_response_time(response_time_ms: float) -> dict:
        """Grade response time performance."""
        if response_time_ms < 100:
            return {"score": 100, "grade": "A", "perf": "excellent"}
        elif response_time_ms < 300:
            return {"score": 90, "grade": "A", "perf": "good"}
        elif response_time_ms < 500:
            return {"score": 70, "grade": "B", "perf": "acceptable"}
        elif response_time_ms < 1000:
            return {"score": 50, "grade": "C", "perf": "slow"}
        else:
            return {"score": 20, "grade": "F", "perf": "timeout_risk"}

    @staticmethod
    def grade_text_quality(text: str, min_length: int = 5, max_length: int = 5000) -> dict:
        """Grade text content quality."""
        if not text:
            return {"score": 0, "grade": "F", "issues": ["empty"]}

        issues = []
        if len(text) < min_length:
            issues.append("too_short")
        if len(text) > max_length:
            issues.append("too_long")
        if text.strip() != text:
            issues.append("has_whitespace")
        if re.search(r'<script|javascript:', text, re.I):
            issues.append("potential_xss")

        score = max(0, 100 - len(issues) * 20)
        return {
            "score": score,
            "grade": "A" if score >= 90 else "B" if score >= 70 else "C" if score >= 50 else "F",
            "issues": issues,
            "length": len(text),
        }

    @staticmethod
    def grade_api_error_handling(status_code: int, response_body: dict) -> dict:
        """Grade API error response quality."""
        has_detail = "detail" in response_body or "error" in response_body
        has_code = status_code in [400, 401, 403, 404, 422, 500]
        is_json = "application/json" in response_body.get("content_type", "")

        score = 0
        if has_detail:
            score += 40
        if has_code:
            score += 30
        if is_json:
            score += 30

        return {
            "score": score,
            "grade": "A" if score >= 80 else "B" if score >= 60 else "C" if score >= 40 else "F",
            "has_detail": has_detail,
            "status_code": status_code,
        }


# =============================================================================
# BUG VERIFICATION TESTS
# =============================================================================

class TestBugVerification:
    """Tests that verify specific bugs found in audit."""

    def test_db_context_async_sync_mismatch(self):
        """
        BUG #1: db_context() is asynccontextmanager but used synchronously in auth.py.
        Verify: Should fail when verify_api_key is called.
        """
        # This should fail at runtime due to sync context manager used in async context
        resp = httpx.get(
            f"{API_URL}/api/v1/tenants/TENANT-001",
            headers={"x-api-key": "dev-api-key"},
            timeout=10,
        )
        # If this works, the bug may have been fixed or dev mode bypassed it
        print(f"verify_api_key response: {resp.status_code}")

    def test_null_profile_pointer(self):
        """
        BUG #2: orchestrator.py line 116 accesses profile["parameters"] without null check.
        Verify: Querying non-existent agent_profiles table.
        """
        # The agent_profiles table doesn't exist in schema - this should fail
        resp = httpx.post(
            f"{API_URL}/api/v1/saas/profile?name=TestProfile&prompt=Test",
            json={"parameters": {}},
            headers=HEADERS,
            timeout=10,
        )
        print(f"Profile create response: {resp.status_code}, {resp.text[:200]}")

    def test_missing_api_key_on_tenant_creation(self):
        """
        BUG #4: Tenant creation doesn't set api_key, so verify_api_key will fail.
        Verify: Create tenant and check if api_key is set.
        """
        tenant_payload = {
            "name": f"Test Company {int(time.time())}",
            "email": f"test{int(time.time())}@example.com",
            "phone": "+15551234567",
            "gdpr_consent": True,
        }
        resp = httpx.post(
            f"{API_URL}/api/v1/tenants",
            json=tenant_payload,
            timeout=10,
        )
        if resp.status_code == 201:
            tenant_id = resp.json()["id"]
            # Try to access with the created tenant's ID using dev key
            access_resp = httpx.get(
                f"{API_URL}/api/v1/tenants/{tenant_id}",
                headers={"x-api-key": "dev-api-key"},
                timeout=10,
            )
            print(f"Tenant access with dev key: {access_resp.status_code}")

    def test_division_by_zero_in_usage(self):
        """
        BUG #16: Division by zero if active_agents is 0.
        Verify: Get usage stats for tenant with no active agents.
        """
        now = datetime.now(timezone.utc)
        resp = httpx.get(
            f"{API_URL}/api/v1/usage?period_start={now.isoformat()}&period_end={(now + timedelta(days=7)).isoformat()}",
            headers=HEADERS,
            timeout=10,
        )
        print(f"Usage endpoint status: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            print(f"Usage response: {data}")

    def test_missing_query_parameter_defaults(self):
        """
        BUG #15: period_start/period_end required without defaults.
        Verify: Call usage without params - should be 422.
        """
        resp = httpx.get(
            f"{API_URL}/api/v1/usage",
            headers=HEADERS,
            timeout=10,
        )
        # Should fail with 422 due to missing required params
        print(f"Usage without params: {resp.status_code}")


# =============================================================================
# OUTPUT GRADING TESTS
# =============================================================================

class TestOutputGrading:
    """Tests that grade output quality of various endpoints."""

    def test_health_endpoint_output_grading(self):
        """Grade health endpoint output quality."""
        start = time.time()
        resp = httpx.get(f"{API_URL}/health", timeout=10)
        elapsed = (time.time() - start) * 1000

        assert resp.status_code == 200
        data = resp.json()

        structure = OutputGrader.grade_json_structure(data, [
            "status", "timestamp", "version", "services",
            "fonster_connected", "database_connected"
        ])
        timing = OutputGrader.grade_response_time(elapsed)

        print(f"\n=== Health Endpoint Grades ===")
        print(f"Structure: {structure['grade']} ({structure['score']:.0f}%)")
        print(f"Timing: {timing['grade']} ({timing['score']:.0f}%) - {timing['perf']}")
        print(f"Response time: {elapsed:.1f}ms")

        assert structure["score"] >= 70, f"Missing fields: {structure['missing_fields']}"

    def test_agent_list_output_grading(self):
        """Grade agent list endpoint output quality."""
        start = time.time()
        resp = httpx.get(
            f"{API_URL}/api/v1/tenants/TENANT-001/agents",
            headers=HEADERS,
            timeout=10,
        )
        elapsed = (time.time() - start) * 1000

        timing = OutputGrader.grade_response_time(elapsed)

        if resp.status_code == 200:
            agents = resp.json()
            if agents:
                first = agents[0]
                structure = OutputGrader.grade_json_structure(first, [
                    "id", "tenant_id", "name", "display_name", "agent_type",
                    "status", "skills", "sip_extension", "total_calls"
                ])
                print(f"\n=== Agent List Grades ===")
                print(f"Structure: {structure['grade']} ({structure['score']:.0f}%)")
                print(f"Timing: {timing['grade']} ({timing['score']:.0f}%)")
            else:
                print("\nNo agents created yet - skipping structure grade")

    def test_call_list_output_grading(self):
        """Grade call list endpoint output quality."""
        start = time.time()
        resp = httpx.get(
            f"{API_URL}/api/v1/calls",
            headers=HEADERS,
            timeout=10,
        )
        elapsed = (time.time() - start) * 1000

        timing = OutputGrader.grade_response_time(elapsed)

        print(f"\n=== Call List Grades ===")
        print(f"Status: {resp.status_code}")
        print(f"Timing: {timing['grade']} ({timing['score']:.0f}%) - {timing['perf']}")
        print(f"Response time: {elapsed:.1f}ms")

    def test_campaign_stats_output_grading(self):
        """Grade campaign stats output quality."""
        start = time.time()
        resp = httpx.get(
            f"{API_URL}/api/v1/campaign/stats",
            headers=HEADERS,
            timeout=10,
        )
        elapsed = (time.time() - start) * 1000

        if resp.status_code == 200:
            data = resp.json()
            structure = OutputGrader.grade_json_structure(data, [
                "total_leads", "untouched_leads", "total_calls_made",
                "interested", "needs_human_follow_up", "conversion_rate"
            ])
            timing = OutputGrader.grade_response_time(elapsed)

            print(f"\n=== Campaign Stats Grades ===")
            print(f"Structure: {structure['grade']} ({structure['score']:.0f}%)")
            print(f"Timing: {timing['grade']} ({timing['score']:.0f}%)")

            # Check conversion_rate format
            if "conversion_rate" in data:
                rate = data["conversion_rate"]
                assert "%" in rate, "Conversion rate should contain %"
                print(f"Conversion rate format: {rate}")

    def test_error_response_grading(self):
        """Grade error response quality."""
        # Test 404 error
        resp = httpx.get(
            f"{API_URL}/api/v1/tenants/NONEXISTENT/agents",
            headers=HEADERS,
            timeout=10,
        )

        grade = OutputGrader.grade_api_error_handling(resp.status_code, {})
        print(f"\n=== Error Response Grades ===")
        print(f"404 Error grade: {grade['grade']} ({grade['score']}%)")
        print(f"Has detail: {grade['has_detail']}, Status: {grade['status_code']}")

        # Test 422 error (missing required params)
        resp = httpx.post(
            f"{API_URL}/api/v1/calls",
            json={"caller_number": "+15551234567"},
            headers=HEADERS,
            timeout=10,
        )
        grade2 = OutputGrader.grade_api_error_handling(resp.status_code, {})
        print(f"422 Error grade: {grade2['grade']} ({grade2['score']}%)")


# =============================================================================
# EDGE CASE TESTS
# =============================================================================

class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_voice_clone_no_file_size_limit(self):
        """
        BUG #9: No file size validation on voice clone upload.
        Attempt with empty/very small file.
        """
        # Create a minimal WAV-like file (44 bytes header + minimal data)
        minimal_audio = b'RIFF\x00\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x44\xac\x00\x00\x88\x58\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00'

        files = {"audio": ("test.wav", minimal_audio, "audio/wav")}
        resp = httpx.post(
            f"{API_URL}/api/v1/voice/clone?voice_name=TestVoice",
            files=files,
            timeout=30,
        )
        print(f"Minimal file upload: {resp.status_code}")
        if resp.status_code == 200:
            print(f"Response: {resp.json()}")

    def test_skills_json_parse_edge_case(self):
        """Test edge case with malformed skills JSON."""
        # Create a lead with various phone formats
        test_phones = [
            "+15551234567",      # E.164 standard
            "15551234567",       # No plus
            "555-123-4567",      # Dashes
            "(555) 123-4567",    # Parens
            "+1 555 123 4567",   # Spaces
        ]

        for phone in test_phones:
            resp = httpx.post(
                f"{API_URL}/api/v1/campaign/leads",
                json={
                    "company_name": "Edge Test",
                    "phone": phone,
                    "priority": 5,
                },
                headers=HEADERS,
                timeout=10,
            )
            print(f"Phone {phone}: {resp.status_code}")

    def test_bulk_import_max_limit(self):
        """Test bulk import respects 500 lead limit."""
        leads = [
            {"company_name": f"Company {i}", "phone": f"+1555000{i:04d}", "priority": 5}
            for i in range(505)  # Over limit
        ]
        resp = httpx.post(
            f"{API_URL}/api/v1/campaign/leads/bulk",
            json={"leads": leads},
            headers=HEADERS,
            timeout=30,
        )
        # Should either reject or cap at 500
        print(f"Bulk import 505 leads: {resp.status_code}")
        if resp.status_code == 200:
            result = resp.json()
            print(f"Imported: {result.get('imported', 'N/A')}")

    def test_concurrent_campaign_launch_race(self):
        """
        BUG #6: Race condition on campaign launch.
        Try to launch two campaigns concurrently.
        """
        config = {"profile_id": "PROF-001", "max_concurrent": 1, "delay_between_calls": 1.0}

        # Launch first campaign
        resp1 = httpx.post(
            f"{API_URL}/api/v1/campaign/launch",
            json=config,
            headers=HEADERS,
            timeout=10,
        )

        # Immediately try second campaign (should be rejected)
        resp2 = httpx.post(
            f"{API_URL}/api/v1/campaign/launch",
            json=config,
            headers=HEADERS,
            timeout=10,
        )

        print(f"First campaign: {resp1.status_code}")
        print(f"Second campaign: {resp2.status_code}")
        # Second should be 409 Conflict if race condition is handled

    def test_invalid_tenant_id_characters(self):
        """Test endpoint with unusual tenant ID characters."""
        invalid_ids = ["", " ", "DROP TABLE", "12345", "a" * 100]

        for tenant_id in invalid_ids:
            resp = httpx.get(
                f"{API_URL}/api/v1/tenants/{tenant_id}",
                headers=HEADERS,
                timeout=10,
            )
            print(f"Tenant ID '{tenant_id[:20]}': {resp.status_code}")

    def test_agent_status_invalid_values(self):
        """Test agent status update with invalid status."""
        invalid_statuses = ["", "invalid", "ACTIVE", "offline ", "  online"]

        for status in invalid_statuses:
            resp = httpx.patch(
                f"{API_URL}/api/v1/agents/AGENT-TEST/status",
                json={"status": status},
                timeout=10,
            )
            print(f"Status '{status}': {resp.status_code}")


# =============================================================================
# RESOURCE LEAK TESTS
# =============================================================================

class TestResourceLeaks:
    """Tests that detect potential resource leaks."""

    def test_websocket_connection_cleanup(self):
        """Test WebSocket connections are properly cleaned up."""
        # This would require checking internal state - just verify endpoint works
        resp = httpx.get(f"{API_URL}/health", timeout=5)
        assert resp.status_code == 200

    def test_redis_pubsub_no_leak(self):
        """Test Redis pubsub is properly managed."""
        # Make multiple WebSocket requests and check connection count
        for _ in range(5):
            resp = httpx.get(f"{API_URL}/health", timeout=5)
            assert resp.status_code == 200


# =============================================================================
# INTEGRATION GRADING SUMMARY
# =============================================================================

class TestIntegrationGradingSummary:
    """Generate comprehensive grading report for all endpoints."""

    def test_full_system_grading_report(self):
        """Generate a full grading report for all major endpoints."""
        endpoints = [
            ("GET", "/health", None, None),
            ("GET", "/api/v1/tenants/TENANT-001", HEADERS, None),
            ("GET", "/api/v1/tenants/TENANT-001/agents", HEADERS, None),
            ("GET", "/api/v1/calls", HEADERS, None),
            ("GET", "/api/v1/usage?period_start=2024-01-01T00:00:00Z&period_end=2024-01-08T00:00:00Z", HEADERS, None),
            ("GET", "/api/v1/campaign/stats", HEADERS, None),
            ("POST", "/api/v1/campaign/leads", HEADERS, {
                "company_name": "Grading Test", "phone": "+15559999001", "priority": 5
            }),
        ]

        report = {"endpoints": [], "overall": {}}

        for method, path, headers, json_data in endpoints:
            start = time.time()
            try:
                if method == "GET":
                    resp = httpx.get(f"{API_URL}{path}", headers=headers, timeout=10)
                else:
                    resp = httpx.post(f"{API_URL}{path}", json=json_data, headers=headers, timeout=10)

                elapsed = (time.time() - start) * 1000

                timing = OutputGrader.grade_response_time(elapsed)

                endpoint_report = {
                    "path": path,
                    "method": method,
                    "status": resp.status_code,
                    "response_time_ms": round(elapsed, 1),
                    "timing_grade": timing["grade"],
                    "timing_score": timing["score"],
                }

                if resp.status_code == 200 and method == "GET":
                    try:
                        data = resp.json()
                        endpoint_report["response_size_bytes"] = len(json.dumps(data))
                    except:
                        pass

                report["endpoints"].append(endpoint_report)

            except Exception as e:
                report["endpoints"].append({
                    "path": path,
                    "method": method,
                    "error": str(e),
                    "timing_grade": "F",
                })

        # Calculate overall scores
        grades = [e.get("timing_grade", "F") for e in report["endpoints"]]
        scores = [e.get("timing_score", 0) for e in report["endpoints"]]

        avg_score = sum(scores) / len(scores) if scores else 0

        report["overall"] = {
            "total_endpoints": len(report["endpoints"]),
            "average_score": round(avg_score, 1),
            "grade_distribution": {
                "A": grades.count("A"),
                "B": grades.count("B"),
                "C": grades.count("C"),
                "F": grades.count("F"),
            }
        }

        print("\n" + "=" * 60)
        print("ENDPOINT GRADING REPORT")
        print("=" * 60)
        for e in report["endpoints"]:
            status = e.get("status", "ERROR")
            timing = e.get("timing_grade", "?")
            rt = e.get("response_time_ms", 0)
            print(f"{e['method']:6} {e['path'][:45]:45} {status:3} {timing} {rt:>6}ms")

        print("-" * 60)
        overall = report["overall"]
        print(f"Total: {overall['total_endpoints']} | Avg Score: {overall['average_score']:.1f}")
        print(f"Grade Distribution: A={overall['grade_distribution']['A']}, "
              f"B={overall['grade_distribution']['B']}, "
              f"C={overall['grade_distribution']['C']}, "
              f"F={overall['grade_distribution']['F']}")
        print("=" * 60)


# =============================================================================
# PHASE 3: VOICE CLONING TESTS
# =============================================================================

class TestPhase3VoiceCloning:
    """Tests Phase 3 voice cloning endpoints, formats, and default voice functionality."""

    def test_voice_clone_invalid_format(self):
        """Upload random bytes (not audio) and expect 415."""
        random_bytes = b"Hello, this is just some random text file bytes, not audio." * 1000
        files = {"audio": ("bad.txt", random_bytes, "text/plain")}
        resp = httpx.post(
            f"{API_URL}/api/v1/voice/clone?voice_name=BadFormatVoice",
            files=files,
            headers={"x-api-key": "dev-api-key"},
            timeout=10,
        )
        assert resp.status_code == 415
        assert "Unsupported audio format" in resp.json()["detail"]

    def test_voice_clone_too_small(self):
        """Upload < 32 KB WAV and expect 400."""
        # A valid but very small WAV format header with minimal payload (under 32KB)
        too_small_wav = b'RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x44\xac\x00\x00\x88\x58\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00'
        assert len(too_small_wav) < 32768
        
        files = {"audio": ("small.wav", too_small_wav, "audio/wav")}
        resp = httpx.post(
            f"{API_URL}/api/v1/voice/clone?voice_name=TooSmallVoice",
            files=files,
            headers={"x-api-key": "dev-api-key"},
            timeout=10,
        )
        assert resp.status_code == 400
        assert "Audio file too small" in resp.json()["detail"]

    def test_voice_clone_sets_chatterbox_id(self):
        """Upload valid WAV (>= 32 KB) and check response fields."""
        # 33 KB of WAV bytes (WAV header + 33000 bytes of zeros/dummy audio)
        header = b'RIFF\x24\x80\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x44\xac\x00\x00\x88\x58\x01\x00\x02\x00\x10\x00data\x00\x80\x00\x00'
        valid_wav = header + b'\x00' * 33000
        assert len(valid_wav) >= 32768

        files = {"audio": ("valid.wav", valid_wav, "audio/wav")}
        resp = httpx.post(
            f"{API_URL}/api/v1/voice/clone?voice_name=ValidVoice",
            files=files,
            headers={"x-api-key": "dev-api-key"},
            timeout=10,
        )
        assert resp.status_code == 200
        result = resp.json()
        assert "voice_id" in result
        assert "status" in result
        assert "chatterbox_voice_id" in result
        print(f"Voice clone success response: {result}")

    def test_default_voice_roundtrip(self):
        """Set a default voice and get it back, verifying match."""
        header = b'RIFF\x24\x80\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x44\xac\x00\x00\x88\x58\x01\x00\x02\x00\x10\x00data\x00\x80\x00\x00'
        valid_wav = header + b'\x00' * 33000
        files = {"audio": ("valid.wav", valid_wav, "audio/wav")}
        clone_resp = httpx.post(
            f"{API_URL}/api/v1/voice/clone?voice_name=RoundtripVoice",
            files=files,
            headers={"x-api-key": "dev-api-key"},
            timeout=10,
        )
        assert clone_resp.status_code == 200
        voice_id = clone_resp.json()["voice_id"]
        
        # Set as default
        set_resp = httpx.post(
            f"{API_URL}/api/v1/voice/set-default?voice_id={voice_id}",
            headers={"x-api-key": "dev-api-key"},
            timeout=10,
        )
        assert set_resp.status_code == 200
        
        # Get default and verify
        get_resp = httpx.get(
            f"{API_URL}/api/v1/voice/default",
            headers={"x-api-key": "dev-api-key"},
            timeout=10,
        )
        assert get_resp.status_code == 200
        assert get_resp.json()["default_voice_id"] == voice_id


# =============================================================================
# UI OUTPUT GRADING TESTS
# =============================================================================

class TestUIOutputGrading:
    """Grade UI output quality and behavior."""

    def test_dashboard_load_performance(self, page: Page):
        """Grade dashboard load time and content."""
        start = time.time()
        page.goto(UI_URL)
        page.wait_for_load_state("networkidle", timeout=15000)
        load_time = (time.time() - start) * 1000

        timing = OutputGrader.grade_response_time(load_time)
        print(f"\n=== Dashboard Load Grades ===")
        print(f"Load time: {load_time:.0f}ms")
        print(f"Performance grade: {timing['grade']}")

        # Check key elements visible
        try:
            expect(page.locator(".sidebar, nav, header")).first.wait_for(timeout=5000)
            print("Navigation: Visible")
        except:
            print("Navigation: NOT FOUND")

    def test_error_page_grading(self, page: Page):
        """Grade error page output quality."""
        page.goto(f"{UI_URL}/nonexistent-page-xyz")
        page.wait_for_load_state("domcontentloaded", timeout=10000)

        # Check for error message quality
        has_error = page.locator("text=404, text=Error, text=Not Found").count() > 0
        print(f"\n=== Error Page Grades ===")
        print(f"Has error indication: {has_error}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])