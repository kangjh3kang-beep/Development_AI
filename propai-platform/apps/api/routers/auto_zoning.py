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


@router.get("/debug-keys")
async def debug_api_keys():
    """API 키 설정 상태 + VWORLD 직접 호출 테스트."""
    import httpx
    vk = app_settings.VWORLD_API_KEY
    mk = app_settings.MOLIT_API_KEY
    lg = app_settings.MOLEG_API_KEY

    # VWORLD 지오코딩 직접 테스트
    vworld_test = "NOT_TESTED"
    if vk:
        try:
            async with httpx.AsyncClient(timeout=10.0, headers={"Referer": "https://developmentai-production.up.railway.app"}) as client:
                resp = await client.get(
                    f"{app_settings.VWORLD_BASE_URL}/address",
                    params={"service": "address", "request": "getcoord", "key": vk, "address": "서울특별시 강남구 역삼동 123", "type": "PARCEL", "format": "json"},
                )
                data = resp.json()
                status = data.get("response", {}).get("status", "UNKNOWN")
                pnu = data.get("response", {}).get("refined", {}).get("structure", {}).get("level4LC", "")
                vworld_test = f"{status} | PNU={pnu}"
        except Exception as e:
            vworld_test = f"ERROR: {str(e)}"

    return {
        "VWORLD_API_KEY": f"{vk[:4]}...{vk[-4:]}" if len(vk) > 8 else ("SET" if vk else "EMPTY"),
        "MOLIT_API_KEY": f"{mk[:4]}...{mk[-4:]}" if len(mk) > 8 else ("SET" if mk else "EMPTY"),
        "MOLEG_API_KEY": f"{lg[:4]}...{lg[-4:]}" if len(lg) > 8 else ("SET" if lg else "EMPTY"),
        "VWORLD_BASE_URL": app_settings.VWORLD_BASE_URL,
        "VWORLD_GEOCODE_TEST": vworld_test,
    }
