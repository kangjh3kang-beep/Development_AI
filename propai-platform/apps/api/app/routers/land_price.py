"""토지 적정 매입가 추정 라우터 — 토지조서 매입예정가 자동 산정."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.services.land_intelligence.land_price_estimator import estimate_land_price

router = APIRouter(prefix="/api/v1/land-price", tags=["토지 적정가"])


class LandPriceRequest(BaseModel):
    pnu: str | None = None
    address: str = ""
    area_sqm: float | None = None
    official_price_per_sqm: float | None = None


@router.post("/estimate")
async def land_price_estimate(req: LandPriceRequest):
    """공시지가×지역 시세보정으로 적정 매입가 추정(참고값, 수정가능)."""
    return await estimate_land_price(
        pnu=req.pnu, address=req.address,
        area_sqm=req.area_sqm, official_price_per_sqm=req.official_price_per_sqm,
    )
