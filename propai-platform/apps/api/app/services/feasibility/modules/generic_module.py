"""범용 모듈 — M03, M05~M07, M09~M15 공통 구현.

특화 로직이 없는 개발유형은 이 범용 모듈로 처리.
M03: 역세권개발, M05: 임대협동, M06: 일반분양, M07: 주상복합,
M09: 지식산업센터, M10: 단독주택, M11: 전원주택, M12: 타운하우스,
M13: 도시형소규모, M14: 공공임대, M15: 민간리츠
"""

from __future__ import annotations

from app.services.feasibility.aggregation_engine import aggregate_feasibility
from app.services.feasibility.modules.base_module import BaseModule, ModuleInput, ModuleOutput
from app.services.feasibility.modules.common.cost_blocks import (
    compute_construction_cost,
    compute_finance_cost,
    compute_land_cost,
    compute_other_cost,
    compute_taxes,
)
from app.services.feasibility.modules.common.revenue_block import compute_revenue

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

        # ── P0-2: 금융비·소프트비 자동추정(파라미터 미입력 시에만) ──
        # 디폴트 호출(loan/소프트비 params 미입력)에서 finance=0·other=0 이면 총사업비가 과소
        # 계상돼 ROI·순이익률이 비현실적으로 과대(예: ROI 566%)된다. 명시 입력이 없을 때 표준
        # 가정으로 자동추정하고 auto_estimated 플래그로 정직 표기(사용자 입력 시 그 값 우선).
        base_cost = float(land["total_land_cost_won"]) + float(construction["total_construction_cost_won"])
        if float(finance.get("total_finance_cost_won") or 0) <= 0 and base_cost > 0:
            months = float(inp.project_months or 30)
            pf_amt = base_cost * 0.70  # 표준 LTV 70%
            est_finance = round(pf_amt * 0.055 * (months / 12.0))  # PF 이자 5.5%, 사업기간 비례
            finance = {**finance, "total_finance_cost_won": est_finance, "auto_estimated": True,
                       "estimate_basis": (f"PF 차입 {pf_amt:,.0f}원(토지+공사 LTV70%)"
                                          f"×5.5%×{months:.0f}개월 자동추정(미입력)")}
        if float(other.get("total_other_cost_won") or 0) <= 0 and base_cost > 0:
            est_other = round(base_cost * 0.07)  # 설계·감리·분양대행·금융수수료·예비비 통칭 7%
            other = {**other, "total_other_cost_won": est_other, "auto_estimated": True,
                     "estimate_basis": (f"소프트비 = (토지+공사) {base_cost:,.0f}원 × 7% "
                                        "자동추정(설계·감리·분양대행·예비비 통칭, 미입력)")}

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
            roe_pct=agg.get("roe_pct"),
            npv_won=agg["npv_won"],
            grade=agg["grade"],
            cost_detail=agg["cost_breakdown_won"],
            tax_detail=taxes,
        )
