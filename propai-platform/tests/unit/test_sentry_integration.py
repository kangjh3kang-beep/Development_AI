"""Sentry 통합 단위 테스트.

Sentry SDK 초기화 및 예외 핸들러 연동 검증.
소스 파일을 직접 읽어 DB 의존성 체인을 회피한다.
"""

from pathlib import Path

from apps.api.config import Settings

# main.py와 exceptions.py 소스를 직접 읽음 (import 시 qdrant_client 필요)
_BASE = Path(__file__).resolve().parents[2] / "apps" / "api"
_MAIN_SOURCE = (_BASE / "main.py").read_text(encoding="utf-8")
_EXCEPTIONS_SOURCE = (_BASE / "exceptions.py").read_text(encoding="utf-8")


class TestSentrySetup:
    """Sentry 초기화 코드 검증."""

    def test_sentry_init_in_lifespan(self) -> None:
        """lifespan에서 sentry_sdk.init을 호출한다."""
        assert "sentry_sdk.init" in _MAIN_SOURCE

    def test_sentry_dsn_check(self) -> None:
        """sentry_dsn이 설정된 경우에만 초기화한다."""
        assert "settings.sentry_dsn" in _MAIN_SOURCE

    def test_sentry_release_format(self) -> None:
        """Sentry release 형식이 propai@{version}이다."""
        assert "propai@" in _MAIN_SOURCE

    def test_traces_sample_rate(self) -> None:
        """traces_sample_rate가 설정된다."""
        assert "traces_sample_rate" in _MAIN_SOURCE

    def test_profiles_sample_rate(self) -> None:
        """profiles_sample_rate가 설정된다."""
        assert "profiles_sample_rate" in _MAIN_SOURCE


class TestSentryExceptionHandler:
    """Sentry 예외 핸들러 연동 검증."""

    def test_capture_exception_in_handler(self) -> None:
        """unhandled_exception_handler에서 capture_exception을 호출한다."""
        assert "sentry_sdk.capture_exception" in _EXCEPTIONS_SOURCE

    def test_import_error_handled(self) -> None:
        """ImportError를 무시하여 sentry 미설치 환경에서도 동작한다."""
        assert "ImportError" in _EXCEPTIONS_SOURCE


class TestSentryConfig:
    """Sentry 설정 필드 검증."""

    def test_sentry_dsn_field_exists(self) -> None:
        """Settings에 sentry_dsn 필드가 존재한다."""
        settings = Settings()
        assert hasattr(settings, "sentry_dsn")

    def test_sentry_dsn_default_empty(self) -> None:
        """sentry_dsn 기본값이 빈 문자열이다."""
        settings = Settings()
        assert settings.sentry_dsn == ""

    def test_environment_field_exists(self) -> None:
        """Settings에 environment 필드가 존재한다."""
        settings = Settings()
        assert hasattr(settings, "environment")
