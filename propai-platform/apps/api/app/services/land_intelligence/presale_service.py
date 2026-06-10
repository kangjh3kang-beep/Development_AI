"""청약홈(한국부동산원) 분양·청약 정보 서비스.

데이터 출처: 공공데이터포털 ApplyhomeInfoDetailSvc(odcloud)
  - APT 분양 공고: getAPTLttotPblancDetail
  - 주택형별 공급금액(분양가): getAPTLttotPblancMdl
키: applyhome_api_key(우선) → molit_api_key(폴백, 동일 data.go.kr serviceKey 체계).
※ 본 API는 별도 활용신청 승인 필요 — 미승인 시 빈 결과를 정직하게 반환(목업 없음).

공용 3기능:
  1) list_announcements(area, months_back)        — 전국/시도별 분양 공고 목록(가벼움)
  2) detail(house_manage_no, pblanc_no)            — 단지 상세 + 주택형별 분양가
  3) nearby(center_lat, center_lon, area, radius)  — 관심지역/반경 필터(지오코딩+거리)
"""

from __future__ import annotations

import asyncio
import math
from datetime import datetime, timedelta
from typing import Any

import httpx
import structlog

from apps.api.config import get_settings

logger = structlog.get_logger(__name__)

_BASE = "https://api.odcloud.kr/api/ApplyhomeInfoDetailSvc/v1"
_DETAIL_URL = f"{_BASE}/getAPTLttotPblancDetail"   # APT 분양 공고
_MODEL_URL = f"{_BASE}/getAPTLttotPblancMdl"       # 주택형별 공급금액(분양가)

# 법정동코드 앞 2자리 → 청약홈 지역명(SUBSCRPT_AREA_CODE_NM 기준)
_LAWD_TO_AREA = {
    "11": "서울", "26": "부산", "27": "대구", "28": "인천", "29": "광주",
    "30": "대전", "31": "울산", "36": "세종", "41": "경기", "42": "강원",
    "51": "강원", "43": "충북", "44": "충남", "45": "전북", "52": "전북",
    "46": "전남", "47": "경북", "48": "경남", "50": "제주",
}
# 전국 시도 목록(메뉴 탭용)
AREA_LIST = ["서울", "경기", "인천", "부산", "대구", "광주", "대전", "울산", "세종",
             "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주"]


def area_from_lawd(lawd_cd: str) -> str | None:
    return _LAWD_TO_AREA.get((lawd_cd or "")[:2])


def _g(row: dict, *keys: str) -> str:
    """여러 후보 키 중 처음 값이 있는 것 반환(스키마 변동 방어)."""
    for k in keys:
        v = row.get(k)
        if v not in (None, "", "null"):
            return str(v).strip()
    return ""


def _parse_date(s: str) -> datetime | None:
    s = (s or "").strip()
    for fmt in ("%Y-%m-%d", "%Y%m%d", "%Y.%m.%d"):
        try:
            return datetime.strptime(s[:10], fmt)
        except Exception:  # noqa: BLE001
            continue
    return None


def _status(begin: str, end: str, today: datetime) -> str:
    b, e = _parse_date(begin), _parse_date(end)
    if b and today < b:
        return "접수예정"
    if b and e and b <= today <= e + timedelta(days=1):
        return "접수중"
    if e and today > e:
        return "마감"
    if b and today >= b:
        return "접수중"
    return "미정"


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


