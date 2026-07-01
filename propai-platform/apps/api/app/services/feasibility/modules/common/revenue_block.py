"""공통 수입 블록 — 분양/임대/조합원 수입 계산 위임."""

from __future__ import annotations

from typing import Any

from app.services.feasibility.modules.base_module import ModuleInput
from app.services.feasibility.revenue_engine import (
    calculate_ancillary_revenue,
    calculate_rental_revenue,
    calculate_sale_revenue,
    calculate_total_revenue,
    calculate_union_revenue,
)


def compute_revenue(inp: ModuleInput) -> dict[str, Any]:
    """표준 수입 계산."""
    sale = None
    union = None
    rental = None

    sale_hh = int(inp.total_households * inp.sale_ratio)
    rental_hh = inp.total_households - sale_hh

    if sale_hh > 0:
        sale = calculate_sale_revenue(
            households=sale_hh,
            avg_area_pyeong=inp.avg_area_pyeong,
            avg_price_per_pyeong=inp.avg_sale_price_per_pyeong,
        )

    # 조합원 분양 (params에서)
    union_hh = inp.params.get("union_households", 0)
    if union_hh > 0:
        union = calculate_union_revenue(
            union_households=union_hh,
            avg_area_pyeong=inp.params.get("union_avg_area_pyeong", inp.avg_area_pyeong),
            avg_allotment_price_per_pyeong=inp.params.get("union_price_per_pyeong", inp.avg_sale_price_per_pyeong),
        )

    if rental_hh > 0 and inp.sale_ratio < 1.0:
        rental = calculate_rental_revenue(
            rental_units=rental_hh,
            avg_area_pyeong=inp.avg_area_pyeong,
            avg_deposit_per_pyeong=inp.params.get("avg_deposit_per_pyeong", 0),
            avg_monthly_rent_per_pyeong=inp.params.get("avg_monthly_rent_per_pyeong", 0),
        )

    ancillary = calculate_ancillary_revenue(
        commercial_area_pyeong=inp.params.get("commercial_area_pyeong", 0),
        commercial_price_per_pyeong=inp.params.get("commercial_price_per_pyeong", 0),
        other_income_won=inp.params.get("other_income_won", 0),
    )

    return calculate_total_revenue(
        sale_revenue=sale,
        union_revenue=union,
        rental_revenue=rental,
        ancillary_revenue=ancillary,
    )
