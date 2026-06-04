"""토지 적정 매입가 추정 라우터 — 토지조서 매입예정가 자동 산정."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import Response
from pydantic import BaseModel

from app.services.land_intelligence.land_price_estimator import estimate_land_price
from app.services.land_intelligence.desk_appraisal_service import desk_appraisal

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


class DeskAppraisalRequest(BaseModel):
    pnu: str | None = None
    address: str = ""
    area_sqm: float | None = None
    official_price_per_sqm: float | None = None
    comparable_avg_per_sqm: float | None = None   # 주변 토지 실거래 평균단가(선택)


@router.post("/desk-appraisal")
async def land_desk_appraisal(req: DeskAppraisalRequest):
    """예상 탁상감정 — 공시지가기준법 + 거래사례비교법 결합(정식감정 아님, 참고용)."""
    return await desk_appraisal(
        pnu=req.pnu, address=req.address, area_sqm=req.area_sqm,
        official_price_per_sqm=req.official_price_per_sqm,
        comparable_avg_per_sqm=req.comparable_avg_per_sqm,
    )


@router.post("/desk-appraisal/pdf")
async def land_desk_appraisal_pdf(req: DeskAppraisalRequest):
    """예상 탁상감정서 PDF 다운로드."""
    from app.services.land_intelligence.desk_appraisal_pdf import build_desk_appraisal_pdf

    result = await desk_appraisal(
        pnu=req.pnu, address=req.address, area_sqm=req.area_sqm,
        official_price_per_sqm=req.official_price_per_sqm,
        comparable_avg_per_sqm=req.comparable_avg_per_sqm,
    )
    if not result.get("ok"):
        return result  # 공시지가 미확인 등 — JSON 오류 반환
    pdf = build_desk_appraisal_pdf(result, address=req.address)
    return Response(
        content=pdf, media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=propai_desk_appraisal.pdf"},
    )
