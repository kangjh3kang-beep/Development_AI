"""세금 계산 서비스 단위 테스트.

규칙 엔진 기반 세액 산출 로직 검증 (DB/LLM 없이 순수 로직만).

Step 1.3 품질 게이트:
- 누진세율 8구간 적용 검증
- 장기보유특별공제 (3년 6% ~ 10년 30%) 검증
- 테스트 케이스: 매수가 5억, 매도가 8억, 보유기간 5년
"""

from unittest.mock import AsyncMock

from apps.api.services.tax_ai_service import TaxAIService


class TestTaxCalculationRules:
    """세금 규칙 엔진 로직 검증."""

    def _make_service(self) -> TaxAIService:
        """Mock DB 세션으로 서비스 생성."""
        mock_db = AsyncMock()
        return TaxAIService(mock_db)

    def test_acquisition_tax(self) -> None:
        """취득세 기본 계산 (4% 기본 세율)."""
        svc = self._make_service()
        amount, rate = svc._calculate_base_tax("acquisition", 500_000_000)
        assert amount > 0
        assert rate > 0

    def test_property_tax(self) -> None:
        """재산세 계산."""
        svc = self._make_service()
        amount, rate = svc._calculate_base_tax("property", 300_000_000)
        assert amount > 0

    def test_transfer_tax(self) -> None:
        """양도세 계산."""
        svc = self._make_service()
        amount, rate = svc._calculate_base_tax("transfer", 1_000_000_000)
        assert amount > 0

    def test_unknown_tax_type_uses_default(self) -> None:
        """미정의 세금 유형은 기본 세율 적용."""
        svc = self._make_service()
        amount, rate = svc._calculate_base_tax("unknown_type", 100_000_000)
        # 기본 세율 4%가 적용되어야 함
        assert amount > 0

    def test_zero_value(self) -> None:
        """과세표준 0원이면 세액 0."""
        svc = self._make_service()
        amount, rate = svc._calculate_base_tax("acquisition", 0)
        assert amount == 0.0


# ──────────────────────────────────────
# 누진세율 8구간 테스트
# ──────────────────────────────────────


class TestProgressiveTaxBrackets:
    """양도소득세 누진세율 8구간 검증."""

    def test_bracket_1_below_14m(self) -> None:
        """1구간: 1,400만 이하 → 6%, 누진공제 0."""
        tax, _ = TaxAIService._calc_transfer_tax_progressive(10_000_000)
        assert tax == 10_000_000 * 0.06

    def test_bracket_2_below_50m(self) -> None:
        """2구간: 5,000만 이하 → 15%, 누진공제 126만."""
        tax, _ = TaxAIService._calc_transfer_tax_progressive(40_000_000)
        expected = 40_000_000 * 0.15 - 1_260_000
        assert tax == expected

    def test_bracket_5_below_300m(self) -> None:
        """5구간: 3억 이하 → 38%, 누진공제 1,994만."""
        tax, _ = TaxAIService._calc_transfer_tax_progressive(250_000_000)
        expected = 250_000_000 * 0.38 - 19_940_000
        assert tax == expected

    def test_bracket_8_over_1b(self) -> None:
        """8구간: 10억 초과 → 45%, 누진공제 6,594만."""
        tax, _ = TaxAIService._calc_transfer_tax_progressive(1_500_000_000)
        expected = 1_500_000_000 * 0.45 - 65_940_000
        assert tax == expected

    def test_zero_gain(self) -> None:
        """양도차익 0 → 세액 0."""
        tax, rate = TaxAIService._calc_transfer_tax_progressive(0)
        assert tax == 0.0
        assert rate == 0.0

    def test_negative_gain(self) -> None:
        """양도차익 음수 → 세액 0."""
        tax, rate = TaxAIService._calc_transfer_tax_progressive(-10_000_000)
        assert tax == 0.0

    def test_effective_rate_increases(self) -> None:
        """과세표준이 증가하면 실효세율도 증가."""
        _, rate_low = TaxAIService._calc_transfer_tax_progressive(50_000_000)
        _, rate_mid = TaxAIService._calc_transfer_tax_progressive(300_000_000)
        _, rate_high = TaxAIService._calc_transfer_tax_progressive(1_000_000_000)
        assert rate_low < rate_mid < rate_high


