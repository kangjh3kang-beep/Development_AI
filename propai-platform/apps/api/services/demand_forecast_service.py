"""부동산 수요 예측 서비스.

이동평균 + 지수평활 기반 시계열 예측.
지역별 수요 지수, 공급-수요 갭 분석, 흡수율 예측.

B02: Redis Connection Pool 고갈 방어 최적화 포함.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import redis.asyncio as redis
import structlog

from apps.api.config import get_settings

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)
settings = get_settings()

# B02: Redis Connection Pool 고갈 방어를 위한 최적화
redis_pool = redis.ConnectionPool.from_url(
    settings.redis_cache_url,
    max_connections=500,
    timeout=5,
    socket_keepalive=True,
    retry_on_timeout=True,
)
redis_client = redis.Redis(connection_pool=redis_pool)

# 계절 보정 계수 (1~12월)
_SEASONAL_FACTORS = {
    1: 0.85,   # 1월 비수기
    2: 0.88,   # 2월 비수기
    3: 1.05,   # 3월 성수기 시작
    4: 1.12,   # 4월 성수기
    5: 1.08,   # 5월 성수기
    6: 0.95,   # 6월 보통
    7: 0.90,   # 7월 비수기 (장마)
    8: 0.88,   # 8월 비수기 (휴가)
    9: 1.10,   # 9월 성수기
    10: 1.15,  # 10월 성수기 (최고)
    11: 1.02,  # 11월 보통
    12: 0.82,  # 12월 비수기 (최저)
}

# 지역별 기본 수요 지수 (서울 기준 100)
_REGIONAL_BASE_INDEX = {
    "서울": 100.0,
    "경기": 85.0,
    "인천": 72.0,
    "부산": 68.0,
    "대구": 55.0,
    "대전": 50.0,
    "광주": 48.0,
    "울산": 45.0,
    "세종": 62.0,
    "강원": 35.0,
    "충북": 38.0,
    "충남": 42.0,
    "전북": 33.0,
    "전남": 30.0,
    "경북": 36.0,
    "경남": 40.0,
    "제주": 52.0,
}

# 부동산 유형별 보정 계수
_PROPERTY_TYPE_FACTORS = {
    "아파트": 1.20,
    "오피스텔": 1.05,
    "상가": 0.85,
    "오피스": 0.90,
    "지식산업센터": 0.95,
    "물류": 1.10,
    "호텔": 0.70,
}


class DemandForecastService:
    """부동산 수요 예측 서비스."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.settings = get_settings()

    @staticmethod
    def seasonal_adjustment(month: int) -> float:
        """월별 계절 보정 계수를 반환한다."""
        return _SEASONAL_FACTORS.get(month, 1.0)

    @staticmethod
    def moving_average(data: list[float], window: int = 3) -> list[float]:
        """단순 이동평균을 계산한다."""
        if len(data) < window:
            return data[:]
        result = []
        for i in range(len(data)):
            if i < window - 1:
                result.append(sum(data[:i + 1]) / (i + 1))
            else:
                result.append(sum(data[i - window + 1:i + 1]) / window)
        return [round(v, 2) for v in result]

    @staticmethod
    def exponential_smoothing(data: list[float], alpha: float = 0.3) -> list[float]:
        """단순 지수평활(SES)을 적용한다."""
        if not data:
            return []
        result = [data[0]]
        for i in range(1, len(data)):
            smoothed = alpha * data[i] + (1 - alpha) * result[-1]
            result.append(round(smoothed, 2))
        return result

    def forecast_demand(
        self,
        *,
        region: str,
        property_type: str = "아파트",
        periods: int = 12,
        base_demand: float | None = None,
        historical_data: list[float] | None = None,
        start_month: int = 1,
    ) -> dict:
        """월별 수요 지수를 예측한다.

        이동평균 + 지수평활 + 계절성 반영.
        """
        if base_demand is None:
            base_demand = _REGIONAL_BASE_INDEX.get(region, 50.0)

        type_factor = _PROPERTY_TYPE_FACTORS.get(property_type, 1.0)
        base = base_demand * type_factor

        if historical_data and len(historical_data) >= 3:
            smoothed = self.exponential_smoothing(historical_data)
            trend = smoothed[-1] - smoothed[0]
            trend_per_period = trend / len(smoothed)
            last_value = smoothed[-1]
        else:
            trend_per_period = 0.0
            last_value = base

        forecasts = []
        for i in range(periods):
            month = ((start_month - 1 + i) % 12) + 1
            seasonal = self.seasonal_adjustment(month)
            value = (last_value + trend_per_period * (i + 1)) * seasonal
            forecasts.append({
                "period": i + 1,
                "month": month,
                "demand_index": round(max(0, value), 2),
                "seasonal_factor": seasonal,
            })

        return {
            "region": region,
            "property_type": property_type,
            "base_demand": round(base, 2),
            "trend_per_period": round(trend_per_period, 4),
            "periods": periods,
            "forecasts": forecasts,
        }

    @staticmethod
    def analyze_supply_demand_gap(
        *,
        supply_units: int,
        demand_index: float,
        avg_household_size: float = 2.5,
        target_population: int = 10000,
    ) -> dict:
        """공급 대비 수요 갭을 분석한다."""
        estimated_demand_units = int(target_population / avg_household_size * demand_index / 100)
        gap = estimated_demand_units - supply_units
        gap_ratio = round(gap / max(supply_units, 1) * 100, 2)

        if gap_ratio > 20:
            market_signal = "공급 부족 (매수 우위)"
        elif gap_ratio > 0:
            market_signal = "소폭 공급 부족"
        elif gap_ratio > -20:
            market_signal = "균형 또는 소폭 공급 과잉"
        else:
            market_signal = "공급 과잉 (매도 우위)"

        return {
            "supply_units": supply_units,
            "estimated_demand_units": estimated_demand_units,
            "gap": gap,
            "gap_ratio": gap_ratio,
            "market_signal": market_signal,
        }

    @staticmethod
    def get_regional_demand_index(region: str) -> dict:
        """지역별 수요 지수를 반환한다."""
        base = _REGIONAL_BASE_INDEX.get(region, 50.0)
        return {
            "region": region,
            "demand_index": base,
            "rank": sorted(_REGIONAL_BASE_INDEX.values(), reverse=True).index(base) + 1
            if base in _REGIONAL_BASE_INDEX.values() else 0,
            "vs_seoul": round(base / 100 * 100, 1),
        }

    @staticmethod
    def predict_absorption_rate(
        *,
        total_units: int,
        price_per_sqm: float,
        regional_avg_price: float,
        demand_index: float = 100.0,
        competitor_units: int = 0,
    ) -> dict:
        """분양/임대 흡수율을 예측한다."""
        if total_units <= 0:
            return {"absorption_rate": 0.0, "months_to_sell": 0, "risk_level": "N/A"}

        # 가격 경쟁력 (1.0 = 시세와 동일)
        price_competitiveness = regional_avg_price / max(price_per_sqm, 1)

        # 수요 강도 (0~1)
        demand_strength = min(demand_index / 100, 2.0)

        # 경쟁 강도 (경쟁물건이 많을수록 감소)
        competition_factor = 1.0 / (1.0 + competitor_units / max(total_units, 1))

        # 기본 흡수율 60% x 보정계수들
        base_rate = 0.60
        absorption_rate = min(
            base_rate * price_competitiveness * demand_strength * competition_factor * 100,
            100.0,
        )
        absorption_rate = round(max(absorption_rate, 5.0), 1)

        # 완판까지 예상 개월 수
        monthly_rate = absorption_rate / 100 / 12
        months_to_sell = int(math.ceil(1.0 / max(monthly_rate, 0.01)))

        if absorption_rate >= 80:
            risk_level = "LOW"
        elif absorption_rate >= 50:
            risk_level = "MEDIUM"
        else:
            risk_level = "HIGH"

        return {
            "absorption_rate": absorption_rate,
            "months_to_sell": months_to_sell,
            "price_competitiveness": round(price_competitiveness, 3),
            "demand_strength": round(demand_strength, 3),
            "competition_factor": round(competition_factor, 3),
            "risk_level": risk_level,
        }
