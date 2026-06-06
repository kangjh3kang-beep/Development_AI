"""온비드(KAMCO 공매) OpenAPI 커넥터 — 실연동 전용(무목업).

data.go.kr 차세대 온비드 OpenAPI를 호출해 전국 공매 부동산 물건 목록/상세를
수집한다. 본 모듈은 ★목업(mock)을 생성하지 않는다:

- 인증키 미설정 → 빈 결과 + data_source="unavailable" + reason(활용신청 필요).
- 호출 실패/무자료 → 빈 결과 + data_source="unavailable" + reason(실패 사유).
- 키가 있고 호출 성공 → 실데이터 정규화 + data_source="onbid_live".

대상 OpenAPI(data.go.kr):
  - 차세대 온비드 부동산 물건목록 조회 (서비스 15157207)
  - 차세대 온비드 부동산 물건 상세(입찰정보) 조회 (서비스 15157251)
실엔드포인트 오퍼레이션명/필드명은 활용신청 승인 후 확정되며, 응답이 예상과
다르면 _extract_items / _normalize 의 방어적 파서가 가능한 범위에서 흡수한다.
무자료/스키마 불일치 시에도 가짜데이터를 만들지 않고 빈 결과를 반환한다.

경매(법원)는 court_scraper.py(스크래핑)로 별도 수집하며, 본 모듈은 공매(온비드)만
담당한다(source="onbid").
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

# ── 차세대 온비드 부동산 OpenAPI(공공데이터포털 apis.data.go.kr) ──
# 서비스 15157207(물건목록) / 15157251(물건상세 입찰정보).
ONBID_BASE_URL = "https://apis.data.go.kr/1611000/nadOpenApi"
# 대표 오퍼레이션(승인 후 확정 — 응답 미스매치는 방어적 파서로 흡수).
ONBID_LIST_OP = "getRealEstAuctnList"
ONBID_DETAIL_OP = "getRealEstAuctnDtl"

# 공매 물건종류명(온비드) → 내부 kind 코드.
KIND_MAP: dict[str, str] = {
    "토지": "land",
    "대지": "land",
    "임야": "land",
    "전": "land",
    "답": "land",
    "주택": "building",
    "건물": "building",
    "근린생활시설": "building",
    "아파트": "apt",
    "오피스텔": "officetel",
    "공장": "factory",
}


def normalize_kind(raw: Any) -> str:
    """온비드 물건종류명을 내부 kind 코드로 정규화한다."""
    s = str(raw or "").strip()
    for key, code in KIND_MAP.items():
        if key in s:
            return code
    return "etc"


def _safe_int(raw: Any) -> Optional[int]:
    if raw is None or raw == "":
        return None
    try:
        return int(float(str(raw).replace(",", "")))
    except (ValueError, TypeError):
        return None


def _parse_dt(raw: Any) -> Optional[str]:
    """온비드 날짜 문자열을 ISO8601(naive)로 변환한다(실패 시 None)."""
    if not raw:
        return None
    s = str(raw).strip()
    for fmt in ("%Y%m%d%H%M", "%Y%m%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(s, fmt).isoformat()
        except ValueError:
            continue
    return None


class OnbidClient:
    """온비드 공매 OpenAPI REST 클라이언트 — 실호출 전용(무목업).

    키가 없거나 호출이 실패하면 가짜데이터 대신 빈 결과 + data_source="unavailable"
    + reason 을 반환한다.
    """

    def __init__(self, service_key: Optional[str], timeout: float = 20.0):
        self._service_key = service_key or ""
        self._timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def has_key(self) -> bool:
        return bool(self._service_key)

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    @staticmethod
    def _unavailable(reason: str) -> dict[str, Any]:
        """무목업: 가짜데이터 없이 빈 결과 + 사유를 반환한다."""
        return {"items": [], "data_source": "unavailable", "total": 0, "reason": reason}

    # ──────────────────────────────────────────
    # 공매 물건 목록 (실호출 전용)
    # ──────────────────────────────────────────

    async def fetch_items(
        self,
        *,
        region: Optional[str] = None,
        kind: Optional[str] = None,
        page: int = 1,
        rows: int = 50,
    ) -> dict[str, Any]:
        """공매 물건 목록을 실 API로 조회한다.

        반환: {"items": [정규화 dict...], "data_source": "onbid_live"|"unavailable",
               "total": int, "note"|"reason": str}
        키 미설정/호출실패/무자료는 ★가짜데이터 없이 빈 결과 + reason 으로 반환한다.
        """
        if not self._service_key:
            return self._unavailable("온비드 인증키 미설정(공공데이터포털 활용신청 필요)")

        params = {
            "serviceKey": self._service_key,
            "numOfRows": rows,
            "pageNo": page,
            "type": "json",
        }
        if region:
            params["sido"] = region
        url = f"{ONBID_BASE_URL}/{ONBID_LIST_OP}"
        try:
            client = await self._get_client()
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            raw_items = self._extract_items(resp.text)
            items = [self._normalize(it) for it in raw_items]
            if kind:
                items = [it for it in items if it.get("kind") == kind]
            if not items:
                return self._unavailable("온비드 응답 무자료(해당 조건의 물건 없음)")
            return {
                "items": items,
                "data_source": "onbid_live",
                "total": len(items),
                "note": "온비드 OpenAPI 실연동",
            }
        except Exception as e:  # noqa: BLE001
            logger.warning("온비드 호출 실패(무목업, 빈 결과 반환): %s", str(e)[:160])
            return self._unavailable(f"온비드 호출 실패: {str(e)[:120]}")

    @staticmethod
    def _extract_items(text: str) -> list[dict[str, Any]]:
        """온비드 XML/JSON 응답에서 item 리스트를 추출한다(방어적).

        무자료/에러 응답이면 빈 리스트(가짜데이터 생성 금지).
        """
        import json as _json
        import xml.etree.ElementTree as ET

        text = (text or "").strip()
        if not text:
            return []
        # JSON 시도
        if text.startswith("{"):
            try:
                body = _json.loads(text).get("response", {}).get("body", {})
                items = body.get("items", {})
                if isinstance(items, dict):
                    items = items.get("item", [])
                if isinstance(items, dict):
                    items = [items]
                return items or []
            except Exception:  # noqa: BLE001
                return []
        # XML 시도
        try:
            root = ET.fromstring(text)
            out: list[dict[str, Any]] = []
            for item in root.iter("item"):
                out.append({child.tag: (child.text or "") for child in item})
            return out
        except Exception:  # noqa: BLE001
            return []

    @staticmethod
    def _normalize(it: dict[str, Any]) -> dict[str, Any]:
        """온비드 원자료를 내부 auction_items 스키마로 정규화한다."""
        address = str(
            it.get("LDNM_ADRS")
            or it.get("NMRD_ADRS")
            or it.get("CLTR_NM")
            or it.get("address")
            or ""
        )
        appraisal = _safe_int(it.get("APSL_ASES_AVL_AMT") or it.get("appraisal_price"))
        min_bid = _safe_int(it.get("MIN_BID_PRC") or it.get("min_bid_price"))
        return {
            "source": "onbid",
            "item_no": str(it.get("CLTR_NO") or it.get("PLNM_NO") or it.get("item_no") or ""),
            "kind": normalize_kind(it.get("CTGR_FULL_NM") or it.get("kind")),
            "region_sido": str(it.get("ADRS_SIDO") or it.get("region_sido") or ""),
            "region_sigungu": str(it.get("ADRS_SGG") or it.get("region_sigungu") or ""),
            "bjd_code": str(it.get("LDNM_LDCD") or it.get("bjd_code") or ""),
            "pnu": str(it.get("PNU") or it.get("pnu") or ""),
            "address": address,
            "appraisal_price": appraisal,
            "min_bid_price": min_bid,
            "fail_count": _safe_int(it.get("USCBD_CNT") or it.get("fail_count")) or 0,
            "status": str(it.get("PBCT_BEGN_DTM") and "open" or it.get("status") or "open"),
            "bid_start": _parse_dt(it.get("PBCT_BEGN_DTM") or it.get("bid_start")),
            "bid_end": _parse_dt(it.get("PBCT_CLS_DTM") or it.get("bid_end")),
            "raw": it,
        }
