"""지역세금 데이터 테스트 — 취득세 매트릭스 + 광역교통부담금 계층조회."""

import pytest

from app.services.tax.regional_tax_data import (
    CAPITAL_GAINS_BRACKETS,
    DEVELOPMENT_CHARGE_RATES,
    FARMLAND_CONVERSION_RATE,
    FOREST_CONVERSION_RATES,
    HUG_GUARANTEE_RATES,
    LTDC_RATES_RESIDENTIAL,
    SCHOOL_SITE_CHARGE_RATE,
    SEWAGE_CHARGES_WON,
    VAT_RATE,
    WATER_SUPPLY_CHARGES_WON,
    get_acquisition_tax_rates,
    get_metro_transport_charge,
    get_utility_charge,
)

# ── 취득세 매트릭스 ──

class TestAcquisitionTaxMatrix:
    def test_forest_basic(self):
        rates = get_acquisition_tax_rates("forest", 0, False)
        assert rates["base_rate"] == 0.022
        assert rates["total_rate"] == pytest.approx(0.026, abs=1e-6)

    def test_farmland_basic(self):
        rates = get_acquisition_tax_rates("farmland", 0, False)
        assert rates["base_rate"] == 0.030
        assert rates["total_rate"] == pytest.approx(0.034, abs=1e-6)

    def test_land_non_housing(self):
        rates = get_acquisition_tax_rates("land", 0, False)
        assert rates["base_rate"] == 0.040
        assert rates["total_rate"] == pytest.approx(0.046, abs=1e-6)

    def test_land_1house_non_adjusted(self):
        rates = get_acquisition_tax_rates("land", 1, False)
        assert rates["base_rate"] == 0.010
        assert rates["surcharge_rate"] == 0.0

    def test_land_2house_adjusted_surcharge(self):
        """조정지역 2주택 중과."""
        rates = get_acquisition_tax_rates("land", 2, True)
        assert rates["base_rate"] == 0.080
        assert rates["total_rate"] == pytest.approx(0.090, abs=1e-6)

    def test_land_3house_adjusted_surcharge(self):
        """조정지역 3주택 중과."""
        rates = get_acquisition_tax_rates("land", 3, True)
        assert rates["base_rate"] == 0.120
        assert rates["total_rate"] == pytest.approx(0.134, abs=1e-6)

    def test_fallback_unknown_category(self):
        """알 수 없는 지목 → 대지 비주택 폴백."""
        rates = get_acquisition_tax_rates("unknown", 0, False)
        assert rates["base_rate"] == 0.040

    def test_house_count_capped_at_3(self):
        """주택수 5 → 3으로 cap."""
        rates = get_acquisition_tax_rates("land", 5, True)
        assert rates == get_acquisition_tax_rates("land", 3, True)


# ── 광역교통부담금 ──

class TestMetroTransportCharge:
    def test_seoul_base(self):
        result = get_metro_transport_charge("서울", "강남구", 1000, "apartment")
        assert result["source"] == "base"
        assert result["per_hh_10k_won"] == 21.0

    def test_gyeonggi_goyang_override(self):
        """시군구 오버라이드: 경기 고양시 → 서울급."""
        result = get_metro_transport_charge("경기", "고양시", 500, "apartment")
        assert result["source"] == "override"
        assert result["per_hh_10k_won"] == 21.0

    def test_gyeonggi_hwaseong_override(self):
        result = get_metro_transport_charge("경기", "화성시", 1000, "officetel")
        assert result["source"] == "override"
        assert result["per_hh_10k_won"] == 8.5

    def test_unregistered_region(self):
        result = get_metro_transport_charge("제주", "제주시", 100, "apartment")
        assert result["source"] == "none"
        assert result["per_hh_10k_won"] == 0.0

    def test_total_calculation(self):
        result = get_metro_transport_charge("서울", "서초구", 2000, "apartment")
        # 21.0만원 × 2000세대 / 10000 = 4.2억
        assert result["total_100m_won"] == pytest.approx(4.2, abs=0.01)


# ── 상하수도 원인자부담금 ──

class TestUtilityCharge:
    def test_sido_lookup(self):
        assert get_utility_charge(WATER_SUPPLY_CHARGES_WON, "서울", "강남구") == 150_000

    def test_sigungu_override(self):
        assert get_utility_charge(WATER_SUPPLY_CHARGES_WON, "경기", "수원시") == 130_000

    def test_unregistered_returns_none(self):
        # ★조례 미등록 지역 → None (수도법 §71 조례위임·전국 단일값 없음). 종전 임의 폴백 120,000은
        #   지어낸 값이라 무목업 위반이었음. 소비처(B03/B04)가 unavailable로 정직 처리한다.
        assert get_utility_charge(WATER_SUPPLY_CHARGES_WON, "충남", "논산시") is None

    def test_sewage_sido(self):
        assert get_utility_charge(SEWAGE_CHARGES_WON, "부산", "해운대구") == 160_000


# ── 상수값 검증 ──

class TestConstants:
    def test_development_charge_rates(self):
        assert DEVELOPMENT_CHARGE_RATES["capital_area"] == 0.30
        assert DEVELOPMENT_CHARGE_RATES["metropolitan"] == 0.25
        assert DEVELOPMENT_CHARGE_RATES["province"] == 0.20

    def test_farmland_conversion(self):
        assert FARMLAND_CONVERSION_RATE == 0.30

    def test_forest_conversion_rates(self):
        assert FOREST_CONVERSION_RATES["conservation"] == 4_700
        assert FOREST_CONVERSION_RATES["semi_conservation"] == 2_500

    def test_school_site(self):
        # 학교용지법 §5의2 현행: 공동주택 0.4% (2025.6.21 개정, 구값 0.8% 아님).
        assert SCHOOL_SITE_CHARGE_RATE == 0.004

    def test_hug_guarantee(self):
        assert HUG_GUARANTEE_RATES["apartment"] == 0.0015

    def test_vat(self):
        assert VAT_RATE == 0.10

    def test_capital_gains_brackets_count(self):
        assert len(CAPITAL_GAINS_BRACKETS) == 8

    def test_ltdc_rates(self):
        assert LTDC_RATES_RESIDENTIAL[3] == 0.06
        assert LTDC_RATES_RESIDENTIAL[15] == 0.30
