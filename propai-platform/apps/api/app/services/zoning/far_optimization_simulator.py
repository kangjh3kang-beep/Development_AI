"""용적률 최적화 시뮬레이터.

기부체납 + 친환경인증 + 공개공지 + 용도용적제 4가지 인센티브를 조합하여
최대 달성 가능 용적률과 최적 시나리오를 제안.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any

from app.services.zoning.far_incentive_calculator import (
    calculate as calc_donation_incentive,
    NATIONAL_FAR_LIMITS,
    ZONE_CATEGORY_MAP,
    ALPHA_COEFFICIENTS,
)

# ── 친환경 인증 인센티브 (녹색건축물법, 건축법 시행령 §6의2) ──

GSEED_BONUS_PCT: dict[str, float] = {
    "1등급(최우수)": 0.06,
    "2등급(우수)": 0.04,
    "3등급(우량)": 0.02,
    "4등급(일반)": 0.01,
}

ENERGY_GRADE_BONUS_PCT: dict[str, float] = {
    "1++등급": 0.12,
    "1+등급": 0.10,
    "1등급": 0.09,
    "2등급": 0.06,
    "3등급": 0.03,
}

GREEN_INCENTIVE_CAP = 0.15  # 친환경 인센티브 합산 상한: 기본용적률의 15%

# ── 공개공지 인센티브 (건축법 §43, 시행령 §27의2) ──

OPEN_SPACE_MIN_RATIO = 0.10       # 대지면적의 10% 이상
OPEN_SPACE_FAR_BONUS_PCT = 0.20   # 기본용적률의 20% 완화

# ── 용도용적제 (서울시 도시계획조례 §55의2) ──

USE_BASED_FAR: dict[str, dict[str, float]] = {
    "일반상업지역": {"상업": 800, "주거": 400, "업무": 700},
    "근린상업지역": {"상업": 600, "주거": 300, "업무": 500},
    "준주거지역": {"상업": 400, "주거": 300, "업무": 350},
    "중심상업지역": {"상업": 1200, "주거": 600, "업무": 1000},
}


# ── 개별 인센티브 계산기 ──

def calc_green_incentive(
    base_far: float,
    gseed_grade: str | None = None,
    energy_grade: str | None = None,
) -> dict[str, Any]:
    gseed = base_far * GSEED_BONUS_PCT.get(gseed_grade or "", 0)
    energy = base_far * ENERGY_GRADE_BONUS_PCT.get(energy_grade or "", 0)
    raw_total = gseed + energy
    capped_total = min(raw_total, base_far * GREEN_INCENTIVE_CAP)
    return {
        "gseed_grade": gseed_grade,
        "gseed_bonus": round(gseed, 2),
        "energy_grade": energy_grade,
        "energy_bonus": round(energy, 2),
        "raw_total": round(raw_total, 2),
        "capped_total": round(capped_total, 2),
        "is_capped": raw_total > base_far * GREEN_INCENTIVE_CAP,
        "legal_basis": "녹색건축물 조성 지원법, 건축법 시행령 제6조의2",
    }

def calc_open_space_incentive(
    base_far: float,
    open_space_ratio: float = 0,
) -> dict[str, Any]:
    eligible = open_space_ratio >= OPEN_SPACE_MIN_RATIO
    bonus = base_far * OPEN_SPACE_FAR_BONUS_PCT if eligible else 0
    return {
        "open_space_ratio": open_space_ratio,
        "eligible": eligible,
        "bonus": round(bonus, 2),
        "reason": f"공개공지 {open_space_ratio*100:.0f}%" + (" >= 10% 충족" if eligible else " < 10% 미달"),
        "legal_basis": "건축법 제43조, 시행령 제27조의2",
    }

def calc_use_based_far(
    zone_type: str,
    use_mix: dict[str, float],
) -> dict[str, Any]:
    rates = USE_BASED_FAR.get(zone_type)
    if not rates:
        return {"applicable": False, "reason": f"{zone_type}: 용도용적제 비적용"}
    weighted = sum(rates.get(use, 0) * ratio for use, ratio in use_mix.items())
    breakdown = {use: {"ratio": round(ratio, 2), "far": rates.get(use, 0)} for use, ratio in use_mix.items()}
    return {
        "applicable": True,
        "weighted_far": round(weighted, 1),
        "breakdown": breakdown,
        "legal_basis": "서울시 도시계획 조례 제55조의2",
    }


# ── 시나리오 정의 ──

@dataclass
class ScenarioInput:
    name: str
    donation_pct: float = 0
    gseed_grade: str | None = None
    energy_grade: str | None = None
    open_space_ratio: float = 0
    use_mix: dict[str, float] | None = None

DEFAULT_SCENARIOS = [
    ScenarioInput("기본 (인센티브 없음)"),
    ScenarioInput("기부체납 10%", donation_pct=10),
    ScenarioInput("기부체납 15%", donation_pct=15),
    ScenarioInput("기부체납 20%", donation_pct=20),
    ScenarioInput("에너지효율 1등급", energy_grade="1등급"),
    ScenarioInput("에너지효율 1++등급", energy_grade="1++등급"),
    ScenarioInput("G-SEED 최우수 + 에너지 1등급", gseed_grade="1등급(최우수)", energy_grade="1등급"),
    ScenarioInput("공개공지 10%", open_space_ratio=0.10),
    ScenarioInput("기부체납 15% + 에너지 1등급", donation_pct=15, energy_grade="1등급"),
    ScenarioInput("기부체납 15% + G-SEED 최우수 + 에너지 1++", donation_pct=15, gseed_grade="1등급(최우수)", energy_grade="1++등급"),
    ScenarioInput("기부체납 20% + 친환경 + 공개공지", donation_pct=20, gseed_grade="1등급(최우수)", energy_grade="1++등급", open_space_ratio=0.10),
]


# ── 메인 시뮬레이션 ──

def simulate_far_scenarios(
    zone_type: str,
    ordinance_far: float,
    national_far: float | None = None,
    land_area_sqm: float = 0,
) -> dict[str, Any]:
    cap_far = national_far if national_far is not None else NATIONAL_FAR_LIMITS.get(zone_type, 250.0)
    base_far = ordinance_far
    category = ZONE_CATEGORY_MAP.get(zone_type, "주거")
    alpha = ALPHA_COEFFICIENTS.get(category, 1.0)

    # 용도용적제 적용 가능한 지역이면 용도별 시나리오 추가
    scenarios = list(DEFAULT_SCENARIOS)
    if zone_type in USE_BASED_FAR:
        scenarios.append(ScenarioInput(
            f"용도용적제 (상업60%+주거40%)",
            use_mix={"상업": 0.6, "주거": 0.4},
        ))
        scenarios.append(ScenarioInput(
            f"용도용적제 (상업40%+주거50%+업무10%)",
            use_mix={"상업": 0.4, "주거": 0.5, "업무": 0.1},
        ))

    results = []
    for sc in scenarios:
        # 1. 기부체납
        donation_bonus = 0.0
        if sc.donation_pct > 0:
            donation_result = calc_donation_incentive(
                zone_type=zone_type,
                ordinance_far=base_far,
                donation_ratio_pct=sc.donation_pct,
                national_far=cap_far,
            )
            donation_bonus = donation_result.get("incentive_far", 0)

        # 2. 친환경
        green = calc_green_incentive(base_far, sc.gseed_grade, sc.energy_grade)
        green_bonus = green["capped_total"]

        # 3. 공개공지
        open_space = calc_open_space_incentive(base_far, sc.open_space_ratio)
        open_bonus = open_space["bonus"]

        # 4. 용도용적제
        use_far_result = None
        if sc.use_mix:
            use_far_result = calc_use_based_far(zone_type, sc.use_mix)

        # 합산 (용도용적제는 별도 체계)
        if use_far_result and use_far_result.get("applicable"):
            achieved = min(use_far_result["weighted_far"], cap_far)
        else:
            total_incentive = donation_bonus + green_bonus + open_bonus
            achieved = min(base_far + total_incentive, cap_far)

        gain_pct = ((achieved - base_far) / base_far * 100) if base_far > 0 else 0

        incentive_items = []
        if donation_bonus > 0:
            incentive_items.append({"source": "기부체납", "bonus": round(donation_bonus, 1), "detail": f"비율 {sc.donation_pct}%"})
        if green_bonus > 0:
            incentive_items.append({"source": "친환경인증", "bonus": round(green_bonus, 1), "detail": f"G-SEED {sc.gseed_grade or '-'}, 에너지 {sc.energy_grade or '-'}"})
        if open_bonus > 0:
            incentive_items.append({"source": "공개공지", "bonus": round(open_bonus, 1), "detail": f"비율 {sc.open_space_ratio*100:.0f}%"})
        if use_far_result and use_far_result.get("applicable"):
            incentive_items.append({"source": "용도용적제", "bonus": 0, "detail": f"가중평균 {use_far_result['weighted_far']}%"})

        gfa_increase = land_area_sqm * (achieved - base_far) / 100 if land_area_sqm > 0 else 0

        results.append({
            "scenario_name": sc.name,
            "base_far": base_far,
            "achieved_far": round(achieved, 1),
            "cap_far": cap_far,
            "gain_from_base_pct": round(gain_pct, 1),
            "is_capped": achieved >= cap_far,
            "incentive_items": incentive_items,
            "total_incentive": round(achieved - base_far, 1),
            "gfa_increase_sqm": round(gfa_increase, 1),
            "donation_pct": sc.donation_pct,
        })

    # 파레토 최적: 최대 FAR 달성 시나리오
    max_far_scenario = max(results, key=lambda r: r["achieved_far"])

    # 추천: 기부체납 15% 이하에서 최대 FAR
    moderate_results = [r for r in results if r["donation_pct"] <= 15]
    recommended = max(moderate_results, key=lambda r: r["achieved_far"]) if moderate_results else max_far_scenario

    return {
        "base_far": base_far,
        "cap_far": cap_far,
        "max_achievable_far": max_far_scenario["achieved_far"],
        "scenarios": results,
        "recommended_scenario": recommended["scenario_name"],
        "recommended_reason": f"기부체납 {recommended['donation_pct']}% 이하에서 최대 {recommended['achieved_far']}% 달성",
        "use_based_far_applicable": zone_type in USE_BASED_FAR,
    }
