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
from typing import Any

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

# SourceSnapshot 기록 ON(W2-1) — 스파이크 결과 G2BClient는 BaseAPIClient를 상속하지 않는
# 별도 httpx 클라이언트라 base_client.py 훅이 닿지 않는다. 실사용 커넥터 2종(VWorld·G2B)
# 중 하나이므로 여기 직접 최소 훅을 둔다(opt-in·best-effort — 기존 반환값/로직 불변).
_SNAPSHOT_ENABLED = True
_SNAPSHOT_SOURCE_ID = "g2b"
_SNAPSHOT_SOURCE_NAME = "나라장터(조달청) 공공데이터포털"
_SNAPSHOT_AUTHORITY_GRADE = "OFFICIAL"


async def _snapshot_success(url: str, params: dict, payload_bytes: bytes, http_status: int) -> None:
    """G2B 성공 응답 SourceSnapshot 기록(opt-in·best-effort) — 실패해도 수집에 영향 없음."""
    if not _SNAPSHOT_ENABLED:
        return
    try:
        from app.services.provenance import source_snapshot

        await source_snapshot.safe_record_success(
            source_id=_SNAPSHOT_SOURCE_ID, method="GET", url=url, params=params,
            payload_bytes=payload_bytes, http_status=http_status,
            source_name=_SNAPSHOT_SOURCE_NAME, authority_grade=_SNAPSHOT_AUTHORITY_GRADE,
        )
    except Exception:  # noqa: BLE001 — 기록 실패가 수집 호출경로를 절대 막으면 안 됨.
        pass


async def _snapshot_dead_letter(
    url: str, params: dict, error_message: str,
    http_status: int | None = None, payload_bytes: bytes | None = None,
) -> None:
    """G2B 실패 응답 SourceSnapshot dead-letter 기록(opt-in·best-effort)."""
    if not _SNAPSHOT_ENABLED:
        return
    try:
        from app.services.provenance import source_snapshot

        await source_snapshot.safe_record_dead_letter(
            source_id=_SNAPSHOT_SOURCE_ID, method="GET", url=url, params=params,
            payload_bytes=payload_bytes, http_status=http_status,
            source_name=_SNAPSHOT_SOURCE_NAME, authority_grade=_SNAPSHOT_AUTHORITY_GRADE,
            error_message=error_message,
        )
    except Exception:  # noqa: BLE001
        pass


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
        self._client: httpx.AsyncClient | None = None

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
        start_date: str | None = None,
        end_date: str | None = None,
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
            await _snapshot_success(url, params, resp.content, resp.status_code)
            return self._extract_items(data)
        except httpx.HTTPStatusError as exc:
            logger.error("G2B 입찰공고 API 오류 (HTTP %d): %s", exc.response.status_code, exc)
            await _snapshot_dead_letter(
                url, params, str(exc),
                http_status=exc.response.status_code, payload_bytes=exc.response.content,
            )
            return []
        except Exception as exc:
            logger.error("G2B 입찰공고 API 호출 실패: %s", exc)
            await _snapshot_dead_letter(url, params, str(exc))
            return []

    async def fetch_all_bid_notices(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
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
        start_date: str | None = None,
        end_date: str | None = None,
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
            await _snapshot_success(url, params, resp.content, resp.status_code)
            return self._extract_items(data)
        except httpx.HTTPStatusError as exc:
            logger.error("G2B 낙찰정보 API 오류 (HTTP %d): %s", exc.response.status_code, exc)
            await _snapshot_dead_letter(
                url, params, str(exc),
                http_status=exc.response.status_code, payload_bytes=exc.response.content,
            )
            return []
        except Exception as exc:
            logger.error("G2B 낙찰정보 API 호출 실패: %s", exc)
            await _snapshot_dead_letter(url, params, str(exc))
            return []

    async def fetch_all_award_results(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
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
