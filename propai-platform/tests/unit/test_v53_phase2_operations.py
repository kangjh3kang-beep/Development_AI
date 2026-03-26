"""Regression tests for v53 phase 2 operations, risk, and permit APIs."""

from pathlib import Path

from apps.api.auth.rbac import check_permission
from apps.api.services.digital_twin_status_service import DigitalTwinStatusService
from apps.api.services.risk_scoring_engine import RiskScoringEngine
from apps.api.services.seumter_permit_service import SeumterPermitService
from packages.schemas.models import (
    DigitalTwinStatusRequest,
    DigitalTwinStatusResponse,
    PermitStatusResponse,
    PermitSubmissionRequest,
    UnifiedRiskAssessmentRequest,
    UnifiedRiskAssessmentResponse,
)

_BASE = Path(__file__).resolve().parents[2]
_MAIN_SOURCE = (_BASE / "apps" / "api" / "main.py").read_text(encoding="utf-8")
_DIGITAL_TWIN_SOURCE = (
    _BASE / "apps" / "api" / "routers" / "digital_twin.py"
).read_text(encoding="utf-8")
_RISK_SOURCE = (_BASE / "apps" / "api" / "routers" / "risk.py").read_text(encoding="utf-8")
_PERMITS_SOURCE = (_BASE / "apps" / "api" / "routers" / "permits.py").read_text(encoding="utf-8")


class TestV53Phase2Contracts:
    def test_digital_twin_status_contract_fields(self) -> None:
        assert "annual_energy_kwh" in DigitalTwinStatusRequest.model_fields
        assert "sensor_health_ratio" in DigitalTwinStatusResponse.model_fields
        assert "highest_anomaly_severity" in DigitalTwinStatusResponse.model_fields

    def test_risk_contract_fields(self) -> None:
        assert "market_risk_score" in UnifiedRiskAssessmentRequest.model_fields
        assert "var_95_ratio" in UnifiedRiskAssessmentResponse.model_fields
        assert "dimension_scores" in UnifiedRiskAssessmentResponse.model_fields

    def test_permit_contract_fields(self) -> None:
        assert "submitted_document_ids" in PermitSubmissionRequest.model_fields
        assert "submission_reference" in PermitStatusResponse.model_fields
        assert "missing_required_documents" in PermitStatusResponse.model_fields


class TestV53Phase2Routers:
    def test_main_registers_new_routers(self) -> None:
        assert 'prefix="/api/v1/risk"' in _MAIN_SOURCE
        assert 'prefix="/api/v1/permits"' in _MAIN_SOURCE

    def test_digital_twin_status_endpoints_exist(self) -> None:
        assert '@router.post("/status/snapshot"' in _DIGITAL_TWIN_SOURCE
        assert '@router.get("/status/{project_id}/latest"' in _DIGITAL_TWIN_SOURCE

    def test_risk_and_permit_endpoints_exist(self) -> None:
        assert "/unified/analyze" in _RISK_SOURCE
        assert "/unified/{project_id}/latest" in _RISK_SOURCE
        assert "/submit" in _PERMITS_SOURCE
        assert "/submissions/{submission_id}/status" in _PERMITS_SOURCE


class TestV53Phase2Services:
    def test_digital_twin_readiness_math(self) -> None:
        sensor_health = DigitalTwinStatusService._sensor_health_ratio(24, 21)
        readiness = DigitalTwinStatusService._readiness_score(
            eui_ratio=1.08,
            sensor_health_ratio=sensor_health,
            occupancy_rate=0.91,
            anomaly_count=2,
            critical_alarm_count=0,
        )
        status = DigitalTwinStatusService._status_from_score(
            readiness,
            anomaly_count=2,
            critical_alarm_count=0,
        )
        assert 0 <= readiness <= 100
        assert sensor_health == 0.875
        assert status in {"healthy", "watch", "critical"}

    def test_risk_dimension_weighting(self) -> None:
        dimensions = RiskScoringEngine._dimension_scores(
            market_risk_score=62.0,
            ltv_ratio=0.68,
            dscr=1.11,
            permit_readiness_ratio=0.55,
            operational_readiness_ratio=0.74,
            climate_risk_score=41.0,
            cost_volatility_ratio=0.19,
            occupancy_rate=0.89,
            presale_ratio=0.44,
        )
        composite = sum(item["score"] * item["weight"] for item in dimensions)
        assert len(dimensions) == 7
        assert round(sum(item["weight"] for item in dimensions), 2) == 1.0
        assert composite > 0
        assert RiskScoringEngine._grade(composite) in {"A", "B", "C", "D", "E", "F"}

    def test_permit_checklist_and_validation(self) -> None:
        checklist = SeumterPermitService._build_checklist(
            permit_type="building_permit",
            building_area_sqm=16000,
            is_public=True,
            is_agricultural=False,
            submitted_document_ids=["BA-01", "BA-02", "BA-03"],
        )
        validation = SeumterPermitService._validate_checklist(checklist)
        assert checklist
        assert validation["required_total"] >= validation["required_submitted"]
        assert validation["readiness_score"] < 100
        assert "Energy compliance sheet" in validation["missing_required_documents"]


class TestV53Phase2Rbac:
    def test_viewer_can_read_digital_twin_status(self) -> None:
        assert check_permission("viewer", "digital_twin_status", "read") is True

    def test_analyst_can_write_risk_engine(self) -> None:
        assert check_permission("analyst", "risk_engine", "write") is True

    def test_manager_can_write_permits(self) -> None:
        assert check_permission("manager", "permits", "write") is True
