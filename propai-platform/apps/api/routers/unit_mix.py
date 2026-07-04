"""유닛믹스 최적화 라우터."""


from fastapi import APIRouter, Depends
from pydantic import BaseModel

from apps.api.app.services.feasibility.unit_mix_optimizer import (
    DEFAULT_DEMAND_RATIO,
    DEFAULT_PRICE_BY_TYPE,
    STANDARD_UNIT_TYPES,
    UnitMixInput,
    UnitMixOptimizer,
)
from apps.api.auth.jwt_handler import CurrentUser, get_current_user

router = APIRouter()


class UnitMixRequest(BaseModel):
    """유닛믹스 최적화 요청."""

    total_gfa_sqm: float
    land_area_sqm: float = 1000
    max_far_pct: float = 250
    max_bcr_pct: float = 60
    max_floors: int = 25
    region: str = "서울"
    price_by_type: dict | None = None
    demand_ratio: dict | None = None
    enabled_types: list | None = None


@router.post("/optimize")
async def optimize_unit_mix(
    req: UnitMixRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """수익 극대화 최적 유닛믹스 계산."""
    optimizer = UnitMixOptimizer()
    inp = UnitMixInput(**req.model_dump())
    return optimizer.optimize(inp)


@router.get("/types")
async def get_unit_types(
    current_user: CurrentUser = Depends(get_current_user),
):
    """표준 평형 타입 및 기본 시세/수요 비율 조회."""
    return {
        "types": STANDARD_UNIT_TYPES,
        "default_prices": DEFAULT_PRICE_BY_TYPE,
        "default_demand": DEFAULT_DEMAND_RATIO,
    }
