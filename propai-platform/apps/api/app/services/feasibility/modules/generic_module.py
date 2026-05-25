"""범용 모듈 — M03, M05~M07, M09~M15 공통 구현.

특화 로직이 없는 개발유형은 이 범용 모듈로 처리.
M03: 역세권개발, M05: 임대협동, M06: 일반분양, M07: 주상복합,
M09: 지식산업센터, M10: 단독주택, M11: 전원주택, M12: 타운하우스,
M13: 도시형소규모, M14: 공공임대, M15: 민간리츠
"""

from __future__ import annotations

from app.services.feasibility.modules.base_module import BaseModule, ModuleInput, ModuleOutput
from app.services.feasibility.modules.common.revenue_block import compute_revenue
from app.services.feasibility.modules.common.cost_blocks import (
    compute_land_cost, compute_construction_cost, compute_finance_cost,
    compute_other_cost, compute_taxes,
)
from app.services.feasibility.aggregation_engine import aggregate_feasibility


MODULE_NAMES: dict[str, str] = {
    "M03": "역세권개발",
    "M05": "임대협동",
    "M06": "일반분양",
    "M07": "주상복합",
    "M09": "지식산업센터",
    "M10": "단독주택",
    "M11": "전원주택",
    "M12": "타운하우스",
    "M13": "도시형소규모",
    "M14": "공공임대",
    "M15": "민간리츠",
}


class GenericModule(BaseModule):
    """범용 개발유형 모듈."""

    def __init__(self, module_code: str):
        self._code = module_code
        self._name = MODULE_NAMES.get(module_code, f"기타({module_code})")

    @property
    def code(self) -> str:
        return self._code

    @property
    def name(self) -> str:
        return self._name

    def calculate(self, inp: ModuleInput) -> ModuleOutput:
        revenue = compute_revenue(inp)
        land = compute_land_cost(inp)
        construction = compute_construction_cost(inp)
        finance = compute_finance_cost(inp)
        other = compute_other_cost(inp)
        taxes = compute_taxes(inp, revenue["total_revenue_won"])

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
            npv_won=agg["npv_won"],
            grade=agg["grade"],
            cost_detail=agg["cost_breakdown_won"],
            tax_detail=taxes,
        )
