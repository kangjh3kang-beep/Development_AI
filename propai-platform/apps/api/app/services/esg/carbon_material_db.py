"""건축자재 탄소배출계수 데이터베이스.

ICE Database (University of Bath) v3.0 + IPCC AR6 기반.
공종코드 → 주요자재 → 탄소배출계수(kgCO2eq/unit) 매핑.

References:
  - ICE v3.0: Inventory of Carbon and Energy, University of Bath (2019)
  - IPCC AR6 WG3: Climate Change 2022 — Mitigation (Chapter 11)
"""

from __future__ import annotations

from typing import Any

# ── 자재별 탄소배출계수 ──────────────────────────────────────────────

MATERIAL_CARBON_DB: dict[str, dict[str, Any]] = {
    # 구조
    "concrete_35mpa": {
        "name": "레미콘 35MPa",
        "unit": "m3",
        "embodied_carbon": 350,
        "source": "ICE v3.0",
        "category": "구조",
    },
    "concrete_25mpa": {
        "name": "레미콘 25MPa",
        "unit": "m3",
        "embodied_carbon": 290,
        "source": "ICE v3.0",
        "category": "구조",
    },
    "rebar_steel": {
        "name": "철근 SD400",
        "unit": "kg",
        "embodied_carbon": 1.99,
        "source": "ICE v3.0",
        "category": "구조",
    },
    "structural_steel": {
        "name": "구조용 H형강",
        "unit": "kg",
        "embodied_carbon": 1.55,
        "source": "ICE v3.0",
        "category": "구조",
    },
    "formwork_plywood": {
        "name": "합판 거푸집",
        "unit": "m2",
        "embodied_carbon": 4.5,
        "source": "ICE v3.0",
        "category": "구조",
    },
    # 마감
    "brick_common": {
        "name": "일반 벽돌",
        "unit": "kg",
        "embodied_carbon": 0.24,
        "source": "ICE v3.0",
        "category": "마감",
    },
    "glass_float": {
        "name": "판유리",
        "unit": "kg",
        "embodied_carbon": 1.44,
        "source": "ICE v3.0",
        "category": "마감",
    },
    "aluminum_window": {
        "name": "알루미늄 창호",
        "unit": "kg",
        "embodied_carbon": 8.24,
        "source": "ICE v3.0",
        "category": "마감",
    },
    "gypsum_board": {
        "name": "석고보드",
        "unit": "kg",
        "embodied_carbon": 0.12,
        "source": "ICE v3.0",
        "category": "마감",
    },
    "ceramic_tile": {
        "name": "자기질 타일",
        "unit": "kg",
        "embodied_carbon": 0.78,
        "source": "ICE v3.0",
        "category": "마감",
    },
    # 단열
    "xps_insulation": {
        "name": "XPS 단열재",
        "unit": "kg",
        "embodied_carbon": 3.29,
        "source": "ICE v3.0",
        "category": "단열",
    },
    "eps_insulation": {
        "name": "EPS 단열재",
        "unit": "kg",
        "embodied_carbon": 3.29,
        "source": "ICE v3.0",
        "category": "단열",
    },
    # 방수
    "waterproofing_membrane": {
        "name": "방수 시트",
        "unit": "m2",
        "embodied_carbon": 2.5,
        "source": "IPCC AR6",
        "category": "방수",
    },
    # 설비
    "copper_pipe": {
        "name": "동관",
        "unit": "kg",
        "embodied_carbon": 2.71,
        "source": "ICE v3.0",
        "category": "설비",
    },
    "pvc_pipe": {
        "name": "PVC 배관",
        "unit": "kg",
        "embodied_carbon": 3.1,
        "source": "ICE v3.0",
        "category": "설비",
    },
    # 저탄소 대체재
    "low_carbon_concrete_35mpa": {
        "name": "저탄소 레미콘 35MPa (고로슬래그 40%)",
        "unit": "m3",
        "embodied_carbon": 210,
        "source": "ICE v3.0 + 보정",
        "category": "구조",
    },
    "recycled_rebar_steel": {
        "name": "재활용 철근 (EAF 70%)",
        "unit": "kg",
        "embodied_carbon": 0.84,
        "source": "ICE v3.0 + 보정",
        "category": "구조",
    },
}

# ── 건물유형별 ㎡당 표준 자재 사용량 ─────────────────────────────────

