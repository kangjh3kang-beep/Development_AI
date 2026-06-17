"""M02 재건축 모듈 — 초과이익환수 포함 (오류#6 수정)."""

from __future__ import annotations

from app.services.feasibility.modules.base_module import BaseModule, ModuleInput, ModuleOutput
from app.services.feasibility.modules.common.revenue_block import compute_revenue
from app.services.feasibility.modules.common.cost_blocks import (
    compute_land_cost, compute_construction_cost, compute_finance_cost,
    compute_other_cost, compute_taxes,
)
from app.services.feasibility.aggregation_engine import aggregate_feasibility
from app.services.tax.disposal_stage_engine import calculate_d05_reconstruction_levy


class M02Reconstruction(BaseModule):
    """M02 재건축 — 초과이익환수 5구간 누진."""

    @property
    def code(self) -> str:
        return "M02"

    @property
    def name(self) -> str:
        return "재건축"

    def calculate(self, inp: ModuleInput) -> ModuleOutput:
        revenue = compute_revenue(inp)
        land = compute_land_cost(inp)
        construction = compute_construction_cost(inp)
        finance = compute_finance_cost(inp)
        other = compute_other_cost(inp)
        taxes = compute_taxes(inp, revenue["total_revenue_won"])

        # 초과이익환수 추가
        excess_gain = inp.params.get("excess_gain_won", 0)
        levy = calculate_d05_reconstruction_levy(excess_gain_won=excess_gain)
        extra_tax = taxes["grand_total_won"] + levy["amount_won"]

        agg = aggregate_feasibility(
            total_revenue_won=revenue["total_revenue_won"],
            total_land_cost_won=land["total_land_cost_won"],
            total_construction_cost_won=construction["total_construction_cost_won"],
            total_finance_cost_won=finance["total_finance_cost_won"],
            total_other_cost_won=other["total_other_cost_won"],
            total_tax_cost_won=extra_tax,
            equity_won=inp.equity_won,
            discount_rate=inp.discount_rate,
            project_months=inp.project_months,
        )

        return ModuleOutput(
            development_type=self.code,
            module_name=self.name,
            total_revenue_won=revenue["total_revenue_won"],
            revenue_detail=revenue,
            total_land_cost_won=land["total_land_cost_won"],
            total_construction_cost_won=construction["total_construction_cost_won"],
            total_finance_cost_won=finance["total_finance_cost_won"],
            total_other_cost_won=other["total_other_cost_won"],
            total_tax_cost_won=extra_tax,
            total_cost_won=agg["total_cost_won"],
            net_profit_won=agg["net_profit_won"],
            profit_rate_pct=agg["profit_rate_pct"],
            roi_pct=agg["roi_pct"],
            roe_pct=agg.get("roe_pct"),
            npv_won=agg["npv_won"],
            grade=agg["grade"],
            cost_detail=agg["cost_breakdown_won"],
            tax_detail=taxes,
            special_detail={
                "reconstruction_levy": levy,
                "excess_gain_won": excess_gain,
            },
        )
