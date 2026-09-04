"""공사비 몬테카를로 시뮬레이션 테스트."""

import pytest

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

    def test_correlation_미지정_기본_독립(self):
        result = CostMonteCarlo(SAMPLE_BASE, iters=1000, seed=42).run()
        assert result["correlation_applied"] is False
        assert result["correlation"] is None


class TestCostMonteCarloCorrelation:
    """W3-3(P9) MC 상관 1차 — opt-in·무회귀·Cholesky 양정치 검증·seed 재현."""

    def test_무회귀_기존_독립경로와_수치_동일(self):
        """correlation 미전달 시 이전 버전과 100% 동일값(회귀 0)."""
        baseline = {
            "mean": 11032653200, "p50": 10953909083, "p90": 12274178601,
        }  # 상관 기능 도입 전 커밋에서 seed=42·iters=5000 로 산출한 값(고정 golden).
        mc = CostMonteCarlo(SAMPLE_BASE, iters=5000, seed=42)
        result = mc.run()
        assert result["mean"] == baseline["mean"]
        assert result["p50"] == baseline["p50"]
        assert result["p90"] == baseline["p90"]

    def test_상관_지정시_correlation_applied_true(self):
        mc = CostMonteCarlo(
            SAMPLE_BASE, iters=1000, seed=1,
            correlation={"material": {"labor": 0.5}},
        )
        result = mc.run()
        assert result["correlation_applied"] is True
        assert result["correlation"] == {"material": {"labor": 0.5}}

    def test_상관_지정해도_seed_재현(self):
        corr = {"material": {"labor": 0.6, "expense": 0.3}, "labor": {"expense": 0.2}}
        r1 = CostMonteCarlo(SAMPLE_BASE, iters=3000, seed=7, correlation=corr).run()
        r2 = CostMonteCarlo(SAMPLE_BASE, iters=3000, seed=7, correlation=corr).run()
        assert r1["mean"] == r2["mean"]
        assert r1["p50"] == r2["p50"]

    def test_양의_상관은_분산_증가(self):
        """공종 간 자재비 동반 상승(양의 상관)은 총공사비 분산을 독립표본보다 키운다."""
        independent = CostMonteCarlo(SAMPLE_BASE, iters=20000, seed=42).run()
        correlated = CostMonteCarlo(
            SAMPLE_BASE, iters=20000, seed=42,
            correlation={"material": {"labor": 0.8, "expense": 0.8}, "labor": {"expense": 0.8}},
        ).run()
        assert correlated["std"] > independent["std"]

    def test_상관행렬_대칭_보완(self):
        """(labor→material) 방향으로만 줘도 대칭 처리(material→labor 동일 적용)."""
        r1 = CostMonteCarlo(SAMPLE_BASE, iters=500, seed=3, correlation={"material": {"labor": 0.4}}).run()
        r2 = CostMonteCarlo(SAMPLE_BASE, iters=500, seed=3, correlation={"labor": {"material": 0.4}}).run()
        assert r1["mean"] == r2["mean"]

    def test_범위밖_상관계수는_ValueError(self):
        with pytest.raises(ValueError):
            CostMonteCarlo(SAMPLE_BASE, correlation={"material": {"labor": 1.5}})

    def test_허용밖_키는_ValueError(self):
        with pytest.raises(ValueError):
            CostMonteCarlo(SAMPLE_BASE, correlation={"design_chg": {"material": 0.2}})

    def test_비양정치_행렬은_ValueError(self):
        # 상호모순 상관(pairwise 전부 0.99 근접 + 하나만 -0.99)은 양정치 불가.
        with pytest.raises(ValueError):
            CostMonteCarlo(
                SAMPLE_BASE,
                correlation={
                    "material": {"labor": 0.99, "expense": 0.99},
                    "labor": {"expense": -0.99},
                },
            )

    def test_empty_base도_상관_지정과_무관하게_안전(self):
        mc = CostMonteCarlo({"total_project_cost": 0}, iters=100, correlation={"material": {"labor": 0.3}})
        result = mc.run()
        assert result["mean"] == 0
        assert result["converged"] is False
