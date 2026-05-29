"""자동 용도지역 감지 + 종합 토지정보 라우터."""

import re

from fastapi import APIRouter
from pydantic import BaseModel

from apps.api.app.services.zoning.auto_zoning_service import AutoZoningService
from apps.api.app.services.land_intelligence.land_info_service import LandInfoService

router = APIRouter()


class ZoningAnalyzeRequest(BaseModel):
    """용도지역 분석 요청."""

    address: str
    pnu: str | None = None
    bcode: str | None = None  # 카카오 법정동 코드 (10자리)
    jibun_address: str | None = None  # 카카오 지번 주소


def _build_pnu_from_bcode(bcode: str, jibun_address: str) -> str | None:
    """법정동 코드(10자리) + 지번 주소에서 PNU(19자리)를 구성한다.

    PNU 구조: 법정동코드(10) + 대지구분(1, 1=대지/2=산) + 본번(4) + 부번(4)
    예: 4115010100 + 1 + 0226 + 0002 = 4115010100102260002
    """
    if not bcode or len(bcode) < 10:
        return None

    # 지번에서 본번/부번 추출 (예: "226-2", "224", "산123-4")
    jibun = jibun_address or ""
    # 지번 주소에서 마지막 번지 부분 추출
    match = re.search(r"(산)?(\d+)(?:-(\d+))?(?:\s|$)", jibun)
    if not match:
        return None

    is_mountain = "2" if match.group(1) else "1"  # 산=2, 대지=1
    main_num = match.group(2).zfill(4)  # 본번 4자리
    sub_num = (match.group(3) or "0").zfill(4)  # 부번 4자리

    return f"{bcode}{is_mountain}{main_num}{sub_num}"


@router.post("/analyze")
async def analyze_zoning(req: ZoningAnalyzeRequest):
    """주소 기반 자동 용도지역 감지 및 법적 한도 매핑."""
    service = AutoZoningService()
    return await service.analyze_by_address(req.address)


@router.post("/comprehensive")
async def comprehensive_land_analysis(req: ZoningAnalyzeRequest):
    """종합 토지정보 수집 — 토지대장+공시지가+토지이용계획+조례 통합.

    카카오 주소 검색의 bcode(법정동 코드)가 전달되면 PNU를 직접 구성하여
    VWORLD 지오코딩 없이 토지정보를 조회한다.
    """
    # PNU 결정: 직접 전달 > bcode로 구성 > VWORLD 지오코딩
    pnu = req.pnu
    if not pnu and req.bcode and req.jibun_address:
        pnu = _build_pnu_from_bcode(req.bcode, req.jibun_address)

    service = LandInfoService()
    return await service.collect_comprehensive(req.address, pnu=pnu)
