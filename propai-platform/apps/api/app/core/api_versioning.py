"""API 버전 관리.

/api/latest → /api/v2 308 Permanent Redirect 를 처리한다.
"""

from typing import Optional


class APIVersionRouter:
    """API 버전 라우팅 관리.

    /api/latest/* 요청을 /api/v2/*로 308 리다이렉트한다.
    """

    LATEST_VERSION = "v2"
    REDIRECT_STATUS = 308  # Permanent Redirect

    def __init__(self, latest_version: Optional[str] = None):
        self._latest = latest_version or self.LATEST_VERSION
        self._version_map: dict[str, str] = {
            "v1": "/api/v1",
            "v2": "/api/v2",
            "latest": f"/api/{self._latest}",
        }

    @property
    def latest_version(self) -> str:
        return self._latest

    def resolve_path(self, path: str) -> tuple[Optional[str], bool]:
        """경로를 해석하여 (리다이렉트 대상, 리다이렉트 필요 여부)를 반환.

        /api/latest/xxx → (/api/v2/xxx, True)
        /api/v1/xxx → (None, False)
        """
        if path.startswith("/api/latest"):
            suffix = path[len("/api/latest"):]
            return f"/api/{self._latest}{suffix}", True
        return None, False

    def get_version_info(self) -> dict:
        """API 버전 정보."""
        return {
            "latest": self._latest,
            "supported": list(self._version_map.keys()),
            "endpoints": dict(self._version_map),
            "redirect_status": self.REDIRECT_STATUS,
        }

    def is_deprecated(self, version: str) -> bool:
        """특정 버전의 폐기 여부."""
        # v1은 폐기 예정
        return version == "v1"


class APIVersionMiddleware:
    """/api/latest → /api/v2 ASGI 리다이렉트 미들웨어."""

    def __init__(self, app, latest_version: str = "v2"):
        self.app = app
        self._router = APIVersionRouter(latest_version)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        redirect_to, should_redirect = self._router.resolve_path(path)

        if should_redirect and redirect_to:
            # 308 Permanent Redirect
            qs = scope.get("query_string", b"")
            if qs:
                redirect_to += f"?{qs.decode()}"

            await send({
                "type": "http.response.start",
                "status": 308,
                "headers": [
                    (b"location", redirect_to.encode()),
                    (b"content-type", b"text/plain"),
                ],
            })
            await send({
                "type": "http.response.body",
                "body": f"Permanent Redirect to {redirect_to}".encode(),
            })
            return

        await self.app(scope, receive, send)
