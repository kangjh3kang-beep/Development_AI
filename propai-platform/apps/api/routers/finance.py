"""Finance router for jeonse, union contribution, and feasibility analysis."""

import logging
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
logger = logging.getLogger(__name__)


def _to_feasibility_response(result) -> FeasibilityAnalysisResponse:
    assumptions = result.assumptions or {}
    cashflows = result.cash_flow_yearly or []
    discount_rate = float(assumptions.get("discount_rate", 0.05))
    # 표준 근거 블록(#5): NPV·IRR·회수기간·위험점수의 실값·산식·출처를 가산(graceful·무목업).
    evidence_block = None
    try:
        from app.services.data_validation.evidence_contract import build_evidence_block

        evidence_block = build_evidence_block(
            items=[
                {"label": "순현재가치(NPV)", "value": round(result.npv),
                 "basis": f"Σ 연도별 현금흐름/(1+할인율 {discount_rate:.1%})^t − 총투자비(DCF)"},
                {"label": "내부수익률(IRR)", "value": round(result.irr, 4),
                 "basis": "NPV=0이 되는 할인율(이분법 수치해)"},
                {"label": "회수기간(월)", "value": result.payback_period_months,
                 "basis": "누적 현금흐름이 0을 넘는 시점(선형보간)"},
                {"label": "위험점수", "value": round(result.risk_score, 4),
                 "basis": "IRR·회수기간·할인율 페널티 − 영업이익률 크레딧 가중합"},
            ],
            sources=["프로젝트 투자·매출 가정(사용자 입력)"],
        )
    except Exception as e:  # noqa: BLE001 — 근거 블록 실패는 기존 결과를 막지 않음(가산·정직).
        logger.warning("사업성 분석 근거 블록 생성 스킵: %s", str(e)[:120])
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
        discount_rate=discount_rate,
        annual_growth_rate=float(assumptions.get("annual_growth_rate", 0.02)),
        analysis_years=int(assumptions.get("analysis_years", len(cashflows) or 10)),
        exit_value_krw=float(assumptions.get("exit_value_krw", result.total_investment)),
        cashflows=cashflows,
        assumptions=assumptions,
        created_at=result.created_at,
        evidence=evidence_block,
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
    # 표준 근거 블록(#5): 전세가율·위험점수의 실값·산식·출처를 가산(graceful·무목업).
    evidence_block = None
    try:
        from app.services.data_validation.evidence_contract import build_evidence_block

        evidence_block = build_evidence_block(
            items=[
                {"label": "전세가율", "value": round(result.jeonse_ratio, 4),
                 "basis": "전세가 ÷ 매매가(추정시세)"},
                {"label": "위험등급", "value": result.risk_level,
                 "basis": "전세가율 구간 분류(SAFE<0.6≤LOW<0.7≤MEDIUM<0.8≤HIGH<0.9≤CRITICAL)"},
                {"label": "위험점수", "value": round(result.risk_score, 4),
                 "basis": f"위험등급 {result.risk_level} 기준 점수"},
            ],
            sources=["국토교통부 실거래가(MOLIT)"],
        )
    except Exception as e:  # noqa: BLE001 — 근거 블록 실패는 기존 결과를 막지 않음(가산·정직).
        logger.warning("전세 리스크 근거 블록 생성 스킵: %s", str(e)[:120])
    return JeonseRiskResponse(
        jeonse_ratio=result.jeonse_ratio,
        risk_level=result.risk_level,
        risk_score=result.risk_score,
        analysis=result.analysis,
        factors=result.factors,
        evidence=evidence_block,
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
    # 표준 근거 블록(#5): 비례율·분담금의 실값·산식·출처를 가산(graceful·무목업).
    evidence_block = None
    try:
        from app.services.data_validation.evidence_contract import build_evidence_block

        evidence_block = build_evidence_block(
            items=[
                {"label": "비례율", "value": round(result.proportional_rate, 4),
                 "basis": "총사업비 ÷ 총감정가(비례율법)"},
                {"label": "개인 분담금", "value": round(result.individual_contribution),
                 "basis": "입주희망면적×평균분양가 − (개인감정가×비례율)"},
                {"label": "총사업비", "value": round(result.total_project_cost),
                 "basis": "입력 총사업비(조합 기준)"},
            ],
            sources=["조합 제출 감정평가·사업비 자료"],
        )
    except Exception as e:  # noqa: BLE001 — 근거 블록 실패는 기존 결과를 막지 않음(가산·정직).
        logger.warning("조합 분담금 근거 블록 생성 스킵: %s", str(e)[:120])
    return UnionContributionResponse(
        proportional_rate=result.proportional_rate,
        individual_contribution=result.individual_contribution,
        total_project_cost=result.total_project_cost,
        breakdown=result.breakdown,
        scenarios=result.scenarios,
        evidence=evidence_block,
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
