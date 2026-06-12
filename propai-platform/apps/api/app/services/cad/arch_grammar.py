"""건축 설계 문법 지식베이스(KB) — 선언 데이터 전용(계산 로직 0).

unit_plan_generator(R3-1)가 산출하는 실 타일링(rooms)을 "실무 평면 도면"으로
격상하기 위한 문법 데이터: 실 타입별 요구사항(문·창·최소치수), 실간 경계 규칙
(open/wall_door — LDK 오픈플랜 관행), 벽 타입(두께·내력), 그리드 모듈, 치수 기준.

설계 원칙(절대 준수):
- **계산 로직 0.** 순수 데이터 + 이름→타입 조회 함수(room_type_of)만.
  경계 추출·문 배치 등 모든 계산은 unit_plan_generator의 엔진이 담당한다.
- **가짜값 금지.** 법정 기준이 없는 항목은 source='통상관행'·legal_basis=None으로
  정직 표기하고, 수치 미정의 항목은 None으로 남긴다(임의 추정치 기입 금지).
- 법령 근거 URL은 legal.legal_reference_registry.build_law_url(검증된 한글주소
  형식)로만 생성한다 — 읽기전용 import, 실패 시 url 필드 없이 텍스트만(할루시네이션
  링크 금지). registry 파일 자체는 수정하지 않는다.

좌표계 전제(unit_plan_generator와 동일): 원점=세대 북서 모서리, +x=동, +y=남,
남측(y=body_depth_m)=채광면.

IFC 후속 계약: BOUNDARY_SCHEMA / OPENING_SCHEMA 상수가 경계·개구 dict의 필드
계약을 고정한다. 후속 IFC 변환(IfcRelSpaceBoundary / IfcDoor / IfcWindow)은
이 스키마 키를 그대로 소비한다 — 키 추가는 additive만 허용, 개명·삭제 금지.
"""

from __future__ import annotations

import contextlib

# ── 법령 URL(읽기전용 — registry 검증 형식만, 실패 시 url 없이 텍스트) ──

try:
    from app.services.legal.legal_reference_registry import build_law_url as _build_law_url
except ImportError:  # registry 미가용 환경 — url 필드 없이 텍스트만(정직 폴백)
    _build_law_url = None


def _legal(law_name: str, article: str) -> dict:
    """법령 근거 레코드 1건 조립(문자열 조립 — 계산 로직 아님).

    url은 registry의 검증된 build_law_url로만 생성하며, 생성 불가 시
    url 키 자체를 생략한다(임의 URL 조립 금지).
    """
    rec: dict = {"law_name": law_name, "article": article}
    if _build_law_url is not None:
        # url 생성 실패 시 url 키 생략이 유일한 안전 폴백(임의 URL 조립 금지)
        with contextlib.suppress(Exception):
            rec["url"] = _build_law_url(law_name, article)
    return rec


# ── 비(非)법령 출처 헬퍼(additive) — 법령화 방지의 핵심 ────────────────────
# _legal()은 검증된 '한국 법령'에만 사용한다. 표준(KDS·NKBA)·실무가이드·통상관행·
# 논문 휴리스틱은 절대 _legal()로 감싸지 않고 아래 전용 헬퍼로 출처를 분리한다.
# 모든 레코드에 source_type(법령|표준|실무가이드|통상관행|논문)을 명시하고, 비법령
# 레코드는 is_legal=False를 강제한다(가짜 법령화·할루시네이션 링크 금지).


def _std(standard: str, clause: str) -> dict:
    """공인 표준(KDS·NKBA 등) 근거 1건(문자열 조립 — 계산 로직 아님).

    standard=표준 식별자(예: 'KDS 14 20 30', 'NKBA Kitchen'), clause=세부 조항.
    법령이 아니므로 url을 생성하지 않으며 is_legal=False를 부착한다.
    """
    return {
        "standard": standard, "clause": clause,
        "source_type": "표준", "is_legal": False,
    }


