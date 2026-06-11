"""R2 법령 시행일 버전드 룰엔진 테스트.

검증 축:
1) get_rule 로더 — 현행 최신본(as_of=None)·구간 일치·수록 구간 밖 정직 경고.
2) 별칭 하위호환 — 기존 상수명(ACQUISITION_TAX_MATRIX 등)이 정답값 그대로(불변).
3) 2026-05-09 양도세 다주택 중과 한시 배제 종료 경계일 ±1일(05-08/05-09/05-10).
4) calculate_all_taxes(as_of_date) — 미지정 시 기존 응답 완전 동일(정답값 고정),
   지정 시 tax_rule_versions·legal_refs 시행일 표기 가산(계산값 불변).
"""

from datetime import date

import pytest

from app.services.tax.regional_tax_data import (
    ACQUISITION_TAX_MATRIX,
    CAPITAL_GAINS_BRACKETS,
    LAND_COMPREHENSIVE_DEDUCTION_WON,
    LAND_FAIR_MARKET_RATIO,
    LAND_COMPREHENSIVE_TAX_BRACKETS,
    calc_land_comprehensive_property_tax,
    get_acquisition_tax_rates,
    get_rule,
)
from app.services.tax.integrated_tax_engine import calculate_all_taxes


# ── 1) get_rule 로더 ──

class TestGetRuleLoader:
    def test_unknown_rule_returns_none(self):
        assert get_rule("no_such_rule") is None

    def test_latest_default_acquisition_matrix(self):
        """as_of=None → 현행 최신본 + 시행일 메타."""
        r = get_rule("acquisition_tax_matrix")
        assert r["match"] == "latest"
        assert r["effective_from"] == "2020-08-12"
        assert r["effective_to"] is None
        assert r["legal_ref_key"] == "acquisition_tax"
        assert len(r["value"]) == 16

    def test_exact_window_match(self):
        r = get_rule("capital_gains_brackets", as_of=date(2024, 6, 1))
        assert r["match"] == "exact"
        assert r["effective_from"] == "2023-01-01"
        assert r["effective_to"] is None
        assert r["legal_ref_key"] == "capital_gains_tax"

    def test_out_of_range_honest_warning(self):
        """수록 구간 이전 as_of → 가짜 과거값 대신 폴백+경고 정직 표기."""
        r = get_rule("capital_gains_brackets", as_of=date(2022, 12, 31))
        assert r["match"] == "out_of_range"
        assert "미보유" in r["warning"]
        # 폴백 value는 최초 수록본(=현행) 그대로 — 임의 추정값 금지.
        assert r["value"][0] == [0, 0.06, 0]
        assert r["value"][-1] == [100000, 0.45, 6594]

    def test_value_is_deep_copy(self):
        """반환 value 변형이 캐시를 오염시키지 않는다."""
        r1 = get_rule("capital_gains_brackets")
        r1["value"][0][1] = 9.99
        r2 = get_rule("capital_gains_brackets")
        assert r2["value"][0][1] == 0.06


# ── 2) 별칭 하위호환 — 기존 정답값 불변 (별칭 경유) ──

