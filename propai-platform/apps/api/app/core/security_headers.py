"""보안 헤더 미들웨어.

OWASP 권장 보안 헤더(HSTS, X-Content-Type-Options, X-Frame-Options,
CSP, Referrer-Policy, X-XSS-Protection)를 모든 응답에 추가한다.
"""

from typing import Optional


# 기본 보안 헤더
DEFAULT_SECURITY_HEADERS: dict[str, str] = {
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "X-XSS-Protection": "1; mode=block",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Content-Security-Policy": "default-src 'self'",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(self)",
    "X-Permitted-Cross-Domain-Policies": "none",
}


class SecurityHeadersMiddleware:
    """ASGI 보안 헤더 미들웨어.

    모든 HTTP 응답에 OWASP 권장 보안 헤더를 추가한다.
    """

    def __init__(self, app, headers: Optional[dict[str, str]] = None):
        self.app = app
        self._headers = headers or DEFAULT_SECURITY_HEADERS

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        header_pairs = [
            (k.lower().encode(), v.encode())
            for k, v in self._headers.items()
        ]

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                existing = list(message.get("headers", []))
                existing.extend(header_pairs)
                message = {**message, "headers": existing}
            await send(message)

        await self.app(scope, receive, send_with_headers)

    @property
    def header_count(self) -> int:
        """설정된 헤더 수."""
        return len(self._headers)

    def get_headers(self) -> dict[str, str]:
        """현재 설정된 헤더 딕셔너리 사본."""
        return dict(self._headers)

    @staticmethod
    def validate_csp(csp: str) -> bool:
        """CSP 문자열 기본 유효성 검증."""
        required = ["default-src"]
        return any(d in csp for d in required)