BUILDING_MATERIAL_INTENSITY: dict[str, dict[str, float]] = {
    "아파트": {
        "concrete_35mpa": 0.45,           # m3/㎡
        "rebar_steel": 75,                # kg/㎡
        "formwork_plywood": 2.8,          # m2/㎡
        "brick_common": 25,               # kg/㎡
        "glass_float": 3.5,               # kg/㎡
        "aluminum_window": 1.2,           # kg/㎡
        "gypsum_board": 8.0,              # kg/㎡
        "ceramic_tile": 5.0,              # kg/㎡
        "xps_insulation": 1.5,            # kg/㎡
        "waterproofing_membrane": 0.15,   # m2/㎡
        "copper_pipe": 0.8,               # kg/㎡
        "pvc_pipe": 1.2,                  # kg/㎡
    },
    "공동주택": {
        "concrete_35mpa": 0.45,
        "rebar_steel": 75,
        "formwork_plywood": 2.8,
        "brick_common": 25,
        "glass_float": 3.5,
        "aluminum_window": 1.2,
        "gypsum_board": 8.0,
        "ceramic_tile": 5.0,
        "xps_insulation": 1.5,
        "waterproofing_membrane": 0.15,
        "copper_pipe": 0.8,
        "pvc_pipe": 1.2,
    },
    "다세대주택": {
        "concrete_25mpa": 0.38,
        "rebar_steel": 60,
        "formwork_plywood": 2.5,
        "brick_common": 35,
        "glass_float": 2.5,
        "aluminum_window": 0.9,
        "gypsum_board": 7.0,
        "ceramic_tile": 4.5,
        "xps_insulation": 1.2,
        "waterproofing_membrane": 0.12,
        "copper_pipe": 0.6,
        "pvc_pipe": 1.0,
    },
    "오피스텔": {
        "concrete_35mpa": 0.50,
        "rebar_steel": 80,
        "formwork_plywood": 3.0,
        "brick_common": 15,
        "glass_float": 6.0,
        "aluminum_window": 2.0,
        "gypsum_board": 10.0,
        "ceramic_tile": 4.0,
        "xps_insulation": 1.8,
        "waterproofing_membrane": 0.12,
        "copper_pipe": 1.0,
        "pvc_pipe": 1.5,
    },
    "근린생활시설": {
        "concrete_35mpa": 0.40,
        "rebar_steel": 65,
        "formwork_plywood": 2.5,
        "brick_common": 20,
        "glass_float": 5.0,
        "aluminum_window": 1.8,
        "gypsum_board": 9.0,
        "ceramic_tile": 6.0,
        "xps_insulation": 1.3,
        "waterproofing_membrane": 0.10,
        "copper_pipe": 0.7,
        "pvc_pipe": 1.3,
    },
}

# ── 운영 에너지 강도 (kWh/㎡/년) ─────────────────────────────────────

OPERATIONAL_ENERGY_INTENSITY: dict[str, float] = {
    "아파트": 120.0,
    "공동주택": 120.0,
    "다세대주택": 110.0,
    "오피스텔": 150.0,
    "근린생활시설": 180.0,
}

# 한국 전력 탄소배출계수 (kgCO2/kWh, 2023 기준)
GRID_EMISSION_FACTOR_KR = 0.4781

# ── 저탄소 자재 대체 매핑 ─────────────────────────────────────────────

LOW_CARBON_ALTERNATIVES: dict[str, str] = {
    "concrete_35mpa": "low_carbon_concrete_35mpa",
    "rebar_steel": "recycled_rebar_steel",
}

# ── G-SEED 등급 기준 (kgCO2eq/㎡, 전생애 50년) ──────────────────────

GSEED_GRADE_THRESHOLDS: dict[str, dict[str, float]] = {
    "아파트": {
        "1등급(최우수)": 800,
        "2등급(우수)": 1000,
        "3등급(우량)": 1200,
        "4등급(일반)": 1500,
    },
    "근린생활시설": {
        "1등급(최우수)": 1000,
        "2등급(우수)": 1300,
        "3등급(우량)": 1600,
        "4등급(일반)": 2000,
    },
}


def calculate_material_carbon(
    building_type: str,
    total_gfa_sqm: float,
    custom_quantities: dict[str, float] | None = None,
) -> dict[str, Any]:
    """건물유형과 연면적에 대해 자재별 Embodied Carbon을 상세 계산한다.

    Args:
        building_type: 건물유형 (아파트, 오피스텔, 근린생활시설 등)
        total_gfa_sqm: 총 연면적(㎡)
        custom_quantities: 사용자 지정 자재 물량 (자재키 → 물량). None이면 표준 원단위 사용.

    Returns:
        자재별 탄소 상세 내역 + 합계
    """
    intensity = BUILDING_MATERIAL_INTENSITY.get(
        building_type,
        BUILDING_MATERIAL_INTENSITY.get("아파트", {}),
    )

    breakdown: list[dict[str, Any]] = []
    total_embodied = 0.0

    materials = custom_quantities if custom_quantities else {
        mat_key: rate * total_gfa_sqm
        for mat_key, rate in intensity.items()
    }

    for mat_key, quantity in materials.items():
        mat_info = MATERIAL_CARBON_DB.get(mat_key)
        if not mat_info:
            continue
        carbon = quantity * mat_info["embodied_carbon"]
        total_embodied += carbon
        breakdown.append({
            "material_key": mat_key,
            "name": mat_info["name"],
            "unit": mat_info["unit"],
            "quantity": round(quantity, 2),
            "embodied_carbon_factor": mat_info["embodied_carbon"],
            "carbon_kgCO2eq": round(carbon, 1),
            "source": mat_info["source"],
            "category": mat_info["category"],
        })

    # 카테고리별 소계
    category_totals: dict[str, float] = {}
    for item in breakdown:
        cat = item["category"]
        category_totals[cat] = category_totals.get(cat, 0) + item["carbon_kgCO2eq"]

    return {
        "building_type": building_type,
        "total_gfa_sqm": total_gfa_sqm,
        "total_embodied_carbon_kgCO2eq": round(total_embodied, 1),
        "embodied_carbon_per_sqm": round(total_embodied / max(total_gfa_sqm, 1), 2),
        "material_breakdown": breakdown,
        "category_totals": {k: round(v, 1) for k, v in category_totals.items()},
    }


