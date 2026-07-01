"""Monte Carlo NPV/IRR 시뮬레이션 테스트."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.finance.monte_carlo_service import MonteCarloService


class TestMonteCarloSimulation:
    """Monte Carlo 시뮬레이션 기본 동작."""

    def setup_method(self):
        self.svc = MonteCarloService()

    def test_basic_simulation_returns_required_fields(self, sample_monte_carlo_params):
        """기본 시뮬레이션 필수 필드 확인."""
        result = self.svc.run_simulation(**sample_monte_carlo_params)
        required = ["npv_mean_krw", "npv_std_krw", "probability_positive_npv",
                     "irr_mean", "n_simulations", "convergence_ratio", "converged"]
        for key in required:
            assert key in result, f"필드 누락: {key}"

    def test_simulation_count_default_10000(self, sample_monte_carlo_params):
        """기본 시뮬레이션 횟수 10,000회."""
        result = self.svc.run_simulation(**sample_monte_carlo_params)
        assert result["n_simulations"] == 10000

    def test_convergence_ratio_calculated(self, sample_monte_carlo_params):
        """수렴 비율 계산 확인."""
        result = self.svc.run_simulation(**sample_monte_carlo_params)
        assert isinstance(result["convergence_ratio"], float)
        assert result["convergence_ratio"] >= 0

    def test_positive_revenue_project(self):
        """수익성 높은 프로젝트 → 양의 NPV 확률 > 50%."""
        result = self.svc.run_simulation(
            total_cost_krw=10_000_000_000,
            expected_revenue_krw=30_000_000_000,
            construction_period_months=24,
        )
        assert result["probability_positive_npv"] > 0.5

    def test_negative_revenue_project(self):
        """비용 > 수익 → NPV 평균 음수."""
        result = self.svc.run_simulation(
            total_cost_krw=100_000_000_000,
            expected_revenue_krw=20_000_000_000,
            construction_period_months=60,
        )
        assert result["npv_mean_krw"] < 0


class TestSensitivityAnalysis:
    """감도 분석 테스트."""

    def setup_method(self):
        self.svc = MonteCarloService()

    def test_sensitivity_returns_all_variables(self):
        """요청한 변수 모두 반환."""
        variables = ["공사비", "분양가", "금리"]
        result = self.svc.sensitivity_analysis(
            base_cost_krw=50_000_000_000,
            base_revenue_krw=70_000_000_000,
            variables=variables,
        )
        for var in variables:
            assert var in result

    def test_sensitivity_high_low_cases(self):
        """각 변수별 high/low 케이스 존재."""
        result = self.svc.sensitivity_analysis(
            base_cost_krw=50_000_000_000,
            base_revenue_krw=70_000_000_000,
            variables=["공사비"],
        )
        assert "high_case_npv" in result["공사비"]
        assert "low_case_npv" in result["공사비"]
        assert result["공사비"]["high_case_npv"] > result["공사비"]["low_case_npv"]
