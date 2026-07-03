"""통합 세금 엔진 테스트 — 38종 일괄 + 개발유형별 코드."""

from app.services.tax.integrated_tax_engine import (
    calculate_all_taxes,
    get_applicable_tax_codes,
)


class TestCalculateAllTaxes:
    def test_basic_land_project(self):
        """대지 기본 프로젝트: 4단계 전체 계산."""
        result = calculate_all_taxes(
            purchase_won=50_000_000_000,
            land_category="land",
            sido_name="서울",
            sigungu_name="강남구",
            total_households=1000,
            total_sale_amount_won=500_000_000_000,
            total_gfa_sqm=100_000,
            total_units=1000,
            avg_area_sqm=100,
            building_type="apartment",
        )
        assert "acquisition" in result
        assert "construction" in result
        assert "sale" in result
        assert "disposal" in result
        assert result["grand_total_won"] > 0
        assert result["total_items_count"] >= 20  # 최소 20종 이상

    def test_forest_project(self):
        """임야 — A09 산림전용 포함."""
        result = calculate_all_taxes(
            purchase_won=10_000_000_000,
            land_category="forest",
            area_sqm=50_000,
            official_price_per_sqm=100_000,
            sido_name="경기",
            sigungu_name="용인시",
            total_households=500,
            total_sale_amount_won=200_000_000_000,
            total_gfa_sqm=50_000,
        )
        acq_codes = [it["code"] for it in result["acquisition"]["items"]]
        assert "A09" in acq_codes

    def test_farmland_project(self):
        """농지 — A08 농지전용 포함."""
        result = calculate_all_taxes(
            purchase_won=5_000_000_000,
            land_category="farmland",
            area_sqm=30_000,
            official_price_per_sqm=80_000,
        )
        acq_codes = [it["code"] for it in result["acquisition"]["items"]]
        assert "A08" in acq_codes

    def test_with_disposal(self):
        """양도세 포함 — D01, D03 계산."""
        result = calculate_all_taxes(
            purchase_won=10_000_000_000,
            gain_10k_won=100_000,  # 10억
            gain_won=1_000_000_000,
            holding_years=5,
        )
        disposal_codes = [it["code"] for it in result["disposal"]["items"]]
        assert "D01" in disposal_codes
        assert "D03" in disposal_codes
        assert "D04" in disposal_codes  # 5년 보유 → 장기보유공제

    def test_summary_by_stage(self):
        result = calculate_all_taxes(
            purchase_won=10_000_000_000,
            total_households=500,
            total_sale_amount_won=100_000_000_000,
            total_gfa_sqm=50_000,
        )
        summary = result["summary_by_stage"]
        assert "acquisition" in summary
        assert "construction" in summary
        assert "sale" in summary
        assert "disposal" in summary


class TestApplicableTaxCodes:
    def test_land_basic(self):
        codes = get_applicable_tax_codes(development_type="M04", land_category="land")
        assert "A01" in codes
        assert "B01" in codes
        assert "C01" in codes
        assert "D01" in codes
        assert "A08" not in codes  # 대지 → 농지전용 없음
        assert "A09" not in codes  # 대지 → 산림전용 없음

    def test_farmland(self):
        codes = get_applicable_tax_codes(development_type="M04", land_category="farmland")
        assert "A08" in codes

    def test_forest(self):
        codes = get_applicable_tax_codes(development_type="M04", land_category="forest")
        assert "A09" in codes

    def test_m02_reconstruction(self):
        """M02 재건축 → D05 초과이익환수."""
        codes = get_applicable_tax_codes(development_type="M02")
        assert "D05" in codes

    def test_min_count(self):
        """최소 20종 이상."""
        codes = get_applicable_tax_codes(development_type="M01")
        assert len(codes) >= 20
