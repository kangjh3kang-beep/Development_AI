"""재건축 조합원 분담금 서비스 단위 테스트.

순수 로직 검증:
1. _calculate_proportional_rate() — 비례율 계산
2. _calculate_contribution() — 개인 분담금 계산
"""

from unittest.mock import AsyncMock

from apps.api.services.union_management_service import UnionManagementService


def _make_service() -> UnionManagementService:
    """Mock DB 세션으로 서비스 생성."""
    return UnionManagementService(AsyncMock())


# ──────────────────────────────────────
# _calculate_proportional_rate 검증
# ──────────────────────────────────────


class TestProportionalRate:
    """비례율 계산 검증. 비례율 = 총사업비 / 총감정가."""

    def test_basic_rate(self) -> None:
        """100억/80억 = 1.25."""
        svc = _make_service()
        rate = svc._calculate_proportional_rate(10_000_000_000, 8_000_000_000)
        assert abs(rate - 1.25) < 1e-6

    def test_rate_below_one(self) -> None:
        """사업비 < 감정가 → 비례율 < 1."""
        svc = _make_service()
        rate = svc._calculate_proportional_rate(5_000_000_000, 10_000_000_000)
        assert abs(rate - 0.5) < 1e-6

    def test_equal_values(self) -> None:
        """사업비 = 감정가 → 비례율 1.0."""
        svc = _make_service()
        rate = svc._calculate_proportional_rate(100, 100)
        assert abs(rate - 1.0) < 1e-6

    def test_zero_appraised_value(self) -> None:
        """감정가 0 → 비례율 1.0 반환 (안전장치)."""
        svc = _make_service()
        rate = svc._calculate_proportional_rate(10_000_000_000, 0)
        assert rate == 1.0

    def test_small_values(self) -> None:
        """소규모 금액도 정상 계산."""
        svc = _make_service()
        rate = svc._calculate_proportional_rate(300, 200)
        assert abs(rate - 1.5) < 1e-6


# ──────────────────────────────────────
# _calculate_contribution 검증
# ──────────────────────────────────────


class TestContribution:
    """개인 분담금 계산 검증. 분담금 = target_value - credit."""

    def test_basic_contribution(self) -> None:
        """target - credit > 0 → 양수 분담금."""
        svc = _make_service()
        # target = 84㎡ × 1,500만원/㎡ = 12.6억
        # credit = 8억 × 1.25 = 10억
        # 분담금 = 12.6억 - 10억 = 2.6억
        result = svc._calculate_contribution(
            target_area_sqm=84.0,
            avg_sale_price_per_sqm=15_000_000,
            individual_appraised_value=800_000_000,
            proportional_rate=1.25,
        )
        expected = 84.0 * 15_000_000 - 800_000_000 * 1.25
        assert abs(result - expected) < 1

    def test_credit_exceeds_target(self) -> None:
        """credit > target → 분담금 0 (음수 불가)."""
        svc = _make_service()
        result = svc._calculate_contribution(
            target_area_sqm=50.0,
            avg_sale_price_per_sqm=10_000_000,
            individual_appraised_value=1_000_000_000,
            proportional_rate=1.25,
        )
        # target = 5억, credit = 12.5억 → max(0, -7.5억) = 0
        assert result == 0

    def test_zero_area(self) -> None:
        """면적 0 → target 0 → 분담금 0."""
        svc = _make_service()
        result = svc._calculate_contribution(0, 15_000_000, 800_000_000, 1.25)
        assert result == 0

    def test_zero_appraised_value(self) -> None:
        """개인 감정가 0 → credit 0 → 분담금 = target."""
        svc = _make_service()
        result = svc._calculate_contribution(84.0, 15_000_000, 0, 1.25)
        assert result == 84.0 * 15_000_000

    def test_rate_one_exact_match(self) -> None:
        """비례율 1.0, target = credit → 분담금 0."""
        svc = _make_service()
        result = svc._calculate_contribution(84.0, 10_000_000, 840_000_000, 1.0)
        assert result == 0

    def test_large_contribution(self) -> None:
        """고급 단지 시나리오 — 큰 분담금."""
        svc = _make_service()
        result = svc._calculate_contribution(
            target_area_sqm=120.0,
            avg_sale_price_per_sqm=30_000_000,
            individual_appraised_value=500_000_000,
            proportional_rate=1.1,
        )
        expected = 120.0 * 30_000_000 - 500_000_000 * 1.1
        assert result > 0
        assert abs(result - expected) < 1