def _practice(note: str, *, source_type: str = "통상관행") -> dict:
    """실무가이드·통상관행 근거 1건. source_type ∈ {실무가이드, 통상관행}.

    법정·표준 근거가 아닌 실무 관행 수치(Neufert 등 가이드 포함)에 사용한다.
    """
    return {"note": note, "source_type": source_type, "is_legal": False}


def _paper(ref: str) -> dict:
    """논문 휴리스틱 근거 1건 — source='논문' 태그 강제, 법령화 절대 금지.

    ref=논문 식별자(arXiv ID/DOI 등). is_legal=False + source_type='논문'을
    불변으로 부착한다(생성 모델 학습/평가 휴리스틱을 법령으로 오인 방지).
    """
    return {"paper_ref": ref, "source_type": "논문", "is_legal": False}


# ── 전역 문법 상수 ──

# 평면 그리드 모듈(mm) — 문·창 배치 좌표는 이 모듈로 스냅한다(통상관행: 50mm).
GRID_MODULE_MM: int = 50

# 치수 기준 — 공동주택 전용면적은 안목치수(벽 내부선 기준)로 산정한다.
DIMENSION_MODE: str = "clear_inner"
DIMENSION_MODE_LEGAL_BASIS: dict = _legal("주택건설기준 등에 관한 규칙", "제3조")

# 문 호스트(진입 측 실) 우선순위 — 1실 1문 불변식에서 문이 면할 실을 고른다.
DOOR_HOST_PRIORITY: tuple[str, ...] = ("corridor", "living", "kitchen_dining")

# 채광·환기 법정 비율(거실·침실 등 거실(居室)) — 건축법 시행령 제51조,
# 세부 산정은 건축물의 피난·방화구조 등의 기준에 관한 규칙 제17조.
DAYLIGHT_WINDOW_AREA_RATIO_MIN: float = 1.0 / 10.0   # 창면적 ≥ 바닥면적 1/10
VENTILATION_AREA_RATIO_MIN: float = 1.0 / 20.0       # 환기면적 ≥ 바닥면적 1/20
_DAYLIGHT_BASIS: dict = _legal("건축법 시행령", "제51조")
_DAYLIGHT_NOTE = (
    "채광 창면적 ≥ 바닥면적 1/10, 환기 ≥ 1/20 — 건축법 시행령 제51조"
    "(세부: 건축물의 피난·방화구조 등의 기준에 관한 규칙 제17조)"
)

# ── 실 타입 KB ──
# 필드: min_area_sqm / min_width_m (None=법정·관행 최소치 미정의 — 가짜값 금지),
#        needs_door / door{width_mm,height_mm,swing,(fire_rated)},
#        needs_window / window{width_mm_min,width_mm_max,height_mm,
#                              area_ratio_min,vent_ratio_min},
#        wet(방수실), source('법령'|'LH기준'|'통상관행'), legal_basis(dict|None), note.

_BEDROOM_DOOR = {"width_mm": 900, "height_mm": 2100, "swing": "in"}
_BATH_DOOR = {"width_mm": 750, "height_mm": 2000, "swing": "in"}
_UTILITY_DOOR = {"width_mm": 750, "height_mm": 2000, "swing": "in"}
_ENTRY_DOOR = {"width_mm": 1000, "height_mm": 2100, "swing": "out", "fire_rated": True}
_DRESS_DOOR = {"width_mm": 800, "height_mm": 2100, "swing": "in"}

_LIVING_WINDOW = {
    "width_mm_min": 1500, "width_mm_max": 2400, "height_mm": 2200,
    "area_ratio_min": DAYLIGHT_WINDOW_AREA_RATIO_MIN,
    "vent_ratio_min": VENTILATION_AREA_RATIO_MIN,
}
_BEDROOM_WINDOW = {
    "width_mm_min": 1500, "width_mm_max": 2400, "height_mm": 1500,
    "area_ratio_min": DAYLIGHT_WINDOW_AREA_RATIO_MIN,
    "vent_ratio_min": VENTILATION_AREA_RATIO_MIN,
}

