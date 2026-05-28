"""자동 용도지역 감지 + 종합 토지정보 라우터."""

from fastapi import APIRouter
from pydantic import BaseModel

from apps.api.app.services.zoning.auto_zoning_service import AutoZoningService
from apps.api.app.services.land_intelligence.land_info_service import LandInfoService
from apps.api.app.core.config import settings as app_settings

router = APIRouter()


class ZoningAnalyzeRequest(BaseModel):
    """용도지역 분석 요청."""

    address: str


@router.post("/analyze")
async def analyze_zoning(req: ZoningAnalyzeRequest):
    """주소 기반 자동 용도지역 감지 및 법적 한도 매핑."""
    service = AutoZoningService()
    return await service.analyze_by_address(req.address)


@router.post("/comprehensive")
async def comprehensive_land_analysis(req: ZoningAnalyzeRequest):
    """종합 토지정보 수집 — 토지대장+공시지가+토지이용계획+조례 통합."""
    service = LandInfoService()
    return await service.collect_comprehensive(req.address)


@router.get("/debug-keys")
async def debug_api_keys():
    """API 키 설정 상태 확인 (값은 마스킹)."""
    vk = app_settings.VWORLD_API_KEY
    mk = app_settings.MOLIT_API_KEY
    lg = app_settings.MOLEG_API_KEY
    return {
        "VWORLD_API_KEY": f"{vk[:4]}...{vk[-4:]}" if len(vk) > 8 else ("SET" if vk else "EMPTY"),
        "MOLIT_API_KEY": f"{mk[:4]}...{mk[-4:]}" if len(mk) > 8 else ("SET" if mk else "EMPTY"),
        "MOLEG_API_KEY": f"{lg[:4]}...{lg[-4:]}" if len(lg) > 8 else ("SET" if lg else "EMPTY"),
        "VWORLD_BASE_URL": app_settings.VWORLD_BASE_URL,
    }
