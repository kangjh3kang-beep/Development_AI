"""조달청 가격정보현황서비스(data.go.kr 15129415) API 클라이언트 — 단가 4계층 리졸버 T1.

나라장터 시설공통자재(토목/건축/기계설비/전기통신) 가격정보(표준시장단가·시장시공가격)를 조회한다.
data.go.kr 1230000(조달청) 계열 — 인증키·레이트리미터·에러 처리는 g2b_client.py(G2BClient)
패턴을 그대로 재사용한다(동일 기관 API 군, 표준 JSON 응답 포맷 공유).

★확인된 오퍼레이션(2026-07 조사, data.go.kr Swagger 문서·요청 파라미터 명세 기준):
  getPriceInfoListFcltyCmmnMtrilEngrk — 시설공통자재(토목) 가격정보.
  건축/기계설비/전기통신 등 자매 오퍼레이션은 공식 문서에서 명세를 확인하지 못해 등록하지
  않는다(무날조 — 미검증 오퍼레이션명을 임의로 발명하지 않음). 실 서비스키로 확인되면
  PRICE_OPERATIONS에 추가한다.

응답 품목(item)의 정확한 필드명(품명/규격/단가 등)도 공식 문서에서 상세 확인이 불가능했다.
이 클라이언트는 응답에서 표준 JSON 봉투(response.body.items)만 해석하고, 품목 필드 파싱은
방어적으로 처리하는 상위 모듈(public_price_ingest.py)에 위임한다(스키마 단정 금지).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

import httpx

logger = logging.getLogger(__name__)

PRICE_SERVICE_BASE = "http://apis.data.go.kr/1230000/ao/PriceInfoService"

# 확인된 오퍼레이션만 등록(무날조 — 미검증 오퍼레이션명 추가 금지).
PRICE_OPERATIONS: dict[str, str] = {
    "시설공통자재": "getPriceInfoListFcltyCmmnMtrilEngrk",
}
_DEFAULT_CATEGORY = "시설공통자재"


class PublicPriceRateLimiter:
    """일일 호출 한도를 준수하기 위한 간이 Rate Limiter(G2BRateLimiter와 동일 패턴)."""

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
            logger.warning("조달청 가격정보 API 일일 호출 한도(%d) 도달", self._max)
            return False
        self._count += 1
        return True


class PublicPriceClient:
    """조달청 나라장터 가격정보현황서비스 REST 클라이언트."""

    def __init__(self, service_key: str, timeout: float = 30.0):
        self._service_key = service_key
        self._timeout = timeout
        self._limiter = PublicPriceRateLimiter()
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def fetch_facility_material_prices(
        self,
        *,
        prdct_clsfc_no: str | None = None,
        krn_prdct_nm: str | None = None,
        page: int = 1,
        num_rows: int = 100,
    ) -> list[dict[str, Any]]:
        """시설공통자재(토목) 가격정보 목록을 조회한다.

        키 미보유/한도초과/호출실패 시 빈 리스트(graceful — 서버 기동·기존 흐름 무영향).
        """
        if not self._service_key:
            return []
        if not await self._limiter.acquire():
            return []

        params: dict[str, Any] = {
            "serviceKey": self._service_key,
            "pageNo": str(page),
            "numOfRows": str(num_rows),
            "type": "json",
        }
        if prdct_clsfc_no:
            params["prdctClsfcNo"] = prdct_clsfc_no
        if krn_prdct_nm:
            params["krnPrdctNm"] = krn_prdct_nm

        url = f"{PRICE_SERVICE_BASE}/{PRICE_OPERATIONS[_DEFAULT_CATEGORY]}"
        client = await self._get_client()

        try:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
            return self._extract_items(data)
        except httpx.HTTPStatusError as exc:
            logger.error("조달청 가격정보 API 오류 (HTTP %d): %s", exc.response.status_code, exc)
            return []
        except Exception as exc:  # noqa: BLE001 — 파싱/네트워크 오류 등 정직 graceful
            logger.error("조달청 가격정보 API 호출 실패: %s", exc)
            return []

    @staticmethod
    def _extract_items(data: dict[str, Any]) -> list[dict[str, Any]]:
        """공공데이터포털 표준 JSON 응답에서 item 리스트를 추출한다(G2BClient와 동일 패턴)."""
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
