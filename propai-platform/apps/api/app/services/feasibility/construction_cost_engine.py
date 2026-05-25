"""공사비 산정 엔진 — 직접공사비/간접공사비/설계감리비.

순수 함수형 설계: DB 의존 없음.
표준품셈 기반 + 건설물가지수 보정.
"""

from __future__ import annotations

from typing import Any

PYEONG_TO_SQM = 3.305785

# 기본 공사비 단가 (원/m², 2025년 기준)
DEFAULT_DIRECT_COST_PER_SQM: dict[str, int] = {
    "apartment": 2_400_000,
    "officetel": 2_600_000,
    "commercial": 2_200_000,
    "office": 2_500_000,
    "warehouse": 1_200_000,
    "townhouse": 2_000_000,
    "single_house": 2_100_000,
}

# 간접공사비 비율 기본값
DEFAULT_INDIRECT_RATIOS: dict[str, float] = {
    "design_fee": 0.04,       # 설계비 (직접공사비 대비)
    "supervision_fee": 0.03,  # 감리비
    "contingency": 0.05,      # 예비비
    "general_expense": 0.03,  # 일반관리비
}


def pyeong_to_sqm(area_pyeong: float) -> float:
    """평 → m² 변환."""
    return round(area_pyeong * PYEONG_TO_SQM, 2)


def sqm_to_pyeong(area_sqm: float) -> float:
    """m² → 평 변환."""
    return round(area_sqm / PYEONG_TO_SQM, 2)


def apply_cost_index(
    base_cost_won: int,
    base_year: int = 2025,
    target_year: int = 2026,
    annual_increase_rate: float = 0.03,
) -> dict[str, Any]:
    """건설물가지수 보정.

    Args:
        base_cost_won: 기준연도 공사비 (원)
        base_year: 기준연도
        target_year: 적용연도
        annual_increase_rate: 연간 물가상승률

    Returns:
        {'base_cost_won', 'index_factor', 'adjusted_cost_won'}
    """
    years_diff = target_year - base_year
    factor = (1 + annual_increase_rate) ** years_diff
    adjusted = int(base_cost_won * factor)

    return {
        "base_cost_won": base_cost_won,
        "index_factor": round(factor, 6),
        "adjusted_cost_won": adjusted,
    }


def calculate_direct_cost(
    *,
    total_gfa_sqm: float,
    building_type: str = "apartment",
    unit_cost_per_sqm: int | None = None,
    cost_index_factor: float = 1.0,
) -> dict[str, Any]:
    """직접공사비 계산.

    Args:
        total_gfa_sqm: 총 연면적 (m²)
        building_type: 건물유형
        unit_cost_per_sqm: 직접공사비 단가 (원/m², None이면 기본값)
        cost_index_factor: 물가보정계수

    Returns:
        {'total_gfa_sqm', 'unit_cost_per_sqm', 'cost_index_factor', 'total_direct_cost_won'}
    """
    if unit_cost_per_sqm is None:
        unit_cost_per_sqm = DEFAULT_DIRECT_COST_PER_SQM.get(
            building_type, DEFAULT_DIRECT_COST_PER_SQM["apartment"]
        )

    adjusted_unit = int(unit_cost_per_sqm * cost_index_factor)
    total = int(total_gfa_sqm * adjusted_unit)

    return {
        "total_gfa_sqm": round(total_gfa_sqm, 2),
        "building_type": building_type,
        "unit_cost_per_sqm": adjusted_unit,
        "cost_index_factor": cost_index_factor,
        "total_direct_cost_won": total,
    }


def calculate_indirect_cost(
    *,
    direct_cost_won: int,
    design_fee_ratio: float | None = None,
    supervision_fee_ratio: float | None = None,
    contingency_ratio: float | None = None,
    general_expense_ratio: float | None = None,
) -> dict[str, Any]:
    """간접공사비 계산.

    Returns:
        {'design_fee_won', 'supervision_fee_won', 'contingency_won',
         'general_expense_won', 'total_indirect_cost_won', 'ratios'}
    """
    ratios = {
        "design_fee": design_fee_ratio if design_fee_ratio is not None else DEFAULT_INDIRECT_RATIOS["design_fee"],
        "supervision_fee": supervision_fee_ratio if supervision_fee_ratio is not None else DEFAULT_INDIRECT_RATIOS["supervision_fee"],
        "contingency": contingency_ratio if contingency_ratio is not None else DEFAULT_INDIRECT_RATIOS["contingency"],
        "general_expense": general_expense_ratio if general_expense_ratio is not None else DEFAULT_INDIRECT_RATIOS["general_expense"],
    }

    items = {}
    total = 0
    for key, ratio in ratios.items():
        amount = int(direct_cost_won * ratio)
        items[f"{key}_won"] = amount
        total += amount

    return {
        **items,
        "total_indirect_cost_won": total,
        "ratios": ratios,
    }


def calculate_total_construction_cost(
    *,
    total_gfa_sqm: float,
    building_type: str = "apartment",
    unit_cost_per_sqm: int | None = None,
    cost_index_factor: float = 1.0,
    design_fee_ratio: float | None = None,
    supervision_fee_ratio: float | None = None,
    contingency_ratio: float | None = None,
    general_expense_ratio: float | None = None,
) -> dict[str, Any]:
    """공사비 총합 (직접 + 간접).

    Returns:
        {'direct', 'indirect', 'total_construction_cost_won'}
    """
    direct = calculate_direct_cost(
        total_gfa_sqm=total_gfa_sqm,
        building_type=building_type,
        unit_cost_per_sqm=unit_cost_per_sqm,
        cost_index_factor=cost_index_factor,
    )

    indirect = calculate_indirect_cost(
        direct_cost_won=direct["total_direct_cost_won"],
        design_fee_ratio=design_fee_ratio,
        supervision_fee_ratio=supervision_fee_ratio,
        contingency_ratio=contingency_ratio,
        general_expense_ratio=general_expense_ratio,
    )

    total = direct["total_direct_cost_won"] + indirect["total_indirect_cost_won"]

    return {
        "direct": direct,
        "indirect": indirect,
        "total_construction_cost_won": total,
    }
