"""API 버전 관리 및 Sunset 정책.

- /api/v1/* : 현재 안정 버전
- /api/v2/* : 차기 버전 (준비 시)
- /api/latest/{path} : 308 Permanent Redirect → 최신 안정 버전
- Sunset 헤더를 통한 비권장 버전 알림
"""


from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

# 현재 최신 안정 버전
CURRENT_STABLE_VERSION = "v1"

# Sunset 예정 버전 (있을 경우)
SUNSET_VERSIONS: dict[str, str] = {
    # "v1": "2026-12-31",  # 예시: v1 비권장 예정일
}


class VersionHeaderMiddleware(BaseHTTPMiddleware):
    """API 응답에 버전 관련 헤더를 추가하는 미들웨어."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)

        # API 버전 헤더 추가
        response.headers["X-API-Version"] = CURRENT_STABLE_VERSION

        # Sunset 헤더 추가 (비권장 버전인 경우)
        path = request.url.path
        for version, sunset_date in SUNSET_VERSIONS.items():
            if f"/api/{version}/" in path:
                response.headers["Sunset"] = sunset_date
                response.headers["Deprecation"] = "true"
                response.headers["Link"] = f'</api/{CURRENT_STABLE_VERSION}/>; rel="successor-version"'
                break

        return response


def create_latest_redirect_router() -> APIRouter:
    """/api/latest/{path} → 최신 안정 버전으로 308 리다이렉트하는 라우터."""
    router = APIRouter()

    @router.api_route(
        "/api/latest/{path:path}",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        status_code=308,
        include_in_schema=False,
    )
    async def redirect_to_latest(request: Request, path: str) -> RedirectResponse:
        """최신 안정 버전으로 308 Permanent Redirect. POST 메서드 보존."""
        target_url = f"/api/{CURRENT_STABLE_VERSION}/{path}"
        if request.url.query:
            target_url = f"{target_url}?{request.url.query}"
        return RedirectResponse(url=target_url, status_code=308)

    return router
