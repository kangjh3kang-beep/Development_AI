"""자가성장 엔진 — 백엔드 요청 텔레메트리 미들웨어(설계서 §3.2).

모든 HTTP 요청의 latency_ms / status_code / 정규화 route / tenant_id 를
api_call 이벤트로 수집한다. 5xx 및 미처리 예외는 severity=error/critical 로
별도 이벤트화(스택 시그니처 정규화).

⚠️ 동기 INSERT 금지: capture_service.record_event() 로 in-memory 큐에 push 만
한다(논블로킹). 적재는 Celery 태스크(또는 인프로세스 폴백)가 담당.
요청경로 오버헤드 < 1ms 목표.

화이트리스트(수집 제외): /health, /metrics, /docs 등 고빈도·관측 경로 +
자기 자신(/api/v1/growth/events)은 수집 루프 방지.
"""

from __future__ import annotations

import hashlib
import re
import time
import traceback

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# 수집 제외 경로(prefix 매칭). 고빈도/관측/자기수집 루프 방지.
_EXCLUDE_PREFIXES = (
    "/health",
    "/metrics",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/favicon",
    "/api/v1/growth/events",  # 자기 자신 — 수집 무한루프 방지
)

# route 정규화용 path 파라미터 치환 패턴.
_RE_UUID = re.compile(
    r"/[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)
# 순수 숫자 ID 세그먼트(예: /projects/123). 버전 세그먼트(/api/v1)는
# 정규화 전에 prefix 로 분리·보존하므로 여기서는 단순 매칭으로 충분하다.
_RE_NUM = re.compile(r"/\d+")
# PNU(19자리)·긴 숫자/해시 토큰.
_RE_LONGTOKEN = re.compile(r"/[0-9a-fA-F]{16,}")
# 버전 세그먼트(/api/v1, /api/v2 …) — 정규화에서 제외(ID 아님).
_RE_VERSION = re.compile(r"^/api/v\d+")


def _normalize_route(path: str) -> str:
    """경로의 ID 세그먼트를 {id} 로 치환해 라우트를 정규화한다.

    ⚠️ /api/v\\d+ 의 버전 세그먼트(v1, v2)는 ID 가 아니므로 보존한다.
    진짜 ID 세그먼트(/projects/123 → /projects/{id})만 치환한다.
    """
    # 버전 prefix(/api/v1)를 떼어 보존하고, 나머지 경로만 숫자 ID 치환.
    m = _RE_VERSION.match(path)
    prefix = ""
    rest = path
    if m:
        prefix = m.group(0)
        rest = path[m.end():]

    out = _RE_UUID.sub("/{id}", rest)
    out = _RE_LONGTOKEN.sub("/{id}", out)
    out = _RE_NUM.sub("/{id}", out)
    return prefix + out


def _excluded(path: str) -> bool:
    return any(path.startswith(p) for p in _EXCLUDE_PREFIXES)


def _stack_signature(exc: BaseException) -> str:
    """예외 스택을 정규화 해시로 압축(군집화용, 가변 토큰 제거)."""
    try:
        tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        # 행번호·주소·16진 토큰 등 가변 부분 제거 후 해시.
        norm = re.sub(r"line \d+", "line N", tb)
        norm = re.sub(r"0x[0-9a-fA-F]+", "0xADDR", norm)
        norm = re.sub(r"\d{6,}", "N", norm)
        return hashlib.sha256(norm.encode("utf-8")).hexdigest()[:16]
    except Exception:  # noqa: BLE001
        return "unknown"


class GrowthTelemetryMiddleware(BaseHTTPMiddleware):
    """요청 단위 텔레메트리 수집(논블로킹 큐 push)."""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if _excluded(path):
            return await call_next(request)

        # 지연 import: 모듈 미존재 환경에서도 앱 부팅 불변.
        try:
            from app.core.request_context import get_current_tenant_id, get_current_user_id
            from app.services.growth import capture_service
        except Exception:  # noqa: BLE001
            return await call_next(request)

        route = _normalize_route(path)
        method = request.method
        t0 = time.perf_counter()
        status_code = 500
        exc_to_raise: BaseException | None = None
        response: Response | None = None
        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception as exc:  # noqa: BLE001 — 예외도 이벤트화 후 재전파.
            exc_to_raise = exc
            status_code = 500

        latency_ms = int((time.perf_counter() - t0) * 1000)

        try:
            tenant_id = get_current_tenant_id()
            user_id = get_current_user_id()
            if exc_to_raise is not None:
                # 미처리 예외 → critical.
                capture_service.record_event(
                    "api_error",
                    {
                        "surface": "api",
                        "route": route,
                        "status_code": status_code,
                        "latency_ms": latency_ms,
                        "severity": "critical",
                        "tenant_id": tenant_id,
                        "user_id": user_id,
                        "payload": {
                            "method": method,
                            "exc_type": type(exc_to_raise).__name__,
                            "stack_sig": _stack_signature(exc_to_raise),
                        },
                    },
                )
            elif status_code >= 500:
                capture_service.record_event(
                    "api_error",
                    {
                        "surface": "api",
                        "route": route,
                        "status_code": status_code,
                        "latency_ms": latency_ms,
                        "severity": "error",
                        "tenant_id": tenant_id,
                        "user_id": user_id,
                        "payload": {"method": method},
                    },
                )
            else:
                # 정상/4xx 는 api_call 로(4xx 는 warn).
                capture_service.record_event(
                    "api_call",
                    {
                        "surface": "api",
                        "route": route,
                        "status_code": status_code,
                        "latency_ms": latency_ms,
                        "severity": "warn" if status_code >= 400 else "info",
                        "tenant_id": tenant_id,
                        "user_id": user_id,
                        "payload": {"method": method},
                    },
                )
        except Exception:  # noqa: BLE001 — 수집 실패가 요청을 깨뜨리지 않는다.
            pass

        if exc_to_raise is not None:
            raise exc_to_raise
        return response
