"""주차 기하 실현 가능성 검증 계약(스펙 P — W3-5).

법정 주차대수 산정 로직(값)의 SSOT는
``app.services.permit.building_code_rules.PARKING_REQUIREMENTS``다. 이 패키지는 그
대수를 그대로 재사용하고, "기하적으로 실제 들어가는지"(①구획 치수 SSOT ②면적 기반
수용력 추정 ③swept path 1차 검증)만 신설한다 — 대수 산정 로직 이중화 없음.
"""

from app.services.parking.capacity import (
    DEFAULT_DEDUCTION_RATIOS,
    ParkingLayoutEstimate,
    estimate_layout_capacity,
)
from app.services.parking.specs import (
    AISLE_SPECS,
    DESIGN_VEHICLE_MIN_TURN_RADIUS_BASIS,
    DESIGN_VEHICLE_MIN_TURN_RADIUS_M,
    STALL_SPECS,
    AisleSpec,
    StallSpec,
    StallType,
)
from app.services.parking.swept_path import SweptPathCheck, check_swept_path
from app.services.parking.verify import (
    ParkingPlanVerdict,
    ParkingPlanVerification,
    required_legal_parking_count,
    verify_parking_plan,
)

__all__ = [
    "StallType",
    "StallSpec",
    "STALL_SPECS",
    "AisleSpec",
    "AISLE_SPECS",
    "DESIGN_VEHICLE_MIN_TURN_RADIUS_M",
    "DESIGN_VEHICLE_MIN_TURN_RADIUS_BASIS",
    "ParkingLayoutEstimate",
    "estimate_layout_capacity",
    "DEFAULT_DEDUCTION_RATIOS",
    "SweptPathCheck",
    "check_swept_path",
    "ParkingPlanVerdict",
    "ParkingPlanVerification",
    "verify_parking_plan",
    "required_legal_parking_count",
]
