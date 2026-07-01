"""Phase E live module regression tests for compliance, leases, and ESG."""

import re
from pathlib import Path

from apps.api.auth.rbac import check_permission
from apps.api.services.compliance_service import ComplianceService
from apps.api.services.esg_service import ESGService
from apps.api.services.lease_service import LeaseService
from packages.schemas.models import (
    ComplianceScreeningRequest,
    ComplianceScreeningResponse,
    ESGAssessmentRequest,
    ESGAssessmentResponse,
    LeaseAnalysisRequest,
    LeaseAnalysisResponse,
)

_BASE = Path(__file__).resolve().parents[2]
_MAIN_SOURCE = (_BASE / "apps" / "api" / "main.py").read_text(encoding="utf-8")
_COMPLIANCE_SOURCE = (_BASE / "apps" / "api" / "routers" / "compliance.py").read_text(encoding="utf-8")
_LEASES_SOURCE = (_BASE / "apps" / "api" / "routers" / "leases.py").read_text(encoding="utf-8")
_ESG_SOURCE = (_BASE / "apps" / "api" / "routers" / "esg.py").read_text(encoding="utf-8")


class TestPhaseELiveContracts:
    def test_compliance_request_and_response_fields(self) -> None:
        assert "transaction_amount_krw" in ComplianceScreeningRequest.model_fields
        assert "documents" in ComplianceScreeningRequest.model_fields
        assert "aml_screening" in ComplianceScreeningResponse.model_fields

    def test_lease_request_and_response_fields(self) -> None:
        assert "discount_rate" in LeaseAnalysisRequest.model_fields
        assert "critical_terms" in LeaseAnalysisRequest.model_fields
        assert "ifrs16_schedule" in LeaseAnalysisResponse.model_fields

    def test_esg_request_and_response_fields(self) -> None:
        assert "gross_floor_area_sqm" in ESGAssessmentRequest.model_fields
        assert "board_independence_ratio" in ESGAssessmentRequest.model_fields
        assert "overall_score" in ESGAssessmentResponse.model_fields
        assert "carbon_total_tco2e" in ESGAssessmentResponse.model_fields


class TestPhaseELiveRouters:
    def test_main_registers_new_routers(self) -> None:
        assert 'prefix="/api/v1/compliance"' in _MAIN_SOURCE
        assert 'prefix="/api/v1/leases"' in _MAIN_SOURCE
        assert 'prefix="/api/v1/esg"' in _MAIN_SOURCE

    def test_compliance_endpoint_exists(self) -> None:
        assert '@router.post("/screening"' in _COMPLIANCE_SOURCE

    def test_leases_endpoint_exists(self) -> None:
        assert '@router.post("/analyze"' in _LEASES_SOURCE

    def test_esg_endpoint_exists(self) -> None:
        # esg.py는 데코레이터가 멀티라인(@router.post(\n "/assessment", ...))이라
        # 단일라인 문자열 매칭이 깨졌었다 → 공백/개행 허용 regex로 'POST /assessment 선언'을 검증.
        # (라우터 실객체 introspection은 esg.py의 `from app...` import가 이 스위트의
        #  import 컨텍스트(레포 루트, `apps.*`만 가용)에서 불가라 소스 매칭이 이 파일의 표준 패턴.)
        assert re.search(r'@router\.post\(\s*"/assessment"', _ESG_SOURCE)


class TestPhaseELiveServices:
    def test_compliance_high_risk_case(self) -> None:
        score, risk_level, match_status, matched_lists, notes = ComplianceService._score_aml_risk(
            transaction_amount_krw=25_000_000_000,
            politically_exposed=True,
            residency_countries=["KR", "IR"],
            document_count=0,
        )
        assert score >= 75
        assert risk_level == "high"
        assert match_status == "hit"
        assert "pep-screening" in matched_lists
        assert "Escalate" in notes

    def test_lease_payment_schedule_shape(self) -> None:
        schedule, opening_liability = LeaseService._build_payment_schedule(
            monthly_rent_krw=12_000_000,
            lease_term_months=12,
            annual_discount_rate=0.06,
        )
        assert len(schedule) == 12
        assert opening_liability > 0
        assert schedule[0]["period"] == 1
        assert schedule[-1]["closing_liability_krw"] >= 0

    def test_esg_score_derivation(self) -> None:
        e_score, s_score, g_score, overall, rating, action_plan = ESGService._derive_scores(
            total_carbon_tco2e=180.0,
            gross_floor_area_sqm=20000.0,
            energy_independence_rate=38.0,
            climate_risk_score=0.28,
            lost_time_incident_rate=0.4,
            community_programs_count=3,
            board_independence_ratio=0.55,
        )
        assert 0 <= e_score <= 100
        assert 0 <= s_score <= 100
        assert 0 <= g_score <= 100
        assert 0 <= overall <= 100
        assert rating in {"1 Star", "2 Star", "3 Star", "4 Star", "5 Star"}
        assert action_plan


class TestPhaseELiveRBAC:
    def test_manager_can_write_compliance(self) -> None:
        assert check_permission("manager", "compliance", "write") is True

    def test_analyst_cannot_write_leases(self) -> None:
        assert check_permission("analyst", "leases", "write") is False

    def test_viewer_can_read_esg(self) -> None:
        assert check_permission("viewer", "esg", "read") is True
