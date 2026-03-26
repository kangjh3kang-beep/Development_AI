"""Part F live module regression tests for maintenance, tenant, and digital twin."""

from pathlib import Path

from apps.api.auth.rbac import check_permission
from apps.api.services.asset_intelligence_service import AssetIntelligenceService
from apps.api.services.maintenance_service import MaintenanceService
from apps.api.services.tenant_experience_service import TenantExperienceService
from packages.schemas.models import (
    AssetIntelligenceRequest,
    AssetIntelligenceResponse,
    MaintenanceAnomalyRequest,
    MaintenanceAnomalyResponse,
    TenantFeedbackRequest,
    TenantFeedbackResponse,
    TenantSatisfactionRequest,
    TenantSatisfactionResponse,
)

_BASE = Path(__file__).resolve().parents[2]
_MAIN_SOURCE = (_BASE / "apps" / "api" / "main.py").read_text(encoding="utf-8")
_MAINTENANCE_SOURCE = (_BASE / "apps" / "api" / "routers" / "maintenance.py").read_text(encoding="utf-8")
_TENANT_SOURCE = (_BASE / "apps" / "api" / "routers" / "tenant.py").read_text(encoding="utf-8")
_DIGITAL_TWIN_SOURCE = (_BASE / "apps" / "api" / "routers" / "digital_twin.py").read_text(encoding="utf-8")


class TestPartFOpsContracts:
    def test_maintenance_request_and_response_fields(self) -> None:
        assert "temperature_c" in MaintenanceAnomalyRequest.model_fields
        assert "work_order_id" in MaintenanceAnomalyResponse.model_fields

    def test_tenant_request_and_response_fields(self) -> None:
        assert "satisfaction_rating" in TenantFeedbackRequest.model_fields
        assert "ai_reply" in TenantFeedbackResponse.model_fields
        assert "promoter_count" in TenantSatisfactionRequest.model_fields
        assert "health_grade" in TenantSatisfactionResponse.model_fields

    def test_digital_twin_request_and_response_fields(self) -> None:
        assert "base_value_krw" in AssetIntelligenceRequest.model_fields
        assert "maintenance_score" in AssetIntelligenceRequest.model_fields
        assert "component_scores" in AssetIntelligenceResponse.model_fields
        assert "capex_recommendations" in AssetIntelligenceResponse.model_fields


class TestPartFOpsRouters:
    def test_main_registers_ops_routers(self) -> None:
        assert 'prefix="/api/v1/maintenance"' in _MAIN_SOURCE
        assert 'prefix="/api/v1/tenant"' in _MAIN_SOURCE
        assert 'prefix="/api/v1/digital-twin"' in _MAIN_SOURCE

    def test_maintenance_endpoint_exists(self) -> None:
        assert '@router.post("/detect-anomaly"' in _MAINTENANCE_SOURCE

    def test_tenant_endpoints_exist(self) -> None:
        assert '@router.post("/feedback/analyze"' in _TENANT_SOURCE
        assert '@router.post("/satisfaction/nps"' in _TENANT_SOURCE

    def test_digital_twin_endpoint_exists(self) -> None:
        assert '@router.post("/asset-intelligence"' in _DIGITAL_TWIN_SOURCE


class TestPartFOpsServices:
    def test_maintenance_evaluation(self) -> None:
        anomaly_score, rul_days, hvac_score, severity, recommendation = MaintenanceService._evaluate(
            vibration_mm_s=11.2,
            temperature_c=39.0,
            energy_efficiency_ratio=0.62,
        )
        assert 0 <= anomaly_score <= 1
        assert rul_days >= 7
        assert 0 <= hvac_score <= 100
        assert severity in {"low", "medium", "high", "critical"}
        assert recommendation

    def test_tenant_sentiment_analysis(self) -> None:
        score, label, reply = TenantExperienceService._analyze_sentiment(
            feedback_text="The service delay and noise issue made us angry.",
            satisfaction_rating=1,
        )
        assert -1 <= score <= 1
        assert label in {"positive", "neutral", "negative"}
        assert reply

    def test_tenant_health_calculation(self) -> None:
        nps, churn_risk, grade = TenantExperienceService._calculate_health(
            promoter_count=42,
            passive_count=18,
            detractor_count=10,
            occupancy_rate=0.94,
            arrears_ratio=0.03,
        )
        assert -100 <= nps <= 100
        assert 0 <= churn_risk <= 1
        assert grade in {"A", "B", "C", "D", "E"}

    def test_asset_intelligence_capex_plan(self) -> None:
        plan = AssetIntelligenceService._capex_plan(
            {
                "maintenance": 58.0,
                "tenant": 64.0,
                "market": 78.0,
                "climate": 61.0,
            }
        )
        assert plan
        assert all("strategy" in item for item in plan)


class TestPartFOpsRbac:
    def test_manager_can_write_maintenance(self) -> None:
        assert check_permission("manager", "maintenance", "write") is True

    def test_viewer_cannot_write_tenant_experience(self) -> None:
        assert check_permission("viewer", "tenant_experience", "write") is False

    def test_analyst_can_write_asset_intelligence(self) -> None:
        assert check_permission("analyst", "asset_intelligence", "write") is True
