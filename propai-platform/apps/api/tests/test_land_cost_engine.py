"""토지비 엔진 테스트 — 매입비/취득세/전용부담금 자동 계산."""

import pytest

from app.services.feasibility.land_cost_engine import (
    calculate_acquisition_tax,
    calculate_farmland_conversion_fee,
    calculate_forest_conversion_fee,
    calculate_land_purchase_cost,
    calculate_total_land_cost,
)


class TestLandPurchaseCost:
    def test_basic(self):
        result = calculate_land_purchase_cost(
            total_area_sqm=50_000,
            official_price_per_sqm=500_000,
            price_multiplier=1.2,
        )
        # 50,000m² × 500,000원 × 1.2 = 300억
        assert result["total_purchase_won"] == 30_000_000_000
        assert result["unit_price_won"] == 600_000

    def test_no_multiplier(self):
        result = calculate_land_purchase_cost(
            total_area_sqm=10_000,
            official_price_per_sqm=1_000_000,
        )
        assert result["total_purchase_won"] == 10_000_000_000


class TestAcquisitionTax:
    def test_forest_tax(self):
        """임야 취득세: 2.6% (기본 2.2 + 교육 0.2 + 농특 0.2)."""
        result = calculate_acquisition_tax(
            purchase_amount_won=10_000_000_000,
            land_category="forest",
        )
        assert result["tax_amount_won"] == pytest.approx(260_000_000, abs=1)

    def test_land_adjusted_2house(self):
        """조정지역 2주택 중과: 9%."""
        result = calculate_acquisition_tax(
            purchase_amount_won=10_000_000_000,
            land_category="land",
            house_count=2,
            is_adjusted_area=True,
        )
        assert result["tax_amount_won"] == pytest.approx(900_000_000, abs=1)

    def test_detail_breakdown(self):
        result = calculate_acquisition_tax(
            purchase_amount_won=10_000_000_000,
            land_category="land",
            house_count=0,
        )
        detail = result["detail"]
        assert detail["base_tax"] == 400_000_000
        assert detail["education_tax"] == 40_000_000
        assert detail["rural_tax"] == 20_000_000


class TestFarmlandConversion:
    def test_basic(self):
        result = calculate_farmland_conversion_fee(
            area_sqm=30_000,
            official_price_per_sqm=100_000,
        )
        # 100,000 × 30% = 30,000원/m² (상한 50,000 미만)
        assert result["fee_per_sqm"] == 30_000
        assert result["total_fee_won"] == 900_000_000

    def test_cap_applied(self):
        """상한 적용: 공시지가 200,000 → 30% = 60,000 → cap 50,000."""
        result = calculate_farmland_conversion_fee(
            area_sqm=10_000,
            official_price_per_sqm=200_000,
        )
        assert result["fee_per_sqm"] == 50_000
        assert result["total_fee_won"] == 500_000_000


class TestForestConversion:
    def test_conservation(self):
        result = calculate_forest_conversion_fee(
            area_sqm=20_000,
            forest_type="conservation",
        )
        assert result["rate_per_sqm"] == 4_700
        assert result["total_fee_won"] == 94_000_000

    def test_semi_default(self):
        result = calculate_forest_conversion_fee(area_sqm=10_000)
        assert result["rate_per_sqm"] == 2_500


class TestTotalLandCost:
    def test_farmland_total(self):
        result = calculate_total_land_cost(
            total_area_sqm=50_000,
            official_price_per_sqm=100_000,
            price_multiplier=1.0,
            land_category="farmland",
        )
        # 매입: 50,000 × 100,000 = 50억
        purchase = result["purchase"]["total_purchase_won"]
        assert purchase == 5_000_000_000
        # 취득세: 3.4%
        tax = result["acquisition_tax"]["tax_amount_won"]
        assert tax == pytest.approx(170_000_000, abs=1)
        # 농지전용: 30,000원/m² × 50,000 = 15억
        conv = result["conversion_fee"]["total_fee_won"]
        assert conv == 1_500_000_000
        # 합계
        assert result["total_land_cost_won"] == purchase + tax + conv

    def test_land_no_conversion(self):
        """대지(land) — 전용부담금 없음."""
        result = calculate_total_land_cost(
            total_area_sqm=10_000,
            official_price_per_sqm=500_000,
            land_category="land",
        )
        assert result["conversion_fee"]["total_fee_won"] == 0
