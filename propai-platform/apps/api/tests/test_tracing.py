"""OpenTelemetry 분산추적 모듈 테스트.

init_tracing, instrument_fastapi 가 graceful하게 동작하는지 검증.
"""

from unittest.mock import MagicMock, patch

import pytest


class TestTracingImport:
    """tracing 모듈 임포트 테스트."""

    def test_init_tracing_import(self):
        """init_tracing 함수 임포트 확인."""
        from apps.api.core.tracing import init_tracing
        assert callable(init_tracing)

    def test_instrument_fastapi_import(self):
        """instrument_fastapi 함수 임포트 확인."""
        from apps.api.core.tracing import instrument_fastapi
        assert callable(instrument_fastapi)

    def test_init_tracing_returns_false_on_import_error(self):
        """OTel 패킴지 미설치 시 False 반환."""
        from apps.api.core.tracing import init_tracing
        # init_tracing returns bool (False if OTel not installed)
        result = init_tracing()
        assert result is False

    def test_init_tracing_graceful_fallback(self):
        """초기화 실패 시 예외로 False 반환."""
        from apps.api.core.tracing import init_tracing
        # 기별 값 호출으로 섰공 또는 False (OTel 미설치) 반환
        result = init_tracing()
        assert isinstance(result, bool)

    def test_instrument_fastapi_graceful(self):
        """자동 계측 실패 시 예외로 False 반환."""
        from apps.api.core.tracing import instrument_fastapi
        app = MagicMock()
        result = instrument_fastapi(app)
        assert isinstance(result, bool)


class TestOtelConfig:
    """OpenTelemetry 설정 값 검증."""

    def test_otel_settings_default(self, monkeypatch):
        """기본 OTel 설정값 확인 (.env/환경변수 오버라이드 격리)."""
        monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
        from apps.api.config import Settings
        s = Settings(_env_file=None)
        assert s.otel_exporter_otlp_endpoint == "http://localhost:4318"
        assert s.otel_service_name == "propai-api"
        assert s.otel_sample_rate == 1.0
        assert s.otel_enabled is False