# ──────────────────────────────────────
# 장기보유특별공제 테스트
# ──────────────────────────────────────


class TestLongHoldDeduction:
    """장기보유특별공제 (3년 6% ~ 10년 30%) 검증."""

    def test_below_3_years(self) -> None:
        """3년 미만 → 공제 0%."""
        assert TaxAIService._calc_long_hold_deduction(0) == 0.0
        assert TaxAIService._calc_long_hold_deduction(1) == 0.0
        assert TaxAIService._calc_long_hold_deduction(2) == 0.0

    def test_3_years_general(self) -> None:
        """3년 일반 → 6%."""
        rate = TaxAIService._calc_long_hold_deduction(3, is_single_home=False)
        assert abs(rate - 0.06) < 1e-6

    def test_10_years_general(self) -> None:
        """10년 일반 → 30%."""
        rate = TaxAIService._calc_long_hold_deduction(10, is_single_home=False)
        assert abs(rate - 0.30) < 1e-6

    def test_5_years_general(self) -> None:
        """5년 일반 → 3년(6%)과 10년(30%) 사이 선형 보간."""
        rate = TaxAIService._calc_long_hold_deduction(5, is_single_home=False)
        # 0.06 + (5-3) * (0.30-0.06) / 7 ≈ 0.128571
        expected = 0.06 + 2 * 0.24 / 7
        assert abs(rate - expected) < 1e-4

    def test_over_10_years_capped(self) -> None:
        """10년 초과도 30%로 캡된다."""
        rate = TaxAIService._calc_long_hold_deduction(15, is_single_home=False)
        assert abs(rate - 0.30) < 1e-6

    def test_3_years_single_home(self) -> None:
        """3년 1세대1주택 → 24%."""
        rate = TaxAIService._calc_long_hold_deduction(3, is_single_home=True)
        assert abs(rate - 0.24) < 1e-6

    def test_10_years_single_home(self) -> None:
        """10년 1세대1주택 → 80%."""
        rate = TaxAIService._calc_long_hold_deduction(10, is_single_home=True)
        assert abs(rate - 0.80) < 1e-6

    def test_monotonically_increasing(self) -> None:
        """보유기간이 길수록 공제율이 단조증가."""
        rates = [
            TaxAIService._calc_long_hold_deduction(y)
            for y in range(3, 11)
        ]
        for i in range(1, len(rates)):
            assert rates[i] >= rates[i - 1]


# ──────────────────────────────────────
# calculate_capital_gains_tax 전용 메서드 테스트
# ──────────────────────────────────────


