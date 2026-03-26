"""Finance router for jeonse, union contribution, and feasibility analysis."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from packages.schemas.models import (
    FeasibilityAnalysisRequest,
    FeasibilityAnalysisResponse,
    JeonseRiskRequest,
    JeonseRiskResponse,
    UnionContributionRequest,
    UnionContributionResponse,
)
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth.jwt_handler import CurrentUser
from apps.api.auth.rbac import RequirePermission
from apps.api.database.session import get_db
from apps.api.services.feasibility_service import FeasibilityService
from apps.api.services.jeonse_risk_service import JeonseRiskService
from apps.api.services.union_management_service import UnionManagementService

router = APIRouter()


def _to_feasibility_response(result) -> FeasibilityAnalysisResponse:
    assumptions = result.assumptions or {}
    cashflows = result.cash_flow_yearly or []
    return FeasibilityAnalysisResponse(
        id=result.id,
        project_id=result.project_id,
        scenario_name=result.scenario_name,
        npv=result.npv,
        irr=result.irr,
        payback_period_months=result.payback_period_months,
        total_investment_krw=result.total_investment,
        total_revenue_krw=result.total_revenue,
        risk_score=result.risk_score,
        discount_rate=float(assumptions.get("discount_rate", 0.05)),
        annual_growth_rate=float(assumptions.get("annual_growth_rate", 0.02)),
        analysis_years=int(assumptions.get("analysis_years", len(cashflows) or 10)),
        exit_value_krw=float(assumptions.get("exit_value_krw", result.total_investment)),
        cashflows=cashflows,
        assumptions=assumptions,
        created_at=result.created_at,
    )


@router.post("/jeonse-risk", response_model=JeonseRiskResponse)
async def analyze_jeonse_risk(
    body: JeonseRiskRequest,
    current_user: CurrentUser = Depends(RequirePermission("finance", "read")),
    db: AsyncSession = Depends(get_db),
) -> JeonseRiskResponse:
    """전세 리스크를 분석한다. 전세가율 기반 위험도 + LLM 종합 분석."""
    service = JeonseRiskService(db)
    result = await service.analyze(
        project_id=body.project_id,
        tenant_id=current_user.tenant_id,
        address=body.address,
        jeonse_price=body.jeonse_price,
        sale_price=body.sale_price,
    )
    return JeonseRiskResponse(
        jeonse_ratio=result.jeonse_ratio,
        risk_level=result.risk_level,
        risk_score=result.risk_score,
        analysis=result.analysis,
        factors=result.factors,
    )


@router.post("/union-contribution", response_model=UnionContributionResponse)
async def calculate_union_contribution(
    body: UnionContributionRequest,
    current_user: CurrentUser = Depends(RequirePermission("finance", "write")),
    db: AsyncSession = Depends(get_db),
) -> UnionContributionResponse:
    """재건축 조합원 분담금을 산정한다. 비례율법 기반 + LLM 시나리오."""
    service = UnionManagementService(db)
    result = await service.calculate_contribution(
        project_id=body.project_id,
        tenant_id=current_user.tenant_id,
        total_project_cost=body.total_project_cost,
        total_appraised_value=body.total_appraised_value,
        individual_appraised_value=body.individual_appraised_value,
        target_area_sqm=body.target_area_sqm,
        avg_sale_price_per_sqm=body.avg_sale_price_per_sqm,
    )
    return UnionContributionResponse(
        proportional_rate=result.proportional_rate,
        individual_contribution=result.individual_contribution,
        total_project_cost=result.total_project_cost,
        breakdown=result.breakdown,
        scenarios=result.scenarios,
    )


@router.post("/feasibility", response_model=FeasibilityAnalysisResponse)
async def analyze_feasibility(
    body: FeasibilityAnalysisRequest,
    current_user: CurrentUser = Depends(RequirePermission("finance", "write")),
    db: AsyncSession = Depends(get_db),
) -> FeasibilityAnalysisResponse:
    """Run and persist a deterministic feasibility analysis scenario."""
    service = FeasibilityService(db)
    try:
        result = await service.analyze(
            project_id=body.project_id,
            tenant_id=current_user.tenant_id,
            scenario_name=body.scenario_name,
            total_investment_krw=body.total_investment_krw,
            annual_revenue_krw=body.annual_revenue_krw,
            annual_operating_cost_krw=body.annual_operating_cost_krw,
            discount_rate=body.discount_rate,
            annual_growth_rate=body.annual_growth_rate,
            analysis_years=body.analysis_years,
            exit_value_krw=body.exit_value_krw,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return _to_feasibility_response(result)


@router.get("/feasibility/{project_id}/latest", response_model=FeasibilityAnalysisResponse)
async def get_latest_feasibility(
    project_id: UUID,
    current_user: CurrentUser = Depends(RequirePermission("finance", "read")),
    db: AsyncSession = Depends(get_db),
) -> FeasibilityAnalysisResponse:
    """Return the most recent persisted feasibility analysis for a project."""
    service = FeasibilityService(db)
    result = await service.get_latest(
        project_id=project_id,
        tenant_id=current_user.tenant_id,
    )
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="사업성 분석 결과를 찾을 수 없습니다",
        )
    return _to_feasibility_response(result)
