"""건축물대장 정보 조회 서비스.

공공데이터포털 건축물대장정보 서비스 (건축HUB) 연동.
엔드포인트: http://apis.data.go.kr/1613000/BldRgstHubService/

PNU 또는 시군구코드+법정동코드 기반으로 건축물 현황을 조회.
"""

import logging
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

BASE_URL = "http://apis.data.go.kr/1613000/BldRgstHubService"


class BuildingRegistryService:
    """건축물대장 조회 서비스."""

    async def get_building_info(self, sigungu_cd: str, bjdong_cd: str, bun: str = "", ji: str = "") -> dict[str, Any] | None:
        """시군구코드+법정동코드로 건축물대장 기본개요를 조회.

        Args:
            sigungu_cd: 시군구코드 (5자리, 예: 11680=강남구)
            bjdong_cd: 법정동코드 (5자리, 예: 10300=역삼동)
            bun: 본번 (4자리, 선택)
            ji: 부번 (4자리, 선택)
        """
        if not settings.MOLIT_API_KEY:
            return None

        params: dict[str, str] = {
            "serviceKey": settings.MOLIT_API_KEY,
            "sigunguCd": sigungu_cd,
            "bjdongCd": bjdong_cd,
            "numOfRows": "1",
            "pageNo": "1",
            "_type": "json",
        }
        if bun:
            params["bun"] = bun.zfill(4)
        if ji:
            params["ji"] = ji.zfill(4)

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(f"{BASE_URL}/getBrBasisOulnInfo", params=params)
                resp.raise_for_status()
                data = resp.json()

            header = data.get("response", {}).get("header", {})
            if header.get("resultCode") != "00":
                logger.warning("건축물대장 조회 실패: %s", header.get("resultMsg"))
                return None

            items = data.get("response", {}).get("body", {}).get("items", {}).get("item", [])
            if not items:
                return None

            item = items[0] if isinstance(items, list) else items
            return {
                "building_name": item.get("bldNm", ""),
                "main_purpose": item.get("mainPurpsCdNm", ""),
                "total_area_sqm": float(item.get("totArea", 0) or 0),
                "building_area_sqm": float(item.get("archArea", 0) or 0),
                "bcr_pct": float(item.get("bcRat", 0) or 0),
                "far_pct": float(item.get("vlRat", 0) or 0),
                "ground_floors": int(item.get("grndFlrCnt", 0) or 0),
                "underground_floors": int(item.get("ugrndFlrCnt", 0) or 0),
                "structure": item.get("strctCdNm", ""),
                "use_approval_date": item.get("useAprDay", ""),
                "new_old_code": item.get("newOldRegstrGbCdNm", ""),
                "address": item.get("platPlc", ""),
                "road_address": item.get("newPlatPlc", ""),
            }
        except Exception as e:
            logger.warning("건축물대장 API 오류: %s", str(e))
            return None

    async def get_building_by_pnu(self, pnu: str) -> dict[str, Any] | None:
        """PNU(19자리)에서 시군구코드/법정동코드/본번/부번을 추출하여 조회."""
        if len(pnu) < 19:
            return None

        sigungu_cd = pnu[:5]
        bjdong_cd = pnu[5:10]
        # PNU 구조: 시군구(5) + 법정동(5) + 대지구분(1) + 본번(4) + 부번(4)
        bun = pnu[11:15]
        ji = pnu[15:19]

        return await self.get_building_info(sigungu_cd, bjdong_cd, bun, ji)
