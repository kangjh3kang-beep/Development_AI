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
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import structlog

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
    )
