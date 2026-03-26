"""Unified risk router for v53."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from packages.schemas.models import (
    UnifiedRiskAssessmentRequest,
    UnifiedRiskAssessmentResponse,
)
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth.jwt_handler import CurrentUser
from apps.api.auth.rbac import RequirePermission
from apps.api.database.session import get_db
from apps.api.services.risk_scoring_engine import RiskScoringEngine

router = APIRouter()


@router.post("/unified/analyze", response_model=UnifiedRiskAssessmentResponse)
async def analyze_unified_risk(
    body: UnifiedRiskAssessmentRequest,
    current_user: CurrentUser = Depends(RequirePermission("risk_engine", "write")),
    db: AsyncSession = Depends(get_db),
) -> UnifiedRiskAssessmentResponse:
    engine = RiskScoringEngine(db)
    result = await engine.analyze(
        tenant_id=current_user.tenant_id,
        project_id=body.project_id,
        base_project_cost_krw=body.base_project_cost_krw,
        market_risk_score=body.market_risk_score,
        ltv_ratio=body.ltv_ratio,
        dscr=body.dscr,
        permit_readiness_ratio=body.permit_readiness_ratio,
        occupancy_rate=body.occupancy_rate,
        presale_ratio=body.presale_ratio,
        climate_risk_score=body.climate_risk_score,
        cost_volatility_ratio=body.cost_volatility_ratio,
    )
    return UnifiedRiskAssessmentResponse.model_validate(result)


@router.get("/unified/{project_id}/latest", response_model=UnifiedRiskAssessmentResponse)
async def get_latest_unified_risk(
    project_id: UUID,
    current_user: CurrentUser = Depends(RequirePermission("risk_engine", "read")),
    db: AsyncSession = Depends(get_db),
) -> UnifiedRiskAssessmentResponse:
    engine = RiskScoringEngine(db)
    result = await engine.get_latest(
        tenant_id=current_user.tenant_id,
        project_id=project_id,
    )
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Latest unified risk assessment was not found",
        )
    return UnifiedRiskAssessmentResponse.model_validate(result)