class TestAliasBackwardCompat:
    def test_acquisition_matrix_exact(self):
        """JSON 외부화 후에도 매트릭스 전체가 기존 하드코딩 값과 동일."""
        expected = {
            ("forest", 0, False): (0.022, 0.0, 0.002, 0.002),
            ("forest", 0, True): (0.022, 0.0, 0.002, 0.002),
            ("forest", 1, False): (0.022, 0.0, 0.002, 0.002),
            ("forest", 1, True): (0.022, 0.0, 0.002, 0.002),
            ("farmland", 0, False): (0.030, 0.0, 0.002, 0.002),
            ("farmland", 0, True): (0.030, 0.0, 0.002, 0.002),
            ("farmland", 1, False): (0.030, 0.0, 0.002, 0.002),
            ("farmland", 1, True): (0.030, 0.0, 0.002, 0.002),
            ("land", 0, False): (0.040, 0.0, 0.004, 0.002),
            ("land", 0, True): (0.040, 0.0, 0.004, 0.002),
            ("land", 1, False): (0.010, 0.0, 0.001, 0.0),
            ("land", 1, True): (0.010, 0.0, 0.001, 0.0),
            ("land", 2, False): (0.010, 0.0, 0.001, 0.0),
            ("land", 2, True): (0.080, 0.0, 0.004, 0.006),
            ("land", 3, False): (0.080, 0.0, 0.004, 0.006),
            ("land", 3, True): (0.120, 0.0, 0.004, 0.010),
        }
        assert ACQUISITION_TAX_MATRIX == expected

    def test_capital_gains_brackets_exact(self):
        assert CAPITAL_GAINS_BRACKETS == [
            (0, 0.06, 0),
            (1_400, 0.15, 126),
            (5_000, 0.24, 576),
            (8_800, 0.35, 1_544),
            (15_000, 0.38, 1_994),
            (30_000, 0.40, 2_594),
            (50_000, 0.42, 3_594),
            (100_000, 0.45, 6_594),
        ]

    def test_land_comprehensive_constants_exact(self):
        assert LAND_COMPREHENSIVE_DEDUCTION_WON == 500_000_000
        assert LAND_FAIR_MARKET_RATIO == 1.0
        assert LAND_COMPREHENSIVE_TAX_BRACKETS == [
            (1_500_000_000, 0.010, 0),
            (4_500_000_000, 0.020, 15_000_000),
            (float("inf"), 0.030, 60_000_000),
        ]

    def test_acquisition_rates_pinned(self):
        """기존 함수 경로 정답값(별칭 경유) 불변."""
        assert get_acquisition_tax_rates("land", 3, True)["base_rate"] == 0.120
        assert get_acquisition_tax_rates("land", 3, True)["total_rate"] == pytest.approx(0.134, abs=1e-6)
        # 주택 6~9억 슬라이딩(7.5억 → 2%) 경로도 불변.
        assert get_acquisition_tax_rates("land", 1, False, purchase_won=750_000_000)["base_rate"] == 0.02

    def test_land_comprehensive_tax_pinned(self):
        """종부세 계산 정답값 고정: 공시 20억 → 과세표준 15억 → 연 1,500만원."""
        r = calc_land_comprehensive_property_tax(2_000_000_000)
        assert r["annual_won"] == 15_000_000
        assert r["rate"] == 0.010
        assert r["taxable_won"] == 1_500_000_000
        assert r["deduction_won"] == 500_000_000
        assert r["fair_market_ratio"] == 1.0


# ── as_of 파라미터 (additive) — 단일 수록 버전이므로 현행과 동일 ──

class TestAsOfParams:
    def test_acquisition_rates_as_of_equals_current(self):
        base = get_acquisition_tax_rates("land", 2, True, purchase_won=1_200_000_000)
        versioned = get_acquisition_tax_rates(
            "land", 2, True, purchase_won=1_200_000_000, as_of=date(2025, 1, 1)
        )
        assert versioned == base

    def test_land_tax_as_of_equals_current(self):
        base = calc_land_comprehensive_property_tax(2_000_000_000, holding_years=3)
        versioned = calc_land_comprehensive_property_tax(
            2_000_000_000, holding_years=3, as_of=date(2025, 6, 1)
        )
        assert versioned == base


# ── 3) 2026-05-09 중과배제 한시조항 종료 경계일 ±1일 ──

class TestSurchargeExclusionBoundary:
    RULE = "capital_gains_multi_home_surcharge_exclusion"

    def test_day_before_end(self):
        """종료 전일(2026-05-08): 배제 버전 선택."""
        r = get_rule(self.RULE, as_of=date(2026, 5, 8))
        assert r["match"] == "exact"
        assert r["value"]["surcharge_excluded"] is True
        assert r["effective_from"] == "2022-05-10"
        assert r["effective_to"] == "2026-05-09"

    def test_end_day_inclusive(self):
        """종료 당일(2026-05-09): 배제 버전 포함(경계 포함)."""
        r = get_rule(self.RULE, as_of=date(2026, 5, 9))
        assert r["match"] == "exact"
        assert r["value"]["surcharge_excluded"] is True
        assert r["effective_to"] == "2026-05-09"

    def test_day_after_end(self):
        """종료 익일(2026-05-10): 종료 후 버전 선택 — 다른 룰 버전."""
        r = get_rule(self.RULE, as_of=date(2026, 5, 10))
        assert r["match"] == "exact"
        assert r["value"]["surcharge_excluded"] is False
        assert r["effective_from"] == "2026-05-10"
        assert r["effective_to"] is None

    def test_latest_is_post_expiry(self):
        """as_of=None 현행 최신본 = 종료 후 개방 구간 버전."""
        r = get_rule(self.RULE)
        assert r["match"] == "latest"
        assert r["effective_from"] == "2026-05-10"
        assert r["value"]["surcharge_excluded"] is False


# ── 4) calculate_all_taxes(as_of_date) — 하위호환 + 시행일 표기 ──

# 고정 입력: 대지 비주택 10억 취득 + 양도차익 1억(보유 2년).
_BASE_KWARGS = dict(
    purchase_won=1_000_000_000,
    land_category="land",
    gain_10k_won=10_000,
    holding_years=2,
)

