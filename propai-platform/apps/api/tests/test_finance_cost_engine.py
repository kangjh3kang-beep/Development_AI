"""금융비 엔진 테스트 — 브릿지/본PF/중도금 + 가중평균금리."""

import pytest

from app.services.feasibility.finance_cost_engine import (
    calculate_bridge_loan,
    calculate_loan_interest,
    calculate_midpay_loan,
    calculate_pf_loan,
    calculate_total_finance_cost,
    calculate_weighted_average_rate,
)


# 스펙: 만기일시상환 월복리 이자 = P × ((1 + r/12)^m − 1)
# (2026-05 Critical 수정으로 단리→월복리 전환. 이전 테스트는 단리 기대값이라 항상 실패했음)
def _compound(principal: int, annual_rate: float, months: int) -> int:
    return int(principal * ((1 + annual_rate / 12) ** months - 1))


class TestLoanInterest:
    def test_basic(self):
        result = calculate_loan_interest(
            principal_won=10_000_000_000,
            annual_rate=0.06,
            months=12,
        )
        # 100억 × ((1.005)^12 − 1) ≈ 6.168억 (월복리)
        assert result["interest_won"] == _compound(10_000_000_000, 0.06, 12)
        assert result["interest_won"] == pytest.approx(616_778_119, rel=1e-4)

    def test_half_year(self):
        result = calculate_loan_interest(
            principal_won=10_000_000_000,
            annual_rate=0.06,
            months=6,
        )
        assert result["interest_won"] == _compound(10_000_000_000, 0.06, 6)
        assert result["interest_won"] == pytest.approx(303_775_094, rel=1e-4)


class TestBridgeLoan:
    def test_basic(self):
        result = calculate_bridge_loan(
            amount_won=50_000_000_000,
            rate=0.06,
            months=12,
            arrangement_fee_rate=0.01,
        )
        # 이자: 500억 월복리 6%/12개월 ≈ 30.84억
        expected_interest = _compound(50_000_000_000, 0.06, 12)
        assert result["interest_won"] == expected_interest
        # 주선수수료: 500억 × 1% = 5억
        assert result["arrangement_fee_won"] == 500_000_000
        assert result["total_bridge_cost_won"] == expected_interest + 500_000_000


class TestPFLoan:
    def test_basic(self):
        result = calculate_pf_loan(
            amount_won=200_000_000_000,
            rate=0.045,
            months=30,
            guarantee_fee_rate=0.015,
        )
        # 이자: 2000억 월복리 4.5%/30개월 (직접 호출 기본값은 전액·만기일시 기준)
        expected_interest = _compound(200_000_000_000, 0.045, 30)
        assert result["interest_won"] == expected_interest
        # 보증료: 2000억 × 1.5% = 30억
        assert result["guarantee_fee_won"] == 3_000_000_000
        assert result["total_pf_cost_won"] == expected_interest + 3_000_000_000


class TestMidpayLoan:
    def test_basic(self):
        result = calculate_midpay_loan(
            amount_won=100_000_000_000,
            rate=0.04,
            months=18,
        )
        expected_interest = _compound(100_000_000_000, 0.04, 18)
        assert result["interest_won"] == expected_interest
        # 총비용 = 이자 + 보증료(1000억 × 0.4% = 4억)
        assert result["total_midpay_cost_won"] == expected_interest + 400_000_000


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