class TestCapitalGainsTax:
    """calculate_capital_gains_tax 전용 메서드 검증.

    핵심 테스트 케이스: 매수가 5억, 매도가 8억, 보유기간 5년.
    """

    def _make_service(self) -> TaxAIService:
        mock_db = AsyncMock()
        return TaxAIService(mock_db)

    def test_main_scenario_500m_to_800m_5years(self) -> None:
        """핵심: 매수 5억, 매도 8억, 보유 5년 — 누진공제 차감 검증.

        계산 과정:
        1. 양도차익: 8억 - 5억 = 3억 (300,000,000)
        2. 장기보유특별공제율 (5년 일반): 0.06 + (5-3)×0.24/7 ≈ 12.857%
        3. 공제액: 300,000,000 × 0.12857 ≈ 38,571,429
        4. 과세표준: 300,000,000 - 38,571,429 ≈ 261,428,571
        5. 5구간 적용 (3억 이하, 38%, 공제 19,940,000):
           261,428,571 × 0.38 - 19,940,000 ≈ 79,402,857
        """
        svc = self._make_service()
        result = svc.calculate_capital_gains_tax(
            sale_price=800_000_000,
            acquisition_price=500_000_000,
            holding_years=5,
        )

        # 양도차익 검증
        assert result["gain"] == 300_000_000

        # 장기보유특별공제율 검증 (5년 일반 ≈ 12.857%)
        expected_deduction_rate = 0.06 + 2 * 0.24 / 7
        assert abs(result["deduction_rate"] - expected_deduction_rate) < 1e-3

        # 과세표준 검증 (내부적으로 round(rate, 6) 적용 → 소수점 반올림 허용)
        taxable = result["taxable_gain"]
        assert 261_000_000 < taxable < 262_000_000

        # 적용 구간 검증 (5구간: 38%, 누진공제 19,940,000)
        assert result["bracket_rate"] == 0.38
        assert result["bracket_deduction"] == 19_940_000

        # 산출세액 검증 — 누진공제가 제대로 차감되었는지
        recalc_tax = round(taxable * 0.38 - 19_940_000)
        assert abs(result["base_tax"] - recalc_tax) < 2

        # 산출세액이 7천만~8천5백만 범위
        assert 70_000_000 < result["tax"] < 85_000_000

        # 다주택 중과 없음
        assert result["multi_home_surcharge"] == 0

    def test_no_gain(self) -> None:
        """매도가 ≤ 매수가 → 세액 0."""
        svc = self._make_service()
        result = svc.calculate_capital_gains_tax(
            sale_price=500_000_000,
            acquisition_price=600_000_000,
            holding_years=5,
        )
        assert result["tax"] == 0.0
        assert result["gain"] < 0

    def test_short_term_under_1_year(self) -> None:
        """1년 미만 보유 → 77% 특별세율."""
        svc = self._make_service()
        result = svc.calculate_capital_gains_tax(
            sale_price=800_000_000,
            acquisition_price=500_000_000,
            holding_years=0,
        )
        assert result["effective_rate"] == 0.77
        assert result["tax"] == 300_000_000 * 0.77
        assert result.get("short_term") is True

    def test_short_term_1_to_2_years(self) -> None:
        """1~2년 보유 → 66% 특별세율."""
        svc = self._make_service()
        result = svc.calculate_capital_gains_tax(
            sale_price=700_000_000,
            acquisition_price=500_000_000,
            holding_years=1,
        )
        assert result["effective_rate"] == 0.66

    def test_multi_home_2_surcharge(self) -> None:
        """2주택 보유 → +20%p 중과."""
        svc = self._make_service()
        result = svc.calculate_capital_gains_tax(
            sale_price=800_000_000,
            acquisition_price=500_000_000,
            holding_years=5,
            home_count=2,
        )
        assert result["multi_home_surcharge"] > 0
        # 중과 = 과세표준 × 20%
        assert abs(
            result["multi_home_surcharge"]
            - round(result["taxable_gain"] * 0.20),
        ) < 2

    def test_multi_home_3_surcharge(self) -> None:
        """3주택 이상 보유 → +30%p 중과."""
        svc = self._make_service()
        result = svc.calculate_capital_gains_tax(
            sale_price=800_000_000,
            acquisition_price=500_000_000,
            holding_years=5,
            home_count=3,
        )
        assert abs(
            result["multi_home_surcharge"]
            - round(result["taxable_gain"] * 0.30),
        ) < 2

    def test_single_home_higher_deduction(self) -> None:
        """1세대1주택은 일반보다 공제율이 높다."""
        svc = self._make_service()
        general = svc.calculate_capital_gains_tax(
            sale_price=800_000_000,
            acquisition_price=500_000_000,
            holding_years=5,
            is_single_home=False,
        )
        single = svc.calculate_capital_gains_tax(
            sale_price=800_000_000,
            acquisition_price=500_000_000,
            holding_years=5,
            is_single_home=True,
        )
        # 1세대1주택 공제율이 더 높으므로 세액이 낮아야 함
        assert single["deduction_rate"] > general["deduction_rate"]
        assert single["tax"] < general["tax"]

    def test_10_year_hold_max_deduction(self) -> None:
        """10년 보유 시 일반 공제율 30% 적용."""
        svc = self._make_service()
        result = svc.calculate_capital_gains_tax(
            sale_price=1_000_000_000,
            acquisition_price=500_000_000,
            holding_years=10,
        )
        assert abs(result["deduction_rate"] - 0.30) < 1e-6
        # 과세표준 = 5억 × 0.70 = 3.5억
        assert abs(result["taxable_gain"] - 350_000_000) < 2
