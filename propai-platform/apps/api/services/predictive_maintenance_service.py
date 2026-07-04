"""예방 정비 서비스.

Weibull 분포 기반 장비 고장 예측, RUL(잔여 유효 수명) 산출,
정비 스케줄 최적화, 알림 임계값 관리.
numpy 미설치 환경 대비 순수 Python 폴백 지원.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    np = None  # type: ignore[assignment]
    HAS_NUMPY = False
    import statistics as _stats

# 장비 유형별 정비 주기 (개월) 및 기대 수명 (시간)
_EQUIPMENT_PROFILES = {
    "elevator": {"name": "엘리베이터", "maintenance_months": 6, "expected_life_hours": 87600, "shape": 2.5},
    "hvac": {"name": "냉난방(HVAC)", "maintenance_months": 3, "expected_life_hours": 43800, "shape": 2.0},
    "electrical": {"name": "전기설비", "maintenance_months": 12, "expected_life_hours": 131400, "shape": 1.8},
    "plumbing": {"name": "배관설비", "maintenance_months": 12, "expected_life_hours": 175200, "shape": 1.5},
    "fire_protection": {"name": "소방설비", "maintenance_months": 6, "expected_life_hours": 175200, "shape": 1.3},
    "generator": {"name": "비상발전기", "maintenance_months": 3, "expected_life_hours": 43800, "shape": 2.2},
}

# 알림 임계값
_ALERT_LEVELS = {
    "NORMAL": (0.0, 0.6),
    "WARNING": (0.6, 0.8),
    "CRITICAL": (0.8, 1.0),
}


class PredictiveMaintenanceService:
    """예방 정비 서비스."""

    def __init__(self, db: AsyncSession | None = None) -> None:
        self.db = db

    # ── 기존 호환 메서드 (변경 금지) ──

    def _calc_std(self, values: list) -> float:
        """numpy 없는 환경 대비 표준편차 계산."""
        if HAS_NUMPY and np is not None:
            return float(np.std(values))
        return _stats.stdev(values) if len(values) >= 2 else 0.0

    def _calc_mean(self, values: list) -> float:
        if HAS_NUMPY and np is not None:
            return float(np.mean(values))
        return _stats.mean(values) if values else 0.0

    # ── Weibull 고장 확률 ──

    @staticmethod
    def weibull_failure_probability(
        operating_hours: float,
        expected_life_hours: float,
        shape: float = 2.0,
    ) -> float:
        """Weibull 분포 기반 누적 고장 확률 (CDF).

        F(t) = 1 - exp(-(t/lambda)^k)
        - t: 가동 시간
        - lambda: 척도 모수 (기대 수명)
        - k: 형상 모수 (shape)
        """
        if operating_hours <= 0 or expected_life_hours <= 0:
            return 0.0
        ratio = operating_hours / expected_life_hours
        return round(1.0 - math.exp(-(ratio ** shape)), 6)

    def predict_failure_probability(
        self,
        equipment_type: str,
        operating_hours: float,
    ) -> dict:
        """장비 유형별 고장 확률을 예측한다."""
        profile = _EQUIPMENT_PROFILES.get(equipment_type)
        if profile is None:
            raise ValueError(f"지원하지 않는 장비 유형: {equipment_type}. "
                           f"사용 가능: {list(_EQUIPMENT_PROFILES.keys())}")

        probability = self.weibull_failure_probability(
            operating_hours,
            profile["expected_life_hours"],
            profile["shape"],
        )

        # 알림 레벨 판정
        alert_level = "NORMAL"
        for level, (low, high) in _ALERT_LEVELS.items():
            if low <= probability < high:
                alert_level = level
                break
        if probability >= 0.8:
            alert_level = "CRITICAL"

        return {
            "equipment_type": equipment_type,
            "equipment_name": profile["name"],
            "operating_hours": operating_hours,
            "expected_life_hours": profile["expected_life_hours"],
            "failure_probability": probability,
            "alert_level": alert_level,
        }

    # ── RUL (잔여 유효 수명) ──

    @staticmethod
    def estimate_rul(
        current_value: float,
        initial_value: float,
        threshold_value: float,
        elapsed_hours: float,
    ) -> dict:
        """잔여 유효 수명(RUL)을 추정한다.

        열화 속도 = (현재값 - 초기값) / 경과시간
        RUL = (임계값 - 현재값) / 열화속도
        """
        if elapsed_hours <= 0:
            return {"rul_hours": 0, "rul_days": 0, "degradation_rate": 0.0, "health_pct": 100.0}

        degradation = current_value - initial_value
        degradation_rate = degradation / elapsed_hours

        if degradation_rate == 0:
            return {"rul_hours": float("inf"), "rul_days": float("inf"), "degradation_rate": 0.0, "health_pct": 100.0}

        remaining = threshold_value - current_value
        if degradation_rate > 0:
            # 값이 증가하며 열화 (온도 등)
            rul_hours = remaining / degradation_rate if remaining > 0 else 0
        else:
            # 값이 감소하며 열화 (효율 등)
            rul_hours = remaining / degradation_rate if remaining < 0 else 0

        rul_hours = max(rul_hours, 0)
        rul_days = round(rul_hours / 24, 1)

        # 건강 점수 (0~100)
        total_range = threshold_value - initial_value
        health_pct = round(max(0, min(100, (1 - degradation / total_range) * 100)), 1) if total_range != 0 else 100.0

        return {
            "rul_hours": round(rul_hours, 1),
            "rul_days": rul_days,
            "degradation_rate": round(degradation_rate, 6),
            "health_pct": health_pct,
        }

    # ── 정비 스케줄 ──

    @staticmethod
    def generate_maintenance_schedule(
        equipment_list: list[dict],
        base_date: datetime | None = None,
    ) -> list[dict]:
        """장비 목록 기반 정비 스케줄을 생성한다.

        equipment_list: [{"id": "EQ-01", "type": "elevator", "last_maintenance": datetime}, ...]
        """
        if base_date is None:
            base_date = datetime.now()

        schedule = []
        for eq in equipment_list:
            eq_type = eq.get("type", "")
            profile = _EQUIPMENT_PROFILES.get(eq_type)
            if profile is None:
                continue

            months = profile["maintenance_months"]
            last = eq.get("last_maintenance", base_date - timedelta(days=months * 30))
            if isinstance(last, str):
                last = datetime.fromisoformat(last)

            next_date = last + timedelta(days=months * 30)
            overdue = next_date < base_date
            days_until = (next_date - base_date).days

            schedule.append({
                "equipment_id": eq.get("id", ""),
                "equipment_type": eq_type,
                "equipment_name": profile["name"],
                "maintenance_interval_months": months,
                "last_maintenance": last.isoformat(),
                "next_maintenance": next_date.isoformat(),
                "days_until_next": days_until,
                "overdue": overdue,
                "priority": "HIGH" if overdue else ("MEDIUM" if days_until < 30 else "LOW"),
            })

        return sorted(schedule, key=lambda x: x["days_until_next"])

    # ── 알림 + 건강 점수 ──

    def check_alert_threshold(
        self,
        readings: list[float],
        warning_threshold: float,
        critical_threshold: float,
    ) -> dict:
        """센서 읽기 값에 대한 알림 레벨을 판정한다."""
        if not readings:
            return {"alert_level": "NORMAL", "current_value": 0, "mean": 0, "std": 0}

        current = readings[-1]
        mean = self._calc_mean(readings)
        std = self._calc_std(readings)

        if current >= critical_threshold:
            alert_level = "CRITICAL"
        elif current >= warning_threshold:
            alert_level = "WARNING"
        else:
            alert_level = "NORMAL"

        return {
            "alert_level": alert_level,
            "current_value": current,
            "mean": round(mean, 4),
            "std": round(std, 4),
            "warning_threshold": warning_threshold,
            "critical_threshold": critical_threshold,
        }

    def get_equipment_health_score(
        self,
        readings: list[float],
        optimal_range: tuple[float, float] = (18.0, 26.0),
    ) -> dict:
        """장비 건강 점수를 계산한다 (0~100)."""
        if not readings:
            return {"health_score": 100, "status": "정보 없음"}

        current = readings[-1]
        mean = self._calc_mean(readings)
        std = self._calc_std(readings)
        low, high = optimal_range
        midpoint = (low + high) / 2
        range_width = (high - low) / 2

        if low <= current <= high:
            # 최적 범위 내
            deviation = abs(current - midpoint) / range_width
            score = max(70, 100 - deviation * 30)
        else:
            # 범위 밖
            excess = (low - current) / max(range_width, 1) if current < low else (current - high) / max(range_width, 1)
            score = max(0, 70 - excess * 35)

        score = round(score, 1)

        if score >= 80:
            status = "양호"
        elif score >= 60:
            status = "주의"
        elif score >= 40:
            status = "경고"
        else:
            status = "위험"

        return {
            "health_score": score,
            "status": status,
            "current_value": current,
            "optimal_range": list(optimal_range),
            "mean": round(mean, 4),
            "std": round(std, 4),
        }
