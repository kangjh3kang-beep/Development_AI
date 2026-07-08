"""
인허가 가능성 검증 -- 용도지역에서 해당 개발유형이 실제 허가 가능한지 판단.
"""

# Mapping: zone type -> allowed development types
ZONE_PERMIT_MATRIX = {
    "제1종전용주거지역": ["M10", "M11"],  # 단독/전원주택만
    "제2종전용주거지역": ["M10", "M11", "M12"],  # + 타운하우스
    "제1종일반주거지역": ["M10", "M11", "M12", "M13"],  # + 도시형생활주택
    "제2종일반주거지역": ["M01", "M02", "M04", "M06", "M10", "M11", "M12", "M13"],  # 공동주택 가능
    "제3종일반주거지역": ["M01", "M02", "M04", "M06", "M07", "M08", "M10", "M11", "M12", "M13"],  # + 주상복합/오피스텔
    "준주거지역": ["M01", "M02", "M04", "M05", "M06", "M07", "M08", "M09", "M10", "M11", "M12", "M13", "M14", "M15"],  # 대부분 가능
    "중심상업지역": ["M05", "M06", "M07", "M08", "M09", "M14", "M15"],  # 상업용 위주
    "일반상업지역": ["M05", "M06", "M07", "M08", "M09", "M13", "M14", "M15"],
    "근린상업지역": ["M05", "M06", "M07", "M08", "M09", "M13"],
    "유통상업지역": ["M05", "M08", "M09"],
    "전용공업지역": ["M09"],  # 지식산업센터만
    "일반공업지역": ["M09"],
    "준공업지역": ["M05", "M06", "M08", "M09", "M13"],
    "보전녹지지역": [],  # 개발 불가
    "생산녹지지역": ["M11"],  # 전원주택 조건부
    "자연녹지지역": ["M10", "M11"],  # 단독/전원
    "역세권개발구역": ["M06", "M07", "M08", "M13", "M14", "M15"],
    "도시재생활성화구역": ["M06", "M08", "M13", "M14"],
}

# Permit complexity by development type
PERMIT_COMPLEXITY = {
    "M01": 5,  # 재개발 -- 매우 어려움 (조합설립, 사업인정, 관리처분)
    "M02": 5,  # 재건축 -- 매우 어려움
    "M03": 4,  # 역세권 -- 어려움 (특별계획구역 지정 필요)
    "M04": 4,  # 지역주택조합 -- 어려움 (조합설립, 인허가 2단계)
    "M05": 3,  # 임대협동조합 -- 보통
    "M06": 2,  # 일반분양 -- 비교적 쉬움
    "M07": 3,  # 주상복합 -- 용도복합 심의 필요
    "M08": 2,  # 오피스텔 -- 비교적 쉬움
    "M09": 3,  # 지식산업센터 -- 산업단지 승인 필요
    "M10": 1,  # 단독주택 -- 가장 쉬움
    "M11": 1,  # 전원주택 -- 가장 쉬움
    "M12": 2,  # 타운하우스 -- 비교적 쉬움
    "M13": 2,  # 도시형생활주택 -- 비교적 쉬움
    "M14": 3,  # 공공임대 -- 공공기관 협의 필요
    "M15": 4,  # 민간리츠 -- 금융감독원 인가 필요
}

DEVELOPMENT_TYPE_NAMES = {
    "M01": "재개발", "M02": "재건축", "M03": "역세권개발", "M04": "지역주택조합",
    "M05": "임대협동조합", "M06": "일반분양", "M07": "주상복합", "M08": "오피스텔",
    "M09": "지식산업센터", "M10": "단독주택", "M11": "전원주택", "M12": "타운하우스",
    "M13": "도시형생활주택", "M14": "공공임대", "M15": "민간리츠",
}


def permitted_types_known(zone_type: str) -> bool:
    """용도지역이 매트릭스에 등재돼 '판정 가능'한지. 미등재(관리·농림 등)는 판정불가."""
    if not zone_type:
        return False
    if zone_type in ZONE_PERMIT_MATRIX:
        return True
    return any(key in zone_type or zone_type in key for key in ZONE_PERMIT_MATRIX)


def get_permitted_types(zone_type: str) -> list[str]:
    """해당 용도지역에서 인허가 가능한 개발유형 목록.

    ★미등재 용도지역(관리지역·농림지역 등)은 종전 '기본 4종(M06/M08/M10/M13) 허용' 폴백이
    농림지역에 일반분양·오피스텔 '허가 가능'을 날조할 위험(완성도 감사 P1) → 빈 목록 반환.
    빈 목록은 '허가불가 단정'이 아니라 '판정불가' — permitted_types_known()으로 구분하라.
    """
    zone_type = zone_type or ""
    # Try exact match
    if zone_type in ZONE_PERMIT_MATRIX:
        return ZONE_PERMIT_MATRIX[zone_type]
    # Try partial match
    for key in ZONE_PERMIT_MATRIX:
        if key in zone_type or zone_type in key:
            return ZONE_PERMIT_MATRIX[key]
    return []  # 미등재 — 판정불가(기본 허용 날조 금지)


def get_permit_complexity(dev_type: str) -> int:
    """인허가 복잡도 (1=쉬움 ~ 5=매우어려움)."""
    return PERMIT_COMPLEXITY.get(dev_type, 3)


def check_permit_feasibility(dev_type: str, zone_type: str) -> dict:
    """특정 개발유형의 인허가 가능성 검증.

    미등재 용도지역은 '불가' 단정이 아니라 zone_known=False + 판정불가 사유로 정직 표기
    (is_permitted는 하위호환상 False 유지 — 소비처는 zone_known으로 구분 가능).
    """
    zone_known = permitted_types_known(zone_type)
    permitted = get_permitted_types(zone_type)
    is_permitted = dev_type in permitted
    complexity = get_permit_complexity(dev_type)

    if zone_known:
        reason = f"{zone_type}에서 {DEVELOPMENT_TYPE_NAMES.get(dev_type, dev_type)} 개발 {'가능' if is_permitted else '불가'}"
    else:
        reason = (f"'{zone_type}'은(는) 인허가 매트릭스 미등재 용도지역 — 판정불가"
                  "(허가 가능/불가 단정 아님, 국토계획법 시행령 별표 확인 필요)")

    return {
        "development_type": dev_type,
        "type_name": DEVELOPMENT_TYPE_NAMES.get(dev_type, dev_type),
        "zone_type": zone_type,
        "is_permitted": is_permitted,
        "zone_known": zone_known,
        "permit_complexity": complexity,
        "complexity_label": ["", "매우쉬움", "쉬움", "보통", "어려움", "매우어려움"][complexity],
        "reason": reason,
    }
