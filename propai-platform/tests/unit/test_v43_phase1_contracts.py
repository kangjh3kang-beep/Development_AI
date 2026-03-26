"""v43 Phase 1 contract and router regression tests."""

from datetime import datetime
from pathlib import Path
from uuid import uuid4

from apps.api.auth.rbac import check_permission
from packages.schemas.models import (
    AICostDashboardResponse,
    DashboardStatsResponse,
    EnergyCertificationRequest,
    KepcoCalculationRequest,
    SystemHealthResponse,
    SystemVersionResponse,
)

_BASE = Path(__file__).resolve().parents[2]
_MAIN_SOURCE = (_BASE / "apps" / "api" / "main.py").read_text(encoding="utf-8")
_ROUTERS_DIR = _BASE / "apps" / "api" / "routers"


class TestV43RouterRegistration:
    """New v43 rollout routers are wired into main.py."""

    def test_system_router_registered(self) -> None:
        assert 'prefix="/api/v1/system"' in _MAIN_SOURCE

    def test_dashboard_router_registered(self) -> None:
        assert 'prefix="/api/v1/dashboard"' in _MAIN_SOURCE

    def test_ai_costs_router_registered(self) -> None:
        assert 'prefix="/api/v1/ai-costs"' in _MAIN_SOURCE

    def test_energy_router_registered(self) -> None:
        assert 'prefix="/api/v1/energy"' in _MAIN_SOURCE

    def test_router_files_exist(self) -> None:
        for name in ("system.py", "dashboard.py", "ai_costs.py", "energy.py"):
            assert (_ROUTERS_DIR / name).exists(), f"{name} missing"


class TestV43SchemaModels:
    """New contract models expose the expected fields."""

    def test_system_version_fields(self) -> None:
        fields = SystemVersionResponse.model_fields
        assert "app_name" in fields
        assert "version" in fields
        assert "environment" in fields
        assert "api_prefixes" in fields

    def test_system_health_round_trip(self) -> None:
        response = SystemHealthResponse(
            status="healthy",
            version="30.0.0",
            environment="development",
            services={"postgres": "healthy"},
            checked_at=datetime.now(),
        )
        restored = SystemHealthResponse.model_validate_json(response.model_dump_json())
        assert restored.status == "healthy"
        assert restored.services["postgres"] == "healthy"

    def test_dashboard_stats_defaults(self) -> None:
        stats = DashboardStatsResponse()
        assert stats.total_projects == 0
        assert stats.projects_by_status == {}
        assert stats.ai_tokens_month == 0

    def test_kepco_request_validation(self) -> None:
        request = KepcoCalculationRequest(usage_kwh=350.5, contract_type="general", demand_kw=12.0)
        assert request.usage_kwh == 350.5
        assert request.contract_type == "general"

    def test_ai_cost_dashboard_round_trip(self) -> None:
        dashboard = AICostDashboardResponse(month="2026-03")
        restored = AICostDashboardResponse.model_validate(dashboard.model_dump())
        assert restored.month == "2026-03"
        assert restored.total_cost_usd == 0.0

    def test_energy_certification_request(self) -> None:
        request = EnergyCertificationRequest(
            project_id=uuid4(),
            total_area_sqm=1250.0,
            floors=8,
            window_wall_ratio=0.33,
            insulation_grade="1?깃툒",
            bems_saving_rate=0.12,
        )
        assert request.floors == 8
        assert request.bems_saving_rate == 0.12


class TestV43RBACPolicies:
    """New operational scopes are available to the intended roles."""

    def test_admin_can_read_system(self) -> None:
        assert check_permission("admin", "system", "read") is True

    def test_viewer_can_read_dashboard(self) -> None:
        assert check_permission("viewer", "dashboard", "read") is True

    def test_analyst_can_read_ai_costs(self) -> None:
        assert check_permission("analyst", "ai_costs", "read") is True

    def test_viewer_cannot_read_ai_costs(self) -> None:
        assert check_permission("viewer", "ai_costs", "read") is False

    def test_viewer_can_read_energy(self) -> None:
        assert check_permission("viewer", "energy", "read") is True
