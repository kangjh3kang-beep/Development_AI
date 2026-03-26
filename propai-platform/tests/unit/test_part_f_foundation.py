"""Part F foundation regression tests."""

from pathlib import Path

from apps.api.auth.rbac import check_permission
from apps.api.database.models.phase_f_asset_intelligence import (
    AssetIntelligenceSnapshot,
    CapexOptimizationResult,
)
from apps.api.database.models.phase_f_domain_agents import DomainAgentApproval, DomainAgentTask
from apps.api.database.models.phase_f_maintenance import (
    EquipmentSensor,
    PredictiveMaintenanceAlert,
    WorkOrder,
)
from apps.api.database.models.phase_f_marketing import MarketingContent, OfferingMemorandum
from apps.api.database.models.phase_f_tenant import (
    TenantFinancialHealth,
    TenantSentimentScore,
    TenantTicket,
)
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


class TestPartFModels:
    def test_marketing_models_have_expected_columns(self) -> None:
        assert {"channel", "headline", "body", "call_to_action"}.issubset(
            {column.name for column in MarketingContent.__table__.columns}
        )
        assert {"marketing_content_id", "sections_json", "risk_factors_json"}.issubset(
            {column.name for column in OfferingMemorandum.__table__.columns}
        )

    def test_domain_agent_models_have_expected_columns(self) -> None:
        assert {"domain", "confidence_score", "requires_approval", "recommendation"}.issubset(
            {column.name for column in DomainAgentTask.__table__.columns}
        )
        assert {"task_id", "approver_role", "status"}.issubset(
            {column.name for column in DomainAgentApproval.__table__.columns}
        )

    def test_maintenance_tenant_asset_models_have_expected_columns(self) -> None:
        assert {"equipment_name", "latest_reading_json", "health_status"}.issubset(
            {column.name for column in EquipmentSensor.__table__.columns}
        )
        assert {"anomaly_score", "remaining_useful_life_days", "severity"}.issubset(
            {column.name for column in PredictiveMaintenanceAlert.__table__.columns}
        )
        assert {"maintenance_alert_id", "priority", "assigned_team"}.issubset(
            {column.name for column in WorkOrder.__table__.columns}
        )
        assert {"category", "feedback_text", "requested_action"}.issubset(
            {column.name for column in TenantTicket.__table__.columns}
        )
        assert {"tenant_ticket_id", "sentiment_score", "ai_reply"}.issubset(
            {column.name for column in TenantSentimentScore.__table__.columns}
        )
        assert {"occupancy_rate", "arrears_ratio", "health_grade"}.issubset(
            {column.name for column in TenantFinancialHealth.__table__.columns}
        )
        assert {"composite_score", "grade", "adjusted_value_krw"}.issubset(
            {column.name for column in AssetIntelligenceSnapshot.__table__.columns}
        )
        assert {"snapshot_id", "expected_roi", "payback_months"}.issubset(
            {column.name for column in CapexOptimizationResult.__table__.columns}
        )


class TestPartFContracts:
    def test_maintenance_contract_fields(self) -> None:
        assert "equipment_type" in MaintenanceAnomalyRequest.model_fields
        assert "remaining_useful_life_days" in MaintenanceAnomalyResponse.model_fields

    def test_tenant_contract_fields(self) -> None:
        assert "feedback_text" in TenantFeedbackRequest.model_fields
        assert "ai_reply" in TenantFeedbackResponse.model_fields
        assert "arrears_ratio" in TenantSatisfactionRequest.model_fields
        assert "health_grade" in TenantSatisfactionResponse.model_fields

    def test_asset_intelligence_contract_fields(self) -> None:
        assert "base_value_krw" in AssetIntelligenceRequest.model_fields
        assert "capex_recommendations" in AssetIntelligenceResponse.model_fields


class TestPartFRoutersAndRbac:
    def test_main_registers_marketing_and_domain_agents(self) -> None:
        assert 'prefix="/api/v1/marketing"' in _MAIN_SOURCE
        assert 'prefix="/api/v1/agents/domain"' in _MAIN_SOURCE

    def test_marketing_permissions(self) -> None:
        assert check_permission("analyst", "marketing", "write") is True
        assert check_permission("viewer", "marketing", "write") is False

    def test_part_f_scope_permissions(self) -> None:
        assert check_permission("manager", "domain_agents", "write") is True
        assert check_permission("manager", "maintenance", "write") is True
        assert check_permission("viewer", "tenant_experience", "read") is True
        assert check_permission("viewer", "asset_intelligence", "read") is True
