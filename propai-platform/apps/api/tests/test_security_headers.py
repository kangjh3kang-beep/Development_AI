"""보안 헤더 미들웨어 테스트.

SecurityHeadersMiddleware가 OWASP 권장 헤더를 정상 추가하는지 검증.
"""

import pytest
from httpx import ASGITransport, AsyncClient
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from apps.api.middleware import SecurityHeadersMiddleware


def _make_test_app() -> Starlette:
    """테스트용 최소 앱 생성."""

    async def homepage(request: Request) -> JSONResponse:
        return JSONResponse({"status": "ok"})

    app = Starlette(routes=[Route("/", homepage)])
    app.add_middleware(SecurityHeadersMiddleware)
    return app


@pytest.fixture()
def test_app() -> Starlette:
    return _make_test_app()


@pytest.mark.asyncio
async def test_x_content_type_options(test_app: Starlette) -> None:
    """X-Content-Type-Options: nosniff 헤더 확인."""
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.get("/")
    assert response.headers.get("x-content-type-options") == "nosniff"


@pytest.mark.asyncio
async def test_x_frame_options(test_app: Starlette) -> None:
    """X-Frame-Options: DENY 헤더 확인."""
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.get("/")
    assert response.headers.get("x-frame-options") == "DENY"


@pytest.mark.asyncio
async def test_strict_transport_security(test_app: Starlette) -> None:
    """Strict-Transport-Security (HSTS) 헤더 확인."""
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.get("/")
    hsts = response.headers.get("strict-transport-security", "")
    assert "max-age=31536000" in hsts
    assert "includeSubDomains" in hsts


@pytest.mark.asyncio
async def test_x_xss_protection(test_app: Starlette) -> None:
    """X-XSS-Protection 헤더 확인."""
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.get("/")
    assert response.headers.get("x-xss-protection") == "1; mode=block"


@pytest.mark.asyncio
async def test_referrer_policy(test_app: Starlette) -> None:
    """Referrer-Policy 헤더 확인."""
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.get("/")
    assert response.headers.get("referrer-policy") == "strict-origin-when-cross-origin"


@pytest.mark.asyncio
async def test_permissions_policy(test_app: Starlette) -> None:
    """Permissions-Policy 헤더 확인."""
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.get("/")
    pp = response.headers.get("permissions-policy", "")
    assert "camera=()" in pp
    assert "microphone=()" in pp


@pytest.mark.asyncio
async def test_content_security_policy(test_app: Starlette) -> None:
    """Content-Security-Policy 헤더 확인."""
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.get("/")
    csp = response.headers.get("content-security-policy", "")
    assert "default-src 'self'" in csp
    assert "frame-ancestors 'none'" in csp


@pytest.mark.asyncio
async def test_all_security_headers_present(test_app: Starlette) -> None:
    """모든 보안 헤더가 동시에 존재하는지 확인."""
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.get("/")

    required_headers = [
        "x-content-type-options",
        "x-frame-options",
        "x-xss-protection",
        "strict-transport-security",
        "referrer-policy",
        "permissions-policy",
        "content-security-policy",
    ]
    for header in required_headers:
        assert header in response.headers, f"누락된 보안 헤더: {header}"
