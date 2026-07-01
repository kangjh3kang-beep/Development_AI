
import numpy as np
import structlog

logger = structlog.get_logger()

class MonteCarloService:
    """Monte Carlo NPV/IRR 시뮬레이션 (10,000회, 수렴 기준: sigma/mean < 0.01)"""

    def __init__(self, seed: int = 42):
        self._seed = seed

    def run_simulation(self, total_cost_krw: float = 0, expected_revenue_krw: float = 0,
                       construction_period_months: int = 36, discount_rate_mean: float = 0.08,
                       discount_rate_std: float = 0.02, revenue_uncertainty: float = 0.15,
                       n_simulations: int = 10000, iterations: int = 0, **kwargs) -> dict:
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
            if total_cost_krw > 0:
                # revenue<=0 표본도 IRR=-100%로 포함 — 양수만 취하면 분포 우측 절단으로 평균 상향 편의
                irr = (revenue / total_cost_krw) ** (1 / T) - 1 if revenue > 0 else -1.0
                irr_results.append(irr)
        npv_array = np.array(npv_results)
        irr_array = np.array(irr_results) if irr_results else np.array([0.0])
        npv_mean = np.mean(npv_array)
        # CV(σ/|μ|)는 분포의 고유 리스크 — 하위호환 위해 유지
        convergence_ratio = np.std(npv_array) / abs(npv_mean) if npv_mean != 0 else 1.0
        # 수렴 판정은 평균의 표준오차 비율 σ/(√N·|μ|) — N 증가 시 감소하는 지표
        se_ratio = (
            np.std(npv_array) / (abs(npv_mean) * np.sqrt(n_simulations))
            if npv_mean != 0 else float("inf")
        )
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
            "standard_error_ratio": round(float(se_ratio), 8),
            "converged": bool(se_ratio < 0.01),
            "method": "Monte Carlo NPV/IRR Simulation",
            "mathematical_basis": "NPV = sum(CF_t/(1+r)^t), r~N(mu,sigma^2)"
        }

    def sensitivity_analysis(self, base_cost_krw: float, base_revenue_krw: float,
                              variables: list[str], range_pct: float = 0.20,
                              discount_rate: float = 0.08,
                              period_months: int = 36) -> dict:
        """변수별 ±range_pct 변동 시 NPV를 실제 재계산하는 일변량 민감도 분석.

        (이전 구현은 변수와 무관하게 base_npv×(1±20%)를 반환해 sensitivity가
        항상 1.0이었음 — 변수별 영향도를 구분하지 못하는 무의미한 출력.)
        """
        T = period_months / 12

        def _npv(cost: float, revenue: float, r: float) -> float:
            return -cost + revenue / ((1 + r) ** T)

        base_npv = _npv(base_cost_krw, base_revenue_krw, discount_rate)
        results = {}
        for var in variables:
            if var in ("cost", "total_cost", "construction_cost", "총사업비", "공사비"):
                high_case = _npv(base_cost_krw * (1 - range_pct), base_revenue_krw, discount_rate)  # 비용↓=NPV↑
                low_case = _npv(base_cost_krw * (1 + range_pct), base_revenue_krw, discount_rate)
            elif var in ("revenue", "sale_price", "분양가", "매출"):
                high_case = _npv(base_cost_krw, base_revenue_krw * (1 + range_pct), discount_rate)
                low_case = _npv(base_cost_krw, base_revenue_krw * (1 - range_pct), discount_rate)
            elif var in ("discount_rate", "rate", "할인율", "금리"):
                high_case = _npv(base_cost_krw, base_revenue_krw, discount_rate * (1 - range_pct))  # 할인율↓=NPV↑
                low_case = _npv(base_cost_krw, base_revenue_krw, discount_rate * (1 + range_pct))
            else:
                results[var] = {
                    "high_case_npv": int(base_npv), "low_case_npv": int(base_npv),
                    "sensitivity": 0.0, "note": f"미지원 변수 '{var}' — 민감도 미산출",
                }
                continue
            swing = high_case - low_case
            results[var] = {
                "high_case_npv": int(high_case),
                "low_case_npv": int(low_case),
                "sensitivity": round(abs(swing) / (2 * abs(base_npv) * range_pct), 4) if base_npv != 0 else 0,
            }
        return results
