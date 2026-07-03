"""예방 정비 서비스 전체 단위 테스트.

PredictiveMaintenanceService의 모든 공개 메서드를 검증한다.
- _calc_std / _calc_mean: 기존 호환 메서드
- weibull_failure_probability: Weibull CDF
- predict_failure_probability: 장비별 고장 확률
- estimate_rul: 잔여 유효 수명
- generate_maintenance_schedule: 정비 스케줄
- check_alert_threshold: 알림 임계값
- get_equipment_health_score: 건강 점수
"""

from __future__ import annotations

import math
from datetime import datetime
from unittest.mock import AsyncMock

import pytest

from apps.api.services.predictive_maintenance_service import (
    _EQUIPMENT_PROFILES,
    PredictiveMaintenanceService,
)


@pytest.fixture
def svc() -> PredictiveMaintenanceService:
    """테스트용 서비스 인스턴스를 생성한다."""
    return PredictiveMaintenanceService(db=AsyncMock())


# ── 기존 호환 메서드 ──


class TestBackwardCompat:
    """_calc_std / _calc_mean 기존 메서드 호환 테스트."""

    def test_calc_mean_basic(self, svc: PredictiveMaintenanceService) -> None:
        """평균 계산이 정확해야 한다."""
        result = svc._calc_mean([10.0, 20.0, 30.0])
        assert abs(result - 20.0) < 0.001

    def test_calc_mean_empty(self, svc: PredictiveMaintenanceService) -> None:
        """빈 리스트는 0.0 또는 NaN을 반환해야 한다 (numpy는 NaN 반환)."""
        result = svc._calc_mean([])
        # numpy 환경에서는 NaN, 순수 Python에서는 0.0
        assert result == 0.0 or math.isnan(result)

    def test_calc_std_basic(self, svc: PredictiveMaintenanceService) -> None:
        """표준편차 계산이 양수여야 한다."""
        result = svc._calc_std([10.0, 20.0, 30.0])
        assert result > 0

    def test_calc_std_single_value(self, svc: PredictiveMaintenanceService) -> None:
        """단일 값의 표준편차는 0이어야 한다."""
        result = svc._calc_std([5.0])
        assert result == 0.0


# ── Weibull 고장 확률 ──


class TestWeibullFailureProbability:
    """Weibull 분포 CDF 테스트."""

    def test_zero_hours_returns_zero(self) -> None:
        """가동 시간 0이면 고장 확률 0이어야 한다."""
        assert PredictiveMaintenanceService.weibull_failure_probability(0, 87600) == 0.0

    def test_negative_hours_returns_zero(self) -> None:
        """음수 가동 시간은 0을 반환해야 한다."""
        assert PredictiveMaintenanceService.weibull_failure_probability(-100, 87600) == 0.0

    def test_at_expected_life(self) -> None:
        """기대 수명 도달 시 약 63.2% 확률이어야 한다 (shape=2일 때 1-exp(-1))."""
        prob = PredictiveMaintenanceService.weibull_failure_probability(
            87600, 87600, shape=2.0
        )
        expected = 1.0 - math.exp(-1.0)  # ~0.6321
        assert abs(prob - expected) < 0.001

    def test_half_life(self) -> None:
        """기대 수명의 절반일 때 확률이 63%보다 낮아야 한다."""
        prob = PredictiveMaintenanceService.weibull_failure_probability(
            43800, 87600, shape=2.0
        )
        assert prob < 0.63
        assert prob > 0.0

    def test_double_life(self) -> None:
        """기대 수명의 2배일 때 확률이 매우 높아야 한다."""
        prob = PredictiveMaintenanceService.weibull_failure_probability(
            175200, 87600, shape=2.0
        )
        assert prob > 0.95


# ── predict_failure_probability ──