ROOM_TYPES: dict[str, dict] = {
    "entry": {
        "min_area_sqm": 1.2, "min_width_m": 1.0,
        "needs_door": True, "door": dict(_ENTRY_DOOR),
        "needs_window": False, "window": None, "wet": False,
        "source": "통상관행", "legal_basis": None,
        "furniture_clearance_ref": None,
        "note": "현관문 1000×2100 외여닫이(out)·방화문·세대당 1개(통상관행)",
    },
    "living": {
        "min_area_sqm": 9.0, "min_width_m": 2.4,
        "needs_door": False, "door": None,
        "needs_window": True, "window": dict(_LIVING_WINDOW), "wet": False,
        "source": "법령", "legal_basis": dict(_DAYLIGHT_BASIS),
        "furniture_clearance_ref": "furniture",
        "note": _DAYLIGHT_NOTE + " / LDK 오픈플랜 — 주방·복도와 벽 미설치(통상관행)",
    },
    "kitchen_dining": {
        "min_area_sqm": 4.5, "min_width_m": 1.8,
        "needs_door": False, "door": None,
        "needs_window": False, "window": None, "wet": True,
        "source": "통상관행", "legal_basis": None,
        "furniture_clearance_ref": "kitchen",
        "note": "LDK 오픈플랜 — 거실·복도와 개방 연결(통상관행)",
    },
    "bedroom": {
        "min_area_sqm": 6.0, "min_width_m": 2.1,
        "needs_door": True, "door": dict(_BEDROOM_DOOR),
        "needs_window": True, "window": dict(_BEDROOM_WINDOW), "wet": False,
        "source": "법령", "legal_basis": dict(_DAYLIGHT_BASIS),
        "furniture_clearance_ref": "furniture",
        "note": "침실문 900×2100 안여닫이(in) / " + _DAYLIGHT_NOTE,
    },
    "master_bedroom": {
        "min_area_sqm": 6.0, "min_width_m": 2.1,
        "needs_door": True, "door": dict(_BEDROOM_DOOR),
        "needs_window": True, "window": dict(_BEDROOM_WINDOW), "wet": False,
        "source": "법령", "legal_basis": dict(_DAYLIGHT_BASIS),
        "furniture_clearance_ref": "furniture",
        "note": "안방 — 침실문 900×2100 안여닫이(in) / " + _DAYLIGHT_NOTE,
    },
    "bath_common": {
        "min_area_sqm": 1.5, "min_width_m": 1.2,
        "needs_door": True, "door": dict(_BATH_DOOR),
        "needs_window": False, "window": None, "wet": True,
        "source": "통상관행", "legal_basis": None,
        "furniture_clearance_ref": "bath",
        "note": "공용욕실 — 욕실문 750×2000 안여닫이(in), 기계환기 가정(통상관행)",
    },
    "bath_master": {
        "min_area_sqm": 1.5, "min_width_m": 1.2,
        "needs_door": True, "door": dict(_BATH_DOOR),
        "needs_window": False, "window": None, "wet": True,
        "source": "통상관행", "legal_basis": None,
        "furniture_clearance_ref": "bath",
        "note": "부속욕실(안방 부속) — 욕실문 750×2000 안여닫이(in)(통상관행)",
    },
    "utility": {
        "min_area_sqm": None, "min_width_m": None,
        "needs_door": True, "door": dict(_UTILITY_DOOR),
        "needs_window": False, "window": None, "wet": True,
        "source": "통상관행", "legal_basis": None,
        "furniture_clearance_ref": None,
        "note": "다용도실 — 문 750 / 최소면적 법정 기준 없음(미정의 — 가짜값 금지)",
    },
    "corridor": {
        "min_area_sqm": None, "min_width_m": 0.9,
        "needs_door": False, "door": None,
        "needs_window": False, "window": None, "wet": False,
        "source": "통상관행", "legal_basis": None,
        "furniture_clearance_ref": "passage",
        "note": "세대 내 복도 — 유효폭 0.9m 관행, 거실·주방·현관과 개방 연결",
    },
    "dress": {
        "min_area_sqm": None, "min_width_m": 1.2,
        "needs_door": True, "door": dict(_DRESS_DOOR),
        "needs_window": False, "window": None, "wet": False,
        "source": "통상관행", "legal_basis": None,
        "furniture_clearance_ref": "furniture",
        "note": "드레스룸 — 안방 부속, 문 800×2100(통상관행)",
    },
    "balcony": {
        "min_area_sqm": None, "min_width_m": None,
        "needs_door": False, "door": None,
        "needs_window": False, "window": None, "wet": False,
        "source": "통상관행", "legal_basis": None,
        "furniture_clearance_ref": None,
        "note": "발코니(서비스면적, 전용 외) — 전면 분합창은 인접 거실·침실 개구로 표현",
    },
}

