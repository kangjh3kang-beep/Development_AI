"""공통 미들웨어.

요청 ID 할당, 로깅 컨텍스트 바인딩, CORS 설정, 보안 헤더.
"""

import time
import uuid

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from apps.api.config import get_settings
from apps.api.logging_config import get_logger

logger = get_logger(__name__)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """보안 헤더 미들웨어.

    OWASP 권장 보안 헤더를 모든 응답에 추가한다:
    - X-Content-Type-Options: nosniff
    - X-Frame-Options: DENY
    - X-XSS-Protection: 1; mode=block
    - Strict-Transport-Security: max-age=31536000; includeSubDomains
    - Referrer-Policy: strict-origin-when-cross-origin
    - Permissions-Policy: camera=(), microphone=(), geolocation=()
    - Content-Security-Policy: default-src 'self'
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)

        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; "
            "font-src 'self' data:; "
            "connect-src 'self' https: wss:; "
            "frame-ancestors 'none'"
        )

        return response


class RequestContextMiddleware(BaseHTTPMiddleware):
    """요청 컨텍스트 미들웨어.

    모든 요청에 request_id를 할당하고,
    로깅 컨텍스트에 request_id, method, path를 바인딩한다.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = str(uuid.uuid4())
        start_time = time.perf_counter()

        # structlog 컨텍스트에 바인딩
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
        )

        # 요청 상태에 request_id 저장
        request.state.request_id = request_id

        response = await call_next(request)

        # 응답 헤더에 request_id 추가
        response.headers["X-Request-ID"] = request_id

        # 요청 처리 시간 로깅
        duration_ms = (time.perf_counter() - start_time) * 1000
        logger.info(
            "요청 처리 완료",
            status_code=response.status_code,
            duration_ms=round(duration_ms, 2),
        )

        return response


def setup_middlewares(app: FastAPI) -> None:
    """앱에 미들웨어를 등록한다."""
    settings = get_settings()

    # CORS 설정 — 환경변수 CORS_ORIGINS에서 콤마 구분 목록 읽기
    origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        # ★ 분양 현장앱은 X-Site-Code/X-Site-Token 커스텀 헤더로 요청한다. 이게 allow_headers 에
        #   없으면 브라우저 CORS 프리플라이트(OPTIONS)가 "Disallowed CORS headers"로 400 되고,
        #   서비스워커가 이를 합성 503("오프라인")으로 표시 → 현장 진입 503의 근본원인. 반드시 포함.
        # ★★2026-08-16 — **같은 결함이 재발했다.** 위 주석이 경고한 그대로, 이번엔
        #   `Idempotency-Key` 가 빠져 있었다. 프론트는 2026-07 부터 설계 승인 버튼에서 그 헤더를
        #   보내고 있었고(`CADEditor.tsx`), 프로덕션 프리플라이트는 그 요청을 **400 으로 거절**했다
        #   (실측: `OPTIONS /api/v1/design-runs/{id}/approve` + idempotency-key → 400, 빼면 200).
        #   즉 배포된 기능 하나가 브라우저에서 한 번도 동작한 적이 없다.
        # ★근본은 이 목록이 **손으로 관리되는 화이트리스트**라는 것이다 — 프론트가 헤더를 새로
        #   추가해도 여기가 따라오지 않고, 실패가 CORS 400 이라 백엔드 로그에도 안 남는다.
        #   그래서 목록을 늘리는 것으로 끝내지 않고 **파생형 락**을 함께 둔다:
        #   `tests/test_cors_custom_headers_derived.py` 가 프론트 소스에서 실제 전송 헤더를
        #   긁어와 이 목록과 대조한다(사람이 센 목록이 아니라 코드에서 파생).
        allow_headers=["Authorization", "Content-Type", "X-Request-ID", "Accept",
                       "X-Site-Code", "X-Site-Token", "Idempotency-Key"],
        expose_headers=["X-Request-ID"],
    )

    # 보안 헤더 (OWASP 권장)
    app.add_middleware(SecurityHeadersMiddleware)

    # 요청 컨텍스트
    app.add_middleware(RequestContextMiddleware)
