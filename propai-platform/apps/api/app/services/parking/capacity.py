"""②주어진 대지/지하층 면적 → 주차 수용가능 대수 1차 추정(스펙 P — W3-5).

무목업: CAD 배치 최적화가 아니라 표준 모듈면적법(module area method) 기반 1차 추정이다.
실제 배치는 진입동선·기둥 위치·경사로 위치·대지 형상에 따라 달라질 수 있으므로 여기 산출된
수치는 "설계 검토용 참고치"다(assumptions/limitations에 명시, verified=False).

★R1 HIGH-1 교정(각형 기하 반영): 이전 버전은 주차각도(θ)와 무관하게 모듈면적을
"구획폭 × (구획길이 + 차로폭/2)"로만 계산해, 각도가 작아질수록(45°<60°<90°) 오히려
수용력이 "더 커지는" 물리적 역전이 있었다(리뷰어 실증: 평행 1000㎡→18.76㎡/대, 물리
불가능 밀도). 실제로는 각도가 얕을수록(90°→45°→0°) 한 대당 차지하는 유효 바닥면적이
"커진다"(직각주차가 가장 효율적) — 자동차가 차로에 대해 비스듬히 놓이면서 같은 줄
안에서의 간격(피치)이 늘어나기 때문이다. 이제 삼각함수로 실제 투영 기하를 반영한다.
"""

from __future__ import annotations

import math

from pydantic import BaseModel, Field

from app.services.parking.specs import (
    PARALLEL_MANEUVER_CLEARANCE_BASIS,
    PARALLEL_MANEUVER_CLEARANCE_M,
    STALL_SPECS,
    AisleSpec,
    StallSpec,
    StallType,
    check_stall_angle_consistency,
    resolve_aisle_spec,
)

# ── 공제율(램프·기둥/벽체·코어) — 실무 설계관례 참고치(assumption) ──────────
# 확정 법정 기준이 아니다. 프로젝트 여건(대지 형상·진입 위치·구조계획)에 따라
# 실제 손실률은 크게 달라질 수 있어 verified=False로 정직 표기한다.
# ★R1 MEDIUM-2 교정: 합계 20%→25%로 보수화(램프 10%·기둥/벽체 8%·코어 7%).
DEFAULT_DEDUCTION_RATIOS: dict[str, float] = {
    "ramp": 0.10,             # 경사로(진입/출입 차로) 손실 — 통상 관례치
    "columns_walls": 0.08,    # 기둥·벽체 손실
    "core": 0.07,             # 계단실·EV·설비 코어 손실
}
DEFAULT_DEDUCTION_BASIS: str = (
    "실무 설계관례 참고치(assumption) — 지하주차장 램프·기둥·코어 손실은 통상 "
    "총 바닥면적의 25% 내외 범위(프로젝트 여건에 따라 편차 큼). 확정 법정 기준 아님 — "
    "verified=False. 상세설계 단계에서 실측 손실률로 대체 필요."
)

# 물리적으로 불가능한 밀도를 잡아내기 위한 참고 하한(1대당 최소 소요면적, 통상 논의되는
# 하한치). 이 값 미만으로 산출되면 산식 결함 가능성이 높다(회귀 테스트 앵커).
PHYSICAL_MIN_MODULE_AREA_SQM: float = 20.0


def _angled_module_area_sqm(
    *, stall: StallSpec, aisle: AisleSpec, parking_angle_deg: int,
) -> tuple[float, str]:
    """직각~예각(0° 제외) 스톨의 유효 모듈면적(㎡/대) — 사인/코사인 투영 기하 반영.

    자동차가 차로에 대해 각도 θ로 비스듬히 배치되면:
      · 피치(같은 줄 안에서 옆 칸까지의 간격, 차로 진행방향) = 구획폭 / sin(θ)
      · 유효깊이(차로에서 구획 안쪽 끝까지의 투영 깊이) = 구획길이·sin(θ) + 구획폭·cos(θ)
    θ=90°(직각)에서는 sin=1·cos=0이 되어 피치=구획폭·유효깊이=구획길이로 환원된다
    (기존 90° 전용 산식과 완전히 일치 — 회귀 없음).
    """
    theta = math.radians(parking_angle_deg)
    sin_t, cos_t = math.sin(theta), math.cos(theta)
    pitch = stall.width_m / sin_t
    effective_depth = stall.length_m * sin_t + stall.width_m * cos_t
    module_area = pitch * (effective_depth + aisle.aisle_width_m / 2.0)
    basis = (
        f"각형 유효기하(피치=구획폭/sin{parking_angle_deg}°, 유효깊이=구획길이·sin+구획폭·cos) "
        f"— {stall.basis} + {aisle.basis}"
    )
    return module_area, basis


def _parallel_module_area_sqm(*, stall: StallSpec, aisle: AisleSpec) -> tuple[float, str]:
    """평행주차(0°) 전용 모듈면적 산식.

    sin(0)=0이라 _angled_module_area_sqm의 "피치=폭/sinθ"가 발산하므로 별도 산식을 쓴다:
      · 피치(차로 방향 간격) = 구획길이(평행주차 시 차로변 점유 길이) + 전후 진출입 여유
      · 유효깊이(차로에서 구획 안쪽까지) = 구획폭(평행주차 시 차로에서의 돌출 깊이)
    """
    pitch = stall.length_m + PARALLEL_MANEUVER_CLEARANCE_M
    effective_depth = stall.width_m
    module_area = pitch * (effective_depth + aisle.aisle_width_m / 2.0)
    basis = (
        f"평행주차 전용 산식(피치=구획길이+전후여유 {PARALLEL_MANEUVER_CLEARANCE_M}m, "
        f"유효깊이=구획폭) — {stall.basis} + {aisle.basis}. {PARALLEL_MANEUVER_CLEARANCE_BASIS}"
    )
    return module_area, basis


