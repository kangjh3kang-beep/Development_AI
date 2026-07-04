"""개발가능유형 실효 검증 엔진.

용도지역 필터링 후 각 개발유형의 법적 조건 부합 여부를 7개 항목으로 검증.
결과: 적합(pass) / 조건부(conditional) / 부적합(fail)
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any

# ── 적합성 판정 ──

class FeasibilityStatus(StrEnum):
    PASS = "적합"
    CONDITIONAL = "조건부"
    FAIL = "부적합"

@dataclass
class ConditionCheck:
    rule: str
    status: str  # pass / fail / conditional / unknown
    detail: str
    is_blocking: bool = False

@dataclass
class FeasibilityResult:
    dev_type: str
    type_name: str
    feasibility_status: FeasibilityStatus
    conditions: list[ConditionCheck]
    blocking_issues: list[str]
    recommendations: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "feasibility_status": self.feasibility_status.value,
            "conditions_met": [asdict(c) for c in self.conditions],
            "blocking_issues": self.blocking_issues,
            "recommendations": self.recommendations,
        }

# ── 법적 기준 상수 ──

MIN_LOT_AREA: dict[str, float] = {
    "M01": 5000, "M02": 5000, "M03": 3000, "M04": 3000, "M05": 1000,
    "M06": 660, "M07": 1000, "M08": 300, "M09": 1000, "M10": 90,
    "M11": 200, "M12": 330, "M13": 150, "M14": 1000, "M15": 3000,
}

ROAD_REQUIREMENT: dict[str, dict[str, float]] = {
    "M01": {"road_width": 6, "frontage": 4},
    "M02": {"road_width": 6, "frontage": 4},
    "M06": {"road_width": 6, "frontage": 4},
    "M07": {"road_width": 8, "frontage": 6},
    "M08": {"road_width": 6, "frontage": 4},
    "M09": {"road_width": 8, "frontage": 6},
    "M10": {"road_width": 4, "frontage": 2},
    "M11": {"road_width": 4, "frontage": 2},
    "M12": {"road_width": 4, "frontage": 2},
    "M13": {"road_width": 4, "frontage": 2},
}

MAX_FLOORS: dict[str, int | None] = {
    "M10": 3, "M11": 3, "M12": 4, "M13": None,
}

BUILDING_TYPE_MAP: dict[str, str] = {
    "M01": "아파트", "M02": "아파트", "M06": "아파트", "M07": "아파트",
    "M08": "오피스텔", "M09": "근린생활시설", "M10": "단독주택",
    "M11": "단독주택", "M12": "다세대주택", "M13": "다세대주택",
    "M14": "공동주택", "M15": "아파트",
}

RESIDENTIAL_ZONES = {
    "제1종전용주거지역", "제2종전용주거지역",
    "제1종일반주거지역", "제2종일반주거지역", "제3종일반주거지역",
    "준주거지역",
}

PARKING_SQM_PER_SPACE = 30  # 지하주차장 1대당 약 30m²
UNDERGROUND_RATIO = 0.70     # 대지면적의 약 70%를 지하주차장으로 활용 가능

# ── 검증 함수 ──

def _check_lot_area(dev_type: str, land_area: float) -> ConditionCheck:
    min_area = MIN_LOT_AREA.get(dev_type, 0)
    if min_area <= 0:
        return ConditionCheck("대지면적", "pass", "면적 제한 없음")
    if land_area >= min_area:
        return ConditionCheck("대지면적", "pass", f"{land_area:.0f}m² >= {min_area:.0f}m² (최소)")
    return ConditionCheck(
        "대지면적", "fail",
        f"{land_area:.0f}m² < {min_area:.0f}m² (최소) — 면적 부족",
        is_blocking=True,
    )

def _check_road(dev_type: str, road_width: float | None, road_frontage: float | None) -> ConditionCheck:
    req = ROAD_REQUIREMENT.get(dev_type)
    if not req:
        return ConditionCheck("접도", "pass", "접도 제한 없음")
    if road_width is None and road_frontage is None:
        return ConditionCheck("접도", "unknown", "접도 데이터 미확인 — 현장 확인 필요")

    issues = []
    if road_width is not None and road_width < req["road_width"]:
        issues.append(f"도로폭 {road_width}m < {req['road_width']}m")
    if road_frontage is not None and road_frontage < req["frontage"]:
        issues.append(f"접도면 {road_frontage}m < {req['frontage']}m")
    if issues:
        return ConditionCheck("접도", "fail", " / ".join(issues), is_blocking=True)
    return ConditionCheck("접도", "pass", f"도로폭 {road_width}m, 접도면 적합")

def _check_parking(dev_type: str, unit_count: int, total_gfa: float, land_area: float) -> ConditionCheck:
    from app.services.land_intelligence.comprehensive_analysis_service import PARKING_RULES
    rule = PARKING_RULES.get(dev_type, {"method": "per_unit", "ratio": 1.0})
    if rule["method"] == "per_unit":
        required = round(unit_count * rule.get("ratio", 1.0))
    else:
        required = round(total_gfa / rule.get("basis_sqm", 150))

    underground_capacity = int(land_area * UNDERGROUND_RATIO / PARKING_SQM_PER_SPACE)
    if underground_capacity >= required:
        return ConditionCheck("주차", "pass", f"필요 {required}대, 지하주차 약 {underground_capacity}대 확보 가능")
    if underground_capacity >= required * 0.7:
        return ConditionCheck("주차", "conditional", f"필요 {required}대, 지하주차 약 {underground_capacity}대 — 기계식주차 병행 검토")
    return ConditionCheck("주차", "conditional", f"필요 {required}대 > 지하추정 {underground_capacity}대 — 주차 확보 방안 필요")

def _check_daylighting(dev_type: str, zone_type: str, floor_count: int, building_area: float) -> ConditionCheck:
    if zone_type not in RESIDENTIAL_ZONES:
        return ConditionCheck("일조권", "pass", "상업/공업지역 — 일조권 사선 면제")
    if floor_count <= 2:
        return ConditionCheck("일조권", "pass", f"{floor_count}층 — 일조권 사선 영향 미미")

    building_height = floor_count * 3.3
    required_distance = building_height / 2
    return ConditionCheck(
        "일조권", "conditional",
        f"건물높이 약 {building_height:.0f}m → 북측 {required_distance:.0f}m 이격 필요 — 인접건물 확인 필요"
    )

def _check_setback(zone_type: str, land_area: float, effective_bcr: float) -> ConditionCheck:
    from app.services.permit.building_code_rules import ZONE_DEFAULTS
    defaults = ZONE_DEFAULTS.get(zone_type, {})
    setback = defaults.get("setback_m", 0)
    if setback <= 0:
        return ConditionCheck("건축선후퇴", "pass", "건축선 후퇴 불요")

    import math
    side = math.sqrt(land_area)
    effective_side = side - 2 * setback
    if effective_side <= 0:
        return ConditionCheck("건축선후퇴", "fail", f"후퇴 {setback}m 적용 시 건축 불가", is_blocking=True)
    effective_area = effective_side ** 2
    building_area = land_area * (effective_bcr / 100)
    if effective_area >= building_area:
        return ConditionCheck("건축선후퇴", "pass", f"후퇴 {setback}m 적용 후 건축면적 확보 가능")
    return ConditionCheck("건축선후퇴", "conditional", f"후퇴 {setback}m 적용 시 건축면적 제한 — 배치 검토 필요")

def _check_floors(dev_type: str, zone_type: str, calculated_floors: int) -> ConditionCheck:
    max_f = MAX_FLOORS.get(dev_type)
    if max_f and calculated_floors > max_f:
        return ConditionCheck(
            "층수제한", "fail",
            f"계획 {calculated_floors}층 > 상한 {max_f}층 ({dev_type})",
            is_blocking=True,
        )

    from app.services.permit.building_code_rules import ZONE_DEFAULTS
    defaults = ZONE_DEFAULTS.get(zone_type, {})
    max_height = defaults.get("max_height", 0)
    if max_height > 0:
        max_floors_from_height = int(max_height / 3.3)
        if calculated_floors > max_floors_from_height:
            return ConditionCheck(
                "층수제한", "fail",
                f"계획 {calculated_floors}층 > 높이제한 {max_height}m (약 {max_floors_from_height}층)",
                is_blocking=True,
            )

    return ConditionCheck("층수제한", "pass", f"계획 {calculated_floors}층 — 제한 이내")

def _check_special_conditions(dev_type: str, zone_type: str, land_area: float, total_gfa: float) -> ConditionCheck:
    from app.services.zoning.development_type_analyzer import ZONE_ALLOWED_BUILDINGS
    allowed = ZONE_ALLOWED_BUILDINGS.get(zone_type, [])

    bldg_type_name = BUILDING_TYPE_MAP.get(dev_type, "")
    issues = []
    for item in allowed:
        name = item.get("type_name", "")
        cond = item.get("conditions", "")
        if not cond or bldg_type_name not in name:
            continue

        if m := re.search(r"(\d+)층\s*이하", cond):
            int(m.group(1))
            issues.append(f"{name}: {cond}")
        if "바닥면적" in cond and (m := re.search(r"([\d,]+)㎡", cond)):
            limit = int(m.group(1).replace(",", ""))
            if total_gfa > limit:
                issues.append(f"{name}: 바닥면적 {total_gfa:.0f}m² > {limit}m²")
        if "주거비율" in cond:
            issues.append(f"주거비율 조건: {cond}")

    if issues:
        return ConditionCheck("조례특수조건", "conditional", " | ".join(issues))
    return ConditionCheck("조례특수조건", "pass", "특수 조건 없음")


# ── 메인 검증 함수 ──

def validate_development_feasibility(
    dev_type: str,
    type_name: str,
    zone_type: str,
    land_area: float,
    effective_far: float,
    effective_bcr: float,
    unit_count: int = 1,
    total_gfa: float = 0,
    floor_count: int = 1,
    road_width: float | None = None,
    road_frontage: float | None = None,
) -> FeasibilityResult:

    checks = [
        _check_lot_area(dev_type, land_area),
        _check_road(dev_type, road_width, road_frontage),
        _check_parking(dev_type, unit_count, total_gfa, land_area),
        _check_daylighting(dev_type, zone_type, floor_count, total_gfa ** 0.5 if total_gfa else 0),
        _check_setback(zone_type, land_area, effective_bcr),
        _check_floors(dev_type, zone_type, floor_count),
        _check_special_conditions(dev_type, zone_type, land_area, total_gfa),
    ]

    blocking = [c.detail for c in checks if c.is_blocking]
    has_fail = any(c.status == "fail" for c in checks)
    has_conditional = any(c.status in ("conditional", "unknown") for c in checks)

    if has_fail:
        status = FeasibilityStatus.FAIL
    elif has_conditional:
        status = FeasibilityStatus.CONDITIONAL
    else:
        status = FeasibilityStatus.PASS

    recommendations = []
    if any(c.rule == "주차" and c.status == "conditional" for c in checks):
        recommendations.append("기계식주차 또는 공동주차장 활용 검토")
    if any(c.rule == "일조권" and c.status == "conditional" for c in checks):
        recommendations.append("북측 인접건물 현황 현장 확인 필요")
    if any(c.rule == "접도" and c.status == "unknown" for c in checks):
        recommendations.append("접도 현황 현장 확인 필요")
    if land_area < MIN_LOT_AREA.get(dev_type, 0) * 1.2 and not has_fail:
        recommendations.append("최소 면적 근접 — 인접 필지 합필 검토")

    return FeasibilityResult(
        dev_type=dev_type,
        type_name=type_name,
        feasibility_status=status,
        conditions=checks,
        blocking_issues=blocking,
        recommendations=recommendations,
    )
