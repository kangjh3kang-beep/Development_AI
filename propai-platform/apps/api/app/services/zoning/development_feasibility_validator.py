"""개발가능유형 실효 검증 엔진.

용도지역 필터링 후 각 개발유형의 법적 조건 부합 여부를 7개 항목으로 검증.
결과: 적합(pass) / 조건부(conditional) / 부적합(fail)
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any

from app.services.legal.legal_limit import LegalLimit, PracticeLimit

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

# ── 최소 대지면적 — **법정이 아니다** ─────────────────────────────────────────
# ★2026-08-23 교정. 종전에는 원시 숫자 15개였고, 미달하면 `부적합`(blocking) 이었다.
#   라이브 실측: 4,000㎡ 아파트 부지가 `4000m² < 5000m² (최소) — 면적 부족` 으로 **부적합**.
#   그 5,000㎡ 의 근거를 코드가 대지 못한다 — `MAX_FLOORS`={"M10":3} 과 **같은 결함**이다.
#
# 법정 최소 대지면적은 **용도지역** 기준이지 개발유형 기준이 아니다
# (건축법 §57·시행령 §80 대지의 분할 제한 — 주거 60㎡·상업 150㎡·공업 150㎡·녹지 200㎡,
#  그 위에 조례가 얹힌다). 아래 값들은 그 축이 아니라 **사업 규모 감각**이다.
#   → `PracticeLimit` 로 둬서 **조건부까지만** 내게 한다(부적합을 낼 자격이 없다).
_LOT_PRACTICE = "플랫폼 실무기준 — 사업유형별 권장 최소 사업규모(법정 최소대지면적 아님)"

MIN_LOT_AREA: dict[str, PracticeLimit] = {
    # ★`note` 는 두지 않는다 — 판정 문구는 `basis` 만 싣기 때문에 아무도 읽지 않는다.
    #   읽히지 않는 데이터를 두면 "있으니 검증됐다"는 착시만 남는다(소비처 0).
    code: PracticeLimit(v, source=_LOT_PRACTICE)
    for code, v in {
        "M01": 5000, "M02": 5000, "M03": 3000, "M04": 3000, "M05": 1000,
        "M06": 660, "M07": 1000, "M08": 300, "M09": 1000, "M10": 90,
        "M11": 200, "M12": 330, "M13": 150, "M14": 1000, "M15": 3000,
    }.items()
}

# ── 접도 — **법정과 실무를 가른다** ───────────────────────────────────────────
# ★법정 접도 규정은 **개발유형이 아니라 연면적**을 키로 삼는다. 종전 표는 키 자체가 틀렸고,
#   그래서 표에 없는 유형(M03·M04·M05·M14·M15)은 접도 1m 라도 **"접도 제한 없음" 통과**였다
#   (라이브 실측: M03 도로폭 3m·접도 1m → `pass`). 미등재가 면죄부가 됐다.
ROAD_FRONTAGE_STATUTE = LegalLimit(
    2,
    law="건축법 §44①",
    note="건축물의 대지는 2m 이상이 도로에 접해야 한다(같은 항 단서의 예외 있음)",
)

#: 건축법 시행령 §28② 가 강화 규정을 적용하는 연면적 문턱(㎡).
ROAD_STRICT_GFA_THRESHOLD_SQM = 2000

ROAD_STRICT_STATUTE: dict[str, LegalLimit] = {
    "road_width": LegalLimit(
        6, law="건축법 시행령 §28②", note="연면적 합계 2,000㎡ 이상 — 너비 6m 이상 도로"
    ),
    "frontage": LegalLimit(
        4, law="건축법 시행령 §28②", note="연면적 합계 2,000㎡ 이상 — 4m 이상 접도"
    ),
}

# 아래는 위 법정선을 **넘어서는** 사업 실무 권장치다(진입·공사차량·분양성).
# 법정이 아니므로 미달해도 `조건부` 까지만 낸다.
_ROAD_PRACTICE = "플랫폼 실무기준 — 사업유형별 권장 진입도로(법정 접도기준 아님)"

ROAD_REQUIREMENT: dict[str, dict[str, PracticeLimit]] = {
    code: {
        "road_width": PracticeLimit(w, source=_ROAD_PRACTICE, note=f"{code} 권장 도로폭"),
        "frontage": PracticeLimit(f, source=_ROAD_PRACTICE, note=f"{code} 권장 접도면"),
    }
    for code, (w, f) in {
        "M01": (6, 4), "M02": (6, 4), "M06": (6, 4), "M07": (8, 6),
        "M08": (6, 4), "M09": (8, 6), "M10": (4, 2), "M11": (4, 2),
        "M12": (4, 2), "M13": (4, 2),
    }.items()
}

# ── 유형별 층수 상한 — **근거 없이는 등재하지 않는다** ────────────────────────
# ★2026-08-23 교정. 종전 값: {"M10": 3, "M11": 3, "M12": 4, "M13": None}.
#   `M10`(단독주택)·`M11`(전원주택)에 **3층**이 근거 없이 박혀 있었고, 그것이 자연녹지
#   부지(건폐 20%·4층)에서 단독주택 계획을 4층→3층으로 깎아 용적률을 80%→60%로 내렸다.
#   건축법 시행령 별표1 제1호를 보면 **3개 층 이하는 다중주택(나목)·다가구주택(다목)** 이고,
#   **단독주택(가목)에는 유형 자체의 층수 제한이 없다** — 값이 틀렸다.
#   (용도지역 층수 제한 — 자연녹지 4층 등 — 은 실효 용적률이 이미 담당한다.)
#
# ★★"등재되지 않음"과 "제한 없음"은 **다르다**.
#     · 등재 + value=None → 법이 제한하지 않는다(근거 있음)
#     · **미등재**        → 근거를 확인하지 못했다 → 제약을 적용하지 않되 **그 사실을 드러낸다**
#   근거 미확인을 조용히 "제한 없음"으로 두면, 종전과 반대 방향의 같은 잘못이 된다.
MAX_FLOORS: dict[str, LegalLimit] = {
    "M10": LegalLimit(
        None,
        law="건축법 시행령 별표1 제1호 가목",
        note="단독주택 — 유형 자체 층수 제한 없음(3개 층 이하는 다중·다가구주택에 한함)",
    ),
    "M11": LegalLimit(
        None,
        law="건축법 시행령 별표1 제1호 가목",
        note="전원주택은 법정 용어가 아닌 단독주택의 일종 — M10 과 같은 근거",
    ),
    "M12": LegalLimit(
        4,
        law="건축법 시행령 별표1 제2호 나목",
        note="타운하우스를 연립주택으로 본 값 — 4개 층 이하",
    ),
    # ★M13(도시형생활주택)은 **등재하지 않는다**: 주택법상 유형(원룸형·단지형연립·단지형다세대)
    #   마다 층수 규율이 달라 단일 상한을 확정할 수 없다. 근거를 확정하기 전에는 값을 만들지
    #   않는다 — 종전 `None`(=제한 없음)은 확정된 사실이 아니라 **미확인의 위장**이었다.
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

# ★건축법 시행령 §61(일조 등의 확보를 위한 건축물의 높이 제한, 정북일조 사선제한)의 적용대상은
#   '전용주거지역 또는 일반주거지역'에 한정된다(준주거지역은 대상 아님). RESIDENTIAL_ZONES는
#   다른 검증(예: 주차·건축선후퇴)과의 하위호환을 위해 준주거를 포함한 그대로 두고, 일조권
#   사선검토 여부만 이 부분집합으로 별도 판별한다(P0-4/RC8).
DAYLIGHTING_APPLICABLE_ZONES = RESIDENTIAL_ZONES - {"준주거지역"}

PARKING_SQM_PER_SPACE = 30  # 지하주차장 1대당 약 30m²
UNDERGROUND_RATIO = 0.70     # 대지면적의 약 70%를 지하주차장으로 활용 가능

# ── 검증 함수 ──

def _check_lot_area(dev_type: str, land_area: float) -> ConditionCheck:
    """대지면적 — **실무 권장치 미달은 부적합이 아니다**.

    ★2026-08-23 교정. 종전에는 근거 없는 숫자에 미달하면 `부적합`(blocking) 이라
    개발유형이 화면에서 통째로 탈락했다(행 `opacity-50`). 법정 최소대지면적은
    **용도지역** 기준이므로(건축법 §57·시행령 §80 및 조례) 이 표로는 위법을 단정할 수 없다.
    """
    limit = MIN_LOT_AREA.get(dev_type)
    if limit is None:
        # ★미등재 = 기준 미확인. `MAX_FLOORS` 가 배운 것 — 조용히 통과시키면 "제한 없음"과
        #   구분되지 않는다.
        return ConditionCheck(
            "대지면적", "unknown",
            f"{land_area:.0f}m² — 이 유형({dev_type})의 최소 사업규모 기준 미확인",
        )
    if limit.unlimited:
        # ★현재 표에는 `value=None` 항목이 없어 **도달하지 않는다**(변이가 생존하는 이유).
        #   그래도 남기는 이유: "이 유형에는 규모 기준을 두지 않는다"를 표에 적을 길이
        #   있어야, 다음 사람이 그 뜻으로 항목을 지우지 않는다(미등재=미확인과 구분).
        return ConditionCheck("대지면적", "pass", f"{land_area:.0f}m² — 기준 없음({limit.basis})")
    min_area = float(limit.value)
    if land_area >= min_area:
        return ConditionCheck("대지면적", "pass", f"{land_area:.0f}m² >= {min_area:.0f}m² (권장 최소)")
    # ★법정이 아니므로 blocking 하지 않는다 — 사업성 경고이지 위법 판정이 아니다.
    return ConditionCheck(
        "대지면적", "conditional",
        f"{land_area:.0f}m² < {min_area:.0f}m² (권장 최소) — 사업규모 부족 검토 필요"
        f" · {limit.basis}",
    )

def _check_road(
    dev_type: str,
    road_width: float | None,
    road_frontage: float | None,
    total_gfa: float = 0,
) -> ConditionCheck:
    """접도 — **법정선을 먼저 보고, 실무 권장치는 조건부로 본다**.

    ★2026-08-23 교정. 종전에는 개발유형 표에 없으면 `"접도 제한 없음"` 으로 **통과**시켰다.
    법정 접도 규정은 유형이 아니라 **연면적**을 키로 삼으므로(건축법 §44①·시행령 §28②)
    표의 부재가 곧 규제의 부재가 아니다 — 라이브에서 M03 이 접도 1m 로 통과하고 있었다.
    """
    if road_width is None and road_frontage is None:
        return ConditionCheck("접도", "unknown", "접도 데이터 미확인 — 현장 확인 필요")

    # ① 법정선 — 위반은 **위법**이므로 부적합을 낼 자격이 있다.
    strict = total_gfa >= ROAD_STRICT_GFA_THRESHOLD_SQM
    violations: list[str] = []
    if strict:
        w_lim, f_lim = ROAD_STRICT_STATUTE["road_width"], ROAD_STRICT_STATUTE["frontage"]
        if road_width is not None and road_width < float(w_lim.value):
            violations.append(f"도로폭 {road_width}m < {w_lim.value:g}m ({w_lim.law})")
        if road_frontage is not None and road_frontage < float(f_lim.value):
            violations.append(f"접도면 {road_frontage}m < {f_lim.value:g}m ({f_lim.law})")
    base = ROAD_FRONTAGE_STATUTE
    if road_frontage is not None and road_frontage < float(base.value):
        violations.append(f"접도면 {road_frontage}m < {base.value:g}m ({base.law})")
    if violations:
        return ConditionCheck("접도", "fail", " / ".join(violations), is_blocking=True)

    # ② 실무 권장치 — 미달해도 위법이 아니므로 `조건부` 까지만.
    req = ROAD_REQUIREMENT.get(dev_type)
    if req is None:
        return ConditionCheck(
            "접도", "pass",
            f"도로폭 {road_width}m, 접도면 {road_frontage}m — 법정 접도기준 충족"
            f"({base.law}) · 이 유형({dev_type})의 실무 권장치는 미등재",
        )
    shortfalls = []
    if road_width is not None and road_width < float(req["road_width"].value):
        shortfalls.append(f"도로폭 {road_width}m < 권장 {req['road_width'].value:g}m")
    if road_frontage is not None and road_frontage < float(req["frontage"].value):
        shortfalls.append(f"접도면 {road_frontage}m < 권장 {req['frontage'].value:g}m")
    if shortfalls:
        return ConditionCheck(
            "접도", "conditional",
            " / ".join(shortfalls) + f" — 법정선({base.law})은 충족 · {req['road_width'].basis}",
        )
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
    """일조권(건축법 §61 정북일조 사선제한) 검토 — 적용대상은 전용·일반주거지역 한정.

    ★P0-4(RC8) 수정: 과거엔 비주거 전량(녹지·관리·농림·자연환경보전 포함)을 "상업/공업지역
    면제"로 하드코딩 라벨링해, 자연녹지 등에서 사실과 다른 서술이 노출됐다(라이브 재현). §61은
    전용·일반주거지역에만 적용되고 준주거지역도 적용대상이 아니므로(DAYLIGHTING_APPLICABLE_ZONES),
    비적용 사유를 용도지역 실제 성격(상업/공업 vs 녹지·관리·농림·보전 등)에 맞게 정확히 서술한다.
    """
    if zone_type not in DAYLIGHTING_APPLICABLE_ZONES:
        from app.services.zoning.special_parcel import _zone_family
        family = _zone_family(zone_type)
        if family in ("상업", "공업") or zone_type == "준주거지역":
            note = f"{zone_type or '해당 용도지역'} — 건축법 §61 정북일조 사선제한 비적용(상업/공업지역·준주거지역은 적용대상 아님)"
        else:
            note = f"{zone_type or '해당 용도지역'} — 건축법 §61 정북일조 사선제한 비적용(전용·일반주거지역 한정 적용)"
        return ConditionCheck("일조권", "pass", note)
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
    limit = MAX_FLOORS.get(dev_type)
    if limit is None:
        # ★미등재 = 근거 미확인. 제약을 **적용하지 않되 침묵하지도 않는다**
        #   (조용히 통과시키면 "제한 없음"과 구분되지 않는다).
        return ConditionCheck(
            "층수제한", "unknown",
            f"계획 {calculated_floors}층 — 이 유형({dev_type})의 층수 상한 근거 미확인",
        )
    if not limit.unlimited and calculated_floors > int(limit.value):
        return ConditionCheck(
            "층수제한", "fail",
            f"계획 {calculated_floors}층 > 상한 {limit.value:g}층 ({limit.law})",
            is_blocking=True,
        )
    if limit.unlimited:
        # 법이 이 유형을 제한하지 않는다 — 근거와 함께 통과시킨다(용도지역 제한은 별도 축).
        return ConditionCheck(
            "층수제한", "pass",
            f"계획 {calculated_floors}층 — 유형 층수 제한 없음({limit.law})",
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
        _check_road(dev_type, road_width, road_frontage, total_gfa),
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
    _lot = MIN_LOT_AREA.get(dev_type)
    _lot_min = float(_lot.value) if _lot is not None and not _lot.unlimited else 0.0
    if _lot_min > 0 and land_area < _lot_min * 1.2 and not has_fail:
        recommendations.append("최소 면적 근접 — 인접 필지 합필 검토")

    return FeasibilityResult(
        dev_type=dev_type,
        type_name=type_name,
        feasibility_status=status,
        conditions=checks,
        blocking_issues=blocking,
        recommendations=recommendations,
    )
