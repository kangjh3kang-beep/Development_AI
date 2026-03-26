"""TaxAIService 단위 테스트.

양도소득세 누진세율 8구간, 장기보유특별공제, 취득세, Monte Carlo 시뮬레이션 등
순수 계산 로직을 검증한다.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from apps.api.services.tax_ai_service import TaxAIService


class TestCalcTransferTaxProgressive:
    """양도소득세 누진세율 8구간 계산 테스트."""

    def test_1구간_1400만원_이하_6퍼센트(self):
        """과세표준 1,000만원 → 세율 6%, 누진공제 0."""
        tax, eff = TaxAIService._calc_transfer_tax_progressive(10_000_000)
        assert tax == pytest.approx(600_000, rel=0.01)
        assert eff == pytest.approx(0.06, abs=0.001)

    def test_2구간_5000만원_이하_15퍼센트(self):
        """과세표준 3,000만원 → 세율 15%, 누진공제 126만원."""
        tax, eff = TaxAIService._calc_transfer_tax_progressive(30_000_000)
        expected = 30_000_000 * 0.15 - 1_260_000  # 3,240,000
        assert tax == pytest.approx(expected, rel=0.01)

    def test_8구간_10억원_초과_45퍼센트(self):
        """과세표준 20억원 → 세율 45%, 누진공제 6,594만원."""
        tax, eff = TaxAIService._calc_transfer_tax_progressive(2_000_000_000)
        expected = 2_000_000_000 * 0.45 - 65_940_000
        assert tax == pytest.approx(expected, rel=0.01)

    def test_과세표준_0_이하는_세금_0(self):
        tax, eff = TaxAIService._calc_transfer_tax_progressive(0)
        assert tax == 0.0
        assert eff == 0.0

    def test_과세표준_음수는_세금_0(self):
        tax, eff = TaxAIService._calc_transfer_tax_progressive(-1_000_000)
        assert tax == 0.0
        assert eff == 0.0

    def test_실효세율은_세액_나누기_과세표준(self):
        tax, eff = TaxAIService._calc_transfer_tax_progressive(100_000_000)
        assert eff == pytest.approx(tax / 100_000_000, abs=0.001)


class TestCalcLongHoldDeduction:
    """장기보유특별공제율 테스트."""

    def test_3년_미만_공제_없음(self):
        assert TaxAIService._calc_long_hold_deduction(2) == 0.0
        assert TaxAIService._calc_long_hold_deduction(0) == 0.0

    def test_일반_3년_6퍼센트(self):
        rate = TaxAIService._calc_long_hold_deduction(3, is_single_home=False)
        assert rate == pytest.approx(0.06, abs=0.001)

    def test_일반_10년_30퍼센트(self):
        rate = TaxAIService._calc_long_hold_deduction(10, is_single_home=False)
        assert rate == pytest.approx(0.30, abs=0.001)

    def test_일반_10년_초과_30퍼센트_상한(self):
        rate = TaxAIService._calc_long_hold_deduction(15, is_single_home=False)
        assert rate == pytest.approx(0.30, abs=0.001)

    def test_1세대1주택_3년_24퍼센트(self):
        rate = TaxAIService._calc_long_hold_deduction(3, is_single_home=True)
        assert rate == pytest.approx(0.24, abs=0.001)

    def test_1세대1주택_10년_80퍼센트(self):
        rate = TaxAIService._calc_long_hold_deduction(10, is_single_home=True)
        assert rate == pytest.approx(0.80, abs=0.001)

    def test_선형보간_5년_일반(self):
        """일반 5년: 6% + (5-3)/(10-3) * (30%-6%) ≈ 12.86%."""
        rate = TaxAIService._calc_long_hold_deduction(5, is_single_home=False)
        expected = 0.06 + (2 / 7) * (0.30 - 0.06)
        assert rate == pytest.approx(expected, abs=0.001)


class TestCalculateCapitalGainsTax:
    """양도소득세 종합 계산 테스트."""

    def _make_svc(self) -> TaxAIService:
        svc = object.__new__(TaxAIService)
        return svc

    def test_양도차익_없으면_세금_0(self):
        svc = self._make_svc()
        result = svc.calculate_capital_gains_tax(
            sale_price=500_000_000,
            acquisition_price=500_000_000,
            holding_years=5,
        )
        assert result["tax"] == 0.0
        assert result["gain"] == 0.0

    def test_양도차익_음수면_세금_0(self):
        svc = self._make_svc()
        result = svc.calculate_capital_gains_tax(
            sale_price=400_000_000,
            acquisition_price=500_000_000,
            holding_years=5,
        )
        assert result["tax"] == 0.0

    def test_1년_미만_단기_보유_77퍼센트(self):
        svc = self._make_svc()
        result = svc.calculate_capital_gains_tax(
            sale_price=600_000_000,
            acquisition_price=500_000_000,
            holding_years=0,
        )
        assert result["effective_rate"] == pytest.approx(0.77, abs=0.01)
        assert result.get("short_term") is True

    def test_1년이상_2년미만_단기_보유_66퍼센트(self):
        svc = self._make_svc()
        result = svc.calculate_capital_gains_tax(
            sale_price=600_000_000,
            acquisition_price=500_000_000,
            holding_years=1,
        )
        assert result["effective_rate"] == pytest.approx(0.66, abs=0.01)

    def test_2주택_중과_20퍼센트_추가(self):
        svc = self._make_svc()
        result = svc.calculate_capital_gains_tax(
            sale_price=1_000_000_000,
            acquisition_price=500_000_000,
            holding_years=5,
            home_count=2,
        )
        assert result["multi_home_surcharge"] > 0

    def test_3주택_이상_중과_30퍼센트_추가(self):
        svc = self._make_svc()
        result = svc.calculate_capital_gains_tax(
            sale_price=1_000_000_000,
            acquisition_price=500_000_000,
            holding_years=5,
            home_count=3,
        )
        surcharge_3 = result["multi_home_surcharge"]
        result_2 = svc.calculate_capital_gains_tax(
            sale_price=1_000_000_000,
            acquisition_price=500_000_000,
            holding_years=5,
            home_count=2,
        )
        assert surcharge_3 > result_2["multi_home_surcharge"]


class TestCalculateBaseTax:
    """취득세 등 기본 세액 산출 테스트."""

    def _make_svc(self) -> TaxAIService:
        svc = object.__new__(TaxAIService)
        return svc

    def test_취득세_기본_4퍼센트(self):
        svc = self._make_svc()
        amount, rate = svc._calculate_base_tax("acquisition", 500_000_000)
        assert rate == 0.04
        assert amount == pytest.approx(20_000_000, rel=0.01)

    def test_취득세_1가구_1퍼센트(self):
        svc = self._make_svc()
        amount, rate = svc._calculate_base_tax(
            "acquisition", 500_000_000, is_first_home=True,
        )
        assert rate == 0.01

    def test_취득세_9억_초과_고가_12퍼센트(self):
        svc = self._make_svc()
        amount, rate = svc._calculate_base_tax("acquisition", 1_000_000_000)
        assert rate == 0.12

    def test_재산세_주거용_0_1퍼센트(self):
        svc = self._make_svc()
        amount, rate = svc._calculate_base_tax("property", 500_000_000)
        # property default rate is 0.001
        assert rate == 0.001

    def test_등록세_기본_2퍼센트(self):
        svc = self._make_svc()
        amount, rate = svc._calculate_base_tax("registration", 500_000_000)
        assert rate == 0.02


class TestMonteCarloScenarios:
    """Monte Carlo 절세 시나리오 테스트."""

    def _make_svc(self) -> TaxAIService:
        svc = object.__new__(TaxAIService)
        return svc

    def test_양도세_아닌_유형은_빈_시나리오(self):
        svc = self._make_svc()
        scenarios = svc._run_monte_carlo_scenarios(
            "acquisition", 500_000_000, 20_000_000,
        )
        assert scenarios == []

    def test_양도세_시나리오_3개_반환(self):
        svc = self._make_svc()
        scenarios = svc._run_monte_carlo_scenarios(
            "transfer", 1_000_000_000, 100_000_000,
            acquisition_price=500_000_000,
            holding_years=5,
            home_count=1,
        )
        assert len(scenarios) == 3

    def test_시나리오에_절세_금액_포함(self):
        svc = self._make_svc()
        scenarios = svc._run_monte_carlo_scenarios(
            "transfer", 1_000_000_000, 100_000_000,
            acquisition_price=500_000_000,
            holding_years=5,
            home_count=1,
        )
        for s in scenarios:
            assert "savings" in s
            assert "estimated_tax" in s
            assert "savings_pct" in s


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
