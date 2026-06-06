"""온비드(KAMCO 공매) OpenAPI 커넥터.

data.go.kr 한국자산관리공사 온비드 물건정보 서비스(서비스ID 1410000 계열)를 호출해
전국 공매 물건 목록·상세를 수집한다. 키 미설정/호출실패 시 구조화 mock으로 폴백하며
응답에 data_source(onbid_live|mock)를 정직 표기한다(공공데이터 폴백 패턴 준수).

경매(법원)는 무료 API가 빈약해 이번 범위에서 제외하되, source 필드(onbid/court)로
향후 확장 지점을 남긴다. 본 모듈은 외부 실호출을 강제하지 않으며, 호출 실패는
graceful 폴백으로 흡수한다(과설계 금지 — 단일 목록/상세 엔드포인트만 사용).
"""

from __future__ import annotations

import logging
import random
from datetime import datetime, timedelta
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

# ── 온비드 공매물건 OpenAPI(공공데이터포털) ──
# 통합 물건/감정/입찰 정보 조회. 실엔드포인트는 키 승인 후 확정되며, 미설정 시 mock.
ONBID_BASE_URL = "http://openapi.onbid.co.kr/openapi/services"
ONBID_THING_PATH = "/KamcoPblsalThingInqireSvc"
# 대표 오퍼레이션: 공매물건 목록(getKamcoPbctCltrList) — 지역/종류/기간 필터 지원.
ONBID_LIST_OP = "getKamcoPbctCltrList"
ONBID_DETAIL_OP = "getKamcoPbctCltrDetailInfo"

# 공매 물건종류 코드(온비드 분류 → 내부 kind 매핑).
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

_SIDO_LIST = [
    "서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종",
    "경기", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주",
]


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
    """온비드 공매 OpenAPI REST 클라이언트(키 폴백 내장)."""

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

    # ──────────────────────────────────────────
    # 공매 물건 목록
    # ──────────────────────────────────────────

    async def fetch_items(
        self,
        *,
        region: Optional[str] = None,
        kind: Optional[str] = None,
        page: int = 1,
        rows: int = 50,
    ) -> dict[str, Any]:
        """공매 물건 목록을 조회한다.

        반환: {"items": [정규화 dict...], "data_source": "onbid_live"|"mock",
               "total": int, "note": str}
        키 미설정/호출실패는 mock으로 graceful 폴백한다(정직 표기).
        """
        if not self._service_key:
            return self._mock_items(region=region, kind=kind, rows=rows,
                                    note="ONBID 서비스 키 미설정 — 구조화 더미(개발/검증용)")

        params = {
            "serviceKey": self._service_key,
            "numOfRows": rows,
            "pageNo": page,
            "DPSL_MTD_CD": "0001",  # 매각방법: 공매(매각)
        }
        if region:
            params["SIDO"] = region
        url = f"{ONBID_BASE_URL}{ONBID_THING_PATH}/{ONBID_LIST_OP}"
        try:
            client = await self._get_client()
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            raw_items = self._extract_items(resp.text)
            items = [self._normalize(it) for it in raw_items]
            if kind:
                items = [it for it in items if it.get("kind") == kind]
            return {
                "items": items,
                "data_source": "onbid_live",
                "total": len(items),
                "note": "온비드 OpenAPI 실연동",
            }
        except Exception as e:  # noqa: BLE001
            logger.warning("온비드 호출 실패 — mock 폴백: %s", str(e)[:160])
            return self._mock_items(region=region, kind=kind, rows=rows,
                                    note=f"온비드 호출 실패 폴백: {str(e)[:80]}")

    @staticmethod
    def _extract_items(text: str) -> list[dict[str, Any]]:
        """온비드 XML/JSON 응답에서 item 리스트를 추출한다(방어적)."""
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

    # ──────────────────────────────────────────
    # Mock 폴백(구조화 더미 — 개발/검증용, 정직 표기)
    # ──────────────────────────────────────────

    def _mock_items(
        self, *, region: Optional[str], kind: Optional[str], rows: int, note: str
    ) -> dict[str, Any]:
        """키 없음/실패 시 결정적이지 않은 구조화 더미 생성(필터 반영)."""
        rng = random.Random(f"{region}-{kind}-{rows}")
        kinds = ["land", "building", "apt", "officetel", "factory"]
        sidos = [region] if region else _SIDO_LIST
        now = datetime.utcnow()
        items: list[dict[str, Any]] = []
        n = min(rows, 30)
        for i in range(n):
            k = kind or rng.choice(kinds)
            sido = rng.choice(sidos)
            appraisal = rng.randint(8, 120) * 10_000_000  # 8천만~12억
            fail = rng.randint(0, 4)
            # 유찰 1회당 통상 -10% 최저가 하락(온비드 공매 관행).
            min_bid = int(appraisal * (0.9 ** fail))
            start = now + timedelta(days=rng.randint(1, 20))
            items.append({
                "source": "onbid",
                "item_no": f"MOCK-{sido}-{2026000000 + i}",
                "kind": k,
                "region_sido": sido,
                "region_sigungu": "",
                "bjd_code": "",
                "pnu": "",
                "address": f"{sido} 표본구 표본동 {rng.randint(1, 999)}-{rng.randint(1, 99)}",
                "appraisal_price": appraisal,
                "min_bid_price": min_bid,
                "fail_count": fail,
                "status": "open",
                "bid_start": start.isoformat(),
                "bid_end": (start + timedelta(days=2)).isoformat(),
                "raw": {"_mock": True},
            })
        return {"items": items, "data_source": "mock", "total": len(items), "note": note}
