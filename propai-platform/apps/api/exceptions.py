"""공통 예외 및 에러 핸들러.

모든 API 예외를 표준 형식으로 변환한다.
"""

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from packages.schemas.models import ErrorResponse

# ★W1-C(R2)+핫픽스: 보고서 발행 게이트 hard 위반 → 4xx 매핑(공용 처리 1곳).
#   `app.*` 임포트는 모듈 상단에 두면 안 된다 — 이 파일은 루트 계약 스위트
#   (propai-platform/tests, cwd=propai-platform)에서도 `apps.api.exceptions`로 임포트되는데
#   그 컨텍스트에서는 `app` 패키지가 해석되지 않아 수집 자체가 깨진다(#425 CI 실측).
#   따라서 register_exception_handlers() 내부(앱 기동 컨텍스트에서만 실행)로 지연 임포트한다.


class PropAIError(Exception):
    """PropAI 기본 예외"""
    def __init__(
        self,
        error_code: str,
        message: str,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        details: dict | None = None,
    ) -> None:
        self.error_code = error_code
        self.message = message
        self.status_code = status_code
        self.details = details
        super().__init__(message)


class NotFoundError(PropAIError):
    """리소스를 찾을 수 없음"""
    def __init__(self, resource: str, resource_id: str) -> None:
        super().__init__(
            error_code="NOT_FOUND",
            message=f"{resource} '{resource_id}'을(를) 찾을 수 없습니다",
            status_code=status.HTTP_404_NOT_FOUND,
        )


class AuthenticationError(PropAIError):
    """인증 실패"""
    def __init__(self, message: str = "인증에 실패했습니다") -> None:
        super().__init__(
            error_code="AUTHENTICATION_FAILED",
            message=message,
            status_code=status.HTTP_401_UNAUTHORIZED,
        )


class PermissionDeniedError(PropAIError):
    """권한 부족"""
    def __init__(self, message: str = "권한이 없습니다") -> None:
        super().__init__(
            error_code="PERMISSION_DENIED",
            message=message,
            status_code=status.HTTP_403_FORBIDDEN,
        )


class ExternalServiceError(PropAIError):
    """외부 서비스 장애"""
    def __init__(self, service: str, message: str = "") -> None:
        super().__init__(
            error_code="EXTERNAL_SERVICE_ERROR",
            message=f"외부 서비스 '{service}' 호출 중 오류: {message}",
            status_code=status.HTTP_502_BAD_GATEWAY,
            details={"service": service},
        )


class TenantIsolationError(PropAIError):
    """테넌트 격리 위반"""
    def __init__(self) -> None:
        super().__init__(
            error_code="TENANT_ISOLATION_VIOLATION",
            message="테넌트 격리 정책 위반",
            status_code=status.HTTP_403_FORBIDDEN,
        )


def register_exception_handlers(app: FastAPI) -> None:
    """FastAPI 앱에 예외 핸들러를 등록한다."""

    @app.exception_handler(PropAIError)
    async def propai_exception_handler(request: Request, exc: PropAIError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=ErrorResponse(
                error_code=exc.error_code,
                message=exc.message,
                details=exc.details,
            ).model_dump(),
        )

    # 핫픽스: 앱 기동 컨텍스트에서만 임포트(모듈 상단 금지 — 위 주석 참조).
    from app.services.report.render.publish_gate import ReportPublishGateError

    @app.exception_handler(ReportPublishGateError)
    async def report_publish_gate_error_handler(
        request: Request, exc: ReportPublishGateError,
    ) -> JSONResponse:
        """W1-C(R2): 발행 게이트 hard 위반은 500이 아니라 정직한 409로 응답한다.

        violations 목록 전체를 details 에 실어 호출부(프론트/자동화)가 어떤 규칙이 왜
        걸렸는지 바로 알 수 있게 한다(예: approved_by 누락, 승인트랙 문서의 확정 표현).
        """
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content=ErrorResponse(
                error_code="REPORT_PUBLISH_GATE_VIOLATION",
                message=str(exc),
                details={
                    "violations": [
                        {"code": v.code, "message": v.message} for v in exc.violations
                    ],
                },
            ).model_dump(),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        # Sentry에 에러 전송
        try:
            import sentry_sdk

            sentry_sdk.capture_exception(exc)
        except ImportError:
            pass

        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorResponse(
                error_code="INTERNAL_SERVER_ERROR",
                message="서버 내부 오류가 발생했습니다",
            ).model_dump(),
        )
