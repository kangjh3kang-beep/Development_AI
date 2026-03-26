"""예외 클래스 단위 테스트."""

from apps.api.exceptions import (
    AuthenticationError,
    ExternalServiceError,
    NotFoundError,
    PermissionDeniedError,
    PropAIError,
    TenantIsolationError,
)


class TestPropAIError:
    """기본 예외 클래스 검증."""

    def test_create(self) -> None:
        err = PropAIError(
            error_code="TEST_ERROR",
            message="테스트 오류",
            status_code=400,
        )
        assert err.error_code == "TEST_ERROR"
        assert err.message == "테스트 오류"
        assert err.status_code == 400
        assert err.details is None

    def test_with_details(self) -> None:
        err = PropAIError(
            error_code="DETAIL_ERROR",
            message="상세 오류",
            details={"key": "value"},
        )
        assert err.details == {"key": "value"}

    def test_is_exception(self) -> None:
        err = PropAIError(error_code="X", message="Y")
        assert isinstance(err, Exception)
        assert str(err) == "Y"


class TestNotFoundError:
    """리소스 미발견 예외 검증."""

    def test_create(self) -> None:
        err = NotFoundError("프로젝트", "abc-123")
        assert err.status_code == 404
        assert "프로젝트" in err.message
        assert "abc-123" in err.message
        assert err.error_code == "NOT_FOUND"


class TestAuthenticationError:
    """인증 오류 검증."""

    def test_default_message(self) -> None:
        err = AuthenticationError()
        assert err.status_code == 401
        assert "인증" in err.message

    def test_custom_message(self) -> None:
        err = AuthenticationError("토큰 만료")
        assert "토큰 만료" in err.message


class TestPermissionDeniedError:
    """권한 부족 오류 검증."""

    def test_create(self) -> None:
        err = PermissionDeniedError()
        assert err.status_code == 403
        assert err.error_code == "PERMISSION_DENIED"


class TestExternalServiceError:
    """외부 서비스 오류 검증."""

    def test_create(self) -> None:
        err = ExternalServiceError("V-World", "타임아웃")
        assert err.status_code == 502
        assert "V-World" in err.message
        assert err.details is not None
        assert err.details["service"] == "V-World"


class TestTenantIsolationError:
    """테넌트 격리 위반 검증."""

    def test_create(self) -> None:
        err = TenantIsolationError()
        assert err.status_code == 403
        assert err.error_code == "TENANT_ISOLATION_VIOLATION"
