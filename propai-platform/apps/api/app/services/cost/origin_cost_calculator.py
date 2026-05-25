"""원가계산서 생성기 — 12단계 법정요율 체인 적용.

계산 체인:
직접비(재료+노무+경비) → 간접노무비(14.4%) → 4대보험(산재/고용/건강/연금)
→ 장기요양/퇴직공제 → 안전보건/환경보전 → 순공사원가
→ 일반관리비(5.5%) → 이윤(15%) → 부가세(10%) → 총 공사비
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


# ── 2026년 법정요율 ──

RATES_2026: dict[str, float] = {
    "indirect_labor_rate": 0.1440,      # 간접노무비율 14.40%
    "industrial_accident": 0.0350,      # 산재보험 3.50%
    "employment_insurance": 0.0090,     # 고용보험 0.90%
    "health_insurance_emp": 0.03595,    # 건강보험(사업주) 3.595%
    "national_pension_emp": 0.04750,    # 국민연금(사업주) 4.75%
    "long_term_care": 0.004724,         # 장기요양보험 0.4724%
    "retirement_fund": 0.02100,         # 퇴직공제 2.10%
    "safety_health": 0.02070,           # 안전보건관리비 2.07%
    "env_preserve": 0.00160,            # 환경보전비 0.16%
    "general_mgmt": 0.05500,            # 일반관리비 5.50%
    "profit": 0.15000,                  # 이윤 15.00%
    "vat": 0.10000,                     # 부가가치세 10.00%
}


@dataclass
class CostItem:
    """개별 공사비 항목."""

    work_code: str
    item_name: str
    spec: str
    unit: str
    quantity: float
    mat_unit: float  # 재료 단가
    labor_unit: float  # 노무 단가
    exp_unit: float  # 경비 단가

    @property
    def mat_amt(self) -> float:
        return self.quantity * self.mat_unit

    @property
    def labor_amt(self) -> float:
        return self.quantity * self.labor_unit

    @property
    def exp_amt(self) -> float:
        return self.quantity * self.exp_unit

    @property
    def total_amt(self) -> float:
        return self.mat_amt + self.labor_amt + self.exp_amt


class OriginCostCalculator:
    """원가계산서 생성기."""

    def calculate(
        self,
        items: list[CostItem] | list[dict[str, Any]],
        rates: dict[str, float] | None = None,
    ) -> dict[str, Any]:
        """원가계산서를 생성한다.

        Args:
            items: CostItem 리스트 또는 dict 리스트
            rates: 법정요율 (None이면 RATES_2026 사용)

        Returns:
            원가계산서 dict
        """
        r = rates or RATES_2026.copy()

        # dict → CostItem 변환
        parsed: list[CostItem] = []
        for it in items:
            if isinstance(it, dict):
                parsed.append(CostItem(
                    work_code=it.get("work_code", ""),
                    item_name=it.get("item_name", ""),
                    spec=it.get("spec", ""),
                    unit=it.get("unit", ""),
                    quantity=float(it.get("quantity", 0)),
                    mat_unit=float(it.get("mat_unit", 0)),
                    labor_unit=float(it.get("labor_unit", 0)),
                    exp_unit=float(it.get("exp_unit", 0)),
                ))
            else:
                parsed.append(it)

        # 1. 직접비
        direct_material = sum(ci.mat_amt for ci in parsed)
        direct_labor = sum(ci.labor_amt for ci in parsed)
        direct_expense = sum(ci.exp_amt for ci in parsed)
        direct_cost = direct_material + direct_labor + direct_expense

        # 2. 간접노무비 (직접노무비 × 14.40%)
        indirect_labor = direct_labor * r["indirect_labor_rate"]
        total_labor = direct_labor + indirect_labor

        # 3. 산재보험 (노무비 × 3.50%)
        industrial_acc = total_labor * r["industrial_accident"]

        # 4. 고용보험 (노무비 × 0.90%)
        employment_ins = total_labor * r["employment_insurance"]

        # 5. 건강보험 (노무비 × 3.595%)
        health_ins = total_labor * r["health_insurance_emp"]

        # 6. 국민연금 (노무비 × 4.75%)
        national_pension = total_labor * r["national_pension_emp"]

        # 7. 장기요양보험 (건강보험 × 12.81% ≈ 노무비 × 0.4724%)
        long_term_care = total_labor * r["long_term_care"]

        # 8. 퇴직공제 (노무비 × 2.10%)
        retirement_fund = total_labor * r["retirement_fund"]

        # 보험료 소계
        insurance_total = (industrial_acc + employment_ins + health_ins +
                           national_pension + long_term_care + retirement_fund)

        # 9. 안전보건관리비 (재료비+노무비 × 2.07%)
        safety_health = (direct_material + total_labor) * r["safety_health"]

        # 10. 환경보전비 (재료비+노무비 × 0.16%)
        env_preserve = (direct_material + total_labor) * r["env_preserve"]

        # 순공사원가
        net_construction = (direct_cost + indirect_labor + insurance_total +
                            safety_health + env_preserve)

        # 11. 일반관리비 (순공사원가 × 5.50%)
        general_mgmt = net_construction * r["general_mgmt"]

        # 12. 이윤 (노무비+경비+일반관리비 × 15%)
        profit_base = total_labor + direct_expense + general_mgmt
        profit = profit_base * r["profit"]

        # 공사비 (세전)
        construction_cost_pre_vat = net_construction + general_mgmt + profit

        # 부가가치세
        vat = construction_cost_pre_vat * r["vat"]

        # 총 공사비
        total_project_cost = construction_cost_pre_vat + vat

        # 공종별 소계
        category_totals: dict[str, float] = {}
        for ci in parsed:
            cat = ci.work_code.split("-")[0] if "-" in ci.work_code else ci.work_code
            category_totals[cat] = category_totals.get(cat, 0) + ci.total_amt

        return {
            "direct_material_cost": round(direct_material),
            "direct_labor_cost": round(direct_labor),
            "direct_expense_cost": round(direct_expense),
            "direct_cost": round(direct_cost),
            "indirect_labor_cost": round(indirect_labor),
            "total_labor_cost": round(total_labor),
            "industrial_acc_ins": round(industrial_acc),
            "employment_ins": round(employment_ins),
            "health_ins": round(health_ins),
            "national_pension": round(national_pension),
            "long_term_care": round(long_term_care),
            "retirement_fund": round(retirement_fund),
            "insurance_total": round(insurance_total),
            "safety_health": round(safety_health),
            "env_preserve": round(env_preserve),
            "net_construction_cost": round(net_construction),
            "general_mgmt": round(general_mgmt),
            "profit": round(profit),
            "construction_cost_pre_vat": round(construction_cost_pre_vat),
            "vat": round(vat),
            "total_project_cost": round(total_project_cost),
            "category_totals": category_totals,
            "item_count": len(parsed),
            "applied_rates": r,
        }

    def to_excel_data(self, result: dict[str, Any]) -> list[list[Any]]:
        """원가계산서 Excel 행렬을 생성한다."""
        rows: list[list[Any]] = [
            ["구 분", "금 액 (원)", "비 고"],
            ["Ⅰ. 직접재료비", f"{result['direct_material_cost']:,}", ""],
            ["Ⅱ. 직접노무비", f"{result['direct_labor_cost']:,}", ""],
            ["Ⅲ. 직접경비", f"{result['direct_expense_cost']:,}", ""],
            ["직접공사비 소계", f"{result['direct_cost']:,}", "Ⅰ+Ⅱ+Ⅲ"],
            ["Ⅳ. 간접노무비", f"{result['indirect_labor_cost']:,}",
             f"직접노무비 × {RATES_2026['indirect_labor_rate']*100:.2f}%"],
            ["Ⅴ. 산재보험료", f"{result['industrial_acc_ins']:,}",
             f"노무비 × {RATES_2026['industrial_accident']*100:.2f}%"],
            ["Ⅵ. 고용보험료", f"{result['employment_ins']:,}",
             f"노무비 × {RATES_2026['employment_insurance']*100:.2f}%"],
            ["Ⅶ. 건강보험료", f"{result['health_ins']:,}",
             f"노무비 × {RATES_2026['health_insurance_emp']*100:.3f}%"],
            ["Ⅷ. 국민연금", f"{result['national_pension']:,}",
             f"노무비 × {RATES_2026['national_pension_emp']*100:.2f}%"],
            ["Ⅸ. 장기요양보험", f"{result['long_term_care']:,}",
             f"노무비 × {RATES_2026['long_term_care']*100:.4f}%"],
            ["Ⅹ. 퇴직공제부금", f"{result['retirement_fund']:,}",
             f"노무비 × {RATES_2026['retirement_fund']*100:.2f}%"],
            ["ⅩⅠ. 안전보건관리비", f"{result['safety_health']:,}",
             f"(재료비+노무비) × {RATES_2026['safety_health']*100:.2f}%"],
            ["ⅩⅡ. 환경보전비", f"{result['env_preserve']:,}",
             f"(재료비+노무비) × {RATES_2026['env_preserve']*100:.2f}%"],
            ["순공사원가", f"{result['net_construction_cost']:,}", ""],
            ["ⅩⅢ. 일반관리비", f"{result['general_mgmt']:,}",
             f"순공사원가 × {RATES_2026['general_mgmt']*100:.2f}%"],
            ["ⅩⅣ. 이윤", f"{result['profit']:,}",
             f"(노무비+경비+일반관리비) × {RATES_2026['profit']*100:.2f}%"],
            ["공사비(세전)", f"{result['construction_cost_pre_vat']:,}", ""],
            ["부가가치세", f"{result['vat']:,}", "10%"],
            ["총 공사비", f"{result['total_project_cost']:,}", ""],
        ]
        return rows
