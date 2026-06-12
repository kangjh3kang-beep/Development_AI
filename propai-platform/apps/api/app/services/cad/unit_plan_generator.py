"""결정론 유닛플랜 생성기(R3-1 MVP) — 단위세대 평면(실 배치) 사각 분할 룰 테이블.

설계 철학(기존 커널 패턴 유지 — design_spec.py 참조):
  LLM은 의도(평형·베이수·코어타입) 파싱만 담당하고, 실 좌표·치수는 본 모듈이
  순수 결정론으로 산출한다(동일 입력 = 동일 출력, LLM·외부호출 0).
  LH/SH 표준평면류의 '공지된 치수 관행'(베이폭·깊이 비율·실 구성 — 예: 84형 3베이
  = 남측 침실·거실·안방 + 북측 주방·침실, 방3 욕2)을 룰 테이블로 코드화한 것이며
  특정 도면의 복제가 아니다.

좌표계(단위 m, 소수 3자리 = mm 정밀도):
  원점(0,0) = 세대 북서측 모서리, +x = 동(우), +y = 남(하).
  남측 채광면 = y = body_depth_m, 북측 외기면 = y = 0.
  판상형 가정 — 동·서면은 세대간 벽(외기면 아님).

밴드 분할(북→남): [북측 클러스터(현관·주방·욕실·침실)] [중간 띠(복도·부속욕실)]
[남측 채광 베이(거실·침실)]. rooms는 본체(W×D)를 빈틈없이 타일링하므로
Σ실면적 = 전용면적(반올림 오차 ≤ 수 cm²).

검증(채광: 거실·침실 외기면 접함 / 최소 실면적 / 침실 최소폭) 위반은
violations 리스트로 정직 반환한다 — 가짜 통과 금지.

경계 엔진(additive — arch_grammar KB 소비):
  extract_boundaries(타일링→실간 공유변·외기변) → classify_boundaries(open/wall/
  wall_door + 1실 1문 불변식) → place_openings(문·창 50mm 그리드 배치) →
  validate_connectivity(현관 기점 BFS). 결과는 UnitPlanResult.boundaries /
  openings / grammar_warnings 에 **additive**로 실린다 — 기존 rooms·violations
  계약(키·값·정답 테스트) 불변.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import structlog

from .arch_grammar import (
    BOUNDARY_DEFAULT_KIND,
    BOUNDARY_RULES,
    DOOR_HOST_PRIORITY,
    DOOR_OWNER_BY_PAIR,
    GRID_MODULE_MM,
    ROOM_TYPES,
    room_type_of,
)

logger = structlog.get_logger(__name__)

# ── 문법 상수(DesignSpec.unit_grammar와 공유) ──

SUPPORTED_BAYS: tuple[int, ...] = (2, 3, 4)
UNIT_CORE_TYPES: tuple[str, ...] = ("계단실형", "복도형", "타워형")

# 발코니(서비스면적) 표준 깊이 — 남측 전면 발코니 1.5m 관행
BALCONY_DEPTH_M = 1.5

# 전용면적 허용 범위(㎡) — 범위 밖이면 명시 오류(가짜 생성 금지)
MIN_UNIT_AREA_SQM = 20.0
MAX_UNIT_AREA_SQM = 250.0

# ── 검증 룰(건축 관행 최소치) ──

MIN_LIVING_AREA_SQM = 9.0    # 거실
MIN_BEDROOM_AREA_SQM = 6.0   # 침실(안방 포함)
MIN_BATH_AREA_SQM = 1.5      # 욕실(공용·부속)
MIN_KITCHEN_AREA_SQM = 4.5   # 주방·식당
MIN_ENTRY_AREA_SQM = 1.2     # 현관
MIN_BEDROOM_WIDTH_M = 2.1    # 침실 최소 단변

_MM = 3  # 좌표 반올림 자릿수(m 소수 3자리 = mm 정밀도)
_EPS = 1e-6


@dataclass(frozen=True)
class UnitRuleRow:
    """평형대×베이수 1개 조합의 사각 분할 룰(치수 관행 코드화).

    south: 남측 채광 베이 (실명, 폭m) — 폭 합 = 본체 전면폭 W
    north: 북측 클러스터 (실명, W 대비 폭 비율) — 마지막 실은 잔여폭으로 보정
    mid:   중간 띠 (실명, 폭m | None=잔여폭) — 복도·부속욕실 등(외기면 없음 허용)
    north_depth_frac / mid_depth_frac: 본체 깊이 D 대비 띠 깊이 비율
    """

    south: tuple[tuple[str, float], ...]
    north: tuple[tuple[str, float], ...]
    mid: tuple[tuple[str, float | None], ...]
    north_depth_frac: float = 0.36
    mid_depth_frac: float = 0.15


# ── 룰 테이블: (평형 밴드, 베이수) → 분할 룰 ──
# 폭 치수는 국내 공동주택 보편 관행 수준(거실 3.6~4.5m, 안방 3.0~3.9m, 침실 ≥2.7m).

UNIT_RULE_TABLE: dict[tuple[str, int], UnitRuleRow] = {
    # 49형(소형, 방2·욕1)
    ("49", 2): UnitRuleRow(
        south=(("거실", 3.6), ("안방", 3.0)),
        north=(("침실2", 0.36), ("주방·식당", 0.42), ("욕실", 0.22)),
        mid=(("현관", 1.5), ("복도", None)),
    ),
    ("49", 3): UnitRuleRow(
        south=(("침실2", 2.7), ("거실", 3.6), ("안방", 3.0)),
        north=(("현관", 0.16), ("주방·식당", 0.48), ("욕실", 0.17), ("다용도실", 0.19)),
        mid=(("복도", None),),
        north_depth_frac=0.38, mid_depth_frac=0.14,
    ),
    # 59형(2베이=방2·욕1 / 3베이=방3·욕2 / 4베이=방3·욕1)
    ("59", 2): UnitRuleRow(
        south=(("거실", 3.9), ("안방", 3.3)),
        north=(("침실2", 0.34), ("주방·식당", 0.44), ("욕실", 0.22)),
        mid=(("현관", 1.5), ("복도", None)),
    ),
    ("59", 3): UnitRuleRow(
        south=(("침실2", 3.0), ("거실", 3.9), ("안방", 3.3)),
        north=(("현관", 0.15), ("주방·식당", 0.40), ("공용욕실", 0.17), ("침실3", 0.28)),
        mid=(("복도", None), ("부속욕실", 1.8)),
        north_depth_frac=0.38, mid_depth_frac=0.15,
    ),
    ("59", 4): UnitRuleRow(
        south=(("침실2", 2.7), ("거실", 4.2), ("안방", 3.0), ("침실3", 2.7)),
        north=(("현관", 0.14), ("주방·식당", 0.42), ("욕실", 0.15), ("다용도실", 0.29)),
        mid=(("복도", None),),
        north_depth_frac=0.34, mid_depth_frac=0.14,
    ),
    # 74형(방3·욕2)
    ("74", 2): UnitRuleRow(
        south=(("거실", 4.0), ("안방", 3.4)),
        north=(("침실2", 0.29), ("침실3", 0.29), ("주방·식당", 0.27), ("현관", 0.15)),
        mid=(("복도", None), ("공용욕실", 2.1), ("부속욕실", 1.8)),
    ),
    ("74", 3): UnitRuleRow(
        south=(("침실2", 3.0), ("거실", 4.0), ("안방", 3.4)),
        north=(("현관", 0.14), ("주방·식당", 0.38), ("공용욕실", 0.17), ("침실3", 0.31)),
        mid=(("복도", None), ("부속욕실", 1.8)),
    ),
    ("74", 4): UnitRuleRow(
        south=(("침실2", 2.85), ("거실", 4.0), ("안방", 3.2), ("침실3", 2.85)),
        north=(("현관", 0.13), ("주방·식당", 0.45), ("공용욕실", 0.15), ("다용도실", 0.27)),
        mid=(("복도", None), ("부속욕실", 1.8)),
        north_depth_frac=0.34, mid_depth_frac=0.15,
    ),
    # 84형(국민평형, 방3·욕2) — 3베이가 가장 보편
    ("84", 2): UnitRuleRow(
        south=(("거실", 4.2), ("안방", 3.6)),
        north=(("침실2", 0.27), ("침실3", 0.27), ("주방·식당", 0.30), ("현관", 0.16)),
        mid=(("복도", None), ("공용욕실", 2.1), ("부속욕실", 1.8)),
    ),
    ("84", 3): UnitRuleRow(
        south=(("침실2", 3.0), ("거실", 4.2), ("안방", 3.6)),
        north=(("현관", 0.14), ("주방·식당", 0.38), ("공용욕실", 0.17), ("침실3", 0.31)),
        mid=(("복도", None), ("부속욕실", 1.8)),
    ),
    ("84", 4): UnitRuleRow(
        south=(("침실2", 3.0), ("거실", 4.2), ("안방", 3.6), ("침실3", 3.0)),
        north=(("현관", 0.13), ("주방·식당", 0.47), ("공용욕실", 0.14), ("다용도실", 0.26)),
        mid=(("복도", None), ("부속욕실", 1.8)),
    ),
    # 114형(중대형, 방4·욕2)
    ("114", 3): UnitRuleRow(
        south=(("침실2", 3.3), ("거실", 4.5), ("안방", 3.9)),
        north=(("현관", 0.13), ("주방·식당", 0.37), ("공용욕실", 0.16), ("침실3", 0.34)),
        mid=(("복도", None), ("드레스룸", 2.4), ("부속욕실", 2.1)),
    ),
    ("114", 4): UnitRuleRow(
        south=(("침실2", 3.3), ("거실", 4.5), ("안방", 3.9), ("침실3", 3.3)),
        north=(("현관", 0.12), ("주방·식당", 0.40), ("공용욕실", 0.13), ("침실4", 0.22),
               ("다용도실", 0.13)),
        mid=(("복도", None), ("부속욕실", 2.1)),
        north_depth_frac=0.35, mid_depth_frac=0.15,
    ),
}


@dataclass
class UnitPlanResult:
    """결정론 유닛플랜 산출 결과(검증 포함)."""

    unit_area_sqm: float            # 입력 전용면적
    band: str                       # 적용 룰 밴드("49"/"59"/"74"/"84"/"114")
    bays: int
    core_type: str
    balcony_extension: bool
    body_width_m: float             # 본체 전면폭 W
    body_depth_m: float             # 본체 깊이 D (= 전용면적/W)
    rooms: list[dict[str, Any]] = field(default_factory=list)      # [{name,x,y,w,h}] (m)
    balconies: list[dict[str, Any]] = field(default_factory=list)  # 서비스면적(전용 외)
    exclusive_area_sqm: float = 0.0  # Σ rooms 면적(전용면적 검증값)
    service_area_sqm: float = 0.0    # Σ 발코니 면적
    violations: list[dict[str, Any]] = field(default_factory=list)
    # ── 경계 엔진 산출(additive — arch_grammar BOUNDARY_SCHEMA/OPENING_SCHEMA) ──
    boundaries: list[dict[str, Any]] = field(default_factory=list)
    openings: list[dict[str, Any]] = field(default_factory=list)
    # 문법 경고(1실 1문 승격·미등록 실명·연결성 미도달 등) — 기존 violations와
    # 분리해 정직 보고(기존 정답 테스트의 violations==[] 계약 무파손).
    grammar_warnings: list[dict[str, Any]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.violations

    def as_dict(self) -> dict[str, Any]:
        return {
            "unit_area_sqm": self.unit_area_sqm,
            "band": self.band,
            "bays": self.bays,
            "core_type": self.core_type,
            "balcony_extension": self.balcony_extension,
            "body_width_m": self.body_width_m,
            "body_depth_m": self.body_depth_m,
            "rooms": self.rooms,
            "balconies": self.balconies,
            "exclusive_area_sqm": self.exclusive_area_sqm,
            "service_area_sqm": self.service_area_sqm,
            "violations": self.violations,
            "boundaries": self.boundaries,
            "openings": self.openings,
            "grammar_warnings": self.grammar_warnings,
        }


# ── 내부 헬퍼 ──

def _band_for(area_sqm: float) -> str:
    """전용면적 → 룰 밴드 매핑(경계는 국내 분양 평형 관행)."""
    if area_sqm < 52.0:
        return "49"
    if area_sqm < 67.0:
        return "59"
    if area_sqm < 79.0:
        return "74"
    if area_sqm < 100.0:
        return "84"
    return "114"


def _is_bedroom(name: str) -> bool:
    return name == "안방" or name.startswith("침실")


def _is_daylight_room(name: str) -> bool:
    """채광 의무실 — 거실·침실은 외기면(북/남)에 접해야 한다."""
    return name == "거실" or _is_bedroom(name)


def _min_area_for(name: str) -> float | None:
    if name == "거실":
        return MIN_LIVING_AREA_SQM
    if _is_bedroom(name):
        return MIN_BEDROOM_AREA_SQM
    if "욕실" in name:
        return MIN_BATH_AREA_SQM
    if name.startswith("주방"):
        return MIN_KITCHEN_AREA_SQM
    if name == "현관":
        return MIN_ENTRY_AREA_SQM
    return None


def _r(v: float) -> float:
    return round(v, _MM)


# ── 검증(가짜 통과 금지 — 위반 목록 정직 반환) ──

def validate_unit_layout(
    rooms: list[dict[str, Any]],
    body_width_m: float,
    body_depth_m: float,
) -> list[dict[str, Any]]:
    """채광·최소 실면적·침실 최소폭·면적 정합 검증.

    위반은 design_spec.Violation 호환 dict 형태로 반환한다
    ({field, rule, legal, actual, message}).
    """
    out: list[dict[str, Any]] = []
    total = 0.0
    for r in rooms:
        name = str(r["name"])
        w = float(r["w"])
        h = float(r["h"])
        area = w * h
        total += area

        # 1) 채광: 거실·침실은 북(y=0) 또는 남(y+h=D) 외기면 접촉
        if _is_daylight_room(name):
            touches = float(r["y"]) <= 1e-3 or (float(r["y"]) + h) >= body_depth_m - 1e-3
            if not touches:
                out.append({
                    "field": name, "rule": "채광(외기면 접함)",
                    "legal": "북측 또는 남측 외기면 접촉", "actual": "내부 배치",
                    "message": f"{name}이(가) 외기면에 접하지 않습니다(채광 불가).",
                })

        # 2) 최소 실면적
        min_a = _min_area_for(name)
        if min_a is not None and area < min_a - _EPS:
            out.append({
                "field": name, "rule": "최소 실면적",
                "legal": min_a, "actual": round(area, 2),
                "message": f"{name} 면적 {area:.2f}㎡ < 최소 {min_a}㎡",
            })

        # 3) 침실 최소 단변(가구 배치 관행)
        if _is_bedroom(name) and min(w, h) < MIN_BEDROOM_WIDTH_M - _EPS:
            out.append({
                "field": name, "rule": "침실 최소폭",
                "legal": MIN_BEDROOM_WIDTH_M, "actual": round(min(w, h), 3),
                "message": f"{name} 단변 {min(w, h):.2f}m < 최소 {MIN_BEDROOM_WIDTH_M}m",
            })

    # 4) 면적 정합: Σ실면적 = 본체면적(타일링 깨짐 감지)
    body_area = body_width_m * body_depth_m
    if abs(total - body_area) > 0.05:
        out.append({
            "field": "rooms", "rule": "면적 정합",
            "legal": round(body_area, 2), "actual": round(total, 2),
            "message": f"실면적 합 {total:.2f}㎡ ≠ 본체면적 {body_area:.2f}㎡ (타일링 오류)",
        })
    return out


# ── 경계 엔진(additive — arch_grammar KB 소비, 기존 계약 불변) ──

_GRID_M = GRID_MODULE_MM / 1000.0
_OPPOSITE_SIDE = {"n": "s", "s": "n", "e": "w", "w": "e"}
_ENTRY_SIDE_PRIORITY: tuple[str, ...] = ("n", "w", "e")   # 현관문: 북>서>동(남=채광면 배제)
_WINDOW_SIDE_PRIORITY: tuple[str, ...] = ("s", "n", "e", "w")  # 창: 남(채광면) 우선
_WINDOW_END_CLEAR_MM = 300.0  # 창 양측 벽 되돌림(통상관행)


def _snap_grid_m(v_m: float) -> float:
    """벽 진행축 좌표를 GRID_MODULE_MM(50mm) 그리드로 스냅(m, mm 정밀 반올림)."""
    return _r(round(v_m / _GRID_M) * _GRID_M)


def extract_boundaries(
    rooms: list[dict[str, Any]],
    body_w: float,
    body_d: float,
    tol: float = 1e-3,
    balconies: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """축정렬 타일링(rooms)에서 실간 공유변·외기변을 추출한다(결정론).

    내부 공유변: 마주보는 변 좌표 일치(±tol) + 구간 겹침(>tol).
      room_a = 북/서측 실, room_b = 남/동측 실, side = a→b 방향('s'|'e').
    외기변: 본체 외곽(x=0/W, y=0/D)에 접한 실 변. room_b=None,
      side = 방위('n'|'s'|'e'|'w', 남=채광면).
    balcony_front: 남측 외기변이 발코니 x구간과 겹치면 True(분합창 대상).

    반환: BOUNDARY_SCHEMA(arch_grammar) dict 리스트 — (y1,x1,y2,x2,orient,실명)
    결정론 정렬 후 id('b###') 부여. kind/wall_type은 classify_boundaries가 부여.
    """
    raw: list[dict[str, Any]] = []
    rects = [
        (str(r["name"]), float(r["x"]), float(r["y"]), float(r["w"]), float(r["h"]))
        for r in rooms
    ]

    # 1) 내부 공유변 — a가 북/서측일 때만 기록(쌍당 1회)
    for i, (an, ax, ay, aw, ah) in enumerate(rects):
        for j, (bn, bx, by, bw, bh) in enumerate(rects):
            if i == j:
                continue
            # 수직 공유변: a 동측변 == b 서측변
            if abs((ax + aw) - bx) <= tol:
                y1 = max(ay, by)
                y2 = min(ay + ah, by + bh)
                if y2 - y1 > tol:
                    x_line = _r(((ax + aw) + bx) / 2.0)
                    raw.append({
                        "room_a": an, "room_b": bn, "side": "e", "orient": "v",
                        "x1": x_line, "y1": _r(y1), "x2": x_line, "y2": _r(y2),
                        "length_m": _r(y2 - y1), "balcony_front": False,
                    })
            # 수평 공유변: a 남측변 == b 북측변
            if abs((ay + ah) - by) <= tol:
                x1 = max(ax, bx)
                x2 = min(ax + aw, bx + bw)
                if x2 - x1 > tol:
                    y_line = _r(((ay + ah) + by) / 2.0)
                    raw.append({
                        "room_a": an, "room_b": bn, "side": "s", "orient": "h",
                        "x1": _r(x1), "y1": y_line, "x2": _r(x2), "y2": y_line,
                        "length_m": _r(x2 - x1), "balcony_front": False,
                    })

    # 2) 외기변 — 본체 외곽 접변(실별 분리)
    bal = list(balconies or [])

    def _balcony_overlaps(x1: float, x2: float) -> bool:
        for b in bal:
            b1 = float(b.get("x") or 0.0)
            b2 = b1 + float(b.get("w") or 0.0)
            if min(x2, b2) - max(x1, b1) > tol:
                return True
        return False

    for name, x, y, w, h in rects:
        if y <= tol:  # 북측 외기
            raw.append({
                "room_a": name, "room_b": None, "side": "n", "orient": "h",
                "x1": _r(x), "y1": 0.0, "x2": _r(x + w), "y2": 0.0,
                "length_m": _r(w), "balcony_front": False,
            })
        if y + h >= body_d - tol:  # 남측 외기(채광면)
            raw.append({
                "room_a": name, "room_b": None, "side": "s", "orient": "h",
                "x1": _r(x), "y1": _r(body_d), "x2": _r(x + w), "y2": _r(body_d),
                "length_m": _r(w), "balcony_front": _balcony_overlaps(x, x + w),
            })
        if x <= tol:  # 서측 외기
            raw.append({
                "room_a": name, "room_b": None, "side": "w", "orient": "v",
                "x1": 0.0, "y1": _r(y), "x2": 0.0, "y2": _r(y + h),
                "length_m": _r(h), "balcony_front": False,
            })
        if x + w >= body_w - tol:  # 동측 외기
            raw.append({
                "room_a": name, "room_b": None, "side": "e", "orient": "v",
                "x1": _r(body_w), "y1": _r(y), "x2": _r(body_w), "y2": _r(y + h),
                "length_m": _r(h), "balcony_front": False,
            })

    # 3) 결정론 정렬 + id 부여
    raw.sort(key=lambda b: (
        b["y1"], b["x1"], b["y2"], b["x2"], b["orient"],
        b["room_a"], b["room_b"] or "",
    ))
    for k, b in enumerate(raw, start=1):
        b["id"] = f"b{k:03d}"
    return raw


def classify_boundaries(
    boundaries: list[dict[str, Any]],
    rooms: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """경계 분류(BOUNDARY_RULES) + 1실 1문 불변식. (classified, warnings) 반환.

    - 외기변: kind='wall', wall_type='exterior'.
    - 내부변: room_type_of → BOUNDARY_RULES(open/wall_door), 미정의 쌍은 wall 기본.
      미등록 실명은 wall 처리 + 정직 경고(침묵 폴백 금지).
    - 1실 1문: needs_door 실(현관 제외 — 현관문은 외기변)의 wall_door 후보를
      DOOR_HOST_PRIORITY로 1개 확정. 과잉은 wall 강등, 0개면 내부 wall 경계를
      승격 + 경고(승격 불가 시 미배치 경고).
    입력 boundaries는 변경하지 않는다(사본 반환).
    """
    warnings: list[dict[str, Any]] = []
    out: list[dict[str, Any]] = []

    for b in boundaries:
        c = dict(b)
        if c.get("room_b") is None:
            c["kind"] = "wall"
            c["wall_type"] = "exterior"
            c["door_owner"] = None
            out.append(c)
            continue
        ta = room_type_of(c["room_a"])
        tb = room_type_of(c["room_b"])
        if ta is None or tb is None:
            unknown = c["room_a"] if ta is None else c["room_b"]
            c["kind"] = BOUNDARY_DEFAULT_KIND
            c["wall_type"] = "partition"
            c["door_owner"] = None
            warnings.append({
                "field": str(unknown), "rule": "실명 매핑",
                "legal": "arch_grammar.ROOM_NAME_MAP 등록 실명", "actual": str(unknown),
                "message": (
                    f"미등록 실명 '{unknown}' — 경계 {c['id']}을(를) wall로 두고"
                    " 경고합니다(침묵 폴백 금지)."
                ),
            })
            out.append(c)
            continue
        pair = frozenset({ta, tb})
        kind = BOUNDARY_RULES.get(pair, BOUNDARY_DEFAULT_KIND)
        c["kind"] = kind
        c["wall_type"] = None if kind == "open" else "partition"
        if kind == "wall_door":
            owner_type = DOOR_OWNER_BY_PAIR.get(pair)
            c["door_owner"] = c["room_a"] if ta == owner_type else c["room_b"]
        else:
            c["door_owner"] = None
        out.append(c)

    # ── 1실 1문 불변식 ──
    host_rank = {t: i for i, t in enumerate(DOOR_HOST_PRIORITY)}
    rank_max = len(DOOR_HOST_PRIORITY)

    def _host_of(c: dict[str, Any], owner_name: str) -> str:
        return str(c["room_b"] if c["room_a"] == owner_name else c["room_a"])

    def _rank(c: dict[str, Any], owner_name: str) -> tuple:
        h = room_type_of(_host_of(c, owner_name))
        return (host_rank.get(h, rank_max), c["id"])

    for room in rooms:
        name = str(room["name"])
        rtype = room_type_of(name)
        if rtype is None or rtype == "entry":
            continue  # 현관문은 외기변(place_openings 담당)
        spec = ROOM_TYPES.get(rtype) or {}
        if not spec.get("needs_door"):
            continue
        door_w_m = float((spec.get("door") or {}).get("width_mm", 900)) / 1000.0
        cands = [c for c in out if c["kind"] == "wall_door" and c.get("door_owner") == name]
        if len(cands) > 1:  # 과잉 → 우선순위 1개만 유지, 나머지 wall 강등
            cands.sort(key=lambda c: _rank(c, name))
            for c in cands[1:]:
                c["kind"] = "wall"
                c["door_owner"] = None
        elif not cands:  # 0개 → 내부 wall 경계 승격 + 경고
            promotable = [
                c for c in out
                if c["kind"] == "wall" and c.get("room_b") is not None
                and name in (c["room_a"], c["room_b"])
                and c["length_m"] >= door_w_m + 0.1
            ]
            if promotable:
                promotable.sort(key=lambda c: (
                    host_rank.get(room_type_of(_host_of(c, name)), rank_max),
                    -float(c["length_m"]), c["id"],
                ))
                chosen = promotable[0]
                chosen["kind"] = "wall_door"
                chosen["door_owner"] = name
                warnings.append({
                    "field": name, "rule": "1실 1문",
                    "legal": "needs_door 실은 출입문 1개",
                    "actual": f"BOUNDARY_RULES 후보 0 → {chosen['id']} 승격",
                    "message": (
                        f"'{name}'의 wall_door 후보가 없어 경계 {chosen['id']}"
                        f"(對 {_host_of(chosen, name)})를 문 경계로 승격했습니다."
                    ),
                })
            else:
                warnings.append({
                    "field": name, "rule": "1실 1문",
                    "legal": "needs_door 실은 출입문 1개", "actual": "배치 가능 경계 없음",
                    "message": f"'{name}'에 문을 낼 내부 경계가 없습니다(미배치 — 정직 경고).",
                })
    return out, warnings


def _snap_center_on(
    boundary: dict[str, Any], width_m: float,
) -> float | None:
    """경계 진행축 중앙을 50mm 그리드로 스냅해 개구 중심 좌표를 구한다.

    개구가 경계 구간을 벗어나면 그리드 위에서 안쪽으로 보정하고,
    그래도 들어가지 않으면 None(미배치 — 가짜 좌표 금지).
    """
    if boundary["orient"] == "h":
        a1, a2 = float(boundary["x1"]), float(boundary["x2"])
    else:
        a1, a2 = float(boundary["y1"]), float(boundary["y2"])
    lo = a1 + width_m / 2.0
    hi = a2 - width_m / 2.0
    if hi < lo - _EPS:
        return None
    c = _snap_grid_m((a1 + a2) / 2.0)
    if c < lo - _EPS:
        c = _r(math.ceil((lo - _EPS) / _GRID_M) * _GRID_M)
    elif c > hi + _EPS:
        c = _r(math.floor((hi + _EPS) / _GRID_M) * _GRID_M)
    if c < lo - _EPS or c > hi + _EPS:
        return None
    return c


def place_openings(
    boundaries: list[dict[str, Any]],
    rooms: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """문·창 개구를 결정론 배치한다. (openings, warnings) 반환.

    - 문: wall_door 경계 중앙 → 50mm 스냅. 스윙 in/out·힌지(start),
      폭·높이는 arch_grammar ROOM_TYPES[*].door.
    - 현관문: 현관 외기변 북>서>동 1개, 방화문(fire_rated).
    - 창: 거실 남측 전면(발코니 전면이면 분합창)+침실 외기변 중앙,
      폭 1500~2400(50mm 모듈), 창면적 ≥ 바닥 1/10 검증(미달 시 경고 — 가짜 통과 금지).
    """
    warnings: list[dict[str, Any]] = []
    doors: list[dict[str, Any]] = []
    windows: list[dict[str, Any]] = []
    rect_by_name = {str(r["name"]): r for r in rooms}

    def _owner_side(b: dict[str, Any], owner_name: str) -> str | None:
        r = rect_by_name.get(owner_name)
        if r is None:
            return None
        if b["orient"] == "h":  # 경계선 y=b["y1"] — 소유실이 남측이면 's'
            return "s" if float(r["y"]) >= float(b["y1"]) - 1e-6 else "n"
        return "e" if float(r["x"]) >= float(b["x1"]) - 1e-6 else "w"

    def _center_xy(b: dict[str, Any], c: float) -> tuple[float, float]:
        if b["orient"] == "h":
            return _r(c), float(b["y1"])
        return float(b["x1"]), _r(c)

    # 1) 내부 문(wall_door)
    for b in boundaries:
        if b.get("kind") != "wall_door" or not b.get("door_owner"):
            continue
        owner = str(b["door_owner"])
        otype = room_type_of(owner)
        spec = (ROOM_TYPES.get(otype) or {}).get("door") if otype else None
        if not spec:
            warnings.append({
                "field": owner, "rule": "문 스펙",
                "legal": "ROOM_TYPES[*].door 정의", "actual": "없음",
                "message": f"'{owner}' 실 타입의 문 스펙이 없어 미배치합니다(정직 경고).",
            })
            continue
        w_m = float(spec["width_mm"]) / 1000.0
        c = _snap_center_on(b, w_m)
        if c is None:
            warnings.append({
                "field": owner, "rule": "문 배치",
                "legal": f"개구 폭 {spec['width_mm']}mm", "actual": f"경계 {b['id']} 길이 {b['length_m']}m",
                "message": f"'{owner}' 문이 경계 {b['id']}에 들어가지 않습니다(미배치).",
            })
            continue
        host = str(b["room_b"] if b["room_a"] == owner else b["room_a"])
        oside = _owner_side(b, owner)
        swing = str(spec.get("swing") or "in")
        swing_side = oside if swing == "in" else _OPPOSITE_SIDE.get(oside or "")
        cx, cy = _center_xy(b, c)
        doors.append({
            "kind": "door", "subtype": "swing", "boundary_id": b["id"],
            "room": owner, "host": host, "orient": b["orient"],
            "center_x_m": cx, "center_y_m": cy,
            "width_mm": int(spec["width_mm"]), "height_mm": int(spec["height_mm"]),
            "swing": swing, "swing_side": swing_side, "hinge": "start",
            "fire_rated": bool(spec.get("fire_rated", False)),
        })

    # 2) 현관문 — 외기변 북>서>동, 세대당 1개, 방화문
    entry_rooms = [str(r["name"]) for r in rooms if room_type_of(str(r["name"])) == "entry"]
    for name in entry_rooms[:1]:
        spec = ROOM_TYPES["entry"]["door"]
        w_m = float(spec["width_mm"]) / 1000.0
        ext = [
            b for b in boundaries
            if b.get("room_b") is None and b["room_a"] == name
            and b.get("side") in _ENTRY_SIDE_PRIORITY
        ]
        ext.sort(key=lambda b: (_ENTRY_SIDE_PRIORITY.index(b["side"]), b["id"]))
        placed = False
        for b in ext:
            c = _snap_center_on(b, w_m)
            if c is None:
                continue
            cx, cy = _center_xy(b, c)
            doors.append({
                "kind": "door", "subtype": "entrance", "boundary_id": b["id"],
                "room": name, "host": None, "orient": b["orient"],
                "center_x_m": cx, "center_y_m": cy,
                "width_mm": int(spec["width_mm"]), "height_mm": int(spec["height_mm"]),
                "swing": str(spec.get("swing") or "out"),
                "swing_side": b["side"],  # out — 외기 방향으로 열림
                "hinge": "start",
                "fire_rated": bool(spec.get("fire_rated", True)),
            })
            placed = True
            break
        if not placed:
            warnings.append({
                "field": name, "rule": "현관문",
                "legal": "현관 외기변(북>서>동) 1개", "actual": "배치 가능 외기변 없음",
                "message": "현관문을 배치할 외기변이 없습니다(미배치 — 정직 경고).",
            })
    for name in entry_rooms[1:]:
        warnings.append({
            "field": name, "rule": "현관문",
            "legal": "세대당 현관문 1개(통상관행)", "actual": f"현관 {len(entry_rooms)}실",
            "message": f"현관이 복수입니다 — '{name}'에는 현관문을 배치하지 않습니다.",
        })

    # 3) 창 — needs_window 실의 외기변(남>북>동>서) 중앙, 폭 1500~2400·면적≥1/10 검증
    for r in rooms:
        name = str(r["name"])
        rtype = room_type_of(name)
        spec = ROOM_TYPES.get(rtype) or {} if rtype else {}
        if not spec.get("needs_window"):
            continue
        wspec = spec.get("window") or {}
        ext = [b for b in boundaries if b.get("room_b") is None and b["room_a"] == name]
        ext.sort(key=lambda b: (
            _WINDOW_SIDE_PRIORITY.index(b["side"])
            if b["side"] in _WINDOW_SIDE_PRIORITY else 9,
            b["id"],
        ))
        if not ext:
            warnings.append({
                "field": name, "rule": "채광창",
                "legal": "외기변 접촉(건축법 시행령 제51조)", "actual": "외기변 없음",
                "message": f"'{name}'에 채광창을 낼 외기변이 없습니다(미배치 — 정직 경고).",
            })
            continue
        b = ext[0]
        edge_mm = float(b["length_m"]) * 1000.0
        avail_mm = edge_mm - 2.0 * _WINDOW_END_CLEAR_MM
        width_mm = int(min(
            float(wspec.get("width_mm_max") or 2400),
            max(float(wspec.get("width_mm_min") or 1500),
                (avail_mm // GRID_MODULE_MM) * GRID_MODULE_MM),
        ))
        if width_mm > edge_mm - 200.0:  # 최소 개구 여유(양측 100mm)도 안 나오면 축소
            width_mm = int(((edge_mm - 200.0) // GRID_MODULE_MM) * GRID_MODULE_MM)
        if width_mm < 300:
            warnings.append({
                "field": name, "rule": "채광창",
                "legal": "창 폭 ≥ 300mm", "actual": f"외기변 {b['length_m']}m",
                "message": f"'{name}' 외기변이 짧아 창을 배치할 수 없습니다(미배치).",
            })
            continue
        c = _snap_center_on(b, width_mm / 1000.0)
        if c is None:
            warnings.append({
                "field": name, "rule": "채광창",
                "legal": f"개구 폭 {width_mm}mm", "actual": f"경계 {b['id']} 길이 {b['length_m']}m",
                "message": f"'{name}' 창이 경계 {b['id']}에 들어가지 않습니다(미배치).",
            })
            continue
        height_mm = int(wspec.get("height_mm") or 1500)
        win_area = width_mm * height_mm / 1e6
        floor_area = float(r["w"]) * float(r["h"])
        ratio_min = float(wspec.get("area_ratio_min") or 0.1)
        if win_area + _EPS < floor_area * ratio_min:
            warnings.append({
                "field": name, "rule": "채광 창면적(바닥 1/10)",
                "legal": round(floor_area * ratio_min, 3), "actual": round(win_area, 3),
                "message": (
                    f"'{name}' 창면적 {win_area:.2f}㎡ < 바닥 1/10 "
                    f"{floor_area * ratio_min:.2f}㎡ (건축법 시행령 제51조)"
                ),
            })
        cx, cy = _center_xy(b, c)
        windows.append({
            "kind": "window",
            "subtype": "balcony_sliding" if b.get("balcony_front") else "window",
            "boundary_id": b["id"],
            "room": name, "host": None, "orient": b["orient"],
            "center_x_m": cx, "center_y_m": cy,
            "width_mm": width_mm, "height_mm": height_mm,
            "swing": None, "swing_side": None, "hinge": None,
            "fire_rated": False,
        })

    # 결정론 id 부여(문 d##, 창 w##)
    doors.sort(key=lambda o: (o["boundary_id"], o["room"]))
    windows.sort(key=lambda o: (o["boundary_id"], o["room"]))
    for k, o in enumerate(doors, start=1):
        o["id"] = f"d{k:02d}"
    for k, o in enumerate(windows, start=1):
        o["id"] = f"w{k:02d}"
    return doors + windows, warnings


def validate_connectivity(
    rooms: list[dict[str, Any]],
    boundaries: list[dict[str, Any]],
    openings: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """현관 기점 BFS — open 경계·문 개구 간선으로 전실 도달 검증.

    미도달 실은 violation dict({field,rule,legal,actual,message})로 정직 반환.
    """
    names = [str(r["name"]) for r in rooms]
    adj: dict[str, set[str]] = {n: set() for n in names}
    for b in boundaries:
        if b.get("kind") == "open" and b.get("room_b") is not None:
            a, c = str(b["room_a"]), str(b["room_b"])
            if a in adj and c in adj:
                adj[a].add(c)
                adj[c].add(a)
    for o in openings:
        if o.get("kind") == "door" and o.get("host"):
            a, c = str(o["room"]), str(o["host"])
            if a in adj and c in adj:
                adj[a].add(c)
                adj[c].add(a)
    starts = [n for n in names if room_type_of(n) == "entry"]
    if not starts:
        return [{
            "field": "현관", "rule": "연결성(현관 기점)",
            "legal": "현관 1실", "actual": "없음",
            "message": "현관이 없어 연결성 검증을 시작할 수 없습니다.",
        }]
    seen: set[str] = {starts[0]}
    queue: list[str] = [starts[0]]
    while queue:
        cur = queue.pop(0)
        for nxt in sorted(adj[cur]):
            if nxt not in seen:
                seen.add(nxt)
                queue.append(nxt)
    return [
        {
            "field": n, "rule": "연결성(현관 도달)",
            "legal": "open 경계·문 간선으로 현관과 연결", "actual": "미도달",
            "message": f"'{n}'이(가) 현관에서 도달 불가합니다(개방 경계·문 없음).",
        }
        for n in names if n not in seen
    ]


# ── 생성기 본체 ──

def generate_unit_plan(
    area_sqm: float,
    bays: int,
    core_type: str = "계단실형",
    balcony_extension: bool = False,
) -> UnitPlanResult:
    """전용면적×베이수 → 단위세대 실 배치를 결정론 산출한다.

    Args:
        area_sqm: 전용면적(㎡). rooms가 이 면적을 타일링한다.
        bays: 남측 채광 베이 수(2/3/4만 지원 — 그 외 ValueError).
        core_type: 계단실형/복도형/타워형(메타데이터 — IFC 통합 시 사용).
        balcony_extension: 발코니 확장 여부(서비스면적 — rooms 전용면적 불변,
            balconies[].extended 플래그·effective 면적에만 반영).

    Returns:
        UnitPlanResult — rooms[{name,x,y,w,h}](m) + violations(검증 위반 목록).

    Raises:
        ValueError: 베이수·전용면적·코어타입이 지원 범위 밖이거나
            해당 평형대×베이수 표준 룰이 정의되지 않은 경우(명시 오류).
    """
    # ── 입력 검증(명시 오류 — 침묵 폴백 금지) ──
    if bays not in SUPPORTED_BAYS:
        raise ValueError(
            f"베이 수는 {'/'.join(str(b) for b in SUPPORTED_BAYS)}만 지원합니다(입력: {bays})"
        )
    if not (MIN_UNIT_AREA_SQM <= float(area_sqm) <= MAX_UNIT_AREA_SQM):
        raise ValueError(
            f"전용면적은 {MIN_UNIT_AREA_SQM}~{MAX_UNIT_AREA_SQM}㎡ 범위만 지원합니다"
            f"(입력: {area_sqm})"
        )
    if core_type not in UNIT_CORE_TYPES:
        raise ValueError(
            f"코어타입은 {'/'.join(UNIT_CORE_TYPES)} 중 하나여야 합니다(입력: {core_type})"
        )

    band = _band_for(float(area_sqm))
    rule = UNIT_RULE_TABLE.get((band, bays))
    if rule is None:
        supported = sorted(b for (bd, b) in UNIT_RULE_TABLE if bd == band)
        raise ValueError(
            f"{band}형 평형대는 {bays}베이 표준 룰이 없습니다"
            f"(지원 베이: {'/'.join(str(b) for b in supported)})"
        )

    # ── 본체 치수: W = 남측 베이폭 합, D = 전용면적/W ──
    body_w = _r(sum(w for _, w in rule.south))
    body_d = _r(float(area_sqm) / body_w)
    depth_n = _r(body_d * rule.north_depth_frac)   # 북측 띠 깊이
    depth_m = _r(body_d * rule.mid_depth_frac)     # 중간 띠 깊이
    depth_s = _r(body_d - depth_n - depth_m)       # 남측 띠 깊이(잔여 — 정합 보장)
    y_mid = depth_n
    y_south = _r(depth_n + depth_m)

    rooms: list[dict[str, Any]] = []

    # 1) 북측 클러스터: 비율폭, 마지막 실은 잔여폭 보정(타일링 정합)
    x = 0.0
    n_count = len(rule.north)
    for i, (name, frac) in enumerate(rule.north):
        if i == n_count - 1:
            w = _r(body_w - x)
        else:
            w = _r(body_w * frac)
        rooms.append({"name": name, "x": x, "y": 0.0, "w": w, "h": depth_n})
        x = _r(x + w)

    # 2) 중간 띠: 고정폭 + 잔여폭(복도) 1실
    fixed_total = sum(w for _, w in rule.mid if w is not None)
    remainder = _r(body_w - fixed_total)
    x = 0.0
    for name, w_opt in rule.mid:
        w = remainder if w_opt is None else _r(w_opt)
        rooms.append({"name": name, "x": x, "y": y_mid, "w": w, "h": depth_m})
        x = _r(x + w)

    # 3) 남측 채광 베이: 룰 테이블 고정폭, 마지막 실 잔여폭 보정
    x = 0.0
    s_count = len(rule.south)
    for i, (name, w_fix) in enumerate(rule.south):
        if i == s_count - 1:
            w = _r(body_w - x)
        else:
            w = _r(w_fix)
        rooms.append({"name": name, "x": x, "y": y_south, "w": w, "h": depth_s})
        x = _r(x + w)

    # ── 발코니(남측 전면, 서비스면적 — 전용면적 타일링과 분리) ──
    balconies: list[dict[str, Any]] = [{
        "name": "발코니",
        "x": 0.0, "y": body_d, "w": body_w, "h": BALCONY_DEPTH_M,
        "extended": bool(balcony_extension),
    }]
    service_area = round(body_w * BALCONY_DEPTH_M, 2)

    exclusive = round(sum(r["w"] * r["h"] for r in rooms), 3)
    violations = validate_unit_layout(rooms, body_w, body_d)
    if violations:
        logger.warning(
            "unit_plan_violations",
            area_sqm=area_sqm, bays=bays, band=band, count=len(violations),
        )

    # ── 경계 엔진(additive) — rooms·violations 기존 계약 불변 ──
    boundaries_raw = extract_boundaries(rooms, body_w, body_d, balconies=balconies)
    boundaries, cls_warnings = classify_boundaries(boundaries_raw, rooms)
    openings, opening_warnings = place_openings(boundaries, rooms)
    grammar_warnings = (
        cls_warnings + opening_warnings
        + validate_connectivity(rooms, boundaries, openings)
    )
    if grammar_warnings:
        logger.warning(
            "unit_plan_grammar_warnings",
            area_sqm=area_sqm, bays=bays, band=band, count=len(grammar_warnings),
        )

    return UnitPlanResult(
        unit_area_sqm=float(area_sqm),
        band=band,
        bays=bays,
        core_type=core_type,
        balcony_extension=bool(balcony_extension),
        body_width_m=body_w,
        body_depth_m=body_d,
        rooms=rooms,
        balconies=balconies,
        exclusive_area_sqm=exclusive,
        service_area_sqm=service_area,
        violations=violations,
        boundaries=boundaries,
        openings=openings,
        grammar_warnings=grammar_warnings,
    )
