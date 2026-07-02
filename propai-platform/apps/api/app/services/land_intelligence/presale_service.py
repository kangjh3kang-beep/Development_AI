"""청약홈(한국부동산원) 분양·청약 정보 서비스.

데이터 출처: 공공데이터포털 ApplyhomeInfoDetailSvc(odcloud) — 이용허락범위 제한 없음.
지원 분양 유형(5종, 각 상세+주택형별 분양가 엔드포인트):
  - apt        : APT 분양(getAPTLttotPblancDetail / Mdl)
  - officetel  : 오피스텔·도시형·민간임대·생활숙박시설(getUrbtyOfctlLttotPblancDetail / Mdl)
  - remndr     : APT 잔여세대(getRemndrLttotPblancDetail / Mdl)
  - opt        : 임의공급(getOPTLttotPblancDetail / Mdl)
  - pblrent    : 공공지원 민간임대(getPblPvtRentLttotPblancDetail / Mdl)

키: applyhome_api_key(우선) → molit_api_key(폴백, 동일 data.go.kr serviceKey 체계).
필드명이 유형마다 조금씩 달라 다중 후보키(_g)로 방어 정규화한다. 무자료 시 정직 표기(목업 없음).

공용 3기능:
  1) list_announcements(area, months_back, product)  — 전국/시도별 목록(product='all'=5종 통합)
  2) detail(house_manage_no, pblanc_no, product)      — 단지 상세 + 주택형별 분양가
  3) nearby(center_lat, center_lon, area, radius)     — 관심지역/반경 필터(지오코딩+거리)
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

# 분양 유형별 엔드포인트(상세/주택형). 순서=메뉴 표기 순서.
PRESALE_TYPES: list[dict[str, str]] = [
    {"key": "apt", "label": "APT", "detail": "getAPTLttotPblancDetail", "model": "getAPTLttotPblancMdl"},
    {"key": "officetel", "label": "오피스텔·생숙", "detail": "getUrbtyOfctlLttotPblancDetail",
     "model": "getUrbtyOfctlLttotPblancMdl"},
    {"key": "remndr", "label": "APT 잔여세대", "detail": "getRemndrLttotPblancDetail",
     "model": "getRemndrLttotPblancMdl"},
    {"key": "opt", "label": "임의공급", "detail": "getOPTLttotPblancDetail", "model": "getOPTLttotPblancMdl"},
    {"key": "pblrent", "label": "공공지원 민간임대", "detail": "getPblPvtRentLttotPblancDetail",
     "model": "getPblPvtRentLttotPblancMdl"},
]
_TYPE_BY_KEY = {t["key"]: t for t in PRESALE_TYPES}

# 법정동코드 앞 2자리 → 청약홈 지역명(SUBSCRPT_AREA_CODE_NM 기준)
_LAWD_TO_AREA = {
    "11": "서울", "26": "부산", "27": "대구", "28": "인천", "29": "광주",
    "30": "대전", "31": "울산", "36": "세종", "41": "경기", "42": "강원",
    "51": "강원", "43": "충북", "44": "충남", "45": "전북", "52": "전북",
    "46": "전남", "47": "경북", "48": "경남", "50": "제주",
}
AREA_LIST = ["서울", "경기", "인천", "부산", "대구", "광주", "대전", "울산", "세종",
             "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주"]


def area_from_lawd(lawd_cd: str) -> str | None:
    return _LAWD_TO_AREA.get((lawd_cd or "")[:2])


def _g(row: dict, *keys: str) -> str:
    """여러 후보 키 중 처음 값이 있는 것 반환(유형별 스키마 변동 방어)."""
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
    """청약홈 분양·청약 정보 조회기(5종 유형)."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self._key = (getattr(self.settings, "applyhome_api_key", "") or "").strip() \
            or (getattr(self.settings, "molit_api_key", "") or "").strip()

    # ── 정규화(유형 공통, 다중 후보키) ──
    def _normalize(self, row: dict, today: datetime, type_cfg: dict) -> dict[str, Any]:
        begin = _g(row, "SUBSCRPT_RCEPT_BGNDE", "RCEPT_BGNDE", "GNRL_RNK1_CRSPAREA_RCPTDE", "RCRIT_RCEPT_BGNDE")
        end = _g(row, "SUBSCRPT_RCEPT_ENDDE", "RCEPT_ENDDE", "GNRL_RNK2_ETC_AREA_RCPTDE", "RCRIT_RCEPT_ENDDE")
        return {
            "product": type_cfg["key"],
            "product_label": type_cfg["label"],
            "house_manage_no": _g(row, "HOUSE_MANAGE_NO"),
            "pblanc_no": _g(row, "PBLANC_NO"),
            "name": _g(row, "HOUSE_NM", "BSNS_MBY_NM") or "분양 단지",
            "address": _g(row, "HSSPLY_ADRES"),
            "area_name": _g(row, "SUBSCRPT_AREA_CODE_NM"),
            "house_kind": _g(row, "HOUSE_SECD_NM", "HOUSE_DTL_SECD_NM"),
            "rent_kind": _g(row, "RENT_SECD_NM"),
            "total_households": _g(row, "TOT_SUPLY_HSHLDCO", "SUPLY_HSHLDCO"),
            "recruit_date": _g(row, "RCRIT_PBLANC_DE"),
            "receipt_begin": begin,
            "receipt_end": end,
            "special_date": _g(row, "SPSPLY_RCEPT_BGNDE"),
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

    # ── 단일 유형 목록 조회 ──
    async def _fetch_type(self, client: httpx.AsyncClient, type_cfg: dict, area: str | None,
                          since: str, max_items: int, today: datetime) -> list[dict[str, Any]]:
        params: dict[str, Any] = {
            "page": 1, "perPage": min(max_items, 300),
            "cond[RCRIT_PBLANC_DE::GTE]": since,
            "serviceKey": self._key,
        }
        if area:
            params["cond[SUBSCRPT_AREA_CODE_NM::EQ]"] = area
        url = f"{_BASE}/{type_cfg['detail']}"
        try:
            resp = await client.get(url, params=params)
            if resp.status_code != 200:
                return []
            data = resp.json().get("data", []) or []
        except Exception as e:  # noqa: BLE001
            logger.warning("presale.fetch_type_failed", product=type_cfg["key"], error=str(e))
            return []
        return [self._normalize(r, today, type_cfg) for r in data]

    # ── 1) 목록(product='all'=5종 통합) ──
    async def list_announcements(
        self, area: str | None = None, months_back: int = 6,
        product: str = "all", max_items: int = 200,
    ) -> dict[str, Any]:
        if not self._key:
            return {"available": False, "items": [], "note": "청약홈 분양정보 API 키 미설정"}
        today = datetime.now()
        since = (today - timedelta(days=int(months_back) * 31)).strftime("%Y-%m-%d")
        types = list(PRESALE_TYPES) if product in ("all", "", None) else [_TYPE_BY_KEY.get(product)]
        types = [t for t in types if t]
        if not types:
            return {"available": False, "items": [], "note": "알 수 없는 분양 유형"}

        try:
            async with httpx.AsyncClient(timeout=25.0) as client:
                results = await asyncio.gather(
                    *[self._fetch_type(client, t, area, since, max_items, today) for t in types]
                )
        except Exception as e:  # noqa: BLE001
            logger.warning("presale.list_failed", error=str(e))
            return {"available": False, "items": [], "note": "청약홈 API 호출 실패"}

        items: list[dict[str, Any]] = [it for sub in results for it in sub]
        items.sort(key=lambda x: x.get("recruit_date") or "", reverse=True)
        order = {"접수중": 0, "접수예정": 1, "미정": 2, "마감": 3}
        items.sort(key=lambda x: order.get(x["status"], 9))
        by_product = {t["key"]: sum(1 for it in items if it["product"] == t["key"]) for t in types}
        return {"available": True, "area": area or "전국", "count": len(items),
                "by_product": by_product, "items": items}

    # ── 2) 상세(+분양가) ──
    async def detail(self, house_manage_no: str, pblanc_no: str = "", product: str = "apt") -> dict[str, Any]:
        """단지 상세 + 주택형별 분양가.

        id 필터(cond[HOUSE_MANAGE_NO::EQ])가 무순위/임의공급/잔여세대(9XX 관리번호)에는
        안 먹는 odcloud 특성 → 실패 시 목록과 동일한 날짜조건으로 전 유형을 가져와
        클라이언트 필터링(목록에 나온 공고는 반드시 찾는다). 분양가(models)는 선택.
        """
        if not self._key:
            return {"available": False, "note": "청약홈 키 미설정"}
        today = datetime.now()
        since = (today - timedelta(days=400)).strftime("%Y-%m-%d")
        target = str(house_manage_no or "").strip()
        target_pb = str(pblanc_no or "").strip()
        if not target and not target_pb:
            return {"available": False, "note": "관리번호 없음"}

        type_cfg = _TYPE_BY_KEY.get(product) or _TYPE_BY_KEY["apt"]
        row: dict | None = None
        try:
            async with httpx.AsyncClient(timeout=25.0) as client:
                # 1) 빠른 경로: 지정 유형에서 id 필터
                if target:
                    try:
                        resp = await client.get(
                            f"{_BASE}/{type_cfg['detail']}",
                            params={"page": 1, "perPage": 50, "serviceKey": self._key,
                                    "cond[HOUSE_MANAGE_NO::EQ]": target})
                        rows = resp.json().get("data", []) if resp.status_code == 200 else []
                        if rows:
                            row = rows[0]
                    except Exception:  # noqa: BLE001
                        pass
                # 2) 폴백: 전 유형을 날짜조건으로 가져와 관리번호/공고번호 일치 행 탐색
                if row is None:
                    ordered = [type_cfg] + [t for t in PRESALE_TYPES if t["key"] != type_cfg["key"]]
                    for tc in ordered:
                        try:
                            resp = await client.get(
                                f"{_BASE}/{tc['detail']}",
                                params={"page": 1, "perPage": 300, "serviceKey": self._key,
                                        "cond[RCRIT_PBLANC_DE::GTE]": since})
                            rows = resp.json().get("data", []) if resp.status_code == 200 else []
                        except Exception:  # noqa: BLE001
                            rows = []
                        for r in rows:
                            if (target and _g(r, "HOUSE_MANAGE_NO") == target) or \
                               (target_pb and _g(r, "PBLANC_NO") == target_pb):
                                row, type_cfg = r, tc
                                break
                        if row is not None:
                            break
                if row is None:
                    return {"available": False, "note": "해당 공고를 찾을 수 없음"}

                info = self._normalize(row, today, type_cfg)

                # 3) 주택형별 분양가(models) — id 필터(실패 시 빈 목록=가격 미표시, 정직)
                mrows: list = []
                try:
                    mresp = await client.get(
                        f"{_BASE}/{type_cfg['model']}",
                        params={"page": 1, "perPage": 50, "serviceKey": self._key,
                                "cond[HOUSE_MANAGE_NO::EQ]": _g(row, "HOUSE_MANAGE_NO")})
                    mrows = mresp.json().get("data", []) if mresp.status_code == 200 else []
                except Exception:  # noqa: BLE001
                    mrows = []
        except Exception as e:  # noqa: BLE001
            logger.warning("presale.detail_failed", error=str(e))
            return {"available": False, "note": "청약홈 상세 호출 실패"}

        models, prices = [], []
        for r in mrows:
            amt = _g(r, "LTTOT_TOP_AMOUNT", "SUPLY_AMOUNT", "LTTOT_AMOUNT")
            try:
                amt_man = int(float(amt)) if amt else None
            except Exception:  # noqa: BLE001
                amt_man = None
            if amt_man:
                prices.append(amt_man)
            models.append({
                "house_ty": _g(r, "HOUSE_TY"),
                "supply_area_m2": _g(r, "SUPLY_AR"),
                "supply_households": _g(r, "SUPLY_HSHLDCO"),
                "special_households": _g(r, "SPSPLY_HSHLDCO"),
                "price_man": amt_man,
            })
        info["models"] = models
        info["price_min_man"] = min(prices) if prices else None
        info["price_max_man"] = max(prices) if prices else None
        info["available"] = True
        return info

    # ── 3) 반경/관심지역 필터(지도용, 5종 통합) ──
    async def nearby(
        self, center_lat: float | None, center_lon: float | None,
        area: str | None, radius_m: int = 3000, months_back: int = 12, max_markers: int = 40,
    ) -> dict[str, Any]:
        listing = await self.list_announcements(area=area, months_back=months_back,
                                                product="all", max_items=300)
        if not listing.get("available"):
            return {"available": False, "items": [], "note": listing.get("note")}
        items = [it for it in listing["items"] if it.get("address")]
        if center_lat is None or center_lon is None:
            return {"available": True, "items": items[:max_markers], "note": "중심좌표 없음 — 거리필터 미적용"}

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
