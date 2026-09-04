"""RFC 9457 problem+json 오류봉투 — C2R 신규 표면 전용 표준 오류 응답(WP-L · A3).

이 파일이 푸는 문제(쉬운 설명):
- 지금까지 API 오류는 라우터마다 제각각(FastAPI 기본 {"detail": ...}·PropAIError {"error_code": ...})이라
  기계가 오류를 일관되게 읽기 어려웠다. RFC 9457은 '오류를 담는 표준 봉투'다 — type(오류 종류 URI)·
  title(짧은 요약)·status(HTTP 코드)·detail(사람이 읽는 상세)·instance(이 요청 식별)의 5필드.
- 본 모듈은 이 표준 봉투와, 그것을 내보내는 공용 예외 핸들러를 제공한다.

★스코프(계획서 §4 WP-L 명시): problem+json은 **신규 C2R 표면부터 opt-in**으로만 적용한다.
  대상 = access · survey/coordinate · basis · design-runs · submission-bundle. 그 외 **기존 전
  라우터 소급은 스코프아웃**이다(FastAPI 기본/PropAIError 봉투 그대로 유지 — 무회귀). 이 경계는
  is_problem_surface(path)가 경로로 판정하며, 그 밖의 경로는 FastAPI 기본 핸들러에 그대로 위임한다.

★기존 예외와의 공존(충돌 없음):
- ProblemException(신규 타입)은 **항상** problem+json으로 렌더된다(표면 무관 — 명시 opt-in).
- HTTPException·RequestValidationError는 **C2R 표면 경로일 때만** problem+json으로 렌더되고,
  그 밖에서는 원래 FastAPI 기본 핸들러(http_exception_handler 등)에 위임한다 → 기존 응답 형태 불변.
- PropAIError·RateLimitExceeded 등 다른 타입의 기존 핸들러는 건드리지 않는다(타입이 달라 무간섭).

★additive 등록: register_problem_handlers(app)는 main.py에서 기존 register_exception_handlers 뒤에
  한 줄로 추가 호출된다. 등록하는 예외 타입(ProblemException·StarletteHTTPException·
  RequestValidationError)은 기존 코드가 등록하지 않은 타입이므로 덮어쓰기 충돌이 없다.
"""
from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exception_handlers import (
    http_exception_handler,
    request_validation_exception_handler,
)
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

# problem+json 미디어 타입(RFC 9457 §3) — 일반 application/json과 구분되는 표준 시그니처.
PROBLEM_MEDIA_TYPE = "application/problem+json"

# type 미지정 시 기본값(RFC 9457 §4.1 권고) — "특별한 의미 없음"을 뜻하는 관례적 URI.
DEFAULT_PROBLEM_TYPE = "about:blank"


# ── C2R 신규 표면 경로 판정(opt-in 경계) ──────────────────────────────────────
# 접두로 판정하는 전용 표면(라우터 전체가 C2R 신규 표면).
_PROBLEM_SURFACE_PREFIXES: tuple[str, ...] = (
    "/api/v1/access",
    "/api/v1/survey/coordinate",
    "/api/v1/basis",
    "/api/v1/design-runs",
)
# 접미로 판정하는 개별 엔드포인트 — design_v61 라우터(/api/v1/design/*)는 대부분 스코프아웃이라
# 접두로 잡으면 과대적용된다. submission-bundle '한 엔드포인트만' 접미로 정확히 집는다.
_PROBLEM_SURFACE_SUFFIXES: tuple[str, ...] = (
    "/submission-bundle",
)


def is_problem_surface(path: str) -> bool:
    """요청 경로가 problem+json opt-in 대상(신규 C2R 표면)인지 판정한다.

    ★스코프아웃 보호: design_v61 라우터의 다른 엔드포인트(/api/v1/design/{id}/mass 등)는 여기서
      False가 되어 기존 오류 봉투를 그대로 쓴다 — 접미 매칭으로 submission-bundle만 정확히 포함한다.
    """
    p = path or ""
    if any(p.startswith(prefix) for prefix in _PROBLEM_SURFACE_PREFIXES):
        return True
    return any(p.rstrip("/").endswith(suffix) for suffix in _PROBLEM_SURFACE_SUFFIXES)


# ── problem+json 응답 모델(스키마 검증 대상) ─────────────────────────────────
class ProblemDetail(BaseModel):
    """RFC 9457 problem+json 본문 — type·title·status는 계약상 항상 존재한다.

    model_config extra='allow'로 확장 멤버(code·errors 등)를 허용한다(RFC 9457 §3.2 '확장 멤버').
    """

    model_config = {"extra": "allow"}

    type: str = Field(default=DEFAULT_PROBLEM_TYPE, description="오류 종류 식별 URI(또는 about:blank)")
    title: str = Field(..., description="오류의 짧고 사람이 읽는 요약(상태코드에 대해 안정적)")
    status: int = Field(..., description="HTTP 상태코드(본문에도 복제 — RFC 9457 §3.1)")
    detail: str | None = Field(default=None, description="이 오류 발생에 특정한 사람이 읽는 상세")
    instance: str | None = Field(default=None, description="이 오류 발생을 식별하는 URI(보통 요청 경로)")


