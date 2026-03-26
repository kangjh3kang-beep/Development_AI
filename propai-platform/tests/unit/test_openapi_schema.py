"""OpenAPI 스키마 구조 단위 테스트.

main.py와 라우터 소스를 분석하여 엔드포인트 등록 검증.
앱 인스턴스 없이 소스 코드 패턴으로 검증한다 (DB 의존성 회피).
"""

from pathlib import Path

from packages.schemas.models import (
    HealthResponse,
    ProjectResponse,
    WebhookDeliveryResponse,
    WebhookResponse,
)

_BASE = Path(__file__).resolve().parents[2] / "apps" / "api"
_MAIN_SOURCE = (_BASE / "main.py").read_text(encoding="utf-8")


# ──────────────────────────────────────
# main.py 라우터 등록 검증
# ──────────────────────────────────────


class TestRouterRegistration:
    """main.py에 라우터가 올바르게 등록되어 있다."""

    def test_projects_router_registered(self) -> None:
        """프로젝트 라우터가 등록되어 있다."""
        assert 'prefix="/api/v1/projects"' in _MAIN_SOURCE

    def test_webhooks_router_registered(self) -> None:
        """웹훅 라우터가 등록되어 있다."""
        assert 'prefix="/api/v1/webhooks"' in _MAIN_SOURCE

    def test_auth_router_registered(self) -> None:
        """인증 라우터가 등록되어 있다."""
        assert 'prefix="/api/v1/auth"' in _MAIN_SOURCE

    def test_avm_router_registered(self) -> None:
        """AVM 라우터가 등록되어 있다."""
        assert 'prefix="/api/v1/avm"' in _MAIN_SOURCE

    def test_health_endpoint_exists(self) -> None:
        """/health 엔드포인트가 정의되어 있다."""
        assert '"/health"' in _MAIN_SOURCE
        assert "health_check" in _MAIN_SOURCE

    def test_metrics_mounted(self) -> None:
        """/metrics 엔드포인트가 마운트되어 있다."""
        assert '"/metrics"' in _MAIN_SOURCE

    def test_all_routers_imported(self) -> None:
        """필수 라우터 모듈이 모두 import되어 있다."""
        required = [
            "agents", "auth", "avm", "bim", "blockchain",
            "construction", "design", "drone", "finance",
            "projects", "regulation", "reports", "tax", "webhooks",
        ]
        for name in required:
            assert name in _MAIN_SOURCE, f"라우터 '{name}' import 누락"


# ──────────────────────────────────────
# 응답 스키마 구조 검증
# ──────────────────────────────────────


class TestResponseSchemas:
    """공유 응답 스키마 구조 검증."""

    def test_project_response_fields(self) -> None:
        """ProjectResponse에 필수 필드가 있다."""
        fields = ProjectResponse.model_fields
        assert "id" in fields
        assert "tenant_id" in fields
        assert "name" in fields
        assert "status" in fields
        assert "created_at" in fields

    def test_webhook_response_fields(self) -> None:
        """WebhookResponse에 필수 필드가 있다."""
        fields = WebhookResponse.model_fields
        assert "id" in fields
        assert "url" in fields
        assert "events" in fields
        assert "is_active" in fields

    def test_webhook_delivery_response_fields(self) -> None:
        """WebhookDeliveryResponse에 필수 필드가 있다."""
        fields = WebhookDeliveryResponse.model_fields
        assert "id" in fields
        assert "webhook_id" in fields
        assert "event_type" in fields
        assert "success" in fields
        assert "attempt" in fields

    def test_health_response_fields(self) -> None:
        """HealthResponse에 필수 필드가 있다."""
        fields = HealthResponse.model_fields
        assert "status" in fields
        assert "version" in fields
        assert "services" in fields

    def test_app_title(self) -> None:
        """앱 제목이 PropAI API이다."""
        assert 'title="PropAI API"' in _MAIN_SOURCE

    def test_app_version(self) -> None:
        """앱 버전이 settings에서 설정된다."""
        assert "settings.app_version" in _MAIN_SOURCE
