"""수요 예측 서비스 단위 테스트.

DemandForecastService의 모든 공개 메서드를 검증한다.
- seasonal_adjustment: 계절 보정 계수
- moving_average: 이동평균
- exponential_smoothing: 지수평활
- forecast_demand: 수요 예측 (과거 데이터 유/무)
- analyze_supply_demand_gap: 공급-수요 갭 분석
- get_regional_demand_index: 지역별 수요 지수
- predict_absorption_rate: 흡수율 예측
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from apps.api.services.demand_forecast_service import (
    DemandForecastService,
    _REGIONAL_BASE_INDEX,
    _SEASONAL_FACTORS,
    redis_client,
    redis_pool,
)


@pytest.fixture
def svc() -> DemandForecastService:
    """테스트용 서비스 인스턴스를 생성한다."""
    mock_db = AsyncMock()
    return DemandForecastService(db=mock_db)


# ── 모듈 레벨 Redis 호환성 ──


class TestRedisBackwardCompat:
    """모듈 레벨 redis_pool / redis_client 존재 여부를 확인한다."""

    def test_redis_pool_exists(self) -> None:
        """redis_pool이 모듈 레벨에 존재해야 한다."""
        assert redis_pool is not None

    def test_redis_client_exists(self) -> None:
        """redis_client가 모듈 레벨에 존재해야 한다."""
        assert redis_client is not None


# ── seasonal_adjustment ──


class TestSeasonalAdjustment:
    """월별 계절 보정 계수 테스트."""

    def test_january_low_season(self) -> None:
        """1월은 비수기(0.85)여야 한다."""
        assert DemandForecastService.seasonal_adjustment(1) == 0.85

    def test_october_peak_season(self) -> None:
        """10월은 최고 성수기(1.15)여야 한다."""
        assert DemandForecastService.seasonal_adjustment(10) == 1.15

    def test_december_lowest(self) -> None:
        """12월은 최저 비수기(0.82)여야 한다."""
        assert DemandForecastService.seasonal_adjustment(12) == 0.82

    def test_invalid_month_returns_default(self) -> None:
        """유효하지 않은 월은 1.0을 반환해야 한다."""
        assert DemandForecastService.seasonal_adjustment(13) == 1.0
        assert DemandForecastService.seasonal_adjustment(0) == 1.0


# ── moving_average ──


class TestMovingAverage:
    """단순 이동평균 테스트."""

    def test_basic_window_3(self) -> None:
        """윈도우 3 이동평균이 정확해야 한다."""
        data = [10.0, 20.0, 30.0, 40.0, 50.0]
        result = DemandForecastService.moving_average(data, window=3)
        assert len(result) == 5
        # 처음 두 값은 누적 평균
        assert result[0] == 10.0
        assert result[1] == 15.0
        # 세 번째부터 윈도우 3 평균
        assert result[2] == 20.0
        assert result[3] == 30.0
        assert result[4] == 40.0

    def test_data_shorter_than_window(self) -> None:
        """데이터가 윈도우보다 짧으면 원본 복사를 반환한다."""
        data = [5.0, 10.0]
        result = DemandForecastService.moving_average(data, window=5)
        assert result == [5.0, 10.0]

    def test_empty_data(self) -> None:
        """빈 리스트에 대해 빈 리스트를 반환한다."""
        assert DemandForecastService.moving_average([], window=3) == []


# ── exponential_smoothing ──


class TestExponentialSmoothing:
    """단순 지수평활 테스트."""

    def test_first_value_unchanged(self) -> None:
        """첫 번째 값은 변경되지 않아야 한다."""
        data = [100.0, 110.0, 120.0]
        result = DemandForecastService.exponential_smoothing(data, alpha=0.3)
        assert result[0] == 100.0

    def test_smoothing_reduces_volatility(self) -> None:
        """지수평활이 변동성을 줄여야 한다."""
        data = [100.0, 200.0, 100.0, 200.0]
        result = DemandForecastService.exponential_smoothing(data, alpha=0.3)
        # 원본보다 범위가 작아야 함
        original_range = max(data) - min(data)
        smoothed_range = max(result) - min(result)
        assert smoothed_range < original_range

    def test_empty_data_returns_empty(self) -> None:
        """빈 데이터는 빈 리스트를 반환한다."""
        assert DemandForecastService.exponential_smoothing([]) == []

    def test_alpha_1_returns_original(self) -> None:
        """alpha=1.0이면 원본과 동일해야 한다."""
        data = [10.0, 20.0, 30.0]
        result = DemandForecastService.exponential_smoothing(data, alpha=1.0)
        assert result == data


# ── forecast_demand ──


class TestForecastDemand:
    """수요 예측 테스트."""

    def test_default_region_seoul(self, svc: DemandForecastService) -> None:
        """서울 지역 기본 수요 예측이 올바른 구조를 반환해야 한다."""
        result = svc.forecast_demand(region="서울", periods=6)
        assert result["region"] == "서울"
        assert result["property_type"] == "아파트"
        assert result["periods"] == 6
        assert len(result["forecasts"]) == 6
        # 서울 아파트 기본 수요: 100 * 1.2 = 120
        assert result["base_demand"] == 120.0

    def test_unknown_region_uses_default(self, svc: DemandForecastService) -> None:
        """알 수 없는 지역은 기본값 50.0을 사용해야 한다."""
        result = svc.forecast_demand(region="미지의도시", property_type="상가")
        # 50 * 0.85 = 42.5
        assert result["base_demand"] == 42.5

    def test_with_historical_data(self, svc: DemandForecastService) -> None:
        """과거 데이터가 있으면 trend_per_period가 0이 아니어야 한다."""
        historical = [80.0, 85.0, 90.0, 95.0, 100.0]
        result = svc.forecast_demand(
            region="경기",
            historical_data=historical,
            periods=3,
        )
        assert result["trend_per_period"] != 0.0
        assert len(result["forecasts"]) == 3

    def test_forecast_month_wraps_around(self, svc: DemandForecastService) -> None:
        """start_month=11이면 11, 12, 1, 2 순으로 월이 순환해야 한다."""
        result = svc.forecast_demand(region="서울", start_month=11, periods=4)
        months = [f["month"] for f in result["forecasts"]]
        assert months == [11, 12, 1, 2]

    def test_demand_index_always_non_negative(self, svc: DemandForecastService) -> None:
        """수요 지수가 음수가 되어서는 안 된다."""
        result = svc.forecast_demand(region="전남", periods=12)
        for f in result["forecasts"]:
            assert f["demand_index"] >= 0


# ── analyze_supply_demand_gap ──


class TestAnalyzeSupplyDemandGap:
    """공급-수요 갭 분석 테스트."""

    def test_supply_shortage(self) -> None:
        """수요가 공급을 크게 초과하면 '공급 부족' 신호를 반환해야 한다."""
        result = DemandForecastService.analyze_supply_demand_gap(
            supply_units=1000,
            demand_index=200.0,
            target_population=50000,
        )
        assert result["gap"] > 0
        assert "공급 부족" in result["market_signal"]

    def test_supply_excess(self) -> None:
        """공급이 수요를 크게 초과하면 '공급 과잉' 신호를 반환해야 한다."""
        result = DemandForecastService.analyze_supply_demand_gap(
            supply_units=50000,
            demand_index=10.0,
            target_population=10000,
        )
        assert result["gap"] < 0
        assert "공급 과잉" in result["market_signal"]

    def test_balanced_market(self) -> None:
        """공급과 수요가 비슷하면 '균형' 신호를 반환해야 한다."""
        result = DemandForecastService.analyze_supply_demand_gap(
            supply_units=4000,
            demand_index=100.0,
            target_population=10000,
        )
        assert "균형" in result["market_signal"]


# ── get_regional_demand_index ──


class TestGetRegionalDemandIndex:
    """지역별 수요 지수 테스트."""

    def test_seoul_is_100(self) -> None:
        """서울의 수요 지수는 100이어야 한다."""
        result = DemandForecastService.get_regional_demand_index("서울")
        assert result["demand_index"] == 100.0
        assert result["rank"] == 1

    def test_unknown_region_default(self) -> None:
        """알 수 없는 지역은 기본값 50.0을 사용해야 한다."""
        result = DemandForecastService.get_regional_demand_index("미지의도시")
        assert result["demand_index"] == 50.0


# ── predict_absorption_rate ──


class TestPredictAbsorptionRate:
    """흡수율 예측 테스트."""

    def test_zero_units(self) -> None:
        """총 세대 0이면 N/A를 반환해야 한다."""
        result = DemandForecastService.predict_absorption_rate(
            total_units=0,
            price_per_sqm=5000000,
            regional_avg_price=5000000,
        )
        assert result["risk_level"] == "N/A"
        assert result["absorption_rate"] == 0.0

    def test_low_risk_high_demand(self) -> None:
        """가격 경쟁력이 높고 수요가 강하면 LOW 리스크여야 한다."""
        result = DemandForecastService.predict_absorption_rate(
            total_units=100,
            price_per_sqm=3000000,
            regional_avg_price=5000000,
            demand_index=150.0,
            competitor_units=0,
        )
        assert result["risk_level"] == "LOW"
        assert result["absorption_rate"] >= 80

    def test_high_risk_oversupply(self) -> None:
        """가격이 비싸고 경쟁이 심하면 HIGH 리스크여야 한다."""
        result = DemandForecastService.predict_absorption_rate(
            total_units=100,
            price_per_sqm=10000000,
            regional_avg_price=5000000,
            demand_index=30.0,
            competitor_units=500,
        )
        assert result["risk_level"] == "HIGH"
        assert result["absorption_rate"] < 50

    def test_medium_risk(self) -> None:
        """중간 조건에서 MEDIUM 리스크를 반환해야 한다."""
        result = DemandForecastService.predict_absorption_rate(
            total_units=200,
            price_per_sqm=4500000,
            regional_avg_price=5000000,
            demand_index=120.0,
            competitor_units=50,
        )
        assert result["risk_level"] == "MEDIUM"

    def test_absorption_rate_bounded(self) -> None:
        """흡수율은 5.0~100.0 범위 내에 있어야 한다."""
        result = DemandForecastService.predict_absorption_rate(
            total_units=50,
            price_per_sqm=1,
            regional_avg_price=10000000,
            demand_index=200.0,
        )
        assert 5.0 <= result["absorption_rate"] <= 100.0