def calculate_operational_carbon(
    building_type: str,
    total_gfa_sqm: float,
    years: int = 30,
) -> dict[str, Any]:
    """운영 단계(B6) 탄소배출량 계산.

    Args:
        building_type: 건물유형
        total_gfa_sqm: 연면적(㎡)
        years: 운영기간(년). 기본 30년.
    """
    energy_intensity = OPERATIONAL_ENERGY_INTENSITY.get(building_type, 120.0)
    annual_energy_kwh = total_gfa_sqm * energy_intensity
    annual_carbon = annual_energy_kwh * GRID_EMISSION_FACTOR_KR
    total_carbon = annual_carbon * years

    return {
        "energy_intensity_kwh_per_sqm": energy_intensity,
        "annual_energy_kwh": round(annual_energy_kwh, 0),
        "annual_carbon_kgCO2eq": round(annual_carbon, 1),
        "total_operational_carbon_kgCO2eq": round(total_carbon, 1),
        "operational_carbon_per_sqm": round(total_carbon / max(total_gfa_sqm, 1), 2),
        "years": years,
        "grid_emission_factor": GRID_EMISSION_FACTOR_KR,
    }


def calculate_low_carbon_scenario(
    building_type: str,
    total_gfa_sqm: float,
) -> dict[str, Any]:
    """저탄소 자재 대체 시나리오 시뮬레이션.

    일반 자재 대비 저탄소 대체재 사용 시 감소량을 산출한다.
    """
    baseline = calculate_material_carbon(building_type, total_gfa_sqm)
    intensity = BUILDING_MATERIAL_INTENSITY.get(
        building_type,
        BUILDING_MATERIAL_INTENSITY.get("아파트", {}),
    )

    # 대체 가능한 자재만 교체한 물량
    alt_quantities: dict[str, float] = {}
    for mat_key, rate in intensity.items():
        alt_key = LOW_CARBON_ALTERNATIVES.get(mat_key, mat_key)
        if alt_key in MATERIAL_CARBON_DB:
            alt_quantities[alt_key] = rate * total_gfa_sqm
        else:
            alt_quantities[mat_key] = rate * total_gfa_sqm

    alt_result = calculate_material_carbon(building_type, total_gfa_sqm, alt_quantities)

    reduction = baseline["total_embodied_carbon_kgCO2eq"] - alt_result["total_embodied_carbon_kgCO2eq"]
    reduction_pct = (
        (reduction / baseline["total_embodied_carbon_kgCO2eq"]) * 100
        if baseline["total_embodied_carbon_kgCO2eq"] > 0
        else 0
    )

    substitutions = []
    for original, alt in LOW_CARBON_ALTERNATIVES.items():
        orig_info = MATERIAL_CARBON_DB.get(original, {})
        alt_info = MATERIAL_CARBON_DB.get(alt, {})
        if orig_info and alt_info:
            substitutions.append({
                "original": orig_info.get("name", original),
                "alternative": alt_info.get("name", alt),
                "original_factor": orig_info["embodied_carbon"],
                "alternative_factor": alt_info["embodied_carbon"],
                "reduction_pct": round(
                    (1 - alt_info["embodied_carbon"] / orig_info["embodied_carbon"]) * 100, 1
                ),
            })

    return {
        "baseline_carbon_kgCO2eq": baseline["total_embodied_carbon_kgCO2eq"],
        "low_carbon_scenario_kgCO2eq": alt_result["total_embodied_carbon_kgCO2eq"],
        "reduction_kgCO2eq": round(reduction, 1),
        "reduction_pct": round(reduction_pct, 1),
        "substitutions": substitutions,
    }


def predict_gseed_grade(
    building_type: str,
    lifecycle_carbon_per_sqm: float,
) -> dict[str, str]:
    """전생애 탄소배출 밀도(kgCO2eq/㎡)로 G-SEED 등급을 예측한다."""
    thresholds = GSEED_GRADE_THRESHOLDS.get(
        building_type,
        GSEED_GRADE_THRESHOLDS.get("아파트", {}),
    )
    predicted_grade = "등급외"
    for grade_name, max_val in thresholds.items():
        if lifecycle_carbon_per_sqm <= max_val:
            predicted_grade = grade_name
            break

    return {
        "predicted_grade": predicted_grade,
        "lifecycle_carbon_per_sqm": round(lifecycle_carbon_per_sqm, 1),
        "thresholds": thresholds,
    }
