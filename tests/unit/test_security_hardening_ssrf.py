"""Tests for the SSRF guard on /security-hardening/pen-test/scan target_url."""

from unittest.mock import patch

import pytest
from fastapi import HTTPException

from api.routers.security_hardening import _validate_pen_test_target


def _fake_getaddrinfo(ip):
    def _inner(host, port):
        return [(None, None, None, None, (ip, 0))]
    return _inner


class TestValidatePenTestTarget:
    def test_allows_public_host(self):
        with patch("socket.getaddrinfo", _fake_getaddrinfo("93.184.216.34")):
            assert _validate_pen_test_target("https://example.com") == "https://example.com"

    def test_rejects_non_http_scheme(self):
        with pytest.raises(HTTPException) as exc:
            _validate_pen_test_target("ftp://example.com")
        assert exc.value.status_code == 400

    def test_rejects_missing_host(self):
        with pytest.raises(HTTPException) as exc:
            _validate_pen_test_target("https://")
        assert exc.value.status_code == 400

    def test_rejects_localhost_hostname(self):
        with pytest.raises(HTTPException) as exc:
            _validate_pen_test_target("http://localhost")
        assert exc.value.status_code == 400

    def test_rejects_loopback_ip(self):
        with patch("socket.getaddrinfo", _fake_getaddrinfo("127.0.0.1")):
            with pytest.raises(HTTPException) as exc:
                _validate_pen_test_target("http://loopback.example")
            assert exc.value.status_code == 400

    def test_rejects_private_ip(self):
        with patch("socket.getaddrinfo", _fake_getaddrinfo("10.0.0.5")):
            with pytest.raises(HTTPException) as exc:
                _validate_pen_test_target("http://internal.example")
            assert exc.value.status_code == 400

    def test_rejects_link_local_metadata_ip(self):
        with patch("socket.getaddrinfo", _fake_getaddrinfo("169.254.169.254")):
            with pytest.raises(HTTPException) as exc:
                _validate_pen_test_target("http://metadata.example")
            assert exc.value.status_code == 400

    def test_rejects_unresolvable_host(self):
        import socket as socket_mod
        with patch("socket.getaddrinfo", side_effect=socket_mod.gaierror):
            with pytest.raises(HTTPException) as exc:
                _validate_pen_test_target("http://does-not-exist.invalid")
            assert exc.value.status_code == 400
