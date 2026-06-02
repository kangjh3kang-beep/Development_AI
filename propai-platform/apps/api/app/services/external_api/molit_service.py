import httpx
from typing import List, Dict, Optional
from app.core.config import settings
import structlog

from apps.api.integrations.molit_client import MolitClient

logger = structlog.get_logger()

class MOLITService:
    """국토교통부 MOLIT API 연동.

    실거래(매매)는 검증된 MolitClient(apis.data.go.kr/1613000, _type=json,
    유형별 Dev/비-Dev 자동, 영문필드 정규화)에 위임한다.
    반환은 정규화 dict: price_10k_won/area_m2/building_name/floor/dong/deal_date/prop_type.
    (구 openapi.molit.go.kr·XML·한글필드 직파싱은 폐기됨)
    """

    def __init__(self) -> None:
        self._client = MolitClient()

    async def get_apt_transactions(self, region_code: str, year_month: str) -> List[Dict]:
        """아파트 매매 실거래가 조회 (정규화)."""
        return await self._client.get_transactions(region_code, year_month, prop_type="apt")

    async def get_officetel_transactions(self, region_code: str, year_month: str) -> List[Dict]:
        """오피스텔 매매 실거래가 조회 (정규화)."""
        return await self._client.get_transactions(region_code, year_month, prop_type="officetel")

    async def get_villa_transactions(self, region_code: str, year_month: str) -> List[Dict]:
        """연립/다세대 매매 실거래가 조회 (정규화)."""
        return await self._client.get_transactions(region_code, year_month, prop_type="villa")

    async def get_commercial_transactions(self, region_code: str, year_month: str) -> List[Dict]:
        """상업/업무용 부동산 매매 실거래가 조회 (정규화)."""
        return await self._client.get_transactions(region_code, year_month, prop_type="commercial")

    async def get_official_land_price(self, pnu_code: str) -> Optional[Dict]:
        """표준 공시지가 조회"""
        params = {
            "serviceKey": settings.MOLIT_API_KEY,
            "pnu": pnu_code,
            "numOfRows": 10,
            "pageNo": 1
        }
        url = "https://apis.data.go.kr/1611000/nsdi/LandPriceService/att/getLandPriceAttr"
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                return resp.json()
            except httpx.HTTPStatusError as e:
                logger.error("공시지가 HTTP 오류", pnu=pnu_code, status=e.response.status_code)
                return None
            except httpx.RequestError as e:
                logger.error("공시지가 네트워크 오류", pnu=pnu_code, error=str(e))
                return None
