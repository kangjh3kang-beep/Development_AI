"""나라장터(G2B) 공공데이터포털 API 클라이언트.

조달청 오픈 API를 통합 호출한다 (data.go.kr 1230000, 라이브 검증 2026-05):
1. 입찰공고정보서비스  /ad/BidPublicInfoService/getBidPblancListInfo{공종}
2. 낙찰정보서비스      /as/ScsbidInfoService/getScsbidListSttus{공종}

필수 파라미터: serviceKey, type=json, pageNo, numOfRows, inqryDiv=1,
              inqryBgnDt(YYYYMMDDHHMM), inqryEndDt
응답 경로: response.body.items (리스트), response.body.totalCount
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

# ── API 오퍼레이션 매핑 (업무구분별) ──
BID_OPERATIONS: dict[str, str] = {
    "공사": "getBidPblancListInfoCnstwk",
    "용역": "getBidPblancListInfoServc",
    "물품": "getBidPblancListInfoThng",
    "외자": "getBidPblancListInfoFrgcpt",
}

AWARD_OPERATIONS: dict[str, str] = {
    "공사": "getScsbidListSttusCnstwk",
    "용역": "getScsbidListSttusServc",
    "물품": "getScsbidListSttusThng",
    "외자": "getScsbidListSttusFrgcpt",
}

G2B_BASE_URL = "http://apis.data.go.kr/1230000"
BID_SERVICE_PATH = "/ad/BidPublicInfoService"
AWARD_SERVICE_PATH = "/as/ScsbidInfoService"


class G2BRateLimiter:
    """일일 호출 한도를 준수하기 위한 간이 Rate Limiter."""

    def __init__(self, max_calls_per_day: int = 9000):
        self._max = max_calls_per_day
        self._count = 0
        self._reset_at = datetime.utcnow() + timedelta(days=1)

    async def acquire(self) -> bool:
        now = datetime.utcnow()
        if now >= self._reset_at:
            self._count = 0
            self._reset_at = now + timedelta(days=1)
        if self._count >= self._max:
            logger.warning("G2B API 일일 호출 한도(%d) 도달", self._max)
            return False
        self._count += 1
        return True


class G2BClient:
    """나라장터 공공데이터포털 REST 클라이언트."""

    def __init__(self, service_key: str, timeout: float = 30.0):
        self._service_key = service_key
        self._timeout = timeout
        self._limiter = G2BRateLimiter()
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    # ──────────────────────────────────────────
    # 입찰 공고 조회
    # ──────────────────────────────────────────

    async def fetch_bid_notices(
        self,
        bid_type: str = "공사",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        page: int = 1,
        num_rows: int = 100,
    ) -> list[dict[str, Any]]:
        """업무구분별 입찰 공고 목록을 조회한다."""

        operation = BID_OPERATIONS.get(bid_type)
        if not operation:
            raise ValueError(f"지원하지 않는 업무구분: {bid_type}. 가능: {list(BID_OPERATIONS.keys())}")

        if not start_date:
            start_date = (datetime.utcnow() - timedelta(days=7)).strftime("%Y%m%d%H%M")
        if not end_date:
            end_date = datetime.utcnow().strftime("%Y%m%d%H%M")

        if not await self._limiter.acquire():
            return []

        params = {
            "serviceKey": self._service_key,
            "pageNo": str(page),
            "numOfRows": str(num_rows),
            "inqryDiv": "1",
            "inqryBgnDt": start_date,
            "inqryEndDt": end_date,
            "type": "json",
        }

        url = f"{G2B_BASE_URL}{BID_SERVICE_PATH}/{operation}"
        client = await self._get_client()

        try:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
            return self._extract_items(data)
        except httpx.HTTPStatusError as exc:
            logger.error("G2B 입찰공고 API 오류 (HTTP %d): %s", exc.response.status_code, exc)
            return []
        except Exception as exc:
            logger.error("G2B 입찰공고 API 호출 실패: %s", exc)
            return []

    async def fetch_all_bid_notices(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """공사/용역/물품 모든 업무구분의 입찰 공고를 수집한다."""
        tasks = [
            self.fetch_bid_notices(bid_type=bt, start_date=start_date, end_date=end_date)
            for bt in ["공사", "용역", "물품"]
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        items: list[dict[str, Any]] = []
        for idx, result in enumerate(results):
            bid_type = list(BID_OPERATIONS.keys())[idx]
            if isinstance(result, Exception):
                logger.error("G2B %s 수집 실패: %s", bid_type, result)
                continue
            for item in result:
                item["_bid_type"] = bid_type
            items.extend(result)
        return items

    # ──────────────────────────────────────────
    # 낙찰 정보 조회
    # ──────────────────────────────────────────

    async def fetch_award_results(
        self,
        bid_type: str = "공사",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        page: int = 1,
        num_rows: int = 100,
    ) -> list[dict[str, Any]]:
        """업무구분별 낙찰 결과 목록을 조회한다."""

        operation = AWARD_OPERATIONS.get(bid_type)
        if not operation:
            raise ValueError(f"지원하지 않는 업무구분: {bid_type}. 가능: {list(AWARD_OPERATIONS.keys())}")

        if not start_date:
            start_date = (datetime.utcnow() - timedelta(days=30)).strftime("%Y%m%d%H%M")
        if not end_date:
            end_date = datetime.utcnow().strftime("%Y%m%d%H%M")

        if not await self._limiter.acquire():
            return []

        params = {
            "serviceKey": self._service_key,
            "pageNo": str(page),
            "numOfRows": str(num_rows),
            "inqryDiv": "1",
            "inqryBgnDt": start_date,
            "inqryEndDt": end_date,
            "type": "json",
        }

        url = f"{G2B_BASE_URL}{AWARD_SERVICE_PATH}/{operation}"
        client = await self._get_client()

        try:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
            return self._extract_items(data)
        except httpx.HTTPStatusError as exc:
            logger.error("G2B 낙찰정보 API 오류 (HTTP %d): %s", exc.response.status_code, exc)
            return []
        except Exception as exc:
            logger.error("G2B 낙찰정보 API 호출 실패: %s", exc)
            return []

    async def fetch_all_award_results(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """공사/용역/물품 모든 업무구분의 낙찰 결과를 수집한다."""
        tasks = [
            self.fetch_award_results(bid_type=bt, start_date=start_date, end_date=end_date)
            for bt in ["공사", "용역", "물품"]
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        items: list[dict[str, Any]] = []
        for idx, result in enumerate(results):
            bid_type = ["공사", "용역", "물품"][idx]
            if isinstance(result, Exception):
                logger.error("G2B %s 낙찰 수집 실패: %s", bid_type, result)
                continue
            for item in result:
                item["_bid_type"] = bid_type
            items.extend(result)
        return items

    # ──────────────────────────────────────────
    # 유틸리티
    # ──────────────────────────────────────────

    @staticmethod
    def _extract_items(data: dict[str, Any]) -> list[dict[str, Any]]:
        """공공데이터포털 표준 JSON 응답에서 item 리스트를 추출한다."""
        try:
            body = data.get("response", {}).get("body", {})
            items = body.get("items", [])
            if isinstance(items, dict):
                item_list = items.get("item", [])
                if isinstance(item_list, dict):
                    return [item_list]
                return item_list if isinstance(item_list, list) else []
            return items if isinstance(items, list) else []
        except (AttributeError, TypeError):
            return []

    @staticmethod
    def build_g2b_detail_url(bid_notice_no: str) -> str:
        """나라장터 공고 상세 페이지 딥링크를 생성한다."""
        return (
            f"https://www.g2b.go.kr/pt/menu/selectSubFrame.do"
            f"?framesrc=/pt/menu/frameTgong.do"
            f"?bidno={bid_notice_no}"
        )
