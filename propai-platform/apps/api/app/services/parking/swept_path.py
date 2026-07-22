"""③swept path 1차 검증 — 설계기준차량 최소회전반경 기반 차로폭 판정(스펙 P — W3-5).

★정직 표기(핵심): 이 모듈은 AutoTURN류 완전한 차량 궤적(오프트래킹) 시뮬레이션이
아니다. 설계기준차량(승용차)의 표준 최소회전반경·주차각도별 차로폭 기준과, 계획된
실제 차로폭/회전반경을 "비교"하는 1차 근사다. 곡선부의 정량적 확폭 소요량 계산은
본 검증 범위 밖이며(상세설계 단계에서 회전궤적 CAD 필요), method·limitations 필드에
항상 명시한다. ★이 검증은 "이중 임계 게이트"(차로폭 하한·회전반경 하한을 각각
독립적으로 통과하는지 boolean 비교)이며, 두 값의 관계를 기하학적으로 결합해
회전궤적을 그려보는 관계식이 아니다(즉 "차로폭 X + 회전반경 Y가 함께 충분한지"를
합성 계산하지 않는다 — 각 기준을 개별 통과선으로만 판정).
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.services.parking.specs import (
    DESIGN_VEHICLE_MIN_TURN_RADIUS_BASIS,
    DESIGN_VEHICLE_MIN_TURN_RADIUS_M,
    resolve_aisle_spec,
)

_METHOD = "simplified_turn_radius_v1"


class SweptPathCheck(BaseModel):
    """swept path 1차 판정 결과 — 항상 method·limitations로 근사 성격을 명시."""

    method: str = _METHOD
    parking_angle_deg: int
    required_aisle_width_m: float
    actual_aisle_width_m: float | None
    aisle_width_ok: bool | None
    required_turn_radius_m: float
    actual_turn_radius_m: float | None
    turn_radius_ok: bool | None
    status: str  # "pass" / "warn" / "fail" / "unavailable"
    basis: str
    assumptions: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    verified: bool = False


def check_swept_path(
    *,
    parking_angle_deg: int = 90,
    actual_aisle_width_m: float | None = None,
    actual_turn_radius_m: float | None = None,
    min_turn_radius_m: float = DESIGN_VEHICLE_MIN_TURN_RADIUS_M,
) -> SweptPathCheck:
    """차로폭/회전반경 실측값을 최소기준과 비교한다(1차 근사 — 완전 궤적 시뮬 아님).

    actual_aisle_width_m·actual_turn_radius_m이 모두 None이면 status="unavailable"
    (판정 불가). 하나만 있으면 "warn"(부분 검증). 둘 다 있고 모두 기준 이상이면 "pass",
    하나라도 미달이면 "fail".
    """
    # ★R1 MEDIUM-3: 미등록 각도는 90°로 폴백 + 그 사실을 assumptions에 명시(capacity.py와 공용 헬퍼).
    aisle, fallback_note = resolve_aisle_spec(parking_angle_deg)
    required_width = aisle.aisle_width_m

    aisle_ok = None if actual_aisle_width_m is None else actual_aisle_width_m >= required_width
    radius_ok = None if actual_turn_radius_m is None else actual_turn_radius_m >= min_turn_radius_m

    if aisle_ok is None and radius_ok is None:
        status = "unavailable"
    elif aisle_ok is False or radius_ok is False:
        status = "fail"
    elif aisle_ok is None or radius_ok is None:
        status = "warn"
    else:
        status = "pass"

    assumptions = [
        f"설계기준차량: 승용차(최소회전반경 {min_turn_radius_m}m 가정 — "
        f"{DESIGN_VEHICLE_MIN_TURN_RADIUS_BASIS})",
    ]
    if fallback_note:
        assumptions.append(fallback_note)

    return SweptPathCheck(
        method=_METHOD,
        parking_angle_deg=parking_angle_deg,
        required_aisle_width_m=required_width,
        actual_aisle_width_m=actual_aisle_width_m,
        aisle_width_ok=aisle_ok,
        required_turn_radius_m=min_turn_radius_m,
        actual_turn_radius_m=actual_turn_radius_m,
        turn_radius_ok=radius_ok,
        status=status,
        basis=f"차로폭 기준: {aisle.basis} / 회전반경 기준: {DESIGN_VEHICLE_MIN_TURN_RADIUS_BASIS}",
        assumptions=assumptions,
        limitations=[
            "완전한 차량 궤적(오프트래킹) 시뮬레이션이 아님 — 최소회전반경·차로폭 "
            "기준 비교만 수행하는 1차 근사(method=simplified_turn_radius_v1)",
            "곡선부 실제 확폭 소요량(정량값)은 본 검증 범위 밖 — 상세설계 단계에서 "
            "회전궤적 CAD/AutoTURN급 시뮬레이션으로 재검증 필요",
        ],
        verified=False,
    )
