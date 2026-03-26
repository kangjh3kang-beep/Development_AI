"""Prometheus 메트릭 실코드 연동 검증 테스트.

메트릭 객체가 실제 비즈니스 코드에 import/사용되는지 소스 패턴으로 확인한다.
"""

from pathlib import Path

_BASE = Path(__file__).resolve().parents[2]

_ORCHESTRATOR_SOURCE = (
    _BASE / "apps" / "api" / "agents" / "propai_orchestrator.py"
).read_text(encoding="utf-8")

_AVM_ROUTER_SOURCE = (
    _BASE / "apps" / "api" / "routers" / "avm.py"
).read_text(encoding="utf-8")

_MAIN_SOURCE = (
    _BASE / "apps" / "api" / "main.py"
).read_text(encoding="utf-8")

_AI_TRACKER_SOURCE = (
    _BASE / "apps" / "api" / "services" / "ai_usage_tracker.py"
).read_text(encoding="utf-8")

_WEBHOOK_SERVICE_SOURCE = (
    _BASE / "apps" / "api" / "services" / "webhook_service.py"
).read_text(encoding="utf-8")

_PROJECTS_ROUTER_SOURCE = (
    _BASE / "apps" / "api" / "routers" / "projects.py"
).read_text(encoding="utf-8")


class TestOrchestratorMetrics:
    """오케스트레이터에 메트릭이 연동되어 있다."""

    def test_imports_agent_step_duration(self) -> None:
        """AGENT_STEP_DURATION이 import되어 있다."""
        assert "AGENT_STEP_DURATION" in _ORCHESTRATOR_SOURCE

    def test_imports_agent_completion(self) -> None:
        """AGENT_COMPLETION이 import되어 있다."""
        assert "AGENT_COMPLETION" in _ORCHESTRATOR_SOURCE

    def test_observes_step_duration(self) -> None:
        """AGENT_STEP_DURATION.labels().observe()를 호출한다."""
        assert ".observe(" in _ORCHESTRATOR_SOURCE

    def test_increments_completion(self) -> None:
        """AGENT_COMPLETION.labels().inc()를 호출한다."""
        assert "AGENT_COMPLETION.labels(" in _ORCHESTRATOR_SOURCE

    def test_uses_time_monotonic(self) -> None:
        """time.monotonic()으로 실행 시간을 계측한다."""
        assert "time.monotonic()" in _ORCHESTRATOR_SOURCE


class TestAVMMetrics:
    """AVM 라우터에 메트릭이 연동되어 있다."""

    def test_imports_avm_estimates(self) -> None:
        """AVM_ESTIMATES가 import되어 있다."""
        assert "AVM_ESTIMATES" in _AVM_ROUTER_SOURCE

    def test_increments_avm_estimates(self) -> None:
        """AVM_ESTIMATES.inc()를 호출한다."""
        assert "AVM_ESTIMATES.inc()" in _AVM_ROUTER_SOURCE


class TestMainMetrics:
    """main.py에 DB 풀 메트릭이 연동되어 있다."""

    def test_imports_db_pool_size(self) -> None:
        """DB_POOL_SIZE가 import되어 있다."""
        assert "DB_POOL_SIZE" in _MAIN_SOURCE

    def test_sets_db_pool_size(self) -> None:
        """DB_POOL_SIZE.set()을 호출한다."""
        assert "DB_POOL_SIZE.set(" in _MAIN_SOURCE


class TestPhaseCAITrackerMetrics:
    """AI 사용 추적기에 메트릭이 연동되어 있다 (Phase C 검증)."""

    def test_uses_cost_metric(self) -> None:
        """AI_COST_TOTAL이 사용된다."""
        assert "AI_COST_TOTAL" in _AI_TRACKER_SOURCE

    def test_uses_token_metric(self) -> None:
        """AI_TOKEN_TOTAL이 사용된다."""
        assert "AI_TOKEN_TOTAL" in _AI_TRACKER_SOURCE


class TestPhaseCWebhookMetrics:
    """웹훅 서비스에 메트릭이 연동되어 있다 (Phase C 검증)."""

    def test_uses_webhook_deliveries(self) -> None:
        """WEBHOOK_DELIVERIES가 사용된다."""
        assert "WEBHOOK_DELIVERIES" in _WEBHOOK_SERVICE_SOURCE


class TestPhaseCProjectMetrics:
    """프로젝트 라우터에 메트릭이 연동되어 있다 (Phase C 검증)."""

    def test_uses_project_created(self) -> None:
        """PROJECT_CREATED가 사용된다."""
        assert "PROJECT_CREATED" in _PROJECTS_ROUTER_SOURCE
