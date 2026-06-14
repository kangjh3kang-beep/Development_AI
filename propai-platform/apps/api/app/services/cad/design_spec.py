"""설계 스펙(DesignSpec) + 제약 검증(ConstraintValidator) — 할루시네이션 방지 토대(L1/L2).

설계 철학(Hypar 패턴 = 업계 검증된 정답):
  자연어/음성은 '의도 파싱'만 담당하고, 실제 기하·면적·수치는 결정론 커널
  (AutoDesignEngine)이 산출한다. LLM은 좌표·법규수치를 직접 만들지 않는다.

- DesignSpec: 검증된 단일 진실 스펙(SSOT). LLM은 이 스펙을 도구로 '편집'만 한다.
- ConstraintValidator: 스펙·기하가 한국 법규/공학 한도를 만족하는지 하드 검증.
  위반은 사유와 함께 반환되어 ① LLM 재시도 ② 사용자 표시(가짜·불법 차단)에 쓰인다.

이 파일은 LLM·외부호출 없이 순수 결정론으로 동작한다(테스트·검증 용이).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from .auto_design_engine import (
    CORRIDOR_WIDTHS,
    UNIT_TYPES,
    ZONE_LIMITS,
    LegalLimits,
    SiteInput,
    _DEFAULT_LIMITS,
)
from .unit_plan_generator import SUPPORTED_BAYS, UNIT_CORE_TYPES

PRIORITIES = ("yield", "balanced", "livability")
# 한국 용도지역 코드 ↔ 한글명(검증 메시지·UI 공용)
ZONE_LABELS: dict[str, str] = {
    "1R": "제1종일반주거", "2R": "제2종일반주거", "3R": "제3종일반주거",
    "GC": "일반상업", "NC": "근린상업", "QI": "준공업", "QR": "준주거",
}


class Violation(BaseModel):
    """법규/공학 제약 위반 1건. LLM 재시도 사유 + 사용자 표시 공용."""

    field: str
    rule: str                       # 위반 규칙(한글)
    legal: float | str              # 법정/허용 값
    actual: float | str             # 실제 값
    severity: Literal["error", "warn"] = "error"
    message: str


class Setback(BaseModel):
    north: float = 3.0
    south: float = 2.0
    east: float = 1.5
    west: float = 1.5


class UnitGrammar(BaseModel):
    """단위세대 평면 문법(R3-1 결정론 유닛플랜).

    DesignSpec.unit_grammar가 None이면 유닛플랜 미생성(기존 동작 완전 불변).
    값 유효성은 validate_spec이 Violation으로 반환한다(LLM 재시도 루프 호환).
    """

    bays: int = Field(default=3, description="남측 채광 베이 수(2/3/4)")
    core_type: str = Field(default="계단실형", description="계단실형/복도형/타워형")
    balcony_extension: bool = Field(default=False, description="발코니 확장 여부")


class DesignSpec(BaseModel):
    """검증된 설계 스펙(단일 진실원). LLM 도구가 편집하고 커널이 기하를 산출한다."""

    site_area_sqm: float = Field(gt=0, description="대지면적(㎡)")
    zone_code: str = "2R"
    building_use: str = "공동주택"
    floor_height_m: float = Field(default=3.0, gt=1.5, le=6.0)
    num_floors: int | None = Field(default=None, ge=1, le=120)  # None=용적률 자동
    target_unit_types: list[str] = Field(default_factory=lambda: ["84A"])
    corridor_width_m: float | None = None  # None=용도 표준값 사용
    setback_m: Setback = Field(default_factory=Setback)
    priority: str = "balanced"
    target_units: int | None = Field(default=None, ge=1)
    target_margin_pct: float | None = None
    # R3-1: 단위세대 평면 문법(옵셔널·additive) — None이면 기존 동작 완전 불변
    unit_grammar: UnitGrammar | None = None
    # 매스 형상(옵셔널·additive): slab/tower/lshape/court. None=자동(대지비율).
    massing_kind: str | None = None

    def to_site_input(self) -> SiteInput:
        """커널(AutoDesignEngine) 입력으로 변환."""
        sb = self.setback_m
        return SiteInput(
            site_area_sqm=self.site_area_sqm,
            zone_code=self.zone_code,
            building_use=self.building_use,
            target_unit_types=self.target_unit_types or ["84A"],
            floor_height_m=self.floor_height_m,
            setback_m={"north": sb.north, "south": sb.south, "east": sb.east, "west": sb.west},
            massing_kind=self.massing_kind,
        )


def legal_limits_for(zone_code: str) -> LegalLimits:
    return ZONE_LIMITS.get(zone_code, _DEFAULT_LIMITS)


def min_corridor_for(building_use: str) -> float:
    return CORRIDOR_WIDTHS.get(building_use, 1.8)


def validate_spec(spec: DesignSpec) -> list[Violation]:
    """스펙 자체의 합법성(기하 생성 전 사전 검증)."""
    out: list[Violation] = []
    lim = legal_limits_for(spec.zone_code)

    # 용도지역 코드 유효성
    if spec.zone_code not in ZONE_LIMITS:
        out.append(Violation(
            field="zone_code", rule="용도지역", legal="/".join(ZONE_LIMITS), actual=spec.zone_code,
            severity="warn", message=f"알 수 없는 용도지역 코드 — 기본 한도로 대체합니다.",
        ))

    # 복도폭 ≥ 용도별 최소
    minc = min_corridor_for(spec.building_use)
    if spec.corridor_width_m is not None and spec.corridor_width_m < minc:
        out.append(Violation(
            field="corridor_width_m", rule="복도 최소폭", legal=minc, actual=spec.corridor_width_m,
            message=f"{spec.building_use} 복도폭은 최소 {minc}m 이상이어야 합니다(현재 {spec.corridor_width_m}m).",
        ))

    # 이격거리 ≥ 법정 최소
    for d, ko in (("north", "북"), ("south", "남"), ("east", "동"), ("west", "서")):
        val = getattr(spec.setback_m, d)
        if val < lim.min_setback_m:
            out.append(Violation(
                field=f"setback_m.{d}", rule="최소 이격거리", legal=lim.min_setback_m, actual=val,
                severity="warn", message=f"{ko}측 이격 {val}m < 법정 {lim.min_setback_m}m",
            ))

    # 층수×층고 ≤ 최고높이(층수 지정 시)
    if spec.num_floors and lim.max_height_m > 0:
        h = spec.num_floors * spec.floor_height_m
        if h > lim.max_height_m + 0.05:
            out.append(Violation(
                field="num_floors", rule="최고높이", legal=lim.max_height_m, actual=round(h, 1),
                message=f"{spec.num_floors}층×{spec.floor_height_m}m={h:.1f}m > 법정 최고 {lim.max_height_m}m",
            ))

    # 우선순위 유효성
    if spec.priority not in PRIORITIES:
        out.append(Violation(
            field="priority", rule="우선순위", legal="/".join(PRIORITIES), actual=spec.priority,
            severity="warn", message="우선순위는 yield/balanced/livability 중 하나여야 합니다.",
        ))

    # R3-1: 단위세대 문법 유효성(unit_grammar 지정 시에만 — 미지정이면 기존 동작 불변)
    if spec.unit_grammar is not None:
        ug = spec.unit_grammar
        if ug.bays not in SUPPORTED_BAYS:
            out.append(Violation(
                field="unit_grammar.bays", rule="베이 수",
                legal="/".join(str(b) for b in SUPPORTED_BAYS), actual=ug.bays,
                message=f"베이 수는 {'/'.join(str(b) for b in SUPPORTED_BAYS)}만 지원합니다"
                        f"(현재 {ug.bays}베이).",
            ))
        if ug.core_type not in UNIT_CORE_TYPES:
            out.append(Violation(
                field="unit_grammar.core_type", rule="코어타입",
                legal="/".join(UNIT_CORE_TYPES), actual=ug.core_type,
                message=f"코어타입은 {'/'.join(UNIT_CORE_TYPES)} 중 하나여야 합니다"
                        f"(현재 '{ug.core_type}').",
            ))

    return out


def validate_geometry(
    spec: DesignSpec,
    *,
    bcr_pct: float | None = None,
    far_pct: float | None = None,
    building_height_m: float | None = None,
    parking_required: int | None = None,
    parking_provided: int | None = None,
) -> list[Violation]:
    """커널 산출 기하/지표의 합법성(생성 후 검증). 화면 표시 전 하드가드.

    값은 커널(AutoDesignEngine.generate 결과)에서 추출해 넘긴다 — LLM 주장이 아님.
    """
    out: list[Violation] = []
    lim = legal_limits_for(spec.zone_code)
    tol = 0.5  # 반올림 허용오차(%)

    if bcr_pct is not None and bcr_pct > lim.building_coverage_ratio * 100 + tol:
        out.append(Violation(
            field="bcr_pct", rule="건폐율 초과", legal=round(lim.building_coverage_ratio * 100, 1),
            actual=round(bcr_pct, 1),
            message=f"건폐율 {bcr_pct:.1f}% > 법정 {lim.building_coverage_ratio * 100:.0f}%",
        ))
    if far_pct is not None and far_pct > lim.floor_area_ratio * 100 + tol:
        out.append(Violation(
            field="far_pct", rule="용적률 초과", legal=round(lim.floor_area_ratio * 100, 1),
            actual=round(far_pct, 1),
            message=f"용적률 {far_pct:.1f}% > 법정 {lim.floor_area_ratio * 100:.0f}%",
        ))
    if building_height_m is not None and lim.max_height_m > 0 and building_height_m > lim.max_height_m + 0.1:
        out.append(Violation(
            field="building_height_m", rule="최고높이 초과", legal=lim.max_height_m,
            actual=round(building_height_m, 1),
            message=f"건물높이 {building_height_m:.1f}m > 법정 {lim.max_height_m}m",
        ))
    if parking_required is not None and parking_provided is not None and parking_provided < parking_required:
        out.append(Violation(
            field="parking", rule="법정주차 부족", legal=parking_required, actual=parking_provided,
            message=f"주차 {parking_provided}대 < 법정 {parking_required}대",
        ))
    return out


def has_errors(violations: list[Violation]) -> bool:
    """error 등급 위반이 하나라도 있으면 True(적용 차단 기준)."""
    return any(v.severity == "error" for v in violations)
