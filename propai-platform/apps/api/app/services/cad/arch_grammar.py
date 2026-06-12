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
        "note": "현관문 1000×2100 외여닫이(out)·방화문·세대당 1개(통상관행)",
    },
    "living": {
        "min_area_sqm": 9.0, "min_width_m": 2.4,
        "needs_door": False, "door": None,
        "needs_window": True, "window": dict(_LIVING_WINDOW), "wet": False,
        "source": "법령", "legal_basis": dict(_DAYLIGHT_BASIS),
        "note": _DAYLIGHT_NOTE + " / LDK 오픈플랜 — 주방·복도와 벽 미설치(통상관행)",
    },
    "kitchen_dining": {
        "min_area_sqm": 4.5, "min_width_m": 1.8,
        "needs_door": False, "door": None,
        "needs_window": False, "window": None, "wet": True,
        "source": "통상관행", "legal_basis": None,
        "note": "LDK 오픈플랜 — 거실·복도와 개방 연결(통상관행)",
    },
    "bedroom": {
        "min_area_sqm": 6.0, "min_width_m": 2.1,
        "needs_door": True, "door": dict(_BEDROOM_DOOR),
        "needs_window": True, "window": dict(_BEDROOM_WINDOW), "wet": False,
        "source": "법령", "legal_basis": dict(_DAYLIGHT_BASIS),
        "note": "침실문 900×2100 안여닫이(in) / " + _DAYLIGHT_NOTE,
    },
    "master_bedroom": {
        "min_area_sqm": 6.0, "min_width_m": 2.1,
        "needs_door": True, "door": dict(_BEDROOM_DOOR),
        "needs_window": True, "window": dict(_BEDROOM_WINDOW), "wet": False,
        "source": "법령", "legal_basis": dict(_DAYLIGHT_BASIS),
        "note": "안방 — 침실문 900×2100 안여닫이(in) / " + _DAYLIGHT_NOTE,
    },
    "bath_common": {
        "min_area_sqm": 1.5, "min_width_m": 1.2,
        "needs_door": True, "door": dict(_BATH_DOOR),
        "needs_window": False, "window": None, "wet": True,
        "source": "통상관행", "legal_basis": None,
        "note": "공용욕실 — 욕실문 750×2000 안여닫이(in), 기계환기 가정(통상관행)",
    },
    "bath_master": {
        "min_area_sqm": 1.5, "min_width_m": 1.2,
        "needs_door": True, "door": dict(_BATH_DOOR),
        "needs_window": False, "window": None, "wet": True,
        "source": "통상관행", "legal_basis": None,
        "note": "부속욕실(안방 부속) — 욕실문 750×2000 안여닫이(in)(통상관행)",
    },
    "utility": {
        "min_area_sqm": None, "min_width_m": None,
        "needs_door": True, "door": dict(_UTILITY_DOOR),
        "needs_window": False, "window": None, "wet": True,
        "source": "통상관행", "legal_basis": None,
        "note": "다용도실 — 문 750 / 최소면적 법정 기준 없음(미정의 — 가짜값 금지)",
    },
    "corridor": {
        "min_area_sqm": None, "min_width_m": 0.9,
        "needs_door": False, "door": None,
        "needs_window": False, "window": None, "wet": False,
        "source": "통상관행", "legal_basis": None,
        "note": "세대 내 복도 — 유효폭 0.9m 관행, 거실·주방·현관과 개방 연결",
    },
    "dress": {
        "min_area_sqm": None, "min_width_m": 1.2,
        "needs_door": True, "door": dict(_DRESS_DOOR),
        "needs_window": False, "window": None, "wet": False,
        "source": "통상관행", "legal_basis": None,
        "note": "드레스룸 — 안방 부속, 문 800×2100(통상관행)",
    },
    "balcony": {
        "min_area_sqm": None, "min_width_m": None,
        "needs_door": False, "door": None,
        "needs_window": False, "window": None, "wet": False,
        "source": "통상관행", "legal_basis": None,
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
