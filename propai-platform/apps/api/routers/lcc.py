"""LCC 생애주기비용 산정 엔드포인트 (ISO 15686-5).

POST /api/v1/lcc/calculate — 40년 LCC NPV 산출
"""

from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth.jwt_handler import CurrentUser
from apps.api.auth.rbac import RequirePermission
from apps.api.database.session import get_db
from apps.api.services.lcc_service import LCCService

router = APIRouter()


# ── 요청/응답 스키마 ──


class LccCalculateRequest(BaseModel):
    """LCC 산출 요청."""

    project_id: UUID = Field(..., description="프로젝트 ID")
    initial_construction_cost: float = Field(..., gt=0, description="초기 건설비 (원)")
    annual_maintenance_cost: float = Field(..., ge=0, description="연간 유지보수비 (원)")
    annual_energy_cost: float = Field(..., ge=0, description="연간 에너지비 (원)")
    nominal_rate: float = Field(default=0.035, ge=0, description="명목할인율")
    inflation_rate: float = Field(default=0.013, ge=0, description="물가상승률")
    energy_escalation_rate: float = Field(default=0.02, ge=0, description="에너지 가격 상승률")
    analysis_period_years: int = Field(default=40, ge=1, le=100, description="분석 기간 (년)")
    repair_schedule: list[dict] | None = Field(
        default=None, description="대수선 스케줄 (미지정 시 기본값 사용)"
    )


class LccAlternativeResult(BaseModel):
    """대안 비교 결과."""

    alternative: str
    description: str
    extra_initial_cost_ratio: float
    energy_saving_rate: float
    npv_total_krw: float


class LccCalculateResponse(BaseModel):
    """LCC 산출 응답."""

    id: UUID
    project_id: UUID
    analysis_period_years: int
    nominal_rate: float
    inflation_rate: float
    real_discount_rate: float
    initial_construction_cost: float
    annual_maintenance_cost: float
    annual_energy_cost: float
    energy_escalation_rate: float
    npv_total: float
    npv_construction: float
    npv_maintenance: float
    npv_energy: float
    npv_repair: float
    repair_schedule: list[dict] | None
    alternatives: list[dict] | None
    yearly_cashflow: list[dict] | None


# ── 엔드포인트 ──


@router.post("/calculate", response_model=LccCalculateResponse)
async def calculate_lcc(
    body: LccCalculateRequest,
    current_user: CurrentUser = Depends(RequirePermission("lcc", "write")),
    db: AsyncSession = Depends(get_db),
) -> LccCalculateResponse:
    """LCC 생애주기비용을 산출한다.

    ISO 15686-5 기준으로 40년 분석기간의 NPV를 계산하고,
    기본안/고단열안/태양광안 대안 비교를 수행한다.
    """
    service = LCCService(db)
    record = await service.calculate(
        tenant_id=current_user.tenant_id,
        project_id=body.project_id,
        initial_construction_cost=body.initial_construction_cost,
        annual_maintenance_cost=body.annual_maintenance_cost,
        annual_energy_cost=body.annual_energy_cost,
        nominal_rate=body.nominal_rate,
        inflation_rate=body.inflation_rate,
        energy_escalation_rate=body.energy_escalation_rate,
        analysis_period_years=body.analysis_period_years,
        repair_schedule=body.repair_schedule,
    )
    return LccCalculateResponse(
        id=record.id,
        project_id=record.project_id,
        analysis_period_years=record.analysis_period_years,
        nominal_rate=record.nominal_rate,
        inflation_rate=record.inflation_rate,
        real_discount_rate=record.real_discount_rate,
        initial_construction_cost=record.initial_construction_cost,
        annual_maintenance_cost=record.annual_maintenance_cost,
        annual_energy_cost=record.annual_energy_cost,
        energy_escalation_rate=record.energy_escalation_rate,
        npv_total=record.npv_total,
        npv_construction=record.npv_construction,
        npv_maintenance=record.npv_maintenance,
        npv_energy=record.npv_energy,
        npv_repair=record.npv_repair,
        repair_schedule=record.repair_schedule_json,
        alternatives=record.alternatives_json,
        yearly_cashflow=record.yearly_cashflow_json,
    )
