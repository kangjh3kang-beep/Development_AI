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
                "household_count": int(item.get("hhldCnt", 0) or 0),  # 세대수
                "family_count": int(item.get("fmlyCnt", 0) or 0),  # 가구수
                "ho_count": int(item.get("hoCnt", 0) or 0),  # 호수
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

    async def get_title_by_pnu(self, pnu: str) -> dict[str, Any] | None:
        """PNU 기반 표제부(getBrTitleInfo) 조회 — 사용승인일·구조·세대수가 충실.

        총괄표제부(getBrBasisOulnInfo)가 사용승인일을 비워두는 경우가 많아,
        노후도·세대수 산정에는 표제부를 사용한다.
        """
        if len(pnu) < 19 or not settings.MOLIT_API_KEY:
            return None
        params = {
            "serviceKey": settings.MOLIT_API_KEY,
            "sigunguCd": pnu[:5], "bjdongCd": pnu[5:10],
            "bun": pnu[11:15], "ji": pnu[15:19],
            "numOfRows": "10", "pageNo": "1", "_type": "json",
        }
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(f"{BASE_URL}/getBrTitleInfo", params=params)
                resp.raise_for_status()
                items = (resp.json().get("response", {}).get("body", {})
                         .get("items", {}) or {}).get("item")
            if not items:
                return None
            rows = items if isinstance(items, list) else [items]
            # 주된 동(연면적 최대) 선택
            def _f(x, k):
                try:
                    return float(x.get(k, 0) or 0)
                except (TypeError, ValueError):
                    return 0.0
            main = max(rows, key=lambda x: _f(x, "totArea"))
            return {
                "building_name": main.get("bldNm", ""),
                "use_approval_date": str(main.get("useAprDay", "") or ""),
                "structure": main.get("strctCdNm", ""),
                "main_purpose": main.get("mainPurpsCdNm", ""),
                "ground_floors": int(_f(main, "grndFlrCnt")),
                "total_area_sqm": _f(main, "totArea"),
                "household_count": int(_f(main, "hhldCnt")),
                "ho_count": int(_f(main, "hoCnt")),
                "family_count": int(_f(main, "fmlyCnt")),
                "dong_count": len(rows),
            }
        except Exception as e:  # noqa: BLE001
            logger.warning("표제부 조회 실패: %s (%s)", pnu, str(e))
            return None
