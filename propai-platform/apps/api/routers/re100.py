"""RE100 이행률 추적 및 K-ETS 배출권 비용 산출 엔드포인트."""

from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth.jwt_handler import CurrentUser
from apps.api.auth.rbac import RequirePermission
from apps.api.database.session import get_db
from apps.api.services.re100_tracker_service import Re100TrackerService

router = APIRouter()


# ── 요청/응답 스키마 ──


class Re100TrackRequest(BaseModel):
    """RE100 추적 요청."""

    project_id: UUID = Field(..., description="프로젝트 ID")
    tracking_year: int = Field(..., description="추적 연도", ge=2020, le=2060)
    total_electricity_mwh: float = Field(
        ..., description="총 전력 사용량 (MWh)", gt=0
    )
    renewable_electricity_mwh: float = Field(
        ..., description="재생에너지 전력량 (MWh)", ge=0
    )
    kts_unit_price_krw: int = Field(
        default=18_000, description="K-ETS 배출권 단가 (원/tCO2eq)", ge=0
    )


class EmissionsResponse(BaseModel):
    """배출량 응답."""

    total_emissions_tco2eq: float
    baseline_emissions_tco2eq: float
    excess_emissions_tco2eq: float


class ProcurementItem(BaseModel):
    """조달 수단 비용 비교 항목."""

    method: str
    description: str
    unit_cost_krw_mwh: int
    total_cost_krw: float


class RoadmapItem(BaseModel):
    """RE100 이행 로드맵 항목."""

    target_year: int
    target_rate: float
    current_gap: float
    additional_renewable_mwh: float
    annual_increase_mwh: float


class Re100TrackResponse(BaseModel):
    """RE100 추적 응답."""

    id: UUID
    re100_rate: float = Field(..., description="RE100 이행률 (0.0~1.0)")
    emissions: EmissionsResponse
    kts_cost: float = Field(..., description="K-ETS 배출권 총 비용 (원)")
    procurement_comparison: list[ProcurementItem]
    roadmap: list[RoadmapItem]
    summary: str


# ── 엔드포인트 ──


@router.post("/track", response_model=Re100TrackResponse)
async def track_re100(
    body: Re100TrackRequest,
    current_user: CurrentUser = Depends(RequirePermission("re100", "read")),
    db: AsyncSession = Depends(get_db),
) -> Re100TrackResponse:
    """RE100 이행률을 추적하고 K-ETS 비용을 산출한다."""
    service = Re100TrackerService(db)
    record = await service.track(
        tenant_id=current_user.tenant_id,
        project_id=body.project_id,
        tracking_year=body.tracking_year,
        total_electricity_mwh=body.total_electricity_mwh,
        renewable_electricity_mwh=body.renewable_electricity_mwh,
        kts_unit_price_krw=body.kts_unit_price_krw,
    )

    return Re100TrackResponse(
        id=record.id,
        re100_rate=record.re100_rate,
        emissions=EmissionsResponse(
            total_emissions_tco2eq=record.total_emissions_tco2eq,
            baseline_emissions_tco2eq=record.baseline_emissions_tco2eq,
            excess_emissions_tco2eq=record.excess_emissions_tco2eq,
        ),
        kts_cost=record.kts_total_cost_krw,
        procurement_comparison=[
            ProcurementItem(**item)
            for item in (record.procurement_breakdown_json or [])
        ],
        roadmap=[
            RoadmapItem(**item) for item in (record.roadmap_json or [])
        ],
        summary=record.summary or "",
    )
