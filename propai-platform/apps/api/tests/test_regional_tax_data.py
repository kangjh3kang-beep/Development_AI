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
    """★실산식: 표준건축비 × 부과율 × 건축연면적 — **법 §11조의3①2·3호**.

    이전 '만원/세대 정액표'(서울 21만원/세대 등)는 법정 산식(연면적 기반)과 다른 날조라 폐기 후 교정.

    ★★**2026-08-27 두 번째 교정 — 인용 조문과 부과율이 둘 다 틀렸다.**
      · 종전 docstring 은 근거를 **§7의2** 라 적었다. 그 조문은
        **「대규모 개발사업의 광역교통 개선대책」**(개발면적 50만㎡ 이상 등)으로
        **부담금 산정과 무관**하다. 산정기준은 **§11조의3** 이다(법제처 DRF 원문 확인).
      · 종전 부과율 **1%(전용 85㎡ 이하)/2%** 는 **법령에 근거가 없다** —
        법·시행령 원문 양쪽에서 **`전용면적` 출현 0회**(대조군: 같은 문서에 `부담금` 63회).
      · 시행령 **§16조의2⑧2호**: *"법 제11조의3제1항제2호 및 제3호의 부과율 : **100분의 2**.
        다만, 별표 1의 대도시권중 **수도권인 경우에는 100분의 4**"*
      → **수도권 4% · 그 외 대도시권 2%**. 상세는
        `tests/test_metro_transport_rate_matches_statute.py`.

    ★이 클래스가 종전 값을 **초록으로 굳히고 있었다** — 값 단언이 틀린 규약을 고정한 사례.
    """

    def test_formula_capital_area_four_percent(self):
        """수도권(서울) — 시행령 §16조의2⑧2호 단서. 200만 × 4% × 10,000㎡ = 8억."""
        r = get_metro_transport_charge(
            sido_name="서울", gfa_sqm=10_000, building_type="apartment",
            exclusive_area_sqm=59, standard_build_cost_won_per_sqm=2_000_000,
        )
        assert r["applicable"] is True
        assert r["rate"] == 0.04
        assert r["amount_won"] == 800_000_000

    def test_formula_non_capital_metro_two_percent(self):
        """비수도권 대도시권(부산) — 같은 호 본문. 200만 × 2% × 10,000㎡ = 4억.

        ★수도권 케이스와 **같은 실행에서** 갈리는지가 핵심이다(한쪽만 보면 상수 구현도 통과).
        """
        r = get_metro_transport_charge(
            sido_name="부산", gfa_sqm=10_000, building_type="apartment",
            exclusive_area_sqm=100, standard_build_cost_won_per_sqm=2_000_000,
        )
        assert r["rate"] == 0.02
        assert r["amount_won"] == 400_000_000

    def test_exclusive_area_does_not_change_the_rate(self):
        """★85㎡ 분기가 부활하면 여기서 잡힌다 — 경계 양쪽이 **같은 요율**이어야 한다."""
        rates = {
            get_metro_transport_charge(
                sido_name="경기", gfa_sqm=10_000, building_type="apartment",
                exclusive_area_sqm=a, standard_build_cost_won_per_sqm=2_000_000,
            )["rate"]
            for a in (59, 84.9, 85.0, 85.1, 100, None)
        }
        assert rates == {0.04}, f"전용면적이 요율을 바꾼다: {rates}"

    def test_non_housing_uses_the_same_statutory_rate(self):
        """주택 외 시설도 같은 호의 요율 — 수도권이면 4%."""
        r = get_metro_transport_charge(
            sido_name="서울", gfa_sqm=10_000, building_type="commercial",
            standard_build_cost_won_per_sqm=2_000_000,
        )
        assert r["rate"] == 0.04

    def test_unavailable_without_standard_cost(self):
        """★무목업: 표준건축비 고시값 미주입 → amount_won None(정직 unavailable·날조 금지)."""
        r = get_metro_transport_charge(sido_name="서울", gfa_sqm=10_000, building_type="apartment")
        assert r["amount_won"] is None
        assert r["confidence"] == "unavailable"

    def test_non_metro_area_zero(self):
        """비대도시권(제주) → 미부과(0·applicable False)."""
        r = get_metro_transport_charge(
            sido_name="제주", gfa_sqm=10_000, building_type="apartment",
            standard_build_cost_won_per_sqm=2_000_000,
        )
        assert r["applicable"] is False
        assert r["amount_won"] == 0

    def test_env_channel_injects_standard_build_cost(self, monkeypatch):
        """운영 주입 채널: env METRO_STANDARD_BUILD_COST_WON_PER_SQM → 실산정 활성."""
        monkeypatch.setenv("METRO_STANDARD_BUILD_COST_WON_PER_SQM", "1,210,000")
        r = get_metro_transport_charge(sido_name="서울", gfa_sqm=10_000, building_type="apartment")
        # 1,210,000 × 4%(서울=수도권 · 시행령 §16조의2⑧2호 단서) × 10,000㎡
        assert r["amount_won"] == int(1_210_000 * 0.04 * 10_000)
        assert r["standard_build_cost_won_per_sqm"] == 1_210_000

    def test_env_channel_explicit_arg_wins_over_env(self, monkeypatch):
        """호출부 명시 인자 > env 우선순위."""
        monkeypatch.setenv("METRO_STANDARD_BUILD_COST_WON_PER_SQM", "1210000")
        r = get_metro_transport_charge(
            sido_name="서울", gfa_sqm=10_000, building_type="commercial",
            standard_build_cost_won_per_sqm=2_000_000,
        )
        assert r["standard_build_cost_won_per_sqm"] == 2_000_000

    def test_env_channel_invalid_value_stays_unavailable(self, monkeypatch):
        """env 비정상 값(음수/0/문자) → None 유지(정직 unavailable·날조 금지)."""
        for bad in ("-5", "abc", "0"):
            monkeypatch.setenv("METRO_STANDARD_BUILD_COST_WON_PER_SQM", bad)
            r = get_metro_transport_charge(sido_name="서울", gfa_sqm=10_000, building_type="apartment")
            assert r["amount_won"] is None
            assert r["confidence"] == "unavailable"


