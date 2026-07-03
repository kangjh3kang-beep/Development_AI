"""공사비 몬테카를로 시뮬레이션 테스트."""

from app.services.cost.cost_monte_carlo import RISK, CostMonteCarlo

SAMPLE_BASE = {
    "direct_material_cost": 5_000_000_000,
    "total_labor_cost": 3_000_000_000,
    "direct_expense_cost": 1_000_000_000,
    "total_project_cost": 12_000_000_000,
}


class TestRiskParams:

    def test_risk_count(self):
        assert len(RISK) == 5

    def test_all_triangular(self):
        for key, (lo, mode, hi) in RISK.items():
            assert lo <= mode <= hi, f"{key}: invalid triangular params"


class TestCostMonteCarlo:

    def test_basic_run(self):
        mc = CostMonteCarlo(SAMPLE_BASE, iters=1000, seed=42)
        result = mc.run()

        assert result["iterations"] == 1000
        assert result["mean"] > 0
        assert result["std"] > 0
        assert result["p10"] <= result["p50"] <= result["p90"]

    def test_percentile_ordering(self):
        mc = CostMonteCarlo(SAMPLE_BASE, iters=5000, seed=42)
        result = mc.run()
        assert result["p10"] <= result["p50"]
        assert result["p50"] <= result["p80"]
        assert result["p80"] <= result["p90"]
        assert result["min"] <= result["p10"]
        assert result["p90"] <= result["max"]

    def test_cv_reasonable(self):
        """CV가 합리적 범위 (0~0.5)."""
        mc = CostMonteCarlo(SAMPLE_BASE, iters=5000, seed=42)
        result = mc.run()
        assert 0 < result["cv"] < 0.5

    def test_risk_contributions_sum(self):
        mc = CostMonteCarlo(SAMPLE_BASE, iters=5000, seed=42)
        result = mc.run()
        total = sum(result["risk_contributions"].values())
        assert abs(total - 100.0) < 1.0

    def test_deterministic_with_seed(self):
        mc1 = CostMonteCarlo(SAMPLE_BASE, iters=1000, seed=42)
        mc2 = CostMonteCarlo(SAMPLE_BASE, iters=1000, seed=42)
        r1 = mc1.run()
        r2 = mc2.run()
        assert r1["mean"] == r2["mean"]
        assert r1["p50"] == r2["p50"]

    def test_empty_base(self):
        mc = CostMonteCarlo({"total_project_cost": 0}, iters=100)
        result = mc.run()
        assert result["mean"] == 0
        assert result["converged"] is False

    def test_convergence_flag(self):
        mc = CostMonteCarlo(SAMPLE_BASE, iters=10000, seed=42)
        result = mc.run()
        # 10000 반복이면 수렴 가능성 높음
        assert isinstance(result["converged"], bool)
