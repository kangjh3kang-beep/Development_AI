"""몬테카를로 시뮬레이션 테스트 — 5변수 수렴 조건."""

import pytest
from app.services.feasibility.monte_carlo_engine import (
    run_monte_carlo, MCVariable,
)


def _simple_npv(vars: dict[str, float]) -> float:
    """간이 NPV 함수."""
    revenue = vars.get("revenue", 1000)
    cost = vars.get("cost", 800)
    return revenue - cost


class TestMonteCarlo:
    def test_basic_run(self):
        result = run_monte_carlo(
            calculate_fn=_simple_npv,
            variables=[
                MCVariable("revenue", mean=1000, std=100),
                MCVariable("cost", mean=800, std=50),
            ],
            n_simulations=10_000,
            seed=42,
        )
        assert result["n_simulations"] == 10_000
        assert result["mean"] == pytest.approx(200, abs=20)
        assert result["std"] > 0
        assert 0 < result["probability_positive"] <= 1.0

    def test_convergence(self):
        """σ/μ < 0.5 (합리적 수렴)."""
        result = run_monte_carlo(
            calculate_fn=_simple_npv,
            variables=[
                MCVariable("revenue", mean=1000, std=50),
                MCVariable("cost", mean=800, std=30),
            ],
            n_simulations=10_000,
            seed=42,
        )
        assert result["convergence_ratio"] < 0.5

    def test_percentiles(self):
        result = run_monte_carlo(
            calculate_fn=_simple_npv,
            variables=[MCVariable("revenue", mean=1000, std=100)],
            n_simulations=5_000,
            seed=42,
        )
        assert result["p5"] < result["p50"] < result["p95"]

    def test_histogram_bins(self):
        result = run_monte_carlo(
            calculate_fn=_simple_npv,
            variables=[MCVariable("revenue", mean=1000, std=100)],
            n_simulations=5_000,
            seed=42,
        )
        if result["histogram"]:  # numpy 사용 시
            assert len(result["histogram"]) == 20

    def test_five_variables(self):
        """5변수 시뮬레이션."""
        result = run_monte_carlo(
            calculate_fn=lambda v: (
                v.get("sale_price", 1000)
                - v.get("land_cost", 200)
                - v.get("construction_cost", 500)
                - v.get("finance_cost", 100)
                - v.get("tax_cost", 50)
            ),
            variables=[
                MCVariable("sale_price", mean=1000, std=100),
                MCVariable("land_cost", mean=200, std=30),
                MCVariable("construction_cost", mean=500, std=50),
                MCVariable("finance_cost", mean=100, std=20),
                MCVariable("tax_cost", mean=50, std=10),
            ],
            n_simulations=10_000,
            seed=42,
        )
        assert result["mean"] == pytest.approx(150, abs=30)
        assert result["n_simulations"] == 10_000

    def test_uniform_distribution(self):
        result = run_monte_carlo(
            calculate_fn=_simple_npv,
            variables=[
                MCVariable("revenue", mean=1000, std=100, distribution="uniform"),
            ],
            n_simulations=5_000,
            seed=42,
        )
        assert result["mean"] == pytest.approx(200, abs=30)


class TestSensitivityEngine:
    def test_basic(self):
        from app.services.feasibility.sensitivity_engine import run_sensitivity_analysis

        base_values = {"sale_price": 1000, "construction_cost": 500, "land_cost": 200}

        def calc_fn(vals):
            profit = vals["sale_price"] - vals["construction_cost"] - vals["land_cost"]
            rate = profit / vals["sale_price"] * 100 if vals["sale_price"] > 0 else 0
            return {"profit_rate_pct": rate, "npv_won": int(profit * 1e8)}

        result = run_sensitivity_analysis(
            base_values=base_values,
            calculate_fn=calc_fn,
        )
        assert len(result["scenarios"]) == 5
        assert len(result["tornado"]) == 5
        # 토네이도: 가장 큰 spread가 첫 번째
        assert result["tornado"][0]["spread"] >= result["tornado"][-1]["spread"]
