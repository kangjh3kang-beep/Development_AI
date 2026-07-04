"""공사비 엔진 테스트 — 직접/간접 공사비 + 물가보정."""

import pytest

from app.services.feasibility.construction_cost_engine import (
    DEFAULT_DIRECT_COST_PER_SQM,
    apply_cost_index,
    calculate_direct_cost,
    calculate_indirect_cost,
    calculate_total_construction_cost,
    pyeong_to_sqm,
    sqm_to_pyeong,
)


class TestUnitConversion:
    def test_pyeong_to_sqm(self):
        assert pyeong_to_sqm(1) == pytest.approx(3.31, abs=0.01)
        assert pyeong_to_sqm(30) == pytest.approx(99.17, abs=0.01)

    def test_sqm_to_pyeong(self):
        assert sqm_to_pyeong(100) == pytest.approx(30.25, abs=0.01)

    def test_round_trip(self):
        original = 34.0
        converted = sqm_to_pyeong(pyeong_to_sqm(original))
        assert converted == pytest.approx(original, abs=0.1)


class TestCostIndex:
    def test_same_year(self):
        result = apply_cost_index(1_000_000, base_year=2025, target_year=2025)
        assert result["index_factor"] == 1.0
        assert result["adjusted_cost_won"] == 1_000_000

    def test_one_year_increase(self):
        result = apply_cost_index(1_000_000, base_year=2025, target_year=2026, annual_increase_rate=0.03)
        assert result["index_factor"] == pytest.approx(1.03, abs=0.001)
        assert result["adjusted_cost_won"] == 1_030_000

    def test_three_year_compound(self):
        result = apply_cost_index(1_000_000, base_year=2023, target_year=2026, annual_increase_rate=0.05)
        expected = int(1_000_000 * (1.05 ** 3))
        assert result["adjusted_cost_won"] == expected


class TestDirectCost:
    def test_apartment_default(self):
        result = calculate_direct_cost(total_gfa_sqm=100_000)
        assert result["unit_cost_per_sqm"] == DEFAULT_DIRECT_COST_PER_SQM["apartment"]
        assert result["total_direct_cost_won"] == 100_000 * DEFAULT_DIRECT_COST_PER_SQM["apartment"]

    def test_custom_unit_cost(self):
        result = calculate_direct_cost(
            total_gfa_sqm=50_000,
            unit_cost_per_sqm=3_000_000,
        )
        assert result["total_direct_cost_won"] == 150_000_000_000

    def test_with_cost_index(self):
        result = calculate_direct_cost(
            total_gfa_sqm=10_000,
            unit_cost_per_sqm=2_000_000,
            cost_index_factor=1.05,
        )
        assert result["unit_cost_per_sqm"] == 2_100_000
        assert result["total_direct_cost_won"] == 21_000_000_000


class TestIndirectCost:
    def test_default_ratios(self):
        result = calculate_indirect_cost(direct_cost_won=100_000_000_000)
        # 설계4% + 감리3% + 예비5% + 일반3% = 15%
        assert result["total_indirect_cost_won"] == 15_000_000_000

    def test_custom_ratios(self):
        result = calculate_indirect_cost(
            direct_cost_won=100_000_000_000,
            design_fee_ratio=0.05,
            supervision_fee_ratio=0.04,
            contingency_ratio=0.03,
            general_expense_ratio=0.02,
        )
        assert result["total_indirect_cost_won"] == 14_000_000_000


class TestTotalConstructionCost:
    def test_basic_total(self):
        result = calculate_total_construction_cost(
            total_gfa_sqm=100_000,
            building_type="apartment",
        )
        direct = result["direct"]["total_direct_cost_won"]
        indirect = result["indirect"]["total_indirect_cost_won"]
        assert result["total_construction_cost_won"] == direct + indirect
        # 직접: 2,400,000 × 100,000 = 2400억
        # 간접: 15% = 360억
        # 합계: 2760억
        assert result["total_construction_cost_won"] == 276_000_000_000
