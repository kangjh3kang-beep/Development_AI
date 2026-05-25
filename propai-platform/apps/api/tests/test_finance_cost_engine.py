"""금융비 엔진 테스트 — 브릿지/본PF/중도금 + 가중평균금리."""

import pytest
from app.services.feasibility.finance_cost_engine import (
    calculate_loan_interest,
    calculate_bridge_loan,
    calculate_pf_loan,
    calculate_midpay_loan,
    calculate_weighted_average_rate,
    calculate_total_finance_cost,
)


class TestLoanInterest:
    def test_basic(self):
        result = calculate_loan_interest(
            principal_won=10_000_000_000,
            annual_rate=0.06,
            months=12,
        )
        # 100억 × 6% × 12/12 = 6억
        assert result["interest_won"] == 600_000_000

    def test_half_year(self):
        result = calculate_loan_interest(
            principal_won=10_000_000_000,
            annual_rate=0.06,
            months=6,
        )
        assert result["interest_won"] == 300_000_000


class TestBridgeLoan:
    def test_basic(self):
        result = calculate_bridge_loan(
            amount_won=50_000_000_000,
            rate=0.06,
            months=12,
            arrangement_fee_rate=0.01,
        )
        # 이자: 500억 × 6% = 30억
        assert result["interest_won"] == 3_000_000_000
        # 주선수수료: 500억 × 1% = 5억
        assert result["arrangement_fee_won"] == 500_000_000
        assert result["total_bridge_cost_won"] == 3_500_000_000


class TestPFLoan:
    def test_basic(self):
        result = calculate_pf_loan(
            amount_won=200_000_000_000,
            rate=0.045,
            months=30,
            guarantee_fee_rate=0.015,
        )
        # 이자: 2000억 × 4.5% × 30/12 = 225억
        assert result["interest_won"] == 22_500_000_000
        # 보증료: 2000억 × 1.5% = 30억
        assert result["guarantee_fee_won"] == 3_000_000_000
        assert result["total_pf_cost_won"] == 25_500_000_000


class TestMidpayLoan:
    def test_basic(self):
        result = calculate_midpay_loan(
            amount_won=100_000_000_000,
            rate=0.04,
            months=18,
        )
        # 1000억 × 4% × 18/12 = 60억
        assert result["interest_won"] == 6_000_000_000
        assert result["total_midpay_cost_won"] == 6_000_000_000


class TestWeightedAverageRate:
    def test_basic(self):
        loans = [
            {"principal_won": 100_000_000_000, "rate": 0.06},
            {"principal_won": 200_000_000_000, "rate": 0.045},
        ]
        # (1000억×6% + 2000억×4.5%) / 3000억 = 5%
        rate = calculate_weighted_average_rate(loans)
        assert rate == pytest.approx(0.05, abs=0.001)

    def test_empty(self):
        assert calculate_weighted_average_rate([]) == 0.0

    def test_single_loan(self):
        loans = [{"principal_won": 100_000_000_000, "rate": 0.05}]
        assert calculate_weighted_average_rate(loans) == 0.05


class TestTotalFinanceCost:
    def test_three_stage(self):
        result = calculate_total_finance_cost(
            bridge_amount_won=50_000_000_000,
            bridge_rate=0.06,
            bridge_months=12,
            pf_amount_won=200_000_000_000,
            pf_rate=0.045,
            pf_months=30,
            midpay_amount_won=100_000_000_000,
            midpay_rate=0.04,
            midpay_months=18,
        )
        total = result["total_finance_cost_won"]
        bridge = result["bridge"]["total_bridge_cost_won"]
        pf = result["pf"]["total_pf_cost_won"]
        midpay = result["midpay"]["total_midpay_cost_won"]
        assert total == bridge + pf + midpay
        assert result["weighted_avg_rate"] > 0

    def test_zero_amounts(self):
        result = calculate_total_finance_cost()
        assert result["total_finance_cost_won"] == 0
        assert result["weighted_avg_rate"] == 0.0