# ── 상하수도 원인자부담금 ──

class TestUtilityCharge:
    def test_lookup_returns_none_while_tables_are_unsourced(self):
        """★2026-08-27: 종전 `== 150_000` / `== 130_000` 단언은 **출처 없는 생성값**을 굳혔다.

        표를 비웠으므로 모든 조회가 `None` 이다. 조회 **경로**(시군구→시도 폴백)는
        `test_sigungu_key_is_tried_before_sido` 가 별도로 잠근다.
        """
        assert get_utility_charge(SEWAGE_CHARGES_WON, "서울", "강남구") is None
        assert get_utility_charge(SEWAGE_CHARGES_WON, "경기", "수원시") is None

    def test_sigungu_key_is_tried_before_sido(self):
        """★조회 **경로**는 살아 있어야 한다 — 표가 비었다고 배선까지 죽으면 안 된다.

        합성 표로 두 모집단을 가른다(시군구 히트 vs 시도 폴백).
        """
        from app.services.tax.regional_tax_data import OrdinanceUnitRate

        def _r(w):
            return OrdinanceUnitRate(won_per_cbm_day=w, basis="테스트", source_url="test://", as_of="2026-01-01")

        table = {"경기": _r(100), "경기_수원시": _r(200)}
        assert get_utility_charge(table, "경기", "수원시").won_per_cbm_day == 200, "시군구 우선"
        assert get_utility_charge(table, "경기", "없는시").won_per_cbm_day == 100, "시도 폴백"
        assert get_utility_charge(table, "강원", "정선군") is None, "미등록"

    def test_unregistered_returns_none(self):
        # ★조례 미등록 지역 → None (수도법 §71 조례위임·전국 단일값 없음). 종전 임의 폴백 120,000은
        #   지어낸 값이라 무목업 위반이었음. 소비처(B03/B04)가 unavailable로 정직 처리한다.
        assert get_utility_charge(SEWAGE_CHARGES_WON, "충남", "논산시") is None

    def test_sewage_table_is_also_empty(self):
        assert get_utility_charge(SEWAGE_CHARGES_WON, "부산", "해운대구") is None


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
