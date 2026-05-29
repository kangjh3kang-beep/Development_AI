"""자동 용도지역 감지 + 종합 토지정보 라우터."""

from fastapi import APIRouter
from pydantic import BaseModel

from apps.api.app.services.zoning.auto_zoning_service import AutoZoningService
from apps.api.app.services.land_intelligence.land_info_service import LandInfoService

router = APIRouter()


class ZoningAnalyzeRequest(BaseModel):
    """용도지역 분석 요청."""

    address: str
    pnu: str | None = None  # 프론트엔드에서 VWORLD 지오코딩으로 미리 얻은 PNU


@router.post("/analyze")
async def analyze_zoning(req: ZoningAnalyzeRequest):
    """주소 기반 자동 용도지역 감지 및 법적 한도 매핑."""
    service = AutoZoningService()
    return await service.analyze_by_address(req.address)


@router.post("/comprehensive")
async def comprehensive_land_analysis(req: ZoningAnalyzeRequest):
    """종합 토지정보 수집 — 토지대장+공시지가+토지이용계획+조례 통합."""
    service = LandInfoService()
    return await service.collect_comprehensive(req.address, pnu=req.pnu)