class TestPredictFailureProbability:
    """장비별 고장 확률 예측 테스트."""

    def test_new_elevator_normal(self, svc: PredictiveMaintenanceService) -> None:
        """새 엘리베이터(가동 1000시간)는 NORMAL이어야 한다."""
        result = svc.predict_failure_probability("elevator", 1000)
        assert result["alert_level"] == "NORMAL"
        assert result["equipment_name"] == "엘리베이터"

    def test_old_hvac_warning_or_critical(self, svc: PredictiveMaintenanceService) -> None:
        """오래된 HVAC(기대수명 초과)는 WARNING 이상이어야 한다."""
        life = _EQUIPMENT_PROFILES["hvac"]["expected_life_hours"]
        # shape=2.0일 때 ratio >= 0.9572이면 확률 >= 0.6 (WARNING)
        result = svc.predict_failure_probability("hvac", life * 1.0)
        assert result["alert_level"] in ("WARNING", "CRITICAL")

    def test_critical_level(self, svc: PredictiveMaintenanceService) -> None:
        """기대수명 초과 시 CRITICAL이어야 한다."""
        life = _EQUIPMENT_PROFILES["generator"]["expected_life_hours"]
        result = svc.predict_failure_probability("generator", life * 1.5)
        assert result["alert_level"] == "CRITICAL"

    def test_invalid_equipment_raises(self, svc: PredictiveMaintenanceService) -> None:
        """지원하지 않는 장비 유형에 ValueError를 발생시켜야 한다."""
        with pytest.raises(ValueError, match="지원하지 않는 장비 유형"):
            svc.predict_failure_probability("spaceship", 1000)


# ── estimate_rul ──


class TestEstimateRul:
    """잔여 유효 수명(RUL) 추정 테스트."""

    def test_positive_degradation(self) -> None:
        """온도가 상승하는 열화 시나리오의 RUL이 양수여야 한다."""
        result = PredictiveMaintenanceService.estimate_rul(
            current_value=50.0,
            initial_value=20.0,
            threshold_value=80.0,
            elapsed_hours=1000,
        )
        assert result["rul_hours"] > 0
        assert result["rul_days"] > 0
        assert result["health_pct"] == 50.0  # (1 - 30/60) * 100

    def test_zero_elapsed_hours(self) -> None:
        """경과 시간 0이면 기본값을 반환해야 한다."""
        result = PredictiveMaintenanceService.estimate_rul(
            current_value=25.0,
            initial_value=20.0,
            threshold_value=80.0,
            elapsed_hours=0,
        )
        assert result["rul_hours"] == 0
        assert result["health_pct"] == 100.0

    def test_no_degradation(self) -> None:
        """열화가 없으면 RUL이 무한대여야 한다."""
        result = PredictiveMaintenanceService.estimate_rul(
            current_value=20.0,
            initial_value=20.0,
            threshold_value=80.0,
            elapsed_hours=500,
        )
        assert result["rul_hours"] == float("inf")
        assert result["health_pct"] == 100.0

    def test_already_exceeded_threshold(self) -> None:
        """이미 임계값을 초과했으면 RUL이 0이어야 한다."""
        result = PredictiveMaintenanceService.estimate_rul(
            current_value=90.0,
            initial_value=20.0,
            threshold_value=80.0,
            elapsed_hours=1000,
        )
        assert result["rul_hours"] == 0


# ── generate_maintenance_schedule ──