# ── 실명(한글) → 실 타입 매핑 ──
# UNIT_RULE_TABLE에 등장하는 실명 전수 + 발코니. '침실N'은 prefix 규칙으로 흡수.
# 미지명 실은 room_type_of가 None을 반환한다(침묵 폴백 금지 — 엔진이 경고 처리).

ROOM_NAME_MAP: dict[str, str] = {
    "현관": "entry",
    "거실": "living",
    "주방·식당": "kitchen_dining",
    "안방": "master_bedroom",
    "욕실": "bath_common",       # 욕실 1개 평형(49/59형 등)의 단일 욕실 = 공용욕실
    "공용욕실": "bath_common",
    "부속욕실": "bath_master",
    "다용도실": "utility",
    "복도": "corridor",
    "드레스룸": "dress",
    "발코니": "balcony",
}

_BEDROOM_NAME_PREFIX = "침실"


def room_type_of(name: object) -> str | None:
    """실명(한글) → 실 타입 ID 조회(순수 lookup — 계산 없음).

    '침실2'·'침실3' 등 '침실' prefix는 bedroom으로, '안방'은 master_bedroom으로.
    매핑에 없는 이름은 None(폴백 금지 — 호출부가 정직 경고 처리).
    """
    if not isinstance(name, str):
        return None
    key = name.strip()
    if key in ROOM_NAME_MAP:
        return ROOM_NAME_MAP[key]
    if key.startswith(_BEDROOM_NAME_PREFIX):
        return "bedroom"
    return None


# ── 실간 경계 규칙 ──
# key = frozenset({타입A, 타입B}), value = 'open'(벽 미설치 — LDK 오픈플랜) |
# 'wall_door'(벽+문). **여기 미정의 쌍은 엔진(classify_boundaries)이 'wall' 기본.**

BOUNDARY_RULES: dict[frozenset, str] = {
    # open 5쌍 — LDK 오픈플랜·동선 개방(통상관행)
    frozenset({"living", "kitchen_dining"}): "open",
    frozenset({"living", "corridor"}): "open",
    frozenset({"kitchen_dining", "corridor"}): "open",
    frozenset({"entry", "corridor"}): "open",
    frozenset({"entry", "living"}): "open",
    # wall_door 6쌍 — 구획+출입문
    frozenset({"bedroom", "corridor"}): "wall_door",
    frozenset({"master_bedroom", "corridor"}): "wall_door",
    frozenset({"bath_common", "corridor"}): "wall_door",
    frozenset({"bath_master", "master_bedroom"}): "wall_door",
    frozenset({"utility", "kitchen_dining"}): "wall_door",
    frozenset({"dress", "master_bedroom"}): "wall_door",
}

