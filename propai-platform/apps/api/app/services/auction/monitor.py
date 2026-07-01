"""경·공매 모니터링 매칭 엔진 — 관심대상(보유토지/Excel업로드/지도구획) ↔ 온비드 물건.

본 모듈은 ★목업을 만들지 않는다. 매칭은 캐시된 실물건(auction_items)·실 watch 대상만
대상으로 한다. 좌표가 필요한 폴리곤(지도구획) 매칭만 VWorld 지오코딩을 호출하며, 그 외
주소/PNU 직접매칭은 지오코딩 없이(빠르게) 수행한다.

매칭 종류:
  1) PNU 직접매칭: watch.pnu == auction_items.pnu (정확).
  2) 주소 텍스트 부분매칭: 정규화(공백/구분자 제거) 후 한쪽이 다른쪽을 포함.
  3) 폴리곤(region): 물건 주소 → VWorld 지오코딩 → 좌표 → shapely point-in-polygon.
     ★지오코딩 폭주 방지: 폴리곤 매칭 대상만 지오코딩하고 좌표는 auction_items에 캐시
     (lat/lng)한다. 지오코딩 실패/무자료는 ★스킵 + 사유 기록(정직, 가짜좌표 금지).

Excel 컬럼 자동감지(parse_watchlist_excel)는 다양한 헤더명(PNU/지번/주소/소재지 등)을
방어적으로 인식한다.
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


# ── Excel 컬럼 자동감지: 정규화된 헤더 → 표준 필드 ──
# 헤더에서 공백/특수문자를 제거하고 소문자화한 키로 매칭한다.
_PNU_HEADERS = {
    "pnu", "pnu코드", "pnucode", "고유번호", "토지고유번호", "필지고유번호",
    "지번코드", "법정동코드지번",
}
_ADDRESS_HEADERS = {
    "주소", "소재지", "소재지지번", "지번주소", "address", "소재지번",
    "토지소재지", "물건소재지", "소재", "번지", "지번", "소재지번지",
    "도로명주소", "address1", "addr",
}
_LABEL_HEADERS = {
    "라벨", "label", "명칭", "이름", "name", "비고", "메모", "note", "물건명",
}


def _norm_header(h: Any) -> str:
    """헤더 문자열을 비교용으로 정규화(공백·특수문자 제거, 소문자)."""
    s = str(h or "").strip().lower()
    return re.sub(r"[\s\-_/().·]", "", s)


def detect_columns(headers: list[Any]) -> dict[str, str | None]:
    """헤더 리스트에서 pnu/address/label 컬럼명을 자동감지한다.

    반환: {"pnu": <원본헤더|None>, "address": <원본헤더|None>, "label": <원본헤더|None>}.
    동일 후보가 여럿이면 먼저 나온 컬럼을 채택한다.
    """
    found: dict[str, str | None] = {"pnu": None, "address": None, "label": None}
    for h in headers:
        norm = _norm_header(h)
        if not norm:
            continue
        if found["pnu"] is None and norm in _PNU_HEADERS:
            found["pnu"] = h
        elif found["address"] is None and norm in _ADDRESS_HEADERS:
            found["address"] = h
        elif found["label"] is None and norm in _LABEL_HEADERS:
            found["label"] = h
    return found


def _looks_like_pnu(v: str) -> bool:
    """PNU 형태(19자리 숫자) 추정 — 헤더 미인식 시 값으로 보조판별."""
    digits = re.sub(r"\D", "", v or "")
    return len(digits) == 19


def parse_watchlist_excel(
    raw: bytes, filename: str = "",
) -> dict[str, Any]:
    """업로드 파일(xlsx/xls/csv)을 파싱해 watch 행 후보를 추출한다(무목업).

    반환: {
      "rows": [{"pnu": str|None, "address": str|None, "label": str|None}, ...],
      "detected_columns": {...}, "parsed_count": int, "skipped_rows": int,
      "total_rows": int, "examples": [...앞 3행...],
    }
    잘못된 파일/빈 컬럼은 ValueError로 정직하게 에러를 던진다.
    """
    import io

    import pandas as pd

    name = (filename or "").lower()
    try:
        if name.endswith(".csv"):
            df = pd.read_csv(io.BytesIO(raw), dtype=str, keep_default_na=False)
        elif name.endswith(".xls"):
            df = pd.read_excel(io.BytesIO(raw), dtype=str, engine="xlrd")
        else:
            # xlsx 및 확장자 불명: openpyxl 기본.
            df = pd.read_excel(io.BytesIO(raw), dtype=str, engine="openpyxl")
    except Exception as e:  # noqa: BLE001
        raise ValueError(f"파일을 읽을 수 없습니다(형식 확인 필요): {str(e)[:160]}") from e

    if df is None or df.shape[1] == 0:
        raise ValueError("빈 파일이거나 컬럼이 없습니다.")

    headers = list(df.columns)
    detected = detect_columns(headers)
    if detected["pnu"] is None and detected["address"] is None:
        raise ValueError(
            "PNU·주소(소재지) 컬럼을 인식하지 못했습니다. "
            f"인식된 헤더={headers}. 헤더에 'PNU' 또는 '주소/소재지/지번'을 포함하세요."
        )

    rows: list[dict[str, Any]] = []
    skipped = 0
    total = int(df.shape[0])
    pnu_col = detected["pnu"]
    addr_col = detected["address"]
    label_col = detected["label"]

    for _, r in df.iterrows():
        pnu_val = str(r.get(pnu_col, "") if pnu_col else "").strip() or None
        addr_val = str(r.get(addr_col, "") if addr_col else "").strip() or None
        label_val = str(r.get(label_col, "") if label_col else "").strip() or None

        # PNU 컬럼 미지정인데 주소 컬럼 값이 PNU 형태면 보조 인식.
        if pnu_val is None and addr_val and _looks_like_pnu(addr_val):
            digits = re.sub(r"\D", "", addr_val)
            pnu_val, addr_val = digits, None

        # PNU는 숫자만 남겨 정규화(부분 하이픈/공백 방어).
        if pnu_val:
            digits = re.sub(r"\D", "", pnu_val)
            pnu_val = digits if len(digits) == 19 else pnu_val

        if not pnu_val and not addr_val:
            skipped += 1
            continue
        rows.append({"pnu": pnu_val, "address": addr_val, "label": label_val})

    return {
        "rows": rows,
        "detected_columns": detected,
        "parsed_count": len(rows),
        "skipped_rows": skipped,
        "total_rows": total,
        "examples": rows[:3],
    }


# ── 주소 텍스트 정규화/매칭 ──
def normalize_address(addr: Any) -> str:
    """주소를 매칭용으로 정규화(공백·구분자 제거)."""
    s = str(addr or "").strip()
    if not s:
        return ""
    # 괄호 안 부가설명 제거(예: "(대) 100㎡").
    s = re.sub(r"\([^)]*\)", "", s)
    s = re.sub(r"[\s,\-]", "", s)
    return s


def address_matches(watch_addr: Any, item_addr: Any) -> bool:
    """두 주소가 부분일치하는지(정규화 후 포함관계). 짧은쪽 길이 6자 미만은 매칭 안함."""
    a = normalize_address(watch_addr)
    b = normalize_address(item_addr)
    if not a or not b:
        return False
    shorter = a if len(a) <= len(b) else b
    longer = b if shorter is a else a
    if len(shorter) < 6:
        return False
    return shorter in longer


# ── 폴리곤(point-in-polygon) ──
def point_in_polygon(lat: float, lon: float, geojson: dict[str, Any]) -> bool:
    """GeoJSON Polygon/MultiPolygon 안에 (lon,lat) 점이 포함되는지(shapely)."""
    from shapely.geometry import Point, shape

    try:
        poly = shape(geojson)
    except Exception:  # noqa: BLE001
        return False
    return poly.contains(Point(lon, lat))
