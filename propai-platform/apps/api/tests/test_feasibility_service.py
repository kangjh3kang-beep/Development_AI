"""FeasibilityService 단위 테스트.

캐시플로우 생성, IRR 계산, 투자회수기간, 리스크 스코어 등
순수 계산 로직을 검증한다.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from packages.schemas.models import FeasibilityCashflowRow

from apps.api.services.feasibility_service import FeasibilityService


class TestBuildCashflows:
    """_build_cashflows 정적 메서드 테스트."""

    def test_기본_캐시플로우_생성(self):
        rows = FeasibilityService._build_cashflows(
            annual_revenue_krw=100_000_000,
            annual_operating_cost_krw=60_000_000,
            annual_growth_rate=0.03,
            discount_rate=0.08,
            analysis_years=5,
        )
        assert len(rows) == 5
        assert rows[0].year == 1
        assert rows[4].year == 5

    def test_1년차_성장율_미적용(self):
        rows = FeasibilityService._build_cashflows(
            annual_revenue_krw=100_000_000,
            annual_operating_cost_krw=60_000_000,
            annual_growth_rate=0.05,
            discount_rate=0.08,
            analysis_years=1,
        )
        assert rows[0].revenue_krw == pytest.approx(100_000_000, rel=0.01)
        assert rows[0].operating_cost_krw == pytest.approx(60_000_000, rel=0.01)

    def test_2년차_성장율_적용(self):
        rows = FeasibilityService._build_cashflows(
            annual_revenue_krw=100_000_000,
            annual_operating_cost_krw=60_000_000,
            annual_growth_rate=0.05,
            discount_rate=0.08,
            analysis_years=2,
        )
        assert rows[1].revenue_krw == pytest.approx(105_000_000, rel=0.01)

    def test_순현금흐름은_매출_마이너스_운영비(self):
        rows = FeasibilityService._build_cashflows(
            annual_revenue_krw=100_000_000,
            annual_operating_cost_krw=40_000_000,
            annual_growth_rate=0.0,
            discount_rate=0.08,
            analysis_years=1,
        )
        assert rows[0].net_cashflow_krw == pytest.approx(60_000_000, rel=0.01)

    def test_할인현금흐름_계산(self):
        rows = FeasibilityService._build_cashflows(
            annual_revenue_krw=100_000_000,
            annual_operating_cost_krw=60_000_000,
            annual_growth_rate=0.0,
            discount_rate=0.10,
            analysis_years=1,
        )
        expected_dcf = 40_000_000 / 1.10
        assert rows[0].discounted_cashflow_krw == pytest.approx(expected_dcf, rel=0.01)


class TestCalcIRR:
    """_calc_irr 정적 메서드 테스트."""

    def test_기본_IRR_계산(self):
        """초기투자 -100, 매년 30씩 5년 → IRR ≈ 15%."""
        cashflows = [-100, 30, 30, 30, 30, 30]
        irr = FeasibilityService._calc_irr(cashflows)
        assert 0.10 < irr < 0.20

    def test_즉시_회수_높은_IRR(self):
        """초기투자 -100, 1년 후 200 → IRR ≈ 100%."""
        cashflows = [-100, 200]
        irr = FeasibilityService._calc_irr(cashflows)
        assert irr == pytest.approx(1.0, abs=0.02)

    def test_전액_손실_음수_IRR(self):
        """초기투자 -100, 매년 10씩 3년 → IRR < 0."""
        cashflows = [-100, 10, 10, 10]
        irr = FeasibilityService._calc_irr(cashflows)
        assert irr < 0


class TestCalcPaybackPeriod:
    """_calc_payback_period_months 정적 메서드 테스트."""

    def _make_rows(self, net_cashflow: float, years: int) -> list[FeasibilityCashflowRow]:
        return [
            FeasibilityCashflowRow(
                year=y,
                revenue_krw=net_cashflow + 10,
                operating_cost_krw=10,
                net_cashflow_krw=net_cashflow,
                discounted_cashflow_krw=net_cashflow * 0.9,
            )
            for y in range(1, years + 1)
        ]

    def test_3년_내_회수(self):
        """투자 100, 매년 40 → 3년 후 회수."""
        rows = self._make_rows(40_000_000, 5)
        months = FeasibilityService._calc_payback_period_months(
            total_investment_krw=100_000_000,
            annual_cashflows=rows,
            exit_value_krw=0,
        )
        assert months == 36  # 3년 × 12

    def test_잔존가치로_회수(self):
        """캐시플로우로 못 갚지만 잔존가치로 회수."""
        rows = self._make_rows(10_000_000, 5)
        months = FeasibilityService._calc_payback_period_months(
            total_investment_krw=100_000_000,
            annual_cashflows=rows,
            exit_value_krw=100_000_000,
        )
        assert months == 60  # 5년 × 12


class TestCalcRiskScore:
    """_calc_risk_score 정적 메서드 테스트."""

    def test_고수익_저위험(self):
        """높은 IRR + 빠른 회수기간 → 낮은 리스크."""
        score = FeasibilityService._calc_risk_score(
            irr=0.20,
            payback_period_months=24,
            total_revenue_krw=200_000_000,
            total_operating_cost_krw=80_000_000,
            discount_rate=0.05,
        )
        assert score < 0.3

    def test_저수익_고위험(self):
        """낮은 IRR + 긴 회수기간 → 높은 리스크."""
        score = FeasibilityService._calc_risk_score(
            irr=0.02,
            payback_period_months=120,
            total_revenue_krw=100_000_000,
            total_operating_cost_krw=90_000_000,
            discount_rate=0.15,
        )
        assert score > 0.5

    def test_리스크_스코어_0_1_범위(self):
        score = FeasibilityService._calc_risk_score(
            irr=0.10,
            payback_period_months=48,
            total_revenue_krw=150_000_000,
            total_operating_cost_krw=80_000_000,
            discount_rate=0.08,
        )
        assert 0.0 <= score <= 1.0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
