import httpx
from typing import List, Dict, Optional
from app.core.config import settings
import structlog

logger = structlog.get_logger()

class MOLITService:
    """국토교통부 MOLIT API 연동"""

    async def get_apt_transactions(self, region_code: str, year_month: str) -> List[Dict]:
        """아파트 매매 실거래가 조회"""
        params = {
            "serviceKey": settings.MOLIT_API_KEY,
            "LAWD_CD": region_code,
            "DEAL_YMD": year_month,
            "numOfRows": 1000,
            "pageNo": 1
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                resp = await client.get(settings.MOLIT_TRANSACTION_URL, params=params)
                resp.raise_for_status()
                data = resp.json()
                return data.get("response", {}).get("body", {}).get("items", {}).get("item", [])
            except httpx.HTTPStatusError as e:
                logger.error("MOLIT 실거래가 HTTP 오류", status=e.response.status_code, error=str(e))
                return []
            except httpx.RequestError as e:
                logger.error("MOLIT 실거래가 네트워크 오류", error=str(e))
                return []

    async def get_officetel_transactions(self, region_code: str, year_month: str) -> List[Dict]:
        """오피스텔 매매 실거래가 조회"""
        return await self._fetch_transactions(
            "https://apis.data.go.kr/1613000/RTMSDataSvcOffiTrade/getRTMSDataSvcOffiTrade",
            region_code, year_month,
        )

    async def get_villa_transactions(self, region_code: str, year_month: str) -> List[Dict]:
        """연립/다세대 매매 실거래가 조회"""
        return await self._fetch_transactions(
            "https://apis.data.go.kr/1613000/RTMSDataSvcRHTrade/getRTMSDataSvcRHTrade",
            region_code, year_month,
        )

    async def get_commercial_transactions(self, region_code: str, year_month: str) -> List[Dict]:
        """상업/업무용 부동산 매매 실거래가 조회"""
        return await self._fetch_transactions(
            "https://apis.data.go.kr/1613000/RTMSDataSvcNrgTrade/getRTMSDataSvcNrgTrade",
            region_code, year_month,
        )

    async def _fetch_transactions(self, url: str, region_code: str, year_month: str) -> List[Dict]:
        params = {
            "serviceKey": settings.MOLIT_API_KEY,
            "LAWD_CD": region_code,
            "DEAL_YMD": year_month,
            "numOfRows": 100,
            "pageNo": 1,
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()
                items = data.get("response", {}).get("body", {}).get("items", {})
                if isinstance(items, dict):
                    return items.get("item", [])
                return []
            except Exception as e:
                logger.warning("MOLIT 실거래가 조회 실패", url=url[:60], error=str(e)[:200])
                return []

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
