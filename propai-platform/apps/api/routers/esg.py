"""ESG router for G84."""

from fastapi import APIRouter, Depends
from packages.schemas.models import ESGAssessmentRequest, ESGAssessmentResponse
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth.jwt_handler import CurrentUser
from apps.api.auth.rbac import RequirePermission
from apps.api.database.session import get_db
from apps.api.services.esg_service import ESGService

router = APIRouter()


@router.post("/assessment", response_model=ESGAssessmentResponse)
async def run_esg_assessment(
    body: ESGAssessmentRequest,
    current_user: CurrentUser = Depends(RequirePermission("esg", "write")),
    db: AsyncSession = Depends(get_db),
) -> ESGAssessmentResponse:
    """Create ESG, carbon, and GRESB assessment outputs."""
    service = ESGService(db)
    report, footprint, assessment = await service.assess(
        tenant_id=current_user.tenant_id,
        project_id=body.project_id,
        reporting_period=body.reporting_period,
        gross_floor_area_sqm=body.gross_floor_area_sqm,
        scope1_tco2e=body.scope1_tco2e,
        scope2_tco2e=body.scope2_tco2e,
        scope3_tco2e=body.scope3_tco2e,
        energy_independence_rate=body.energy_independence_rate,
        climate_risk_score=body.climate_risk_score,
        lost_time_incident_rate=body.lost_time_incident_rate,
        community_programs_count=body.community_programs_count,
        board_independence_ratio=body.board_independence_ratio,
        disclosures=body.disclosures,
    )
    return ESGAssessmentResponse(
        assessment_id=assessment.id,
        project_id=report.project_id,
        reporting_period=report.reporting_period,
        status=report.status,
        environmental_score=report.environmental_score,
        social_score=report.social_score,
        governance_score=report.governance_score,
        overall_score=assessment.score,
        gresb_rating=assessment.rating,
        carbon_total_tco2e=footprint.scope1_tco2e + footprint.scope2_tco2e + footprint.scope3_tco2e,
        disclosures=report.disclosures_json or [],
        action_plan=assessment.action_plan,
    )
