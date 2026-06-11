"""취득단계 세금 엔진 테스트 — A01~A10."""

import pytest
from app.services.tax.acquisition_stage_engine import (
    calculate_a01_acquisition_tax,
    calculate_a04_stamp_tax,
    calculate_a05_registration_tax,
    calculate_a06_housing_bond,
    calculate_a08_farmland_conversion,
    calculate_a09_forest_conversion,
    calculate_a10_development_charge,
    calculate_all_acquisition_stage,
)


class TestA01AcquisitionTax:
    def test_forest(self):
        """임야 취득세 기본율 2.2%."""
        result = calculate_a01_acquisition_tax(10_000_000_000, "forest")
        assert result["amount_won"] == 220_000_000

    def test_land_adjusted_3house(self):
        """조정지역 3주택 중과 12%."""
        result = calculate_a01_acquisition_tax(
            10_000_000_000, "land", house_count=3, is_adjusted=True
        )
        assert result["amount_won"] == 1_200_000_000


class TestA04StampTax:
    def test_small(self):
        # 인지세법 제3조: 3천만~5천만 구간 4만원 (이전 0원은 하위구간 미반영 버그)
        assert calculate_a04_stamp_tax(50_000_000)["amount_won"] == 40_000

    def test_exempt(self):
        # 1천만원 이하 비과세
        assert calculate_a04_stamp_tax(10_000_000)["amount_won"] == 0

    def test_medium(self):
        assert calculate_a04_stamp_tax(500_000_000)["amount_won"] == 150_000

    def test_large(self):
        assert calculate_a04_stamp_tax(5_000_000_000)["amount_won"] == 350_000


class TestA05RegistrationTax:
    def test_basic(self):
        # 2011년 지방세법 개편: 소유권이전 등록세는 취득세(A01) 통합 — 별도 2% 부과는 이중과세
        result = calculate_a05_registration_tax(10_000_000_000)
        assert result["amount_won"] == 0

    def test_mortgage(self):
        # 저당권 설정 등기: 채권금액의 0.2%
        result = calculate_a05_registration_tax(10_000_000_000, mortgage_amount_won=5_000_000_000)
        assert result["amount_won"] == 10_000_000


class TestA06HousingBond:
    def test_basic(self):
        result = calculate_a06_housing_bond(10_000_000_000)
        # 채권매입: 100억 × 5% = 5억, 할인비용: 5억 × 5% = 2500만
        assert result["amount_won"] == 25_000_000


class TestA08FarmlandConversion:
    def test_oasan_reference(self):
        """오산 임야 11.55억 참조 — 농지전용."""
        result = calculate_a08_farmland_conversion(
            area_sqm=77_000,
            official_price_per_sqm=100_000,
        )
        # 100,000 × 30% = 30,000원/m² × 77,000 = 23.1억
        assert result["amount_won"] == 2_310_000_000


class TestA09ForestConversion:
    def test_conservation(self):
        result = calculate_a09_forest_conversion(area_sqm=50_000, forest_type="conservation")
        # 50,000 × 4,700 = 2.35억
        assert result["amount_won"] == 235_000_000


class TestA10DevelopmentCharge:
    def test_capital_area(self):
        """수도권 30% 부과."""
        result = calculate_a10_development_charge(
            end_land_value_won=50_000_000_000,
            start_land_value_won=10_000_000_000,
            development_cost_won=20_000_000_000,
            project_years=3.0,
            region_type="capital_area",
        )
        # 정상상승: 100억 × 3% × 3 = 9억
        # 과표: 500 - 100 - 9 - 200 = 191억
        # 부담금: 191억 × 30% = 57.3억
        assert result["amount_won"] == pytest.approx(5_730_000_000, abs=1)

    def test_no_gain(self):
        """지가상승 없으면 0."""
        result = calculate_a10_development_charge(
            end_land_value_won=10_000_000_000,
            start_land_value_won=10_000_000_000,
            development_cost_won=5_000_000_000,
        )
        assert result["amount_won"] == 0


class TestAllAcquisitionStage:
    def test_forest_full(self):
        """임야 매입 전체 — 10종 중 8종 적용."""
        result = calculate_all_acquisition_stage(
            purchase_won=10_000_000_000,
            land_category="forest",
            area_sqm=50_000,
            official_price_per_sqm=100_000,
        )
        assert result["stage"] == "acquisition"
        # A01~A07 기본 + A09 산림전용 = 8종
        assert result["applicable_count"] == 8
        assert result["total_won"] > 0

    def test_land_basic(self):
        """대지 — 전용부담금 없이 7종."""
        result = calculate_all_acquisition_stage(
            purchase_won=50_000_000_000,
            land_category="land",
        )
        assert result["applicable_count"] == 7
        codes = [it["code"] for it in result["items"]]
        assert "A08" not in codes
        assert "A09" not in codes
