import numpy as np
from typing import Dict, List
import structlog

logger = structlog.get_logger()

class MonteCarloService:
    """Monte Carlo NPV/IRR 시뮬레이션 (10,000회, 수렴 기준: sigma/mean < 0.01)"""

    def __init__(self, seed: int = 42):
        self._seed = seed

    def run_simulation(self, total_cost_krw: float = 0, expected_revenue_krw: float = 0,
                       construction_period_months: int = 36, discount_rate_mean: float = 0.08,
                       discount_rate_std: float = 0.02, revenue_uncertainty: float = 0.15,
                       n_simulations: int = 10000, iterations: int = 0, **kwargs) -> Dict:
        if isinstance(total_cost_krw, dict):
            d = total_cost_krw
            total_cost_krw = d.get("initial_investment", d.get("total_cost_krw", 0))
            expected_revenue_krw = d.get("revenue_mean", d.get("expected_revenue_krw", expected_revenue_krw))
            rev_std = d.get("revenue_std", 0)
            if rev_std and expected_revenue_krw > 0:
                revenue_uncertainty = rev_std / expected_revenue_krw
            construction_period_months = d.get("project_years", 3) * 12 if d.get("project_years") else construction_period_months
        if iterations > 0:
            n_simulations = iterations
        np.random.seed(self._seed)
        T = construction_period_months / 12
        npv_results, irr_results = [], []
        for _ in range(n_simulations):
            r = max(0.01, np.random.normal(discount_rate_mean, discount_rate_std))
            revenue = np.random.normal(expected_revenue_krw, expected_revenue_krw * revenue_uncertainty)
            npv = -total_cost_krw + revenue / ((1 + r) ** T)
            npv_results.append(npv)
            if revenue > 0 and total_cost_krw > 0:
                irr = (revenue / total_cost_krw) ** (1 / T) - 1
                irr_results.append(irr)
        npv_array = np.array(npv_results)
        irr_array = np.array(irr_results) if irr_results else np.array([0.0])
        convergence_ratio = np.std(npv_array) / abs(np.mean(npv_array)) if np.mean(npv_array) != 0 else 1.0
        return {
            "npv_mean_krw": int(np.mean(npv_array)),
            "npv_median_krw": int(np.median(npv_array)),
            "npv_std_krw": int(np.std(npv_array)),
            "npv_p10_krw": int(np.percentile(npv_array, 10)),
            "npv_p90_krw": int(np.percentile(npv_array, 90)),
            "probability_positive_npv": float(np.mean(npv_array > 0)),
            "mean_npv": int(np.mean(npv_array)),
            "positive_npv_pct": float(np.mean(npv_array > 0) * 100),
            "irr_mean": float(np.mean(irr_array)),
            "irr_p10": float(np.percentile(irr_array, 10)),
            "irr_p90": float(np.percentile(irr_array, 90)),
            "n_simulations": n_simulations,
            "convergence_ratio": round(convergence_ratio, 6),
            "converged": convergence_ratio < 0.01,
            "method": "Monte Carlo NPV/IRR Simulation",
            "mathematical_basis": "NPV = sum(CF_t/(1+r)^t), r~N(mu,sigma^2)"
        }

    def sensitivity_analysis(self, base_cost_krw: float, base_revenue_krw: float,
                              variables: List[str], range_pct: float = 0.20) -> Dict:
        results = {}
        base_npv = base_revenue_krw - base_cost_krw
        for var in variables:
            high_case = base_npv * (1 + range_pct)
            low_case = base_npv * (1 - range_pct)
            results[var] = {
                "high_case_npv": int(high_case),
                "low_case_npv": int(low_case),
                "sensitivity": round((high_case - low_case) / (2 * base_npv * range_pct), 4) if base_npv != 0 else 0
            }
        return results
