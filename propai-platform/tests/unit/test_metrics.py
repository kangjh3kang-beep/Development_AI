"""Prometheus 커스텀 메트릭 단위 테스트.

메트릭 객체 존재, 라벨, 네이밍 컨벤션 검증.
"""

from pathlib import Path

from apps.api.metrics import (
    AGENT_COMPLETION,
    AGENT_STEP_DURATION,
    AI_COST_TOTAL,
    AI_TOKEN_TOTAL,
    AVM_ESTIMATES,
    DB_POOL_CHECKED_OUT,
    DB_POOL_SIZE,
    PROJECT_CREATED,
    WEBHOOK_DELIVERIES,
)

# 메트릭 연동 소스 검증용
_AI_TRACKER_SOURCE = (
    Path(__file__).resolve().parents[2] / "apps" / "api" / "services" / "ai_usage_tracker.py"
).read_text(encoding="utf-8")

_PROJECTS_ROUTER_SOURCE = (
    Path(__file__).resolve().parents[2] / "apps" / "api" / "routers" / "projects.py"
).read_text(encoding="utf-8")

_WEBHOOK_SERVICE_SOURCE = (
    Path(__file__).resolve().parents[2] / "apps" / "api" / "services" / "webhook_service.py"
).read_text(encoding="utf-8")


class TestMetricNaming:
    """메트릭 이름 네이밍 컨벤션 검증."""

    def test_ai_cost_prefix(self) -> None:
        """AI 비용 메트릭이 propai_ 접두어를 사용한다."""
        assert AI_COST_TOTAL._name.startswith("propai_")

    def test_ai_token_prefix(self) -> None:
        """AI 토큰 메트릭이 propai_ 접두어를 사용한다."""
        assert AI_TOKEN_TOTAL._name.startswith("propai_")

    def test_agent_step_prefix(self) -> None:
        """에이전트 단계 메트릭이 propai_ 접두어를 사용한다."""
        assert AGENT_STEP_DURATION._name.startswith("propai_")

    def test_project_created_prefix(self) -> None:
        """프로젝트 생성 메트릭이 propai_ 접두어를 사용한다."""
        assert PROJECT_CREATED._name.startswith("propai_")

    def test_webhook_deliveries_prefix(self) -> None:
        """웹훅 전송 메트릭이 propai_ 접두어를 사용한다."""
        assert WEBHOOK_DELIVERIES._name.startswith("propai_")

    def test_db_pool_prefix(self) -> None:
        """DB 풀 메트릭이 propai_ 접두어를 사용한다."""
        assert DB_POOL_SIZE._name.startswith("propai_")
        assert DB_POOL_CHECKED_OUT._name.startswith("propai_")


class TestMetricLabels:
    """메트릭 라벨 검증."""

    def test_ai_cost_labels(self) -> None:
        """AI 비용 Counter에 service, model 라벨이 있다."""
        assert AI_COST_TOTAL._labelnames == ("service", "model")

    def test_ai_token_labels(self) -> None:
        """AI 토큰 Counter에 service, model, direction 라벨이 있다."""
        assert AI_TOKEN_TOTAL._labelnames == ("service", "model", "direction")

    def test_agent_step_labels(self) -> None:
        """에이전트 단계 Histogram에 step_name 라벨이 있다."""
        assert AGENT_STEP_DURATION._labelnames == ("step_name",)

    def test_agent_completion_labels(self) -> None:
        """에이전트 완주 Counter에 status 라벨이 있다."""
        assert AGENT_COMPLETION._labelnames == ("status",)

    def test_webhook_deliveries_labels(self) -> None:
        """웹훅 전송 Counter에 status 라벨이 있다."""
        assert WEBHOOK_DELIVERIES._labelnames == ("status",)


class TestMetricTypes:
    """메트릭 타입 검증."""

    def test_avm_estimates_is_counter(self) -> None:
        """AVM 추정 메트릭이 Counter이다."""
        assert AVM_ESTIMATES._type == "counter"

    def test_db_pool_size_is_gauge(self) -> None:
        """DB 풀 크기 메트릭이 Gauge이다."""
        assert DB_POOL_SIZE._type == "gauge"

    def test_agent_step_is_histogram(self) -> None:
        """에이전트 단계 메트릭이 Histogram이다."""
        assert AGENT_STEP_DURATION._type == "histogram"


class TestMetricIntegration:
    """메트릭이 소스 코드에 연동되어 있는지 검증."""

    def test_ai_tracker_uses_cost_metric(self) -> None:
        """ai_usage_tracker가 AI_COST_TOTAL을 사용한다."""
        assert "AI_COST_TOTAL" in _AI_TRACKER_SOURCE

    def test_ai_tracker_uses_token_metric(self) -> None:
        """ai_usage_tracker가 AI_TOKEN_TOTAL을 사용한다."""
        assert "AI_TOKEN_TOTAL" in _AI_TRACKER_SOURCE

    def test_projects_router_uses_created_metric(self) -> None:
        """projects 라우터가 PROJECT_CREATED를 사용한다."""
        assert "PROJECT_CREATED" in _PROJECTS_ROUTER_SOURCE

    def test_webhook_service_uses_deliveries_metric(self) -> None:
        """webhook_service가 WEBHOOK_DELIVERIES를 사용한다."""
        assert "WEBHOOK_DELIVERIES" in _WEBHOOK_SERVICE_SOURCE
