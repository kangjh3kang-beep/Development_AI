"""②주어진 대지/지하층 면적 → 주차 수용가능 대수 1차 추정(스펙 P — W3-5).

무목업: CAD 배치 최적화가 아니라 표준 모듈면적법(module area method) 기반 1차 추정이다.
실제 배치는 진입동선·기둥 위치·경사로 위치·대지 형상에 따라 달라질 수 있으므로 여기 산출된
수치는 "설계 검토용 참고치"다(assumptions/limitations에 명시, verified=False).
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.services.parking.specs import AISLE_SPECS, STALL_SPECS, StallType

# ── 공제율(램프·기둥/벽체·코어) — 실무 설계관례 참고치(assumption) ──────────
# 확정 법정 기준이 아니다. 프로젝트 여건(대지 형상·진입 위치·구조계획)에 따라
# 실제 손실률은 크게 달라질 수 있어 verified=False로 정직 표기한다.
DEFAULT_DEDUCTION_RATIOS: dict[str, float] = {
    "ramp": 0.08,            # 경사로(진입/출입 차로) 손실 — 통상 관례치
    "columns_walls": 0.07,   # 기둥·벽체 손실
    "core": 0.05,            # 계단실·EV·설비 코어 손실
}
DEFAULT_DEDUCTION_BASIS: str = (
    "실무 설계관례 참고치(assumption) — 지하주차장 램프·기둥·코어 손실은 통상 "
    "총 바닥면적의 20% 내외 범위(프로젝트 여건에 따라 편차 큼). 확정 법정 기준 아님 — "
    "verified=False. 상세설계 단계에서 실측 손실률로 대체 필요."
)


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

    표준 모듈법(module area method): 맞은편 2열이 차로 폭의 절반씩을 공유하는
    표준 배열을 가정해 "1대당 소요면적 = 구획폭 × (구획길이 + 차로폭/2)"으로
    계산한다. 실제 배치 최적화(회전·기둥 회피 등)는 반영하지 않는다(limitations 명시).
    """
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
    aisle = AISLE_SPECS.get(parking_angle_deg, AISLE_SPECS[90])

    module_area = stall.width_m * (stall.length_m + aisle.aisle_width_m / 2.0)
    capacity = int(usable // module_area) if module_area > 0 else 0

    return ParkingLayoutEstimate(
        gross_area_sqm=round(gross_area_sqm, 1),
        deduction_ratio_total=round(total_ratio, 4),
        deduction_breakdown=dict(ratios),
        usable_area_sqm=round(usable, 1),
        stall_type=stall_type,
        parking_angle_deg=parking_angle_deg,
        module_area_per_stall_sqm=round(module_area, 2),
        estimated_capacity=max(0, capacity),
        basis=(
            f"표준 모듈법(module area method) — 구획 {stall.width_m}m×{stall.length_m}m"
            f"({stall.basis}) + 차로 {aisle.aisle_width_m}m 절반 공유"
            f"({aisle.basis}). {DEFAULT_DEDUCTION_BASIS}"
        ),
        assumptions=[
            "직사각형 순수 바닥판·양방향 맞배치(2열) 표준 배열 가정"
            "(단일열/부정형 배치는 실제 수용력이 다를 수 있음)",
            f"공제율 합계 {total_ratio * 100:.0f}%"
            f"(램프 {ratios.get('ramp', 0) * 100:.0f}%·"
            f"기둥/벽체 {ratios.get('columns_walls', 0) * 100:.0f}%·"
            f"코어 {ratios.get('core', 0) * 100:.0f}%) — 실무 관례치",
        ],
        limitations=[
            "실제 CAD 배치 최적화가 아닌 면적 나눗셈 기반 1차 추정 — "
            "진입동선·기둥 실제위치는 미반영",
            "부정형 대지·복수 진입로 등은 수용력을 저하시킬 수 있음(보수적 재검토 권장)",
        ],
        verified=False,
    )
