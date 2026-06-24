"""Unit tests for SecurityHeadersMiddleware.

Creates a minimal FastAPI app with only the security middleware and a test
route, then verifies that all security headers are set on every response.
"""

from fastapi import FastAPI, Request
from fastapi.responses import Response
from fastapi.testclient import TestClient
import pytest


@pytest.fixture
def app():
    """Create a minimal FastAPI app with SecurityHeadersMiddleware."""
    from apps.api.middleware.security import SecurityHeadersMiddleware

    application = FastAPI()
    application.add_middleware(SecurityHeadersMiddleware)

    @application.get("/test")
    async def test_route():
        return {"message": "ok"}

    @application.get("/empty")
    async def empty_route():
        return ""

    return application


@pytest.fixture
def client(app):
    """TestClient bound to the minimal security app."""
    with TestClient(app) as c:
        yield c


class TestSecurityHeadersMiddleware:
    """Verify all security headers are set on responses."""

    def test_strict_transport_security(self, client):
        """HSTS header is set with max-age and includeSubDomains."""
        resp = client.get("/test")
        assert resp.headers.get("Strict-Transport-Security") == \
            "max-age=31536000; includeSubDomains"

    def test_x_content_type_options(self, client):
        """X-Content-Type-Options header is set to nosniff."""
        resp = client.get("/test")
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"

    def test_x_frame_options(self, client):
        """X-Frame-Options header is set to DENY."""
        resp = client.get("/test")
        assert resp.headers.get("X-Frame-Options") == "DENY"

    def test_x_xss_protection(self, client):
        """X-XSS-Protection header is set to 1; mode=block."""
        resp = client.get("/test")
        assert resp.headers.get("X-XSS-Protection") == "1; mode=block"

    def test_referrer_policy(self, client):
        """Referrer-Policy header is set to strict-origin-when-cross-origin."""
        resp = client.get("/test")
        assert resp.headers.get("Referrer-Policy") == \
            "strict-origin-when-cross-origin"

    def test_content_security_policy(self, client):
        """Content-Security-Policy header contains expected directives."""
        resp = client.get("/test")
        csp = resp.headers.get("Content-Security-Policy", "")
        assert "default-src 'self'" in csp
        assert "script-src 'self'" in csp
        assert "style-src 'self' 'unsafe-inline'" in csp
        assert "font-src 'self'" in csp
        assert "img-src 'self' data: https:" in csp
        assert "connect-src 'self' wss: ws:" in csp
        assert "frame-ancestors 'none'" in csp

    def test_all_security_headers_present(self, client):
        """All 6 security headers are present on every response (case-insensitive check)."""
        resp = client.get("/test")
        # httpx returns lowercase header keys; use case-insensitive lookup
        expected_lower = {
            "strict-transport-security",
            "x-content-type-options",
            "x-frame-options",
            "x-xss-protection",
            "referrer-policy",
            "content-security-policy",
        }
        actual_lower = {k.lower() for k in resp.headers.keys()}
        missing = expected_lower - actual_lower
        assert not missing, f"Missing headers: {missing}"

    def test_headers_on_empty_response(self, client):
        """Security headers are set even on responses with empty body."""
        resp = client.get("/empty")
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"
        assert resp.headers.get("X-Frame-Options") == "DENY"
        assert resp.headers.get("Strict-Transport-Security") is not None

    def test_headers_on_nonexistent_route(self, client):
        """Security headers are set on 404 responses too."""
        resp = client.get("/nonexistent")
        assert resp.status_code == 404
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"
        assert resp.headers.get("X-Frame-Options") == "DENY"
        assert resp.headers.get("Strict-Transport-Security") is not None

    def test_headers_are_not_overwritten_by_route(self):
        """Route handler cannot overwrite security headers (middleware sets after call_next)."""
        from apps.api.middleware.security import SecurityHeadersMiddleware

        app2 = FastAPI()
        app2.add_middleware(SecurityHeadersMiddleware)

        @app2.get("/override")
        async def override_route(_request: Request):
            return Response("overridden", headers={
                "X-Frame-Options": "SAMEORIGIN",
                "X-Content-Type-Options": "sniff",
            })

        with TestClient(app2) as c:
            resp = c.get("/override")
            # The middleware sets headers after call_next, so middleware values win
            assert resp.headers.get("X-Frame-Options") == "DENY"
            assert resp.headers.get("X-Content-Type-Options") == "nosniff"