# 미정의 쌍 기본값(엔진 측 계약 — 데이터로 고정)
BOUNDARY_DEFAULT_KIND: str = "wall"

# wall_door 쌍의 문 소유실(문이 '들어가는' 실) — frozenset은 순서를 잃으므로
# 소유 타입을 명시 선언한다(1실 1문 불변식의 기준).
DOOR_OWNER_BY_PAIR: dict[frozenset, str] = {
    frozenset({"bedroom", "corridor"}): "bedroom",
    frozenset({"master_bedroom", "corridor"}): "master_bedroom",
    frozenset({"bath_common", "corridor"}): "bath_common",
    frozenset({"bath_master", "master_bedroom"}): "bath_master",
    frozenset({"utility", "kitchen_dining"}): "utility",
    frozenset({"dress", "master_bedroom"}): "dress",
}

# ── 벽 타입 KB ──
# 공동주택 세대간 경계벽·내력벽 두께 근거: 주택건설기준 등에 관한 규정 제14조(경계벽).
# 세대 내 칸막이벽 120mm는 법정 기준이 아닌 통상관행으로 정직 표기.

_PARTY_WALL_BASIS: dict = _legal("주택건설기준 등에 관한 규정", "제14조")

WALL_TYPES: dict[str, dict] = {
    "exterior": {
        "thickness_mm": 200, "bearing": True,
        "source": "법령", "legal_basis": dict(_PARTY_WALL_BASIS),
        "note": "외벽 — 내력 200mm(경계벽 기준 준용, 단열층 별도)",
    },
    "unit_party": {
        "thickness_mm": 200, "bearing": True,
        "source": "법령", "legal_basis": dict(_PARTY_WALL_BASIS),
        "note": "세대간 경계벽 — 철근콘크리트 200mm 이상(주택건설기준 등에 관한 규정 제14조)",
    },
    "core": {
        "thickness_mm": 200, "bearing": True,
        "source": "법령", "legal_basis": dict(_PARTY_WALL_BASIS),
        "note": "코어(계단실·승강로) 벽 — 내력 200mm(경계벽 기준 준용)",
    },
    "partition": {
        "thickness_mm": 120, "bearing": False,
        "source": "통상관행", "legal_basis": None,
        "note": "세대 내 칸막이벽 — 비내력 120mm(조적·경량벽 통상관행)",
    },
}

# ── 인접 선호 가중치 KB(additive·데이터 전용) ────────────────────────────────
# 출처: 건축 프로그래밍 통상관행(A1 — archisoup/BriefBuilder류 인접 매트릭스).
# 값 도메인: +2(필수 인접)~−2(필수 분리). 0(중립)은 미수록(미정의=중립으로 엔진 처리).
# 키는 frozenset[str]로 대칭 보장(거실-현관 == 현관-거실). 타입은 ROOM_TYPES 키만.
# 법령·표준 아님 — source_type='통상관행'(아래 메타). 판정·합산은 엔진(체커)이 담당.

ADJACENCY_WEIGHTS: dict[frozenset, int] = {
    frozenset({"living", "kitchen_dining"}): 2,    # LDK 강결합
    frozenset({"kitchen_dining", "utility"}): 2,   # 주방-다용도(서비스 동선)
    frozenset({"master_bedroom", "bath_master"}): 2,  # 안방존 전용욕 결합
    frozenset({"master_bedroom", "dress"}): 2,     # 안방존 드레스룸 결합
    frozenset({"living", "entry"}): 1,             # 거실-현관 근접 선호
    frozenset({"living", "corridor"}): 1,          # 거실-복도(분배 동선)
    frozenset({"bedroom", "corridor"}): 1,         # 침실-복도 접근
    frozenset({"living", "bath_common"}): -1,      # 거실-욕실 직접노출 회피
    frozenset({"bedroom", "kitchen_dining"}): -1,  # 침실-주방 소음·냄새 분리
    frozenset({"entry", "bath_common"}): -2,       # 현관-욕실 직접대면 필수분리
}