# 정답값(수기 검산 고정):
# A01 40,000,000 + A02 4,000,000 + A03 2,000,000 + A04 150,000 + A05 0
# + A06 2,500,000 + A07 3,000,000 = 취득 51,650,000
# D01 19,560,000(과표 1억, 35% 누진공제 1,544만) + D03 1,956,000 = 양도 21,516,000
_EXPECTED_ACQ = 51_650_000
_EXPECTED_DISPOSAL = 21_516_000
_EXPECTED_GRAND = 73_166_000


class TestCalculateAllTaxesAsOf:
    def test_backward_compat_without_as_of(self):
        """as_of_date 미지정 → 기존 응답 완전 동일(정답값 고정, 신규 키 부재)."""
        result = calculate_all_taxes(**_BASE_KWARGS)
        assert result["acquisition"]["total_won"] == _EXPECTED_ACQ
        assert result["disposal"]["total_won"] == _EXPECTED_DISPOSAL
        assert result["grand_total_won"] == _EXPECTED_GRAND
        # additive 절대조건: 미지정 시 신규 키가 응답에 등장하지 않는다.
        assert "as_of_date" not in result
        assert "tax_rule_versions" not in result
        assert "tax_rule_version_warnings" not in result
        for record in result["legal_refs"]:
            assert "effective_label" not in record
            assert "rule_versions" not in record

    def test_as_of_does_not_change_amounts(self):
        """as_of_date 지정 — 단일 수록 버전 룰이므로 계산값 불변 + 메타 가산."""
        result = calculate_all_taxes(**_BASE_KWARGS, as_of_date=date(2026, 5, 8))
        assert result["grand_total_won"] == _EXPECTED_GRAND
        assert result["acquisition"]["total_won"] == _EXPECTED_ACQ
        assert result["disposal"]["total_won"] == _EXPECTED_DISPOSAL
        assert result["as_of_date"] == "2026-05-08"
        rule_keys = {v["rule_key"] for v in result["tax_rule_versions"]}
        assert "acquisition_tax_matrix" in rule_keys
        assert "capital_gains_brackets" in rule_keys
        assert "capital_gains_multi_home_surcharge_exclusion" in rule_keys

    @staticmethod
    def _exclusion_entry(result):
        return next(
            v for v in result["tax_rule_versions"]
            if v["rule_key"] == "capital_gains_multi_home_surcharge_exclusion"
        )

    def test_boundary_selects_different_rule_versions(self):
        """2026-05-09 경계 전후로 응답 메타의 룰 버전이 달라진다(계산값은 불변)."""
        before = calculate_all_taxes(**_BASE_KWARGS, as_of_date=date(2026, 5, 8))
        after = calculate_all_taxes(**_BASE_KWARGS, as_of_date=date(2026, 5, 10))

        ex_before = self._exclusion_entry(before)
        ex_after = self._exclusion_entry(after)
        assert ex_before["value"]["surcharge_excluded"] is True
        assert ex_before["effective_to"] == "2026-05-09"
        assert ex_after["value"]["surcharge_excluded"] is False
        assert ex_after["effective_from"] == "2026-05-10"
        # 양 시점 모두 현행 단일 버전 세율표 → 금액 동일(하위호환).
        assert before["grand_total_won"] == after["grand_total_won"] == _EXPECTED_GRAND

    def test_legal_refs_carry_effective_label(self):
        """legal_refs에 '시행일' 표기(legal_ref_key 결합) 가산."""
        result = calculate_all_taxes(**_BASE_KWARGS, as_of_date=date(2026, 5, 8))
        refs = {r["key"]: r for r in result["legal_refs"]}

        acq = refs["acquisition_tax"]
        assert acq["effective_label"] == "시행 2020-08-12 ~ 현행"
        assert acq["effective_from"] == "2020-08-12"
        assert acq["url"].startswith("https://www.law.go.kr")

        cgt = refs["capital_gains_tax"]
        assert cgt["effective_label"].startswith("시행 2023-01-01")
        labels = [rv["effective_label"] for rv in cgt["rule_versions"]]
        assert "시행 2022-05-10 ~ 2026-05-09" in labels

    def test_out_of_range_as_of_emits_honest_warnings(self):
        """수록 구간 밖 as_of(2021-01-01) → 경고 표기 + 계산값은 현행 폴백 불변."""
        result = calculate_all_taxes(**_BASE_KWARGS, as_of_date=date(2021, 1, 1))
        assert result["grand_total_won"] == _EXPECTED_GRAND
        warnings = result["tax_rule_version_warnings"]
        assert any("capital_gains_brackets" in w for w in warnings)
        # 취득세 매트릭스는 2020-08-12 시행 — 2021-01-01은 구간 내(exact, 경고 없음).
        matrix_entry = next(
            v for v in result["tax_rule_versions"] if v["rule_key"] == "acquisition_tax_matrix"
        )
        assert matrix_entry["match"] == "exact"
        assert "warning" not in matrix_entry
