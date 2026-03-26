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
    )
