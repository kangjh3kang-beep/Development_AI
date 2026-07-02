"""토지이음 '행위제한내용 설명' 보강 — 건축선·도로조건(결정론) + 고시정보 연결.

토지이음의 층수·높이제한(일조)·건폐율/용적률은 이미 다른 모듈이 다룬다. 본 모듈은 미수집이던
 ① 도로조건(접도요건, 건축법 제44조·시행령 제28조): 연면적별 접도 길이·도로 너비 충족 판정.
 ② 건축선(건축법 제46조): 소요너비 미달 도로의 건축선 후퇴 거리.
 ③ 고시정보(결정고시·지형도면고시·실시계획인가): 토지이음 고시 목록 deep-link(시군구 스코프).
를 결정론·근거기반으로 산출한다(무목업 — road_side 미상은 정직 미산정).
"""
from __future__ import annotations

from typing import Any
from urllib.parse import quote

# 도로접면(road_side, 국토부 roadSideCodeNm) → 추정 도로 너비(m) 하한.
#   광대=25m↑, 중로=12~25m, 소로=8~12m, 세로(가)=차량통행 가능 소도로, 세로(불)=불가, 맹지=미접.
_ROAD_WIDTH_BY_SIDE: tuple[tuple[tuple[str, ...], float | None, str], ...] = (
    (("광대",), 25.0, "광대로(폭 25m 이상)"),
    (("중로",), 12.0, "중로(폭 12~25m)"),
    (("소로",), 8.0, "소로(폭 8~12m)"),
    (("세로(가)", "세로가"), 4.0, "세로(가) — 차량통행 가능 소도로(폭 약 4m)"),
    (("세로(불)", "세로불"), 2.0, "세로(불) — 차량통행 불가(폭 4m 미만)"),
    (("맹지",), None, "맹지 — 도로에 접하지 않음"),
)


def _road_width(road_side: str | None) -> tuple[float | None, str]:
    s = (road_side or "").replace(" ", "")
    if not s:
        return None, "도로접면 정보 없음(미상)"
    for kws, w, label in _ROAD_WIDTH_BY_SIDE:
        if any(kw.replace(" ", "") in s for kw in kws):
            return w, label
    return None, f"도로접면 '{road_side}' — 너비 미상"


def assess_road_conditions(road_side: str | None, planned_gfa_sqm: float | None = None) -> dict[str, Any]:
    """접도요건(건축법 제44조·시행령 제28조) 충족 판정 — 연면적별 도로 너비·접도 길이.

    기준(시행령 제28조): 연면적 2,000㎡ 미만 → 대지 2m 이상이 너비 4m 이상 도로에 접.
                         연면적 2,000㎡ 이상(공장 3,000㎡) → 4m 이상이 너비 6m 이상 도로에 접.
    """
    width, label = _road_width(road_side)
    gfa = float(planned_gfa_sqm or 0)
    big = gfa >= 2000.0
    req_road_w = 6.0 if big else 4.0
    req_contact_m = 4.0 if big else 2.0
    tier = "연면적 2,000㎡ 이상" if big else "연면적 2,000㎡ 미만"

    if width is None and "맹지" in (road_side or ""):
        status, note = "불가", "맹지(도로 미접) — 건축허가 불가. 도로 확보(사도·진입로) 선행 필요."
    elif width is None:
        status, note = "미상", "도로접면 정보 미확보 — 접도요건 충족 여부 현장·지적도 확인 필요(정직 미산정)."
    elif width >= req_road_w:
        status, note = "충족", f"{label} — 요구 도로너비 {req_road_w:g}m 충족."
    else:
        status, note = "검토", (f"{label} — 요구 도로너비 {req_road_w:g}m 미달 가능. 건축선 후퇴 또는 "
                               "도로 확보 검토 필요(현장 확인).")
    return {
        "road_side": road_side, "road_width_label": label,
        "estimated_road_width_m": width,
        "gfa_tier": tier,
        "required_road_width_m": req_road_w, "required_contact_m": req_contact_m,
        "status": status, "note": note,
        "basis": "건축법 제44조(대지와 도로의 관계)·시행령 제28조",
        "legal_ref_keys": ["road_relation"],
    }


def building_line_setback(road_side: str | None) -> dict[str, Any]:
    """건축선 후퇴(건축법 제46조) — 소요너비(4m) 미달 도로는 중심선에서 (4m-도로폭)/2 후퇴.

    소요너비 4m 도로 기준: 도로폭 w<4m이면 중심선에서 2m 선을 건축선으로(=각 측 (4-w)/2 후퇴).
    """
    width, label = _road_width(road_side)
    REQ = 4.0  # noqa: N806 — 법정 소요너비(도로 4m) 상수 표기 관례
    if width is None:
        return {"setback_m": None, "label": label,
                "note": "도로폭 미상 — 건축선 후퇴 산정 불가(현장 확인). 맹지면 도로 확보 선행.",
                "basis": "건축법 제46조(건축선의 지정)", "legal_ref_keys": ["building_line"]}
    if width >= REQ:
        return {"setback_m": 0.0, "label": label,
                "note": f"{label} — 소요너비 {REQ:g}m 이상이라 건축선 후퇴 없음(대지경계=건축선).",
                "basis": "건축법 제46조(건축선의 지정)", "legal_ref_keys": ["building_line"]}
    setback = round((REQ - width) / 2.0, 2)
    return {"setback_m": setback, "label": label,
            "note": (f"{label}(폭 약 {width:g}m) — 소요너비 {REQ:g}m 미달. 도로 중심선에서 {REQ / 2:g}m "
                     f"선을 건축선으로(각 측 약 {setback:g}m 후퇴, 후퇴부 대지면적 제외)."),
            "basis": "건축법 제46조(건축선의 지정)·제47조(건축선에 따른 건축제한)",
            "legal_ref_keys": ["building_line", "building_line_limit"]}


def gosi_info(sido: str | None = None, sigungu: str | None = None) -> dict[str, Any]:
    """고시정보(결정고시·지형도면고시·실시계획인가) 연결 — 토지이음 고시 목록 deep-link.

    전국 단위 LURIS 고시 API의 부지단위 자동매칭은 별도 키·연동이 필요하므로(무날조 원칙),
    현 단계는 해당 시·군·구 스코프의 토지이음 고시정보 목록 deep-link를 제공해 즉시 열람 가능케 한다.
    """
    base = "https://www.eum.go.kr/web/gs/gv/gvGosiList.jsp"
    region = " ".join([x for x in [sido, sigungu] if x]).strip()
    return {
        "available": False,           # 부지단위 자동매칭 미연동(정직). 목록 deep-link로 대체.
        "region": region or None,
        "categories": ["결정고시", "지형도면고시", "실시계획인가고시"],
        "list_url": base + (f"?searchRegion={quote(region)}" if region else ""),
        "note": ("부지 인근 도시관리계획 결정·지형도면·실시계획인가 고시는 토지이음 고시정보에서 "
                 "열람하세요. 부지단위 자동매칭은 LURIS 고시 API 연동 시 제공 예정(현재 목록 링크 제공)."),
        "source": "토지이음(LURIS) 고시정보",
    }
