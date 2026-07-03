"""사업 타당성 분석 서비스."""


class FeasibilityService:
    """NPV/IRR/Payback 사업 타당성 검토."""

    def run_feasibility_study(self, project_id: str, params: dict) -> dict:
        total_investment = params.get("total_investment", 0)
        expected_revenue = params.get("expected_revenue", 0)
        discount_rate = params.get("discount_rate", 0.08)
        period = params.get("period_years", 5)
        annual_cf = expected_revenue / period if period > 0 else 0
        npv = -total_investment + sum(
            annual_cf / ((1 + discount_rate) ** t) for t in range(1, period + 1)
        )
        irr = self._calc_irr(total_investment, annual_cf, period)
        payback = total_investment / annual_cf if annual_cf > 0 else float("inf")
        return {
            "project_id": project_id,
            "npv": round(npv),
            "irr": round(irr, 4),
            "payback_years": round(payback, 2),
            "total_investment": total_investment,
            "expected_revenue": expected_revenue,
            "feasible": npv > 0,
        }

    @staticmethod
    def _calc_irr(investment: float, annual_cf: float, periods: int,
                  tol: float = 1e-6, max_iter: int = 100) -> float:
        if annual_cf <= 0 or investment <= 0:
            return 0.0
        lo, hi = -0.5, 5.0
        for _ in range(max_iter):
            mid = (lo + hi) / 2
            npv = -investment + sum(annual_cf / ((1 + mid) ** t) for t in range(1, periods + 1))
            if abs(npv) < tol:
                return mid
            if npv > 0:
                lo = mid
            else:
                hi = mid
        return (lo + hi) / 2