class PresaleService:
    """청약홈 분양·청약 정보 조회기."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self._key = (getattr(self.settings, "applyhome_api_key", "") or "").strip() \
            or (getattr(self.settings, "molit_api_key", "") or "").strip()

    # ── 정규화 ──
    def _normalize(self, row: dict, today: datetime) -> dict[str, Any]:
        begin = _g(row, "SUBSCRPT_RCEPT_BGNDE", "RCEPT_BGNDE", "GNRL_RNK1_CRSPAREA_RCPTDE")
        end = _g(row, "SUBSCRPT_RCEPT_ENDDE", "RCEPT_ENDDE", "GNRL_RNK2_ETC_AREA_RCPTDE")
        return {
            "house_manage_no": _g(row, "HOUSE_MANAGE_NO"),
            "pblanc_no": _g(row, "PBLANC_NO"),
            "name": _g(row, "HOUSE_NM", "BSNS_MBY_NM") or "분양 단지",
            "address": _g(row, "HSSPLY_ADRES"),
            "area_name": _g(row, "SUBSCRPT_AREA_CODE_NM"),
            "house_kind": _g(row, "HOUSE_SECD_NM", "HOUSE_DTL_SECD_NM"),  # 분양/임대 등
            "rent_kind": _g(row, "RENT_SECD_NM"),
            "total_households": _g(row, "TOT_SUPLY_HSHLDCO"),
            "recruit_date": _g(row, "RCRIT_PBLANC_DE"),
            "receipt_begin": begin,
            "receipt_end": end,
            "special_date": _g(row, "SPSPLY_RCEPT_BGNDE"),  # 특별공급 접수
            "winner_date": _g(row, "PRZWNER_PRESNATN_DE"),
            "contract_begin": _g(row, "CNTRCT_CNCLS_BGNDE"),
            "contract_end": _g(row, "CNTRCT_CNCLS_ENDDE"),
            "move_in": _g(row, "MVN_PREARNGE_YM"),
            "developer": _g(row, "BSNS_MBY_NM"),
            "constructor": _g(row, "CNSTRCT_ENTRPS_NM"),
            "tel": _g(row, "MDHS_TELNO"),
            "homepage": _g(row, "HMPG_ADRES"),
            "url": _g(row, "PBLANC_URL", "HMPG_ADRES"),
            "status": _status(begin, end, today),
        }

    # ── 1) 목록 ──
    async def list_announcements(
        self, area: str | None = None, months_back: int = 6, max_items: int = 200
    ) -> dict[str, Any]:
        """전국(area=None) 또는 시도별 분양 공고 목록(가벼움 — 분양가 미포함)."""
        if not self._key:
            return {"available": False, "items": [], "note": "청약홈 분양정보 API 키 미설정(활용신청 필요)"}
        today = datetime.now()
        since = (today - timedelta(days=int(months_back) * 31)).strftime("%Y-%m-%d")
        params: dict[str, Any] = {
            "page": 1, "perPage": min(max_items, 300),
            "cond[RCRIT_PBLANC_DE::GTE]": since,
            "serviceKey": self._key,
        }
        if area:
            params["cond[SUBSCRPT_AREA_CODE_NM::EQ]"] = area
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.get(_DETAIL_URL, params=params)
            if resp.status_code != 200:
                return {"available": False, "items": [],
                        "note": f"청약홈 API 응답 {resp.status_code}(키 미승인 가능)"}
            data = resp.json().get("data", []) or []
        except Exception as e:  # noqa: BLE001
            logger.warning("presale.list_failed", error=str(e))
            return {"available": False, "items": [], "note": "청약홈 API 호출 실패"}

        items = [self._normalize(r, today) for r in data]
        # 모집공고일 최신순
        items.sort(key=lambda x: x.get("recruit_date") or "", reverse=True)
        # 상태 우선순위(접수중>접수예정>마감) 보조정렬
        order = {"접수중": 0, "접수예정": 1, "미정": 2, "마감": 3}
        items.sort(key=lambda x: order.get(x["status"], 9))
        return {"available": True, "area": area or "전국", "count": len(items), "items": items}

    # ── 2) 상세(+분양가) ──
    async def detail(self, house_manage_no: str, pblanc_no: str = "") -> dict[str, Any]:
        """단지 상세 + 주택형별 공급금액(분양가 최저~최고)."""
        if not self._key or not house_manage_no:
            return {"available": False, "note": "키 미설정 또는 관리번호 없음"}
        today = datetime.now()
        base_params = {"page": 1, "perPage": 50, "serviceKey": self._key,
                       "cond[HOUSE_MANAGE_NO::EQ]": house_manage_no}
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                d_resp, m_resp = await asyncio.gather(
                    client.get(_DETAIL_URL, params=base_params),
                    client.get(_MODEL_URL, params=base_params),
                )
            drows = d_resp.json().get("data", []) if d_resp.status_code == 200 else []
            mrows = m_resp.json().get("data", []) if m_resp.status_code == 200 else []
        except Exception as e:  # noqa: BLE001
            logger.warning("presale.detail_failed", error=str(e))
            return {"available": False, "note": "청약홈 상세 호출 실패"}

        if not drows:
            return {"available": False, "note": "해당 공고를 찾을 수 없음"}
        info = self._normalize(drows[0], today)
        models = []
        prices = []
        for r in mrows:
            amt = _g(r, "LTTOT_TOP_AMOUNT")  # 분양최고금액(만원)
            try:
                amt_man = int(float(amt)) if amt else None
            except Exception:  # noqa: BLE001
                amt_man = None
            if amt_man:
                prices.append(amt_man)
            models.append({
                "house_ty": _g(r, "HOUSE_TY"),                 # 주택형(예: 084.9871A)
                "supply_area_m2": _g(r, "SUPLY_AR"),           # 공급면적
                "supply_households": _g(r, "SUPLY_HSHLDCO"),   # 공급세대수
                "special_households": _g(r, "SPSPLY_HSHLDCO"),
                "price_man": amt_man,                          # 분양최고금액(만원)
            })
        info["models"] = models
        info["price_min_man"] = min(prices) if prices else None
        info["price_max_man"] = max(prices) if prices else None
        info["available"] = True
        return info

    # ── 3) 반경/관심지역 필터(지도용) ──
    async def nearby(
        self, center_lat: float | None, center_lon: float | None,
        area: str | None, radius_m: int = 3000, months_back: int = 12, max_markers: int = 30,
    ) -> dict[str, Any]:
        """중심좌표 반경 내 분양 단지(지오코딩+거리필터). 지도 '분양정보' 카테고리용."""
        listing = await self.list_announcements(area=area, months_back=months_back, max_items=300)
        if not listing.get("available"):
            return {"available": False, "items": [], "note": listing.get("note")}
        items = [it for it in listing["items"] if it.get("address")]
        if center_lat is None or center_lon is None:
            # 중심 없음 → 거리필터 불가, 목록만(좌표 없음)
            return {"available": True, "items": items[:max_markers], "note": "중심좌표 없음 — 거리필터 미적용"}

        # 공급위치 지오코딩(캐시 공유) → 거리 필터
        from apps.api.app.services.land_intelligence.nearby_map_service import NearbyMapService
        geocoder = NearbyMapService()
        addrs = list({it["address"] for it in items})
        coords = await geocoder.geocode_addresses(addrs)
        out = []
        for it in items:
            c = coords.get(it["address"])
            if not c:
                continue
            dist = _haversine_m(center_lat, center_lon, c["lat"], c["lon"])
            if dist <= radius_m:
                out.append({**it, "lat": c["lat"], "lon": c["lon"], "distance_m": round(dist)})
        out.sort(key=lambda x: x["distance_m"])
        return {"available": True, "count": len(out), "items": out[:max_markers]}
