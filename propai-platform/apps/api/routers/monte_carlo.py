"""Monte Carlo 시뮬레이션 라우터.

10,000회 확률적 시뮬레이션을 통해 NPV/IRR 분포,
VaR, Expected Shortfall 등 리스크 지표를 산출하는 API.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth.jwt_handler import CurrentUser
from apps.api.auth.rbac import RequirePermission
from apps.api.database.session import get_db
from apps.api.services.monte_carlo_service import MonteCarloService

router = APIRouter()


# ── 요청/응답 스키마 ──


class MonteCarloRequest(BaseModel):
    """Monte Carlo 시뮬레이션 요청 스키마."""

    project_id: UUID
    base_revenue_krw: float = Field(gt=0, description="기본 연간 매출 (원)")
    base_cost_krw: float = Field(gt=0, description="기본 연간 비용 (원)")
    total_investment_krw: float = Field(gt=0, description="총 투자비 (원)")
    discount_rate: float = Field(
        default=0.08, ge=0, le=1, description="기본 할인율"
    )
    base_vacancy_rate: float = Field(
        default=0.05, ge=0, le=1, description="기본 공실률"
    )
    analysis_years: int = Field(
        default=10, ge=1, le=50, description="분석 기간 (년)"
    )
    exit_value_ratio: float = Field(
        default=1.18, description="출구 가치 배율"
    )
    n_simulations: int = Field(
        default=10_000, ge=100, le=100_000, description="시뮬레이션 횟수"
    )
    scenario_name: str = Field(
        default="기본 시나리오", max_length=200, description="시나리오명"
    )
    seed: int | None = Field(
        default=None, description="난수 시드 (재현성 보장용, null이면 무작위)"
    )


class MonteCarloResponse(BaseModel):
    """Monte Carlo 시뮬레이션 응답 스키마."""

    id: UUID
    project_id: UUID
    scenario_name: str
    n_simulations: int

    # NPV 백분위수
    p10_npv: float = Field(description="NPV 10번째 백분위수 (원)")
    p50_npv: float = Field(description="NPV 중앙값 (원)")
    p90_npv: float = Field(description="NPV 90번째 백분위수 (원)")

    # IRR 백분위수
    p10_irr: float = Field(description="IRR 10번째 백분위수")
    p50_irr: float = Field(description="IRR 중앙값")
    p90_irr: float = Field(description="IRR 90번째 백분위수")

    # 리스크 지표
    var_95: float = Field(description="95% VaR (절대값, 원)")
    expected_shortfall: float = Field(description="Expected Shortfall (절대값, 원)")

    # 통계 요약
    mean_npv: float = Field(description="NPV 평균 (원)")
    std_npv: float = Field(description="NPV 표준편차 (원)")

    # 표준 근거 블록(#5): {evidence, legal_refs, provenance, trust}. 가산(graceful·구버전 None).
    evidence: dict | None = Field(default=None, description="근거·산식·출처 블록")

    class Config:
        """Pydantic 모델 설정."""
        from_attributes = True


# ── 엔드포인트 ──


@router.post("/simulate", response_model=MonteCarloResponse)
async def run_simulation(
    body: MonteCarloRequest,
    current_user: CurrentUser = Depends(RequirePermission("finance", "write")),
    db: AsyncSession = Depends(get_db),
) -> MonteCarloResponse:
    """Monte Carlo 시뮬레이션을 실행한다.

    10,000회 확률적 시뮬레이션으로 NPV/IRR 분포를 산출하고,
    VaR, Expected Shortfall 등 리스크 지표를 반환한다.
    """
    service = MonteCarloService(db)

    try:
        result = await service.simulate(
            project_id=body.project_id,
            tenant_id=current_user.tenant_id,
            base_revenue=body.base_revenue_krw,
            base_cost=body.base_cost_krw,
            base_rate=body.discount_rate,
            base_vacancy=body.base_vacancy_rate,
            total_investment=body.total_investment_krw,
            analysis_years=body.analysis_years,
            exit_value_ratio=body.exit_value_ratio,
            n_simulations=body.n_simulations,
            scenario_name=body.scenario_name,
            seed=body.seed,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    return MonteCarloResponse(
        id=result.id,
        project_id=result.project_id,
        scenario_name=result.scenario_name,
        n_simulations=result.n_simulations,
        p10_npv=result.p10_npv,
        p50_npv=result.p50_npv,
        p90_npv=result.p90_npv,
        p10_irr=result.p10_irr,
        p50_irr=result.p50_irr,
        p90_irr=result.p90_irr,
        var_95=result.var_95,
        expected_shortfall=result.expected_shortfall,
        mean_npv=result.mean_npv,
        std_npv=result.std_npv,
    )
