"""개발 가능 유형 분석기.

국토의 계획 및 이용에 관한 법률 시행령 별표2~20 기반.
용도지역+대지면적 조건으로 건축 가능한 건축물 유형을 자동 판정.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# ── 건축법 시행령 별표1 건축물 용도분류 (주요 15개) ──
BUILDING_USE_CATEGORIES: dict[str, str] = {
    "01": "단독주택",
    "02": "공동주택",
    "03": "제1종 근린생활시설",
    "04": "제2종 근린생활시설",
    "05": "문화 및 집회시설",
    "06": "종교시설",
    "07": "판매시설",
    "08": "운수시설",
    "09": "의료시설",
    "10": "교육연구시설",
    "11": "노유자시설",
    "12": "수련시설",
    "13": "운동시설",
    "14": "업무시설",
    "15": "숙박시설",
}

# ── 용도지역별 허용 건축물 유형 ──
# 각 항목: type_name, type_code, min_area_sqm, conditions, legal_basis
ZONE_ALLOWED_BUILDINGS: dict[str, list[dict[str, Any]]] = {
    "제1종전용주거지역": [
        {"type_name": "단독주택", "type_code": "01", "min_area_sqm": 0, "conditions": "", "legal_basis": "시행령 별표2"},
        {"type_name": "공동주택(다세대)", "type_code": "02", "min_area_sqm": 0, "conditions": "4층 이하", "legal_basis": "시행령 별표2"},
        {"type_name": "제1종 근린생활시설", "type_code": "03", "min_area_sqm": 0, "conditions": "바닥면적 합계 1,000㎡ 미만", "legal_basis": "시행령 별표2"},
        {"type_name": "종교시설", "type_code": "06", "min_area_sqm": 0, "conditions": "", "legal_basis": "시행령 별표2"},
        {"type_name": "교육연구시설", "type_code": "10", "min_area_sqm": 0, "conditions": "초등학교", "legal_basis": "시행령 별표2"},
    ],
    "제2종전용주거지역": [
        {"type_name": "단독주택", "type_code": "01", "min_area_sqm": 0, "conditions": "", "legal_basis": "시행령 별표3"},
        {"type_name": "공동주택(아파트 제외)", "type_code": "02", "min_area_sqm": 0, "conditions": "", "legal_basis": "시행령 별표3"},
        {"type_name": "제1종 근린생활시설", "type_code": "03", "min_area_sqm": 0, "conditions": "", "legal_basis": "시행령 별표3"},
        {"type_name": "종교시설", "type_code": "06", "min_area_sqm": 0, "conditions": "", "legal_basis": "시행령 별표3"},
        {"type_name": "교육연구시설", "type_code": "10", "min_area_sqm": 0, "conditions": "", "legal_basis": "시행령 별표3"},
        {"type_name": "노유자시설", "type_code": "11", "min_area_sqm": 0, "conditions": "", "legal_basis": "시행령 별표3"},
    ],
    "제1종일반주거지역": [
        {"type_name": "단독주택", "type_code": "01", "min_area_sqm": 0, "conditions": "", "legal_basis": "시행령 별표4"},
        {"type_name": "공동주택(아파트 제외)", "type_code": "02", "min_area_sqm": 0, "conditions": "4층 이하", "legal_basis": "시행령 별표4"},
        {"type_name": "제1종 근린생활시설", "type_code": "03", "min_area_sqm": 0, "conditions": "", "legal_basis": "시행령 별표4"},
        {"type_name": "제2종 근린생활시설", "type_code": "04", "min_area_sqm": 0, "conditions": "일부 업종 제한", "legal_basis": "시행령 별표4"},
        {"type_name": "종교시설", "type_code": "06", "min_area_sqm": 0, "conditions": "", "legal_basis": "시행령 별표4"},
        {"type_name": "교육연구시설", "type_code": "10", "min_area_sqm": 0, "conditions": "", "legal_basis": "시행령 별표4"},
        {"type_name": "노유자시설", "type_code": "11", "min_area_sqm": 0, "conditions": "", "legal_basis": "시행령 별표4"},
    ],
    "제2종일반주거지역": [
        {"type_name": "단독주택", "type_code": "01", "min_area_sqm": 0, "conditions": "", "legal_basis": "시행령 별표5"},
        {"type_name": "공동주택(아파트 포함)", "type_code": "02", "min_area_sqm": 0, "conditions": "", "legal_basis": "시행령 별표5"},
        {"type_name": "제1종 근린생활시설", "type_code": "03", "min_area_sqm": 0, "conditions": "", "legal_basis": "시행령 별표5"},
        {"type_name": "제2종 근린생활시설", "type_code": "04", "min_area_sqm": 0, "conditions": "", "legal_basis": "시행령 별표5"},
        {"type_name": "종교시설", "type_code": "06", "min_area_sqm": 0, "conditions": "", "legal_basis": "시행령 별표5"},
        {"type_name": "의료시설", "type_code": "09", "min_area_sqm": 0, "conditions": "병원", "legal_basis": "시행령 별표5"},
        {"type_name": "교육연구시설", "type_code": "10", "min_area_sqm": 0, "conditions": "", "legal_basis": "시행령 별표5"},
        {"type_name": "노유자시설", "type_code": "11", "min_area_sqm": 0, "conditions": "", "legal_basis": "시행령 별표5"},
        {"type_name": "운동시설", "type_code": "13", "min_area_sqm": 0, "conditions": "", "legal_basis": "시행령 별표5"},
        {"type_name": "업무시설(오피스텔)", "type_code": "14", "min_area_sqm": 300, "conditions": "준주거지역 인접 시", "legal_basis": "시행령 별표5"},
    ],
    "제3종일반주거지역": [
        {"type_name": "단독주택", "type_code": "01", "min_area_sqm": 0, "conditions": "", "legal_basis": "시행령 별표6"},
        {"type_name": "공동주택(아파트 포함)", "type_code": "02", "min_area_sqm": 0, "conditions": "", "legal_basis": "시행령 별표6"},
        {"type_name": "제1종 근린생활시설", "type_code": "03", "min_area_sqm": 0, "conditions": "", "legal_basis": "시행령 별표6"},
        {"type_name": "제2종 근린생활시설", "type_code": "04", "min_area_sqm": 0, "conditions": "", "legal_basis": "시행령 별표6"},
        {"type_name": "문화 및 집회시설", "type_code": "05", "min_area_sqm": 0, "conditions": "공연장, 전시장", "legal_basis": "시행령 별표6"},
        {"type_name": "종교시설", "type_code": "06", "min_area_sqm": 0, "conditions": "", "legal_basis": "시행령 별표6"},
        {"type_name": "의료시설", "type_code": "09", "min_area_sqm": 0, "conditions": "", "legal_basis": "시행령 별표6"},
        {"type_name": "교육연구시설", "type_code": "10", "min_area_sqm": 0, "conditions": "", "legal_basis": "시행령 별표6"},
        {"type_name": "노유자시설", "type_code": "11", "min_area_sqm": 0, "conditions": "", "legal_basis": "시행령 별표6"},
        {"type_name": "업무시설(오피스텔)", "type_code": "14", "min_area_sqm": 300, "conditions": "", "legal_basis": "시행령 별표6"},
    ],
    "준주거지역": [
        {"type_name": "단독주택", "type_code": "01", "min_area_sqm": 0, "conditions": "", "legal_basis": "시행령 별표7"},
        {"type_name": "공동주택(아파트 포함)", "type_code": "02", "min_area_sqm": 0, "conditions": "", "legal_basis": "시행령 별표7"},
        {"type_name": "제1종 근린생활시설", "type_code": "03", "min_area_sqm": 0, "conditions": "", "legal_basis": "시행령 별표7"},
        {"type_name": "제2종 근린생활시설", "type_code": "04", "min_area_sqm": 0, "conditions": "", "legal_basis": "시행령 별표7"},
        {"type_name": "판매시설", "type_code": "07", "min_area_sqm": 0, "conditions": "", "legal_basis": "시행령 별표7"},
        {"type_name": "의료시설", "type_code": "09", "min_area_sqm": 0, "conditions": "", "legal_basis": "시행령 별표7"},
        {"type_name": "교육연구시설", "type_code": "10", "min_area_sqm": 0, "conditions": "", "legal_basis": "시행령 별표7"},
        {"type_name": "업무시설", "type_code": "14", "min_area_sqm": 0, "conditions": "", "legal_basis": "시행령 별표7"},
        {"type_name": "숙박시설", "type_code": "15", "min_area_sqm": 500, "conditions": "조례 허용 시", "legal_basis": "시행령 별표7"},
        {"type_name": "주상복합", "type_code": "02+14", "min_area_sqm": 1000, "conditions": "주거비율 90% 이하", "legal_basis": "시행령 별표7"},
    ],
    "중심상업지역": [
        {"type_name": "업무시설", "type_code": "14", "min_area_sqm": 0, "conditions": "", "legal_basis": "시행령 별표8"},
        {"type_name": "판매시설", "type_code": "07", "min_area_sqm": 0, "conditions": "", "legal_basis": "시행령 별표8"},
        {"type_name": "공동주택(아파트 포함)", "type_code": "02", "min_area_sqm": 0, "conditions": "주거비율 제한", "legal_basis": "시행령 별표8"},
        {"type_name": "제1종 근린생활시설", "type_code": "03", "min_area_sqm": 0, "conditions": "", "legal_basis": "시행령 별표8"},
        {"type_name": "제2종 근린생활시설", "type_code": "04", "min_area_sqm": 0, "conditions": "", "legal_basis": "시행령 별표8"},
        {"type_name": "문화 및 집회시설", "type_code": "05", "min_area_sqm": 0, "conditions": "", "legal_basis": "시행령 별표8"},
        {"type_name": "숙박시설", "type_code": "15", "min_area_sqm": 0, "conditions": "", "legal_basis": "시행령 별표8"},
        {"type_name": "의료시설", "type_code": "09", "min_area_sqm": 0, "conditions": "", "legal_basis": "시행령 별표8"},
    ],
    "일반상업지역": [
        {"type_name": "업무시설", "type_code": "14", "min_area_sqm": 0, "conditions": "", "legal_basis": "시행령 별표9"},
        {"type_name": "판매시설", "type_code": "07", "min_area_sqm": 0, "conditions": "", "legal_basis": "시행령 별표9"},
        {"type_name": "공동주택(아파트 포함)", "type_code": "02", "min_area_sqm": 0, "conditions": "", "legal_basis": "시행령 별표9"},
        {"type_name": "제1종 근린생활시설", "type_code": "03", "min_area_sqm": 0, "conditions": "", "legal_basis": "시행령 별표9"},
        {"type_name": "제2종 근린생활시설", "type_code": "04", "min_area_sqm": 0, "conditions": "", "legal_basis": "시행령 별표9"},
        {"type_name": "문화 및 집회시설", "type_code": "05", "min_area_sqm": 0, "conditions": "", "legal_basis": "시행령 별표9"},
        {"type_name": "숙박시설", "type_code": "15", "min_area_sqm": 0, "conditions": "", "legal_basis": "시행령 별표9"},
        {"type_name": "주상복합", "type_code": "02+14", "min_area_sqm": 1000, "conditions": "주거비율 제한", "legal_basis": "시행령 별표9"},
    ],
    "근린상업지역": [
        {"type_name": "제1종 근린생활시설", "type_code": "03", "min_area_sqm": 0, "conditions": "", "legal_basis": "시행령 별표10"},
        {"type_name": "제2종 근린생활시설", "type_code": "04", "min_area_sqm": 0, "conditions": "", "legal_basis": "시행령 별표10"},
        {"type_name": "판매시설", "type_code": "07", "min_area_sqm": 0, "conditions": "", "legal_basis": "시행령 별표10"},
        {"type_name": "공동주택(아파트 포함)", "type_code": "02", "min_area_sqm": 0, "conditions": "", "legal_basis": "시행령 별표10"},
        {"type_name": "업무시설", "type_code": "14", "min_area_sqm": 0, "conditions": "", "legal_basis": "시행령 별표10"},
        {"type_name": "의료시설", "type_code": "09", "min_area_sqm": 0, "conditions": "", "legal_basis": "시행령 별표10"},
        {"type_name": "숙박시설", "type_code": "15", "min_area_sqm": 300, "conditions": "조례 허용 시", "legal_basis": "시행령 별표10"},
    ],
    "유통상업지역": [
        {"type_name": "판매시설", "type_code": "07", "min_area_sqm": 0, "conditions": "", "legal_basis": "시행령 별표11"},
        {"type_name": "운수시설", "type_code": "08", "min_area_sqm": 0, "conditions": "", "legal_basis": "시행령 별표11"},
        {"type_name": "업무시설", "type_code": "14", "min_area_sqm": 0, "conditions": "", "legal_basis": "시행령 별표11"},
        {"type_name": "제1종 근린생활시설", "type_code": "03", "min_area_sqm": 0, "conditions": "", "legal_basis": "시행령 별표11"},
        {"type_name": "제2종 근린생활시설", "type_code": "04", "min_area_sqm": 0, "conditions": "", "legal_basis": "시행령 별표11"},
    ],
    "전용공업지역": [
        {"type_name": "업무시설", "type_code": "14", "min_area_sqm": 0, "conditions": "공장 부속 사무소", "legal_basis": "시행령 별표12"},
        {"type_name": "제1종 근린생활시설", "type_code": "03", "min_area_sqm": 0, "conditions": "공장지원 시설", "legal_basis": "시행령 별표12"},
    ],
    "일반공업지역": [
        {"type_name": "업무시설", "type_code": "14", "min_area_sqm": 0, "conditions": "", "legal_basis": "시행령 별표13"},
        {"type_name": "제1종 근린생활시설", "type_code": "03", "min_area_sqm": 0, "conditions": "", "legal_basis": "시행령 별표13"},
        {"type_name": "제2종 근린생활시설", "type_code": "04", "min_area_sqm": 0, "conditions": "일부 제한", "legal_basis": "시행령 별표13"},
        {"type_name": "의료시설", "type_code": "09", "min_area_sqm": 0, "conditions": "", "legal_basis": "시행령 별표13"},
        {"type_name": "교육연구시설", "type_code": "10", "min_area_sqm": 0, "conditions": "직업훈련소 등", "legal_basis": "시행령 별표13"},
    ],
    "준공업지역": [
        {"type_name": "단독주택", "type_code": "01", "min_area_sqm": 0, "conditions": "", "legal_basis": "시행령 별표14"},
        {"type_name": "공동주택(아파트 포함)", "type_code": "02", "min_area_sqm": 0, "conditions": "", "legal_basis": "시행령 별표14"},
        {"type_name": "제1종 근린생활시설", "type_code": "03", "min_area_sqm": 0, "conditions": "", "legal_basis": "시행령 별표14"},
        {"type_name": "제2종 근린생활시설", "type_code": "04", "min_area_sqm": 0, "conditions": "", "legal_basis": "시행령 별표14"},
        {"type_name": "업무시설", "type_code": "14", "min_area_sqm": 0, "conditions": "", "legal_basis": "시행령 별표14"},
        {"type_name": "판매시설", "type_code": "07", "min_area_sqm": 0, "conditions": "", "legal_basis": "시행령 별표14"},
        {"type_name": "의료시설", "type_code": "09", "min_area_sqm": 0, "conditions": "", "legal_basis": "시행령 별표14"},
        {"type_name": "교육연구시설", "type_code": "10", "min_area_sqm": 0, "conditions": "", "legal_basis": "시행령 별표14"},
    ],
    "보전녹지지역": [
        {"type_name": "단독주택", "type_code": "01", "min_area_sqm": 0, "conditions": "기존 건축물 증·개축", "legal_basis": "시행령 별표15"},
        {"type_name": "종교시설", "type_code": "06", "min_area_sqm": 0, "conditions": "", "legal_basis": "시행령 별표15"},
    ],
    "생산녹지지역": [
        {"type_name": "단독주택", "type_code": "01", "min_area_sqm": 0, "conditions": "", "legal_basis": "시행령 별표16"},
        {"type_name": "제1종 근린생활시설", "type_code": "03", "min_area_sqm": 0, "conditions": "", "legal_basis": "시행령 별표16"},
        {"type_name": "교육연구시설", "type_code": "10", "min_area_sqm": 0, "conditions": "", "legal_basis": "시행령 별표16"},
    ],
    "자연녹지지역": [
        {"type_name": "단독주택", "type_code": "01", "min_area_sqm": 0, "conditions": "", "legal_basis": "시행령 별표17"},
        {"type_name": "제1종 근린생활시설", "type_code": "03", "min_area_sqm": 0, "conditions": "", "legal_basis": "시행령 별표17"},
        {"type_name": "종교시설", "type_code": "06", "min_area_sqm": 0, "conditions": "", "legal_basis": "시행령 별표17"},
        {"type_name": "교육연구시설", "type_code": "10", "min_area_sqm": 0, "conditions": "", "legal_basis": "시행령 별표17"},
        {"type_name": "수련시설", "type_code": "12", "min_area_sqm": 0, "conditions": "자연학습장 등", "legal_basis": "시행령 별표17"},
    ],
}

# ── 주요 용도지역별 건축 제한 유형 ──
_ZONE_RESTRICTED: dict[str, list[dict[str, str]]] = {
    "제1종전용주거지역": [
        {"type_name": "아파트", "reason": "제1종전용주거지역 내 아파트 건축 불가"},
        {"type_name": "판매시설", "reason": "주거전용지역 내 판매시설 불가"},
        {"type_name": "숙박시설", "reason": "주거전용지역 내 숙박시설 불가"},
        {"type_name": "업무시설", "reason": "주거전용지역 내 업무시설 불가"},
    ],
    "제2종전용주거지역": [
        {"type_name": "아파트", "reason": "제2종전용주거지역 내 아파트 건축 불가"},
        {"type_name": "판매시설", "reason": "주거전용지역 내 판매시설 불가"},
        {"type_name": "숙박시설", "reason": "주거전용지역 내 숙박시설 불가"},
    ],
    "제1종일반주거지역": [
        {"type_name": "아파트", "reason": "제1종일반주거지역 내 아파트 건축 불가 (4층 이하만)"},
        {"type_name": "판매시설", "reason": "주거지역 내 대규모 판매시설 불가"},
        {"type_name": "숙박시설", "reason": "제1종일반주거지역 내 숙박시설 불가"},
    ],
    "전용공업지역": [
        {"type_name": "공동주택", "reason": "전용공업지역 내 주거시설 불가"},
        {"type_name": "숙박시설", "reason": "전용공업지역 내 숙박시설 불가"},
        {"type_name": "판매시설", "reason": "전용공업지역 내 대규모 판매시설 불가"},
    ],
    "보전녹지지역": [
        {"type_name": "공동주택", "reason": "보전녹지지역 내 공동주택 불가"},
        {"type_name": "판매시설", "reason": "보전녹지지역 내 판매시설 불가"},
        {"type_name": "업무시설", "reason": "보전녹지지역 내 업무시설 불가"},
        {"type_name": "숙박시설", "reason": "보전녹지지역 내 숙박시설 불가"},
    ],
}


def _recommend_by_area(
    zone_type: str,
    land_area_sqm: float,
    allowed_types: list[dict[str, Any]],
) -> tuple[str, str]:
    """대지면적 기반 추천 유형과 사유를 반환."""
    allowed_names = {t["type_name"] for t in allowed_types}

    if land_area_sqm < 300:
        # 소규모 필지
        if "단독주택" in allowed_names:
            return "단독주택", f"대지면적 {land_area_sqm:.0f}㎡ 소규모 필지에 적합한 단독주택 추천"
        for name in allowed_names:
            if "다세대" in name:
                return name, f"대지면적 {land_area_sqm:.0f}㎡ 소규모 필지에 적합한 다세대주택 추천"
        if "제1종 근린생활시설" in allowed_names:
            return "제1종 근린생활시설", f"대지면적 {land_area_sqm:.0f}㎡ 소규모 상업 활용 추천"

    elif land_area_sqm < 1000:
        # 중규모 필지
        for name in allowed_names:
            if "다세대" in name or ("공동주택" in name and "아파트" not in name):
                return name, f"대지면적 {land_area_sqm:.0f}㎡ 중규모 필지에 적합한 다세대/연립주택 추천"
        if "제2종 근린생활시설" in allowed_names:
            return "제2종 근린생활시설", f"대지면적 {land_area_sqm:.0f}㎡ 중규모 필지에 적합한 근린생활시설 추천"
        if "제1종 근린생활시설" in allowed_names:
            return "제1종 근린생활시설", f"대지면적 {land_area_sqm:.0f}㎡ 중규모 근생 추천"

    else:
        # 대규모 필지
        for name in allowed_names:
            if "아파트" in name:
                return name, f"대지면적 {land_area_sqm:.0f}㎡ 대규모 필지에 적합한 아파트 추천"
        if "업무시설" in allowed_names or "업무시설(오피스텔)" in allowed_names:
            return "업무시설(오피스텔)", f"대지면적 {land_area_sqm:.0f}㎡ 대규모 필지에 적합한 오피스텔 추천"
        for name in allowed_names:
            if "주상복합" in name:
                return name, f"대지면적 {land_area_sqm:.0f}㎡ 대규모 필지에 적합한 주상복합 추천"

    # 폴백: 허용 목록 첫 번째
    if allowed_types:
        first = allowed_types[0]["type_name"]
        return first, f"{zone_type} 내 대표 건축유형인 {first} 추천"
    return "단독주택", "허용 유형 정보 없음 — 단독주택 기본 추천"


def analyze(
    zone_type: str,
    land_area_sqm: float,
    existing_building: str | None = None,
) -> dict[str, Any]:
    """용도지역+대지면적 기반 개발 가능 유형 분석.

    Args:
        zone_type: 용도지역명 (예: "제2종일반주거지역")
        land_area_sqm: 대지면적 (㎡)
        existing_building: 기존 건축물 용도 (있을 경우)

    Returns:
        dict: allowed_types, restricted_types, recommended_type, recommendation_reason
    """
    # 허용 건축물 유형 조회
    raw_allowed = ZONE_ALLOWED_BUILDINGS.get(zone_type, [])

    # 부분 매칭 시도
    if not raw_allowed:
        for key in ZONE_ALLOWED_BUILDINGS:
            if key in zone_type or zone_type in key:
                raw_allowed = ZONE_ALLOWED_BUILDINGS[key]
                break

    # 대지면적 필터링 + GFA 추산
    from .auto_zoning_service import ZONE_LIMITS

    zone_limits = ZONE_LIMITS.get(zone_type, {})
    max_far = zone_limits.get("max_far", 200)
    max_bcr = zone_limits.get("max_bcr", 60)
    max_gfa_sqm = land_area_sqm * (max_far / 100)

    allowed_types: list[dict[str, Any]] = []
    for item in raw_allowed:
        min_area = item.get("min_area_sqm", 0)
        is_recommended = land_area_sqm >= min_area
        allowed_types.append({
            "type_name": item["type_name"],
            "type_code": item["type_code"],
            "conditions": item.get("conditions", ""),
            "recommended": is_recommended,
            "max_gfa_sqm": round(max_gfa_sqm, 1),
            "remarks": f"최소 대지면적 {min_area}㎡ 필요" if min_area > 0 and not is_recommended else "",
        })

    # 제한 유형
    restricted_types = _ZONE_RESTRICTED.get(zone_type, [])
    if not restricted_types:
        for key in _ZONE_RESTRICTED:
            if key in zone_type or zone_type in key:
                restricted_types = _ZONE_RESTRICTED[key]
                break

    # 추천 유형 결정
    recommended_type, recommendation_reason = _recommend_by_area(
        zone_type, land_area_sqm, allowed_types
    )

    # 기존 건물이 있으면 추천 사유에 반영
    if existing_building:
        recommendation_reason += f" (기존 건축물: {existing_building})"

    return {
        "zone_type": zone_type,
        "land_area_sqm": land_area_sqm,
        "max_gfa_sqm": round(max_gfa_sqm, 1),
        "max_bcr_pct": max_bcr,
        "max_far_pct": max_far,
        "allowed_types": allowed_types,
        "restricted_types": restricted_types,
        "recommended_type": recommended_type,
        "recommendation_reason": recommendation_reason,
        "legal_basis": "국토의 계획 및 이용에 관한 법률 시행령 별표2~20",
    }
