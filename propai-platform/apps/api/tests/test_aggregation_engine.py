"""수지 합산 엔진 테스트 — 수익률/ROI/NPV/등급 판정.

참조값: 오산 M04 수익률 19.1%, ROI 23.6%.
"""

import pytest
from app.services.feasibility.aggregation_engine import (
    determine_grade,
    aggregate_feasibility,
    compare_scenarios,
    GRADE_THRESHOLDS,
)


class TestGrade:
    def test_grade_a(self):
        assert determine_grade(25.0) == "A"
        assert determine_grade(20.0) == "A"

    def test_grade_b(self):
        assert determine_grade(19.9) == "B"
        assert determine_grade(15.0) == "B"

    def test_grade_c(self):
        assert determine_grade(14.9) == "C"
        assert determine_grade(10.0) == "C"

    def test_grade_d(self):
        assert determine_grade(9.9) == "D"
        assert determine_grade(5.0) == "D"

    def test_grade_e(self):
        assert determine_grade(4.9) == "E"
        assert determine_grade(0.0) == "E"

    def test_grade_f(self):
        assert determine_grade(-0.1) == "F"
        assert determine_grade(-50.0) == "F"


class TestAggregate:
    def test_m04_reference(self):
        """오산 M04 참조값 대조: 수익률 ~19.1%, ROI ~23.6%."""
        result = aggregate_feasibility(
            total_revenue_won=1_181_200_000_000,     # 11,812억
            total_land_cost_won=22_400_000_000,       # 224억
            total_construction_cost_won=800_000_000_000, # 8,000억 (직접+간접)
            total_finance_cost_won=100_000_000_000,    # 1,000억
            total_other_cost_won=33_300_000_000,       # 333억
            total_tax_cost_won=0,
            equity_won=0,
            discount_rate=0.08,
            project_months=48,
        )

        # 총사업비: 224 + 8000 + 1000 + 333 = 9,557억
        assert result["total_cost_won"] == 955_700_000_000

        # 순이익: 11,812 - 9,557 = 2,255억
        assert result["net_profit_won"] == 225_500_000_000

        # 수익률: 2255/11812 × 100 ≈ 19.09%
        assert result["profit_rate_pct"] == pytest.approx(19.09, abs=0.5)

        # ROI: 2255/9557 × 100 ≈ 23.6%
        assert result["roi_pct"] == pytest.approx(23.6, abs=0.5)

        # 등급: B (15~20%)
        assert result["grade"] == "B"

    def test_zero_revenue(self):
        result = aggregate_feasibility(total_revenue_won=0)
        assert result["profit_rate_pct"] == 0
        assert result["grade"] == "E"  # 0% = E

    def test_cost_breakdown_pct(self):
        result = aggregate_feasibility(
            total_revenue_won=100_000_000_000,
            total_land_cost_won=20_000_000_000,
            total_construction_cost_won=50_000_000_000,
            total_finance_cost_won=10_000_000_000,
            total_other_cost_won=5_000_000_000,
            total_tax_cost_won=5_000_000_000,
        )
        pct = result["cost_breakdown_pct"]
        assert pct["land"] == pytest.approx(22.22, abs=0.1)
        assert pct["construction"] == pytest.approx(55.56, abs=0.1)
        total_pct = sum(pct.values())
        assert total_pct == pytest.approx(100.0, abs=0.1)

    def test_npv_discount(self):
        result = aggregate_feasibility(
            total_revenue_won=100_000_000_000,
            total_construction_cost_won=80_000_000_000,
            discount_rate=0.10,
            project_months=24,
        )
        net = result["net_profit_won"]  # 200억
        npv = result["npv_won"]
        # NPV < 순이익 (할인 적용)
        assert npv < net

    def test_with_equity(self):
        """자기자본 기준 ROI."""
        result = aggregate_feasibility(
            total_revenue_won=100_000_000_000,
            total_construction_cost_won=80_000_000_000,
            equity_won=20_000_000_000,
        )
        # ROI = 200억 / 200억 × 100 = 100%
        assert result["roi_pct"] == 100.0


class TestCompareScenarios:
    def test_ranking(self):
        scenarios = [
            {"name": "낙관", "profit_rate_pct": 25.0, "roi_pct": 30.0, "grade": "A"},
            {"name": "기본", "profit_rate_pct": 15.0, "roi_pct": 20.0, "grade": "B"},
            {"name": "비관", "profit_rate_pct": 5.0, "roi_pct": 8.0, "grade": "D"},
        ]
        result = compare_scenarios(scenarios)
        assert len(result["ranking"]) == 3
        assert result["ranking"][0]["name"] == "낙관"
        assert result["ranking"][0]["rank"] == 1
        assert result["best_profit"]["name"] == "낙관"

    def test_empty(self):
        result = compare_scenarios([])
        assert result["ranking"] == []