class TestGenerateMaintenanceSchedule:
    """정비 스케줄 생성 테스트."""

    def test_overdue_equipment(self) -> None:
        """정비 기한이 지난 장비가 overdue=True여야 한다."""
        base = datetime(2025, 6, 1)
        equipment = [
            {
                "id": "EQ-01",
                "type": "elevator",
                "last_maintenance": datetime(2024, 1, 1),  # 6개월 주기, 한참 초과
            },
        ]
        schedule = PredictiveMaintenanceService.generate_maintenance_schedule(
            equipment, base_date=base,
        )
        assert len(schedule) == 1
        assert schedule[0]["overdue"] is True
        assert schedule[0]["priority"] == "HIGH"

    def test_normal_schedule(self) -> None:
        """정비 기한이 남은 장비가 overdue=False여야 한다."""
        base = datetime(2025, 6, 1)
        equipment = [
            {
                "id": "EQ-02",
                "type": "hvac",
                "last_maintenance": datetime(2025, 5, 20),  # 3개월 주기, 방금 정비
            },
        ]
        schedule = PredictiveMaintenanceService.generate_maintenance_schedule(
            equipment, base_date=base,
        )
        assert len(schedule) == 1
        assert schedule[0]["overdue"] is False

    def test_sorted_by_urgency(self) -> None:
        """스케줄이 days_until_next 오름차순으로 정렬되어야 한다."""
        base = datetime(2025, 6, 1)
        equipment = [
            {"id": "EQ-A", "type": "elevator", "last_maintenance": datetime(2025, 5, 1)},
            {"id": "EQ-B", "type": "hvac", "last_maintenance": datetime(2024, 1, 1)},
        ]
        schedule = PredictiveMaintenanceService.generate_maintenance_schedule(
            equipment, base_date=base,
        )
        assert len(schedule) == 2
        assert schedule[0]["days_until_next"] <= schedule[1]["days_until_next"]

    def test_unknown_type_skipped(self) -> None:
        """알 수 없는 장비 유형은 건너뛰어야 한다."""
        schedule = PredictiveMaintenanceService.generate_maintenance_schedule(
            [{"id": "X", "type": "spaceship"}],
            base_date=datetime(2025, 6, 1),
        )
        assert len(schedule) == 0


# ── check_alert_threshold ──


class TestCheckAlertThreshold:
    """알림 임계값 테스트."""

    def test_normal_reading(self, svc: PredictiveMaintenanceService) -> None:
        """정상 범위 읽기는 NORMAL이어야 한다."""
        result = svc.check_alert_threshold([20.0, 21.0, 22.0], 50.0, 80.0)
        assert result["alert_level"] == "NORMAL"
        assert result["current_value"] == 22.0

    def test_warning_reading(self, svc: PredictiveMaintenanceService) -> None:
        """경고 임계값 이상이면 WARNING이어야 한다."""
        result = svc.check_alert_threshold([20.0, 55.0], 50.0, 80.0)
        assert result["alert_level"] == "WARNING"

    def test_critical_reading(self, svc: PredictiveMaintenanceService) -> None:
        """위험 임계값 이상이면 CRITICAL이어야 한다."""
        result = svc.check_alert_threshold([20.0, 85.0], 50.0, 80.0)
        assert result["alert_level"] == "CRITICAL"

    def test_empty_readings(self, svc: PredictiveMaintenanceService) -> None:
        """빈 읽기 리스트는 NORMAL을 반환해야 한다."""
        result = svc.check_alert_threshold([], 50.0, 80.0)
        assert result["alert_level"] == "NORMAL"


# ── get_equipment_health_score ──


class TestGetEquipmentHealthScore:
    """장비 건강 점수 테스트."""

    def test_optimal_range(self, svc: PredictiveMaintenanceService) -> None:
        """최적 범위 내 값은 70점 이상이어야 한다."""
        result = svc.get_equipment_health_score([22.0], optimal_range=(18.0, 26.0))
        assert result["health_score"] >= 70
        assert result["status"] == "양호"

    def test_out_of_range_high(self, svc: PredictiveMaintenanceService) -> None:
        """최적 범위를 크게 초과하면 점수가 낮아야 한다."""
        result = svc.get_equipment_health_score([50.0], optimal_range=(18.0, 26.0))
        assert result["health_score"] < 70

    def test_out_of_range_low(self, svc: PredictiveMaintenanceService) -> None:
        """최적 범위보다 크게 낮으면 점수가 낮아야 한다."""
        result = svc.get_equipment_health_score([0.0], optimal_range=(18.0, 26.0))
        assert result["health_score"] < 70

    def test_empty_readings(self, svc: PredictiveMaintenanceService) -> None:
        """빈 읽기 리스트는 '정보 없음'을 반환해야 한다."""
        result = svc.get_equipment_health_score([])
        assert result["status"] == "정보 없음"
        assert result["health_score"] == 100

    def test_critical_status(self, svc: PredictiveMaintenanceService) -> None:
        """극단적으로 벗어난 값은 '위험' 상태여야 한다."""
        result = svc.get_equipment_health_score([100.0], optimal_range=(18.0, 26.0))
        assert result["status"] == "위험"
        assert result["health_score"] < 40
