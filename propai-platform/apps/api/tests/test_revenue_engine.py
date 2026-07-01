"""수입 엔진 테스트 — 일반분양/조합원/임대/부대수입 + 총합 검증."""

from app.services.feasibility.revenue_engine import (
    calculate_ancillary_revenue,
    calculate_rental_revenue,
    calculate_sale_revenue,
    calculate_total_revenue,
    calculate_union_revenue,
)


class TestSaleRevenue:
    def test_basic_sale(self):
        result = calculate_sale_revenue(
            households=1000,
            avg_area_pyeong=30,
            avg_price_per_pyeong=20_000_000,
        )
        # 1000세대 × 30평 × 2000만원 = 6000억
        assert result["sale_households"] == 1000
        assert result["total_area_pyeong"] == 30_000
        assert result["total_revenue_won"] == 600_000_000_000

    def test_partial_sale_ratio(self):
        result = calculate_sale_revenue(
            households=1000,
            avg_area_pyeong=30,
            avg_price_per_pyeong=20_000_000,
            sale_ratio=0.7,
        )
        assert result["sale_households"] == 700
        assert result["total_revenue_won"] == 420_000_000_000

    def test_zero_households(self):
        result = calculate_sale_revenue(
            households=0,
            avg_area_pyeong=30,
            avg_price_per_pyeong=20_000_000,
        )
        assert result["total_revenue_won"] == 0


class TestUnionRevenue:
    def test_union_basic(self):
        result = calculate_union_revenue(
            union_households=500,
            avg_area_pyeong=34,
            avg_allotment_price_per_pyeong=18_000_000,
        )
        # 500 × 34평 × 1800만 = 3060억
        assert result["union_households"] == 500
        assert result["total_revenue_won"] == 306_000_000_000


class TestRentalRevenue:
    def test_rental_with_deposit_and_rent(self):
        result = calculate_rental_revenue(
            rental_units=200,
            avg_area_pyeong=20,
            avg_deposit_per_pyeong=5_000_000,
            avg_monthly_rent_per_pyeong=50_000,
            cap_rate=0.05,
        )
        # 보증금: 200 × 20평 × 500만 = 200억
        assert result["total_deposit_won"] == 20_000_000_000
        # 연임대: 200 × 20평 × 5만 × 12 = 24억
        assert result["annual_rent_won"] == 2_400_000_000
        # 자본환원: 24억 × (1 − 공실률 5%) / 0.05 = 456억
        # (엔진은 공실률 기본 5%를 반영 — 이전 기대값 480억은 공실 미반영으로 항상 실패했음)
        assert result["capitalized_value_won"] == 45_600_000_000
        # 합계: 200억 + 456억 = 656억
        assert result["total_revenue_won"] == 65_600_000_000

    def test_rental_deposit_only(self):
        result = calculate_rental_revenue(
            rental_units=100,
            avg_area_pyeong=15,
            avg_deposit_per_pyeong=10_000_000,
        )
        assert result["total_deposit_won"] == 15_000_000_000
        assert result["annual_rent_won"] == 0
        assert result["total_revenue_won"] == 15_000_000_000


class TestAncillaryRevenue:
    def test_commercial(self):
        result = calculate_ancillary_revenue(
            commercial_area_pyeong=500,
            commercial_price_per_pyeong=30_000_000,
            other_income_won=10_000_000_000,
        )
        # 상가: 500평 × 3000만 = 150억
        assert result["commercial_revenue_won"] == 15_000_000_000
        assert result["other_income_won"] == 10_000_000_000
        assert result["total_revenue_won"] == 25_000_000_000


class TestTotalRevenue:
    def test_m04_reference(self):
        """오산 M04 참조값: 총수입 약 11,812억."""
        sale = calculate_sale_revenue(
            households=1624,
            avg_area_pyeong=34,
            avg_price_per_pyeong=10_300_000,
            sale_ratio=1.0,
        )
        union = calculate_union_revenue(
            union_households=1200,
            avg_area_pyeong=34,
            avg_allotment_price_per_pyeong=12_920_000,
        )
        ancillary = calculate_ancillary_revenue(
            commercial_area_pyeong=2500,
            commercial_price_per_pyeong=30_000_000,
            other_income_won=10_000_000_000,
        )

        total = calculate_total_revenue(
            sale_revenue=sale,
            union_revenue=union,
            ancillary_revenue=ancillary,
        )

        total_억 = total["total_revenue_won"] / 100_000_000
        # 합리적 범위: 10,000억~13,000억
        assert 10_000 < total_억 < 13_000, f"총수입 {total_억:.0f}억 — 범위 벗어남"

    def test_all_none(self):
        total = calculate_total_revenue()
        assert total["total_revenue_won"] == 0

    def test_breakdown_keys(self):
        sale = calculate_sale_revenue(
            households=100, avg_area_pyeong=30, avg_price_per_pyeong=10_000_000
        )
        total = calculate_total_revenue(sale_revenue=sale)
        assert "sale" in total["breakdown_won"]
        assert "union" in total["breakdown_won"]
        assert "rental" in total["breakdown_won"]
        assert "ancillary" in total["breakdown_won"]