# 인접 선호 메타(출처 정직 표기 — 법령화 금지)
ADJACENCY_WEIGHTS_META: dict = _practice(
    "인접 선호행렬 +2(필수인접)~−2(필수분리) — 건축 프로그래밍 통상관행(A1). "
    "frozenset 키로 대칭, 0(중립)은 미수록.",
)

# 인접 판정 거리 임계(논문 휴리스틱) — dist < dist_ratio×planLength → 인접.
# source='논문' 태그 필수(R4). KB엔 임계값만, 그래프 판정 함수는 엔진.
ADJACENCY_DETECT: dict = {
    "dist_ratio": 0.03,
    **_paper("arXiv 2108.05947 / ScienceDirect 2023(인접 판정 거리 임계 0.03)"),
}

# ── 인체공학 클리어런스 KB(additive·데이터 전용, mm) ─────────────────────────
# 가구·기구 주변 여유. 표준(NKBA)·실무가이드(Neufert) 출처를 항목별로 정직 분리.
# ROOM_TYPES[*].furniture_clearance_ref가 아래 키(kitchen/bath/furniture/passage)를 참조.
# 판정(가구 수용·동선 관통)은 엔진(check_*) 담당 — 여기엔 수치만.

CLEARANCES: dict[str, dict] = {
    "kitchen": {
        "work_triangle": {
            "leg_min_mm": 1200, "leg_max_mm": 2700,
            "sum_max_mm": 6700, "no_traffic": True,
        },
        "aisle_mm": {
            "cook1": 1067, "cook2": 1219, "walkway": 914,
            "opposed_min": 1067, "opposed_max": 1219,
        },
        "landing_mm": {
            "sink": [610, 460], "fridge_handle": 380,
            "cooktop": 300, "builtin_cab_w": 918,
        },
        "source": _std("NKBA Kitchen", "G5·G6·G7(작업삼각형·통로·착지면)"),
    },
    "bath": {
        "wc_to_wall_mm": 380, "wc_to_wall_rec_mm": 460,
        "wc_front_mm": 530, "wc_front_rec_mm": 760,
        "dual_lav_mm": 760, "dual_lav_rec_mm": 910,
        "source": _std("NKBA Bathroom", "변기·세면 클리어런스(권장치 별도)"),
    },
    "furniture": {
        "dining_wall_mm": 750, "dining_wall_pass_mm": 1000,
        "dining_perimeter_mm": 900,
        "bed_access_mm": 700, "wardrobe_front_mm": 900,
        "source": _practice(
            "가구 클리어런스: 식탁-벽 750(통행1000)·식탁둘레 900·침대진입 700·"
            "옷장앞 900 — Neufert(N1)", source_type="실무가이드",
        ),
    },
    "passage": {
        "single_mm": 600, "standard_mm": 900,
        "two_min_mm": 1000, "two_max_mm": 1500,
        "unit_corridor_min_mm": 900, "unit_corridor_max_mm": 1200,
        "source": _practice(
            "통로/복도폭: 1인 600·표준 900·2인교행 1000~1500·세대내복도 900~1200 — "
            "Neufert·실무(N2)", source_type="실무가이드",
        ),
    },
}

# ── 구조 경간 KB(additive·데이터 전용) ───────────────────────────────────────
# 출처: KDS 14 20 30(슬래브·보 최소두께비, 표준) + RC/벽식 설계 통상관행.
# 보정계수(factor_fy/factor_lw)는 '식 표현 문자열'만 KB에 두고, 적용 계산은 엔진.
# 계산 로직 0 원칙 유지 — 비율·식·범위 데이터만.

