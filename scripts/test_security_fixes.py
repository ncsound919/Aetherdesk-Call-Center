#!/usr/bin/env python3
"""
AetherDesk Security Fix Validation Tests
==========================================
Tests that verify the security fixes we implemented are working correctly.

Run after starting the API server:
    python scripts/test_security_fixes.py
"""
import asyncio
import httpx
import os
import sys
import json
from datetime import datetime


API_URL = os.getenv("API_URL", "http://localhost:8000")
DEV_API_KEY = os.getenv("DEV_API_KEY", "dev-api-key")


class TestResult:
    def __init__(self, name: str, passed: bool, message: str, details: dict = None):
        self.name = name
        self.passed = passed
        self.message = message
        self.details = details or {}
        self.timestamp = datetime.now().isoformat()


class SecurityFixValidator:
    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.results: list[TestResult] = []

    async def test(self, name: str, test_func):
        """Run a single test and record result"""
        try:
            result = await test_func()
            self.results.append(result)
            status = "PASS" if result.passed else "FAIL"
            print(f"  [{status}] {result.name}: {result.message}")
            return result.passed
        except Exception as e:
            self.results.append(TestResult(name, False, f"Exception: {str(e)}"))
            print(f"  [FAIL] {name}: Exception: {e}")
            return False

    async def test_no_hardcoded_db_password(self):
        """Test: Database connection requires proper environment variable"""
        # Read the database.py file and check for hardcoded password
        with open("apps/api/services/database.py") as f:
            content = f.read()

        # Check that the old hardcoded password is not present
        has_hardcoded = "postgresql://aetherdesk_admin:password@" in content
        has_none_default = 'os.getenv(\n    "DATABASE_URL",\n    None\n)' in content
        has_error_raise = "raise RuntimeError" in content and "DATABASE_URL" in content

        passed = not has_hardcoded and has_none_default and has_error_raise
        return TestResult(
            "No Hardcoded DB Password",
            passed,
            "Database password not hardcoded" if passed else "Hardcoded password found!",
            {"has_none_default": has_none_default, "has_error_raise": has_error_raise}
        )

    async def test_cors_not_wildcard(self):
        """Test: CORS configuration doesn't allow wildcard origin"""
        with open("apps/api/main.py") as f:
            content = f.read()

        # Check that wildcard is not in CORS origins
        has_wildcard = '"*"' in content and "CORSMiddleware" in content
        uses_env = "CORS_ORIGIN" in content

        passed = not has_wildcard and uses_env
        return TestResult(
            "CORS Not Wildcard",
            passed,
            "CORS properly configured" if passed else "CORS still has wildcard!",
            {"uses_env_var": uses_env}
        )

    async def test_api_keys_rotated(self):
        """Test: API keys are not hardcoded in deployment.yml"""
        with open("kubernetes/deployment.yml") as f:
            content = f.read()

        # Check for real API keys
        has_deepgram_key = "6d7905409a8d2384ab88de756a671b7fe5be7fa3" in content
        has_groq_key = "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" in content

        passed = not has_deepgram_key and not has_groq_key
        return TestResult(
            "API Keys Rotated",
            passed,
            "API keys not hardcoded" if passed else "Real API keys still in file!",
            {"deepgram_rotated": not has_deepgram_key, "groq_rotated": not has_groq_key}
        )

    async def test_auth_on_incoming_endpoint(self):
        """Test: /voice/incoming endpoint has authentication"""
        with open("apps/api/routers/voice.py") as f:
            content = f.read()

        # Check that verify_api_key is imported and used
        has_import = "verify_api_key" in content
        has_dependency = "Depends(verify_api_key)" in content

        passed = has_import and has_dependency
        return TestResult(
            "Voice Incoming Auth",
            passed,
            "Authentication added" if passed else "Missing authentication!",
            {"has_import": has_import, "has_dependency": has_dependency}
        )

    async def test_auth_on_clone_endpoint(self):
        """Test: /api/v1/voice/clone endpoint has authentication"""
        with open("apps/api/routers/voice_cloning.py") as f:
            content = f.read()

        has_import = "verify_api_key" in content
        has_dependency = "Depends(verify_api_key)" in content

        passed = has_import and has_dependency
        return TestResult(
            "Voice Clone Auth",
            passed,
            "Authentication added" if passed else "Missing authentication!",
            {"has_import": has_import, "has_dependency": has_dependency}
        )

    async def test_dev_passwords_configurable(self):
        """Test: Development passwords are configurable via env vars"""
        with open("apps/api/routers/auth.py") as f:
            content = f.read()

        # Our fix: DEV_USERS is empty by default, passwords only available
        # when DEV_USERS_CONFIGURED=true AND env vars are set
        has_env_config_check = "DEV_USERS_CONFIGURED" in content
        no_hardcoded_passwords = "admin123" not in content and "agent123" not in content
        # Note: "admin123" as a substring check covers it

        passed = has_env_config_check and no_hardcoded_passwords
        return TestResult(
            "Dev Passwords Configurable",
            passed,
            "Dev passwords configurable via env vars" if passed else "Hardcoded dev passwords found!",
            {"has_env_config": has_env_config_check, "no_hardcoded": no_hardcoded_passwords}
        )

    async def test_chatterbox_formdata(self):
        """Test: Chatterbox API uses proper FormData for file upload"""
        with open("apps/api/routers/voice_cloning.py") as f:
            content = f.read()

        uses_formdata = "FormData" in content
        uses_add_field = "add_field" in content

        passed = uses_formdata and uses_add_field
        return TestResult(
            "Chatterbox FormData Fix",
            passed,
            "Using proper FormData" if passed else "Still using broken data format!",
            {"uses_formdata": uses_formdata, "uses_add_field": uses_add_field}
        )

    async def test_voice_profile_limit(self):
        """Test: Voice profiles have a size limit"""
        with open("apps/api/routers/voice_cloning.py") as f:
            content = f.read()

        has_max_limit = "MAX_VOICE_PROFILES" in content
        has_eviction = "_evict_oldest_profile" in content

        passed = has_max_limit and has_eviction
        return TestResult(
            "Voice Profile Limit",
            passed,
            "Memory leak fixed" if passed else "Unbounded voice profiles!",
            {"has_max": has_max_limit, "has_eviction": has_eviction}
        )

    async def test_protocols_auth(self):
        """Test: Protocol upload endpoint has authentication"""
        with open("apps/api/routers/protocols.py") as f:
            content = f.read()

        has_auth = "verify_api_key" in content
        has_path_check = "SAFE_FILENAME_RE" in content

        passed = has_auth and has_path_check
        return TestResult(
            "Protocols Upload Auth",
            passed,
            "Auth added with security fixes" if passed else "Missing auth or security!",
            {"has_auth": has_auth, "has_path_sanitization": has_path_check}
        )

    async def test_saas_no_hardcoded_key(self):
        """Test: SaaS router doesn't have hardcoded API key"""
        with open("apps/api/routers/saas.py") as f:
            content = f.read()

        has_hardcoded = 'default="ak-acme-123"' in content

        passed = not has_hardcoded
        return TestResult(
            "SaaS No Hardcoded Key",
            passed,
            "No hardcoded API key" if passed else "Hardcoded API key found!",
            {"no_hardcoded": not has_hardcoded}
        )

    async def test_api_returns_401_without_auth(self):
        """Test: API endpoints return 401/403 without authentication"""
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Try accessing protected endpoint without auth
            # Note: With HTTPBearer(auto_error=False), missing auth header
            # leads to credentials=None, which then raises 401 in get_current_user
            response = await client.get(f"{self.base_url}/api/v1/calls?tenant_id=test")

            # Should be 401 (unauthorized) or 403 (forbidden)
            passed = response.status_code in (401, 403)
            return TestResult(
                "API Returns 401/403 Without Auth",
                passed,
                f"Returns {response.status_code} as expected" if passed else f"Returns {response.status_code} instead of 401/403",
                {"status_code": response.status_code}
            )

    async def test_health_endpoint_public(self):
        """Test: Health check endpoint is publicly accessible"""
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{self.base_url}/api/v1/health")

            passed = response.status_code == 200
            return TestResult(
                "Health Endpoint Public",
                passed,
                "Health check accessible" if passed else f"Health check returned {response.status_code}",
                {"status_code": response.status_code}
            )

    async def run_all(self):
        """Run all security validation tests"""
        print("\n[INFO] Validating Security Fixes...")
        print("=" * 60)

        # File-based tests (don't need server running)
        await self.test("No Hardcoded DB Password", self.test_no_hardcoded_db_password)
        await self.test("CORS Not Wildcard", self.test_cors_not_wildcard)
        await self.test("API Keys Rotated", self.test_api_keys_rotated)
        await self.test("Voice Incoming Auth", self.test_auth_on_incoming_endpoint)
        await self.test("Voice Clone Auth", self.test_auth_on_clone_endpoint)
        await self.test("Dev Passwords Configurable", self.test_dev_passwords_configurable)
        await self.test("Chatterbox FormData Fix", self.test_chatterbox_formdata)
        await self.test("Voice Profile Limit", self.test_voice_profile_limit)
        await self.test("Protocols Upload Auth", self.test_protocols_auth)
        await self.test("SaaS No Hardcoded Key", self.test_saas_no_hardcoded_key)

        # Runtime tests (need server running)
        print("\n  Runtime tests (require server)...")
        try:
            await self.test("API Returns 401 Without Auth", self.test_api_returns_401_without_auth)
            await self.test("Health Endpoint Public", self.test_health_endpoint_public)
        except Exception as e:
            print(f"  [WARN] Runtime tests skipped: {e}")

        # Summary
        passed = sum(1 for r in self.results if r.passed)
        total = len(self.results)

        print("\n" + "=" * 60)
        print("SECURITY VALIDATION SUMMARY")
        print("=" * 60)
        print(f"Passed: {passed}/{total}")
        print(f"Failed: {total - passed}/{total}")

        if passed < total:
            print("\nFAILED TESTS:")
            for r in self.results:
                if not r.passed:
                    print(f"  - {r.name}: {r.message}")

        print("=" * 60)

        # Export results
        with open("security_validation_results.json", "w") as f:
            json.dump([
                {
                    "name": r.name,
                    "passed": r.passed,
                    "message": r.message,
                    "details": r.details,
                    "timestamp": r.timestamp
                }
                for r in self.results
            ], f, indent=2)
            print("Results saved to security_validation_results.json")

        return passed == total


async def main():
    validator = SecurityFixValidator(API_URL, DEV_API_KEY)
    success = await validator.run_all()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())