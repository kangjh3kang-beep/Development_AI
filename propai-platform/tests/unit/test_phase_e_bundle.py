"""Phase E foundation and router regression tests."""

from pathlib import Path

from apps.api.auth.rbac import check_permission
from apps.api.database.models.phase_e_climate import (
    ClimateRiskAssessment,
    InsuranceRecommendation,
)
from apps.api.database.models.phase_e_compliance import AMLScreening, ComplianceCheck, KYCDocument
from apps.api.database.models.phase_e_esg import CarbonFootprint, ESGReport, GRESBAssessment
from apps.api.database.models.phase_e_lease import LeaseAbstraction, LeaseIFRS16Schedule
from apps.api.database.models.phase_e_underwriting import (
    DataRoomDocument,
    InvestmentUnderwriting,
    LPReport,
)
from packages.schemas.models import (
    ClimateRiskAssessmentRequest,
    ClimateRiskAssessmentResponse,
    ComplianceCheckResponse,
    ESGAssessmentResponse,
    InsuranceRecommendationResponse,
    LeaseAbstractionResponse,
    LeaseIFRS16ScheduleResponse,
    UnderwritingRequest,
    UnderwritingResponse,
)

_BASE = Path(__file__).resolve().parents[2]
_MAIN_SOURCE = (_BASE / "apps" / "api" / "main.py").read_text(encoding="utf-8")
_UNDERWRITING_SOURCE = (_BASE / "apps" / "api" / "routers" / "underwriting.py").read_text(encoding="utf-8")
_CLIMATE_SOURCE = (_BASE / "apps" / "api" / "routers" / "climate.py").read_text(encoding="utf-8")


class TestPhaseEModels:
    def test_underwriting_models_have_expected_columns(self) -> None:
        underwriting_columns = {column.name for column in InvestmentUnderwriting.__table__.columns}
        assert {
            "project_name",
            "projected_profit_krw",
            "profit_margin_ratio",
            "debt_ratio",
            "equity_multiple",
            "recommendation",
            "key_risks",
        }.issubset(underwriting_columns)

        report_columns = {column.name for column in LPReport.__table__.columns}
        assert {"underwriting_id", "executive_summary", "metrics_json"}.issubset(report_columns)

        doc_columns = {column.name for column in DataRoomDocument.__table__.columns}
        assert {"underwriting_id", "file_name", "document_type", "storage_url"}.issubset(doc_columns)

    def test_compliance_and_lease_models_have_expected_columns(self) -> None:
        assert {"check_type", "status", "findings_json"}.issubset(
            {column.name for column in ComplianceCheck.__table__.columns}
        )
        assert {"document_kind", "verified", "metadata_json"}.issubset(
            {column.name for column in KYCDocument.__table__.columns}
        )
        assert {"match_status", "risk_level", "matched_lists_json"}.issubset(
            {column.name for column in AMLScreening.__table__.columns}
        )
        assert {"tenant_name", "monthly_rent_krw", "critical_terms_json"}.issubset(
            {column.name for column in LeaseAbstraction.__table__.columns}
        )
        assert {"lease_abstraction_id", "rou_asset_krw", "payment_schedule_json"}.issubset(
            {column.name for column in LeaseIFRS16Schedule.__table__.columns}
        )

    def test_esg_and_climate_models_have_expected_columns(self) -> None:
        assert {"reporting_period", "environmental_score", "disclosures_json"}.issubset(
            {column.name for column in ESGReport.__table__.columns}
        )
        assert {"scope1_tco2e", "scope3_tco2e", "breakdown_json"}.issubset(
            {column.name for column in CarbonFootprint.__table__.columns}
        )
        assert {"assessment_year", "rating", "gaps_json"}.issubset(
            {column.name for column in GRESBAssessment.__table__.columns}
        )
        assert {"annual_expected_loss_krw", "risk_factors", "mitigation_tips"}.issubset(
            {column.name for column in ClimateRiskAssessment.__table__.columns}
        )
        assert {"climate_risk_assessment_id", "coverage_type", "coverage_limit_krw"}.issubset(
            {column.name for column in InsuranceRecommendation.__table__.columns}
        )


class TestPhaseESchemas:
    def test_underwriting_request_and_response_fields(self) -> None:
        assert "data_room_documents" in UnderwritingRequest.model_fields
        assert "assumptions_json" in UnderwritingRequest.model_fields
        assert "recommendation" in UnderwritingResponse.model_fields
        assert "equity_multiple" in UnderwritingResponse.model_fields

    def test_placeholder_phase_e_contracts_exist(self) -> None:
        assert "findings" in ComplianceCheckResponse.model_fields
        assert "critical_terms" in LeaseAbstractionResponse.model_fields
        assert "payment_schedule" in LeaseIFRS16ScheduleResponse.model_fields
        assert "gresb_rating" in ESGAssessmentResponse.model_fields

    def test_climate_contract_fields(self) -> None:
        assert "asset_value_krw" in ClimateRiskAssessmentRequest.model_fields
        assert "insurance_recommendations" in ClimateRiskAssessmentResponse.model_fields
        assert "coverage_limit_krw" in InsuranceRecommendationResponse.model_fields


class TestPhaseERouters:
    def test_main_registers_phase_e_routers(self) -> None:
        assert 'prefix="/api/v1/underwriting"' in _MAIN_SOURCE
        assert 'prefix="/api/v1/climate"' in _MAIN_SOURCE

    def test_underwriting_endpoints_exist(self) -> None:
        assert '@router.get("/history"' in _UNDERWRITING_SOURCE
        assert '@router.post("/{project_id}"' in _UNDERWRITING_SOURCE

    def test_climate_endpoint_exists(self) -> None:
        assert '@router.post("/risk"' in _CLIMATE_SOURCE


class TestPhaseERbac:
    def test_manager_can_write_underwriting(self) -> None:
        assert check_permission("manager", "underwriting", "write") is True

    def test_analyst_cannot_write_underwriting(self) -> None:
        assert check_permission("analyst", "underwriting", "write") is False

    def test_viewer_can_read_esg(self) -> None:
        assert check_permission("viewer", "esg", "read") is True

    def test_viewer_can_read_climate(self) -> None:
        assert check_permission("viewer", "climate", "read") is True

    def test_viewer_cannot_write_climate(self) -> None:
        assert check_permission("viewer", "climate", "write") is False
