"""보안 헤더 미들웨어 테스트."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestSecurityHeaders:
    """SecurityHeadersMiddleware 테스트."""

    def test_default_headers_count(self):
        from app.core.security_headers import DEFAULT_SECURITY_HEADERS
        assert len(DEFAULT_SECURITY_HEADERS) == 8

    def test_hsts_header_present(self):
        from app.core.security_headers import DEFAULT_SECURITY_HEADERS
        assert "Strict-Transport-Security" in DEFAULT_SECURITY_HEADERS
        assert "31536000" in DEFAULT_SECURITY_HEADERS["Strict-Transport-Security"]

    def test_content_type_options(self):
        from app.core.security_headers import DEFAULT_SECURITY_HEADERS
        assert DEFAULT_SECURITY_HEADERS["X-Content-Type-Options"] == "nosniff"

    def test_frame_options_deny(self):
        from app.core.security_headers import DEFAULT_SECURITY_HEADERS
        assert DEFAULT_SECURITY_HEADERS["X-Frame-Options"] == "DENY"

    def test_csp_default_src(self):
        from app.core.security_headers import DEFAULT_SECURITY_HEADERS
        assert "default-src" in DEFAULT_SECURITY_HEADERS["Content-Security-Policy"]

    def test_referrer_policy(self):
        from app.core.security_headers import DEFAULT_SECURITY_HEADERS
        assert DEFAULT_SECURITY_HEADERS["Referrer-Policy"] == "strict-origin-when-cross-origin"

    def test_middleware_header_count(self):
        from app.core.security_headers import SecurityHeadersMiddleware
        mw = SecurityHeadersMiddleware(app=None)
        assert mw.header_count == 8

    def test_middleware_get_headers(self):
        from app.core.security_headers import SecurityHeadersMiddleware
        mw = SecurityHeadersMiddleware(app=None)
        headers = mw.get_headers()
        assert isinstance(headers, dict)
        assert "X-XSS-Protection" in headers

    def test_custom_headers(self):
        from app.core.security_headers import SecurityHeadersMiddleware
        custom = {"X-Custom": "value"}
        mw = SecurityHeadersMiddleware(app=None, headers=custom)
        assert mw.header_count == 1
        assert mw.get_headers()["X-Custom"] == "value"

    def test_validate_csp_valid(self):
        from app.core.security_headers import SecurityHeadersMiddleware
        assert SecurityHeadersMiddleware.validate_csp("default-src 'self'") is True

    def test_validate_csp_invalid(self):
        from app.core.security_headers import SecurityHeadersMiddleware
        assert SecurityHeadersMiddleware.validate_csp("script-src 'unsafe-inline'") is False

    def test_xss_protection_header(self):
        from app.core.security_headers import DEFAULT_SECURITY_HEADERS
        assert DEFAULT_SECURITY_HEADERS["X-XSS-Protection"] == "1; mode=block"
