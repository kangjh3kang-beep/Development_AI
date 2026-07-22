"""verify_parking_plan — 요구대수 vs 수용추정 vs 기하판정 종합(스펙 P — W3-5).

★스파이크 확정 사실(이중화 금지): 법정 주차대수 산정 로직은 이미
``app.services.permit.building_code_rules``에 실재한다
(``BuildingCodeRuleEngine._check_parking`` · ``PARKING_REQUIREMENTS`` 테이블 —
주차장법 시행령 §6 별표1 근거, ``/api/v1/building-compliance/rule-check``(BL-005)로
이미 노출 중). 본 모듈은 그 상수 테이블(``PARKING_REQUIREMENTS``)을 그대로
재사용하고 새로운 수치를 선언하지 않는다 — 새로 추가하는 것은 오직
"기하 실현 가능성"(구획 치수·수용력 추정·swept path) 계약뿐이다.
"""

from __future__ import annotations

import math
from enum import StrEnum

from pydantic import BaseModel, Field

from app.services.parking.capacity import ParkingLayoutEstimate, estimate_layout_capacity
from app.services.parking.specs import StallType
from app.services.parking.swept_path import SweptPathCheck, check_swept_path
from app.services.permit.building_code_rules import PARKING_REQUIREMENTS


class ParkingPlanVerdict(StrEnum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


# ── 수용력 3밴드 판정 여유계수(assumption) ★R1 MEDIUM-2 ─────────────────────
# 계획대수/추정수용력 비율(capacity_margin_ratio)이 이 값 이하면 "여유 충분"(PASS),
# 초과~1.0까지는 "경계 구간"(WARN — 정밀 배치도로 재확인 필요), 1.0 초과는 FAIL.
LAYOUT_WARN_MARGIN_RATIO: float = 0.85
LAYOUT_WARN_MARGIN_BASIS: str = (
    "실무 설계관례 참고치(assumption) — 1차 추정 수용력의 85%를 넘어서면 실제 배치에서 "
    "여유가 부족할 위험이 커진다고 보수적으로 가정. 확정 법정 기준 아님 — verified=False."
)


def required_legal_parking_count(
    *,
    building_type: str,
    unit_count: int = 0,
    total_gfa_sqm: float = 0.0,
) -> tuple[int, str]:
    """법정 요구 주차대수 산정 — PARKING_REQUIREMENTS(SSOT) 재사용.

    산식은 ``BuildingCodeRuleEngine._check_parking``과 동일하다(같은 상수 테이블을
    참조할 뿐 새 값을 선언하지 않음 — 중복 로직 아님).
    """
    req = PARKING_REQUIREMENTS.get(building_type, PARKING_REQUIREMENTS.get("아파트", {}))
    if req.get("per_unit") is not None:
        required = math.ceil(unit_count * req["per_unit"])
        basis = f"{unit_count}세대 × {req['per_unit']}대/세대(주차장법 시행령 제6조 별표1)"
    else:
        per_sqm = req.get("additional_per_sqm", 150)
        required = math.ceil(total_gfa_sqm / per_sqm) if per_sqm else 0
        basis = f"연면적 {total_gfa_sqm:.0f}㎡ ÷ {per_sqm}㎡(주차장법 시행령 제6조 별표1)"
    return required, basis


class ParkingPlanVerification(BaseModel):
    """주차계획 종합 검증 결과 — PASS/WARN/FAIL + 근거·가정·한계."""

    verdict: ParkingPlanVerdict
    required_count: int
    required_count_basis: str
    planned_count: int
    layout: ParkingLayoutEstimate | None
    swept_path: SweptPathCheck | None
    # ★R1 MEDIUM-2: 3밴드 판정 근거 수치를 결과 필드로 정직 노출(마진 계수 은닉 금지).
    capacity_margin_ratio: float | None = None
    capacity_warn_threshold_ratio: float = LAYOUT_WARN_MARGIN_RATIO
    reasons: list[str] = Field(default_factory=list)
    basis: str
    assumptions: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    verified: bool = False


def verify_parking_plan(
    *,
    building_type: str = "아파트",
    unit_count: int = 0,
    total_gfa_sqm: float = 0.0,
    planned_parking_count: int = 0,
    available_layout_area_sqm: float | None = None,
    stall_type: StallType = StallType.GENERAL,
    parking_angle_deg: int = 90,
    actual_aisle_width_m: float | None = None,
    actual_turn_radius_m: float | None = None,
    deduction_ratios: dict[str, float] | None = None,
) -> ParkingPlanVerification:
    """법정 요구대수·기하 수용력 추정·swept path 1차 판정을 종합해 PASS/WARN/FAIL을 낸다.

    ① 요구대수(법정, PARKING_REQUIREMENTS 재사용) vs 계획대수(planned_parking_count)
    ② 제공 면적(available_layout_area_sqm)이 있으면 모듈법 수용력 추정 대비 계획대수
    ③ 차로폭/회전반경 실측값이 있으면 swept path 1차 판정
    입력이 부족한 항목은 판정에서 제외하고 limitations에 정직 표기(가짜 pass 금지) —
    누락된 항목이 있으면 verdict는 최소 WARN, 명백한 미달이 하나라도 있으면 FAIL.
    """
    required, required_basis = required_legal_parking_count(
        building_type=building_type, unit_count=unit_count, total_gfa_sqm=total_gfa_sqm,
    )

    reasons: list[str] = []
    assumptions: list[str] = []
    limitations: list[str] = []

    count_ok: bool | None
    if required > 0 or planned_parking_count > 0:
        count_ok = planned_parking_count >= required
        if count_ok:
            reasons.append(f"계획 대수({planned_parking_count}대) ≥ 법정 요구({required}대)")
        else:
            reasons.append(f"계획 대수({planned_parking_count}대) < 법정 요구({required}대)")
    else:
        count_ok = None
        limitations.append("세대수/연면적 미입력 — 법정 요구대수 산정 불가")

    layout: ParkingLayoutEstimate | None = None
    layout_ok: bool | None = None
    capacity_margin_ratio: float | None = None
    if available_layout_area_sqm is not None and available_layout_area_sqm > 0:
        layout = estimate_layout_capacity(
            gross_area_sqm=available_layout_area_sqm,
            stall_type=stall_type,
            parking_angle_deg=parking_angle_deg,
            deduction_ratios=deduction_ratios,
        )
        limitations.extend(layout.limitations)
        assumptions.extend(layout.assumptions)
        assumptions.append(LAYOUT_WARN_MARGIN_BASIS)

        capacity = layout.estimated_capacity
        # ★R1 MEDIUM-2: 이진(≥/<) 판정 대신 3밴드(여유 충분/경계/초과) 판정.
        if capacity <= 0:
            layout_ok = False if planned_parking_count > 0 else None
            reasons.append(
                f"제공면적({available_layout_area_sqm:.0f}㎡) 기준 추정 수용력 0대 — 물리 수용 불가"
            )
        else:
            capacity_margin_ratio = round(planned_parking_count / capacity, 4)
            if capacity_margin_ratio <= LAYOUT_WARN_MARGIN_RATIO:
                layout_ok = True
                reasons.append(
                    f"제공면적({available_layout_area_sqm:.0f}㎡) 기준 추정 수용력 {capacity}대, "
                    f"계획 {planned_parking_count}대 — 여유 충분(마진비율 {capacity_margin_ratio:.2f} "
                    f"≤ {LAYOUT_WARN_MARGIN_RATIO})"
                )
            elif capacity_margin_ratio <= 1.0:
                layout_ok = None  # 경계 구간 — 하드 FAIL 아닌 WARN(soft_warns로 반영)
                reasons.append(
                    f"제공면적({available_layout_area_sqm:.0f}㎡) 기준 추정 수용력 {capacity}대, "
                    f"계획 {planned_parking_count}대 — 경계 구간(마진비율 {capacity_margin_ratio:.2f}, "
                    f"{LAYOUT_WARN_MARGIN_RATIO}~1.0) — 정밀 배치도 확인 필요"
                )
            else:
                layout_ok = False
                reasons.append(
                    f"제공면적({available_layout_area_sqm:.0f}㎡) 기준 추정 수용력 {capacity}대 < "
                    f"계획 {planned_parking_count}대(마진비율 {capacity_margin_ratio:.2f}) — "
                    "기하적으로 물리 수용 곤란"
                )
    else:
        limitations.append("대지/지하층 가용면적 미입력 — 수용력 추정 생략")

    swept: SweptPathCheck | None = None
    swept_ok: bool | None = None
    if actual_aisle_width_m is not None or actual_turn_radius_m is not None:
        swept = check_swept_path(
            parking_angle_deg=parking_angle_deg,
            actual_aisle_width_m=actual_aisle_width_m,
            actual_turn_radius_m=actual_turn_radius_m,
        )
        # ★R1 HIGH-2 교정: "warn"(부분입력)·"unavailable"은 None(soft warn)으로 유지해야
        # 한다 — 이전엔 status=="pass" 비교만 해서 "warn"이 False로 접혀 하드 FAIL을
        # 유발했다(자기 계약 위반: docstring/reasons는 "부분 검증만 수행"이라 해놓고
        # 실제로는 종합판정을 FAIL로 강제했었다).
        swept_ok = None if swept.status in ("warn", "unavailable") else (swept.status == "pass")
        if swept.status == "fail":
            reasons.append("swept path 1차 판정: 차로폭/회전반경 기준 미달")
        elif swept.status == "warn":
            reasons.append("swept path 1차 판정: 일부 입력 결손 — 부분 검증만 수행")
        else:
            reasons.append("swept path 1차 판정: 차로폭/회전반경 기준 충족")
        limitations.extend(swept.limitations)
        assumptions.extend(swept.assumptions)
    else:
        limitations.append("차로폭/회전반경 미입력 — swept path 1차 검증 생략")

    hard_fails = (count_ok is False) or (layout_ok is False) or (swept_ok is False)
    soft_warns = (count_ok is None) or (layout_ok is None) or (swept_ok is None)
    if hard_fails:
        verdict = ParkingPlanVerdict.FAIL
    elif soft_warns:
        verdict = ParkingPlanVerdict.WARN
    else:
        verdict = ParkingPlanVerdict.PASS

    return ParkingPlanVerification(
        verdict=verdict,
        required_count=required,
        required_count_basis=required_basis,
        planned_count=planned_parking_count,
        layout=layout,
        swept_path=swept,
        capacity_margin_ratio=capacity_margin_ratio,
        capacity_warn_threshold_ratio=LAYOUT_WARN_MARGIN_RATIO,
        reasons=reasons,
        basis=(
            "법정대수(주차장법 시행령 §6 별표1, PARKING_REQUIREMENTS 재사용) vs "
            "기하 수용력 추정(모듈법, 1차 근사) vs swept path 1차(회전반경/차로폭) 종합 판정"
        ),
        assumptions=assumptions,
        limitations=limitations,
        verified=False,
    )
