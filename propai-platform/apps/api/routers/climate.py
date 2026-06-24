"""Climate risk router for G85."""

from fastapi import APIRouter, Depends
from packages.schemas.models import (
    ClimateRiskAssessmentRequest,
    ClimateRiskAssessmentResponse,
    InsuranceRecommendationResponse,
)
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth.jwt_handler import CurrentUser
from apps.api.auth.rbac import RequirePermission
from apps.api.database.session import get_db
from apps.api.services.climate_risk_service import ClimateRiskService

router = APIRouter()


@router.post("/risk", response_model=ClimateRiskAssessmentResponse)
async def analyze_climate_risk(
    body: ClimateRiskAssessmentRequest,
    current_user: CurrentUser = Depends(RequirePermission("climate", "read")),
    db: AsyncSession = Depends(get_db),
) -> ClimateRiskAssessmentResponse:
    """Analyze climate risk and return insurance package guidance."""
    service = ClimateRiskService(db)
    assessment, recommendations = await service.analyze_and_store(
        tenant_id=current_user.tenant_id,
        project_id=body.project_id,
        lat=body.lat,
        lon=body.lon,
        construction_period_months=body.construction_period_months,
        asset_value_krw=body.asset_value_krw,
    )

    # 표준 근거 블록(#5): 실제 산출한 위험점수·연간기대손실 값과 그 산식·근거(자연재해대책)를 가산.
    evidence = None
    try:
        from app.services.data_validation.evidence_contract import build_evidence_block

        evidence = build_evidence_block(
            items=[
                {"label": "침수위험 점수(0~1)", "value": assessment.flood_risk_score,
                 "basis": "시공 기후 베이스라인(좌표·공사기간 기반) 침수 위험도"},
                {"label": "폭염위험 점수(0~1)", "value": assessment.heat_risk_score,
                 "basis": "시공 기후 베이스라인 폭염 위험도"},
                {"label": "종합 위험등급", "value": assessment.overall_risk_level,
                 "basis": "침수·폭염 위험점수 종합 판정"},
                {"label": "연간 기대손실(원)", "value": assessment.annual_expected_loss_krw,
                 "basis": "자산가치 × (0.4% + 최대위험점수 × 2.8%)"},
            ],
            legal_ref_keys=["disaster_impact"],
            sources=["자연재해대책법(재해영향평가)", "시공 기후 베이스라인 분석"],
        )
    except Exception:  # noqa: BLE001 — 근거 블록 실패는 기후위험 결과를 막지 않음(가산·정직).
        pass

    return ClimateRiskAssessmentResponse(
        assessment_id=assessment.id,
        project_id=assessment.project_id,
        flood_risk_score=assessment.flood_risk_score,
        heat_risk_score=assessment.heat_risk_score,
        overall_risk_level=assessment.overall_risk_level,
        annual_expected_loss_krw=assessment.annual_expected_loss_krw,
        risk_factors=assessment.risk_factors or [],
        mitigation_tips=assessment.mitigation_tips or [],
        insurance_recommendations=[
            InsuranceRecommendationResponse(
                recommendation_id=recommendation.id,
                coverage_type=recommendation.coverage_type,
                priority=recommendation.priority,
                annual_premium_estimate_krw=recommendation.annual_premium_estimate_krw,
                coverage_limit_krw=recommendation.coverage_limit_krw,
                rationale=recommendation.rationale or "",
            )
            for recommendation in recommendations
        ],
        created_at=assessment.created_at,
        evidence=evidence,
    )