STRUCTURE_SPANS: dict = {
    # 1방향 슬래브 최소두께비(처짐 검토 생략 가능 최소두께 = 경간×비율)
    "slab_min_ratio": {
        "simple": 1.0 / 20.0, "one_end": 1.0 / 24.0,
        "both": 1.0 / 28.0, "cantilever": 1.0 / 10.0,
    },
    # 보 최소춤비
    "beam_min_ratio": {
        "simple": 1.0 / 16.0, "one_end": 1.0 / 18.5,
        "both": 1.0 / 21.0, "cantilever": 1.0 / 8.0,
    },
    # 최소두께 보정계수 — '식'만 보관(엔진이 적용). fy≠400MPa·경량콘크리트 보정.
    "factor_fy": "0.43 + fy/700",                 # fy(MPa)
    "factor_lw": "max(1.65 - 0.00031*wc, 1.09)",  # wc=단위질량(kg/m^3)
    # 무량판 2방향 슬래브 — 통상 두께 범위(식 파라미터 β=장변/단변은 엔진 산정)
    "flat_plate_typ_mm": [250, 300],
    "flat_plate_thickness_formula": "ln*(0.8 + fy/1400) / (36 + 9*beta)",  # ln=순경간
    # RC 라멘 — 기둥 경간·부담면적(통상관행)
    "rc_frame": {
        "col_span_mm": [6000, 9000], "col_span_typ_mm": [6000, 7500],
        "tributary_sqm": 30, "warn_over_mm": 9000,
        **_practice("RC라멘 기둥경간 6~9m(typ 6~7.5)·부담면적≈30㎡(C1)"),
    },
    # 벽식 — 벽간격·벽두께(통상관행)
    "bearing_wall": {
        "spacing_max_mm": 6000, "thickness_mm": [200, 250], "no_beam": True,
        **_practice("벽식 벽간격≤6m·벽두께 200~250mm·무보(C2)"),
    },
    "source": _std("KDS 14 20 30", "표4.2-1(처짐 검토 생략 최소두께비·보정계수)"),
}

# ── 단면(층고·반자) 규칙 KB(additive·데이터 전용, mm) ────────────────────────
# 출처: 반자·층고 최소치는 한국 법령(주택건설기준 등에 관한 규정·주택법 시행규칙),
# 슬래브 두께·층고 적층·Blondel(계단)은 표준/관행. 법정 최소치만 _legal()로 근거 부착.
# 판정(반자≥2.2·층고≥2.4)은 엔진(check_ceiling_floor_height) 담당.

_SECTION_HEIGHT_BASIS: dict = _legal("주택건설기준 등에 관한 규정", "제3조")

SECTION_RULES: dict = {
    "ceiling_h_min_mm": 2200,   # 법정 반자높이 최소(거실)
    "ceiling_h_typ_mm": 2300,   # 통상 반자높이
    "floor_h_min_mm": 2400,     # 통상 층고 최소(반자+슬래브·설비)
    "floor_h_typ_mm": 2800,     # 통상 층고(공동주택)
    "floor_h_formula": "ceiling_h + slab_thickness + service_plenum",  # 층고 적층(엔진 산정)
    "slab_typ_mm": {"rahmen": [120, 150], "flat": [250, 300]},
    # 계단 Blondel 식: 2R + T = 600~635mm(R=챌판높이, T=디딤판폭) — 관행
    "stair_blondel_mm": {"two_r_plus_t_min": 600, "two_r_plus_t_max": 635},
    "ceiling_floor_legal_basis": dict(_SECTION_HEIGHT_BASIS),
    "stair_source": _practice("계단 Blondel 2R+T=600~635mm(보행 편의 관행)"),
    "source": _std("KDS(슬래브 두께)", "법정 반자·층고는 ceiling_floor_legal_basis 참조"),
}

