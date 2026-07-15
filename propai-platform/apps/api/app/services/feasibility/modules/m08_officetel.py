"""M08 오피스텔 DCF 모듈 — 할인현금흐름 t=1 기준 (오류#7 수정)."""

from __future__ import annotations

from typing import Any

from app.services.feasibility.aggregation_engine import aggregate_feasibility
from app.services.feasibility.modules.base_module import BaseModule, ModuleInput, ModuleOutput
from app.services.feasibility.modules.common.cost_blocks import (
    apply_auto_estimates,
    compute_construction_cost,
    compute_finance_cost,
    compute_land_cost,
    compute_other_cost,
    compute_taxes,
)
from app.services.feasibility.modules.common.revenue_block import compute_revenue


def calculate_dcf_value(
    *,
    annual_noi_won: int,
    discount_rate: float,
    terminal_cap_rate: float,
    hold_years: int,
) -> dict[str, Any]:
    """DCF 계산 (t=1 기준, 오류#7 수정).

    NPV = Σ(NOI_t / (1+r)^t) + TV / (1+r)^N, t = 1..N
    TV = NOI_N+1 / cap_rate
    """
    if discount_rate <= 0 or hold_years <= 0:
        return {"npv_won": 0, "terminal_value_won": 0, "pv_noi_won": 0}

    pv_noi = 0
    for t in range(1, hold_years + 1):
        pv_noi += annual_noi_won / ((1 + discount_rate) ** t)

    terminal_noi = annual_noi_won * (1 + 0.02)  # 2% 성장 가정
    terminal_value = terminal_noi / terminal_cap_rate if terminal_cap_rate > 0 else 0
    pv_terminal = terminal_value / ((1 + discount_rate) ** hold_years)

    npv = int(pv_noi + pv_terminal)

    return {
        "npv_won": npv,
        "pv_noi_won": int(pv_noi),
        "terminal_value_won": int(terminal_value),
        "pv_terminal_won": int(pv_terminal),
        "hold_years": hold_years,
    }


class M08Officetel(BaseModule):
    """M08 오피스텔 — DCF 기반 수익분석."""

    @property
    def code(self) -> str:
        return "M08"

    @property
    def name(self) -> str:
        return "오피스텔"

    def calculate(self, inp: ModuleInput) -> ModuleOutput:
        revenue = compute_revenue(inp)
        land = compute_land_cost(inp)
        construction = compute_construction_cost(inp)
        finance = compute_finance_cost(inp)
        other = compute_other_cost(inp)
        # ★감사 수지10 봉합: 금융비·소프트비 자동추정(공용 — generic과 동일 표준 가정).
        #   params 미입력 시 finance=0·other=0으로 ROI가 과대(예: 566%)되던 비대칭 해소.
        finance, other = apply_auto_estimates(inp, land, construction, finance, other)
        taxes = compute_taxes(
            inp, revenue["total_revenue_won"],
            development_cost_won=int(construction["total_construction_cost_won"]),
        )

        # DCF 분석 (임대수익 기반)
        annual_noi = inp.params.get("annual_noi_won", 0)
        terminal_cap = inp.params.get("terminal_cap_rate", 0.06)
        hold_years = inp.params.get("hold_years", 10)

        dcf = calculate_dcf_value(
            annual_noi_won=annual_noi,
            discount_rate=inp.discount_rate,
            terminal_cap_rate=terminal_cap,
            hold_years=hold_years,
        )

        agg = aggregate_feasibility(
            total_revenue_won=revenue["total_revenue_won"],
            total_land_cost_won=land["total_land_cost_won"],
            total_construction_cost_won=construction["total_construction_cost_won"],
            total_finance_cost_won=finance["total_finance_cost_won"],
            total_other_cost_won=other["total_other_cost_won"],
            total_tax_cost_won=taxes["grand_total_won"],
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
            total_tax_cost_won=taxes["grand_total_won"],
            total_cost_won=agg["total_cost_won"],
            net_profit_won=agg["net_profit_won"],
            profit_rate_pct=agg["profit_rate_pct"],
            roi_pct=agg["roi_pct"],
            roe_pct=agg.get("roe_pct"),
            npv_won=dcf["npv_won"] if annual_noi > 0 else agg["npv_won"],
            grade=agg["grade"],
            cost_detail=agg["cost_breakdown_won"],
            tax_detail=taxes,
            special_detail={"dcf": dcf},
        )
