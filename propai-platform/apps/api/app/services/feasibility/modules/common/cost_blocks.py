"""공통 비용 블록 — 토지비/공사비/금융비/기타비 계산 위임."""

from __future__ import annotations

from typing import Any

from app.services.feasibility.land_cost_engine import calculate_total_land_cost
from app.services.feasibility.construction_cost_engine import calculate_total_construction_cost
from app.services.feasibility.finance_cost_engine import calculate_total_finance_cost
from app.services.tax.integrated_tax_engine import calculate_all_taxes
from app.services.feasibility.modules.base_module import ModuleInput


def compute_land_cost(inp: ModuleInput) -> dict[str, Any]:
    """표준 토지비 계산."""
    return calculate_total_land_cost(
        total_area_sqm=inp.total_land_area_sqm,
        official_price_per_sqm=inp.official_price_per_sqm,
        price_multiplier=inp.price_multiplier,
        land_category=inp.land_category,
        house_count=inp.house_count,
        is_adjusted_area=inp.is_adjusted_area,
        compensation_won=inp.params.get("compensation_won", 0),
    )


def compute_construction_cost(inp: ModuleInput) -> dict[str, Any]:
    """표준 공사비 계산.

    공사비 정밀 분석 결과를 params.construction_cost_override_won 로 주입하면
    수지·사업성(ROI)이 그 공사비를 그대로 사용한다(3자 단일 데이터원 정합).
    """
    override = inp.params.get("construction_cost_override_won")
    if override and float(override) > 0:
        total = int(float(override))
        return {
            "direct": {"total_direct_cost_won": total},
            "indirect": {"total_indirect_cost_won": 0},
            "total_construction_cost_won": total,
            "source": "cost_analysis_override",
        }
    return calculate_total_construction_cost(
        total_gfa_sqm=inp.total_gfa_sqm,
        building_type=inp.building_type,
        unit_cost_per_sqm=inp.params.get("unit_cost_per_sqm"),
        cost_index_factor=inp.params.get("cost_index_factor", 1.0),
    )


def compute_finance_cost(inp: ModuleInput) -> dict[str, Any]:
    """표준 금융비 계산."""
    return calculate_total_finance_cost(
        bridge_amount_won=inp.bridge_amount_won,
        bridge_rate=inp.bridge_rate,
        bridge_months=inp.bridge_months,
        pf_amount_won=inp.pf_amount_won,
        pf_rate=inp.pf_rate,
        pf_months=inp.pf_months,
        midpay_amount_won=inp.midpay_amount_won,
        midpay_rate=inp.midpay_rate,
        midpay_months=inp.midpay_months,
    )


def compute_other_cost(inp: ModuleInput) -> dict[str, Any]:
    """기타경비 계산."""
    marketing = inp.params.get("marketing_cost_won", 0)
    management = inp.params.get("management_cost_won", 0)
    reserve = inp.params.get("reserve_cost_won", 0)
    return {
        "marketing_won": marketing,
        "management_won": management,
        "reserve_won": reserve,
        "total_other_cost_won": marketing + management + reserve,
    }


def compute_taxes(inp: ModuleInput, total_sale_won: int = 0) -> dict[str, Any]:
    """세금 일괄 계산."""
    purchase_won = int(inp.total_land_area_sqm * inp.official_price_per_sqm * inp.price_multiplier)
    return calculate_all_taxes(
        purchase_won=purchase_won,
        land_category=inp.land_category,
        house_count=inp.house_count,
        is_adjusted=inp.is_adjusted_area,
        area_sqm=inp.total_land_area_sqm,
        official_price_per_sqm=inp.official_price_per_sqm,
        region_type=inp.region_type,
        sido_name=inp.sido_name,
        sigungu_name=inp.sigungu_name,
        total_households=inp.total_households,
        total_sale_amount_won=total_sale_won,
        total_gfa_sqm=inp.total_gfa_sqm,
        building_type=inp.building_type,
        total_units=inp.total_households,
        avg_area_sqm=inp.avg_area_pyeong * 3.305785 if inp.avg_area_pyeong else 85.0,
    )