# ── 주차 모듈 KB(additive·데이터 전용, mm) ───────────────────────────────────
# 주차구획·차로폭 치수는 주차장법 시행규칙 제3조(검증된 한국 법령) → _legal() 근거.
# 세대당 주차대수(0.7~1.0)는 주차장법 시행령 별표1·지자체 조례로 변동 → 통상관행 표기
# (지역·용도별 상이 — 단일 법정값 없음, 가짜 법령화 금지).

_PARKING_DIM_BASIS: dict = _legal("주차장법 시행규칙", "제3조")

PARKING_MODULE: dict = {
    "stall_mm": {"w": 2500, "l": 5000},          # 일반형 주차구획(법령)
    "stall_expanded_mm": {"w": 2600, "l": 5200},  # 확장형 주차구획(법령)
    "aisle_mm": {"right_angle": 6000},            # 직각주차 차로폭(법령)
    "stall_legal_basis": dict(_PARKING_DIM_BASIS),
    # 세대당 대수는 지역·조례별 변동 — 단일 법정값 없음(정직 표기)
    "units_per_household": [0.7, 1.0],
    "units_per_household_meta": _practice(
        "세대당 주차대수 0.7~1.0 — 지역·용도·지자체 조례별 상이(주차장법 시행령 별표1 위임). "
        "단일 법정값 없음(가짜 법령화 금지).",
    ),
    "source_note": "구획·차로 치수=주차장법 시행규칙 제3조(법령) / 세대당 대수=조례 변동(관행)",
}


# ── 경계/개구 dict 필드 계약(IFC 후속 변환이 그대로 소비 — additive만 허용) ──

BOUNDARY_SCHEMA: dict[str, str] = {
    "id": "경계 ID 'b###' — extract_boundaries 결정론 정렬 후 부여(IfcRelSpaceBoundary 근원)",
    "room_a": "실명(한글). 내부 경계는 북/서측 실, 외기 경계는 해당 실",
    "room_b": "실명(한글) | None(외기 경계)",
    "side": "내부: room_a→room_b 방향('s'|'e') / 외기: 외기면 방위('n'|'s'|'e'|'w', 남=채광면)",
    "orient": "'h'(수평 변 — 동서 방향) | 'v'(수직 변 — 남북 방향)",
    "x1,y1,x2,y2": "변 양끝 좌표(m, 원점=북서, +x=동, +y=남, x1<=x2, y1<=y2)",
    "length_m": "변 길이(m)",
    "balcony_front": "bool — 남측 발코니 전면 변(분합창 대상)",
    "kind": "classify_boundaries 부여: 'open'|'wall'|'wall_door'",
    "wall_type": "classify_boundaries 부여: WALL_TYPES 키('exterior'|'partition'…) | None(open)",
    "door_owner": "kind='wall_door'일 때 문 소유 실명(한글) | None",
}

OPENING_SCHEMA: dict[str, str] = {
    "id": "개구 ID 'd##'(문)/'w##'(창) — 결정론 정렬 후 부여(IfcDoor/IfcWindow 근원)",
    "kind": "'door' | 'window'",
    "subtype": "'swing'(여닫이문)|'entrance'(현관 방화문)|'window'(창)|'balcony_sliding'(분합창)",
    "boundary_id": "소속 경계 ID(BOUNDARY_SCHEMA.id)",
    "room": "개구 소유 실명(문=문이 들어가는 실, 창=채광 대상 실)",
    "host": "진입측 실명(한글) | None(외기 개구)",
    "orient": "'h'|'v' — 소속 경계와 동일",
    "center_x_m,center_y_m": "개구 중심 좌표(m) — 벽 진행축 좌표는 GRID_MODULE_MM 스냅",
    "width_mm,height_mm": "개구 폭·높이(mm)",
    "swing": "'in'|'out'|None(창)",
    "swing_side": "문짝이 열리는 방향('n'|'s'|'e'|'w')|None(창)",
    "hinge": "'start'(변 시작측 — 좌표 작은 끝)|None(창)",
    "fire_rated": "bool — 방화문 여부",
}