def build_problem(
    *,
    status: int,
    title: str,
    detail: str | None = None,
    type_: str = DEFAULT_PROBLEM_TYPE,
    instance: str | None = None,
    code: str | None = None,
    extensions: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """problem+json 본문 dict를 만든다(결정적·순수). code는 도메인 오류코드 확장 멤버."""
    body: dict[str, Any] = {
        "type": type_ or DEFAULT_PROBLEM_TYPE,
        "title": title,
        "status": int(status),
    }
    if detail is not None:
        body["detail"] = detail
    if instance is not None:
        body["instance"] = instance
    if code is not None:
        body["code"] = code
    if extensions:
        # 예약 멤버는 확장이 덮어쓰지 못하게 한다(계약 필드 보호).
        for k, v in extensions.items():
            if k not in ("type", "title", "status"):
                body[k] = v
    return body


def problem_response(
    *,
    status: int,
    title: str,
    detail: str | None = None,
    type_: str = DEFAULT_PROBLEM_TYPE,
    instance: str | None = None,
    code: str | None = None,
    extensions: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    """problem+json JSONResponse(미디어타입 application/problem+json)를 만든다."""
    body = build_problem(
        status=status, title=title, detail=detail, type_=type_,
        instance=instance, code=code, extensions=extensions,
    )
    return JSONResponse(
        status_code=int(status), content=body,
        media_type=PROBLEM_MEDIA_TYPE, headers=headers,
    )


class ProblemException(Exception):  # noqa: N818 — HTTPException 관례(Error 접미 없음)를 따른다
    """problem+json으로 렌더될 도메인 예외 — 표면 무관 항상 problem+json(명시 opt-in).

    신규 C2R 라우터(design-runs 등)에서 raise하면 등록된 핸들러가 RFC 9457 봉투로 응답한다.
    HTTPException과 달리 type·code 등 풍부한 필드를 직접 실을 수 있다.
    """

    def __init__(
        self,
        *,
        status: int,
        title: str,
        detail: str | None = None,
        type_: str = DEFAULT_PROBLEM_TYPE,
        code: str | None = None,
        extensions: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status = int(status)
        self.title = title
        self.detail = detail
        self.type_ = type_ or DEFAULT_PROBLEM_TYPE
        self.code = code
        self.extensions = extensions or {}
        self.headers = headers or {}
        super().__init__(detail or title)

    def to_response(self, instance: str | None = None) -> JSONResponse:
        return problem_response(
            status=self.status, title=self.title, detail=self.detail,
            type_=self.type_, instance=instance, code=self.code,
            extensions=self.extensions, headers=self.headers or None,
        )


# 상태코드 → 관례적 title(detail 미지정 시 사람이 읽을 안정적 요약).
_STATUS_TITLES: dict[int, str] = {
    400: "Bad Request",
    401: "Unauthorized",
    403: "Forbidden",
    404: "Not Found",
    409: "Conflict",
    413: "Payload Too Large",
    422: "Unprocessable Entity",
    429: "Too Many Requests",
    500: "Internal Server Error",
    502: "Bad Gateway",
    503: "Service Unavailable",
}


def _title_for(status: int) -> str:
    return _STATUS_TITLES.get(int(status), "Error")


def register_problem_handlers(app: FastAPI) -> None:
    """FastAPI 앱에 problem+json 핸들러를 additive 등록한다(main.py에서 1회 호출).

    등록 타입 3종:
      1) ProblemException  : 항상 problem+json(표면 무관 — 명시 opt-in 타입).
      2) StarletteHTTPException(=FastAPI HTTPException 상위) : C2R 표면 경로일 때만 problem+json,
         그 밖은 FastAPI 기본 http_exception_handler에 위임(기존 봉투·헤더 그대로 — 무회귀).
      3) RequestValidationError(422) : C2R 표면 경로일 때만 problem+json, 그 밖은 기본 위임.
    """

    @app.exception_handler(ProblemException)
    async def _problem_exception_handler(request: Request, exc: ProblemException) -> Response:
        return exc.to_response(instance=str(request.url.path))

    @app.exception_handler(StarletteHTTPException)
    async def _http_exception_handler(request: Request, exc: StarletteHTTPException) -> Response:
        # ★스코프 경계: C2R 표면이 아니면 기존 FastAPI 기본 핸들러로 위임(응답 형태·헤더 불변).
        if not is_problem_surface(request.url.path):
            return await http_exception_handler(request, exc)
        detail = exc.detail
        # detail이 dict면(예: submission-bundle 422 {"message","missing"}) 확장 멤버로 편입.
        extensions: dict[str, Any] | None = None
        detail_text: str | None
        if isinstance(detail, dict):
            detail_text = str(detail.get("message") or detail.get("detail") or "")
            extensions = {k: v for k, v in detail.items() if k not in ("message", "detail")}
        elif detail is None:
            detail_text = None
        else:
            detail_text = str(detail)
        return problem_response(
            status=exc.status_code,
            title=_title_for(exc.status_code),
            detail=detail_text or None,
            instance=str(request.url.path),
            extensions=extensions,
            headers=dict(getattr(exc, "headers", None) or {}) or None,
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> Response:
        # ★스코프 경계: C2R 표면이 아니면 기존 FastAPI 기본 422 핸들러로 위임.
        if not is_problem_surface(request.url.path):
            return await request_validation_exception_handler(request, exc)
        return problem_response(
            status=422,
            title=_title_for(422),
            detail="요청 본문·파라미터 검증에 실패했습니다.",
            instance=str(request.url.path),
            code="VALIDATION_ERROR",
            # RequestValidationError.errors()는 직렬화 가능한 오류 목록(필드·사유).
            extensions={"errors": exc.errors()},
        )