class ParkingLayoutEstimate(BaseModel):
    """면적 기반 주차 수용력 1차 추정 결과."""

    gross_area_sqm: float
    deduction_ratio_total: float
    deduction_breakdown: dict[str, float]
    usable_area_sqm: float
    stall_type: StallType
    parking_angle_deg: int
    module_area_per_stall_sqm: float
    estimated_capacity: int
    basis: str
    assumptions: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    verified: bool = False


def estimate_layout_capacity(
    *,
    gross_area_sqm: float,
    stall_type: StallType = StallType.GENERAL,
    parking_angle_deg: int = 90,
    deduction_ratios: dict[str, float] | None = None,
) -> ParkingLayoutEstimate:
    """대지/지하층 총 면적(gross_area_sqm)에서 물리적으로 들어갈 대수를 1차 추정한다.

    표준 모듈법(module area method) + 각형 투영 기하(_angled_module_area_sqm)로
    "1대당 유효 소요면적"을 산출한 뒤 공제 후 usable_area를 나눈다. 실제 배치
    최적화(회전·기둥 회피 등)는 반영하지 않는다(limitations 명시).
    """
    assumptions: list[str] = []
    limitations: list[str] = []

    if gross_area_sqm <= 0:
        return ParkingLayoutEstimate(
            gross_area_sqm=gross_area_sqm,
            deduction_ratio_total=0.0,
            deduction_breakdown={},
            usable_area_sqm=0.0,
            stall_type=stall_type,
            parking_angle_deg=parking_angle_deg,
            module_area_per_stall_sqm=0.0,
            estimated_capacity=0,
            basis="면적 입력값 0 이하 — 추정 불가",
            assumptions=[],
            limitations=["대지/지하층 면적 미입력 또는 0 이하"],
            verified=False,
        )

    ratios = deduction_ratios if deduction_ratios is not None else DEFAULT_DEDUCTION_RATIOS
    total_ratio = sum(ratios.values())
    usable = gross_area_sqm * (1.0 - total_ratio)

    stall = STALL_SPECS[stall_type]

    # ★R1 MEDIUM-3: 미등록 각도는 90°로 폴백 + 그 사실을 assumptions에 명시. 아이슬 폭뿐
    # 아니라 삼각함수 계산에 쓰는 유효각도(effective_angle_deg)도 함께 90°로 맞춰야
    # "90° 기준 적용"이라는 assumption 문구가 실제 계산과 정합한다(부분 폴백 금지 —
    # 아이슬만 90°인데 sin/cos는 미등록 원본각을 쓰면 물리적으로 존재하지 않는 조합이 됨).
    aisle, fallback_note = resolve_aisle_spec(parking_angle_deg)
    effective_angle_deg = 90 if fallback_note else parking_angle_deg
    if fallback_note:
        assumptions.append(fallback_note)

    # ★R1 MEDIUM-3: (stall_type, angle) 상호 정합성 가드 — 위반해도 계산은 진행하되 경고.
    # 원본 요청각(parking_angle_deg)을 기준으로 검사한다(폴백 여부와 무관하게 사용자 입력 그대로).
    mismatch_note = check_stall_angle_consistency(stall_type, parking_angle_deg)
    if mismatch_note:
        limitations.append(mismatch_note)

    if effective_angle_deg == 0:
        module_area, geometry_basis = _parallel_module_area_sqm(stall=stall, aisle=aisle)
    else:
        module_area, geometry_basis = _angled_module_area_sqm(
            stall=stall, aisle=aisle, parking_angle_deg=effective_angle_deg,
        )

    capacity = int(usable // module_area) if module_area > 0 else 0

    assumptions.extend([
        "직사각형 순수 바닥판·양방향 맞배치(2열) 표준 배열 가정"
        "(단일열/부정형 배치는 실제 수용력이 다를 수 있음)",
        f"공제율 합계 {total_ratio * 100:.0f}%"
        f"(램프 {ratios.get('ramp', 0) * 100:.0f}%·"
        f"기둥/벽체 {ratios.get('columns_walls', 0) * 100:.0f}%·"
        f"코어 {ratios.get('core', 0) * 100:.0f}%) — 실무 관례치",
    ])
    limitations.extend([
        "실제 CAD 배치 최적화가 아닌 면적 나눗셈 기반 1차 추정 — "
        "진입동선·기둥 실제위치는 미반영",
        "부정형 대지·복수 진입로 등은 수용력을 저하시킬 수 있음(보수적 재검토 권장)",
    ])

    return ParkingLayoutEstimate(
        gross_area_sqm=round(gross_area_sqm, 1),
        deduction_ratio_total=round(total_ratio, 4),
        deduction_breakdown=dict(ratios),
        usable_area_sqm=round(usable, 1),
        stall_type=stall_type,
        parking_angle_deg=parking_angle_deg,
        module_area_per_stall_sqm=round(module_area, 2),
        estimated_capacity=max(0, capacity),
        basis=f"표준 모듈법(module area method) — {geometry_basis}. {DEFAULT_DEDUCTION_BASIS}",
        assumptions=assumptions,
        limitations=limitations,
        verified=False,
    )
