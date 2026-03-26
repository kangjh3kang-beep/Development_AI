"""MaintenanceService 단위 테스트.

예측 유지보수 이상 점수 산정(_evaluate) 정적 메서드를 검증한다.
가중치: 진동 0.45 + 온도 0.30 + 효율 0.25
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from apps.api.services.maintenance_service import MaintenanceService


class TestEvaluate:
    """_evaluate 정적 메서드 테스트."""

    def test_정상_범위_저위험(self):
        """진동 낮음, 온도 낮음, 효율 높음 → low."""
        score, rul, hvac, severity, rec = MaintenanceService._evaluate(
            vibration_mm_s=2.0,
            temperature_c=26.0,
            energy_efficiency_ratio=0.95,
        )
        assert severity == "low"
        assert score < 0.35

    def test_critical_임계값(self):
        """매우 높은 진동 + 온도 + 낮은 효율 → critical."""
        score, rul, hvac, severity, rec = MaintenanceService._evaluate(
            vibration_mm_s=12.0,
            temperature_c=42.0,
            energy_efficiency_ratio=0.3,
        )
        assert severity == "critical"
        assert score >= 0.78

    def test_high_임계값(self):
        """중간 높은 값 → high."""
        score, rul, hvac, severity, rec = MaintenanceService._evaluate(
            vibration_mm_s=8.0,
            temperature_c=36.0,
            energy_efficiency_ratio=0.55,
        )
        assert severity in {"high", "critical"}
        assert score >= 0.58

    def test_medium_임계값(self):
        """약간 높은 값 → medium."""
        score, rul, hvac, severity, rec = MaintenanceService._evaluate(
            vibration_mm_s=5.0,
            temperature_c=30.0,
            energy_efficiency_ratio=0.75,
        )
        assert severity in {"medium", "low"}
        assert score >= 0.20

    def test_이상점수_0_1_범위(self):
        score, *_ = MaintenanceService._evaluate(
            vibration_mm_s=6.0,
            temperature_c=35.0,
            energy_efficiency_ratio=0.7,
        )
        assert 0.0 <= score <= 1.0

    def test_잔여수명_최소7일(self):
        """critical 상태에서도 최소 7일."""
        _, rul, *_ = MaintenanceService._evaluate(
            vibration_mm_s=15.0,
            temperature_c=50.0,
            energy_efficiency_ratio=0.1,
        )
        assert rul >= 7

    def test_정상_잔여수명_365이하(self):
        _, rul, *_ = MaintenanceService._evaluate(
            vibration_mm_s=0.0,
            temperature_c=24.0,
            energy_efficiency_ratio=1.0,
        )
        assert rul <= 365

    def test_HVAC_효율_점수(self):
        """efficiency_ratio 0.85 → hvac_efficiency_score 85.0."""
        _, _, hvac, *_ = MaintenanceService._evaluate(
            vibration_mm_s=3.0,
            temperature_c=28.0,
            energy_efficiency_ratio=0.85,
        )
        assert hvac == pytest.approx(85.0, abs=0.1)

    def test_HVAC_효율_0_100_범위(self):
        _, _, hvac, *_ = MaintenanceService._evaluate(
            vibration_mm_s=3.0,
            temperature_c=28.0,
            energy_efficiency_ratio=1.2,
        )
        assert 0.0 <= hvac <= 100.0

    def test_critical_권장사항_키워드(self):
        """critical → 즉시 점검 권장."""
        *_, severity, rec = MaintenanceService._evaluate(
            vibration_mm_s=12.0,
            temperature_c=42.0,
            energy_efficiency_ratio=0.3,
        )
        assert severity == "critical"
        assert "immediate" in rec.lower() or "work order" in rec.lower()

    def test_low_권장사항_키워드(self):
        *_, severity, rec = MaintenanceService._evaluate(
            vibration_mm_s=1.0,
            temperature_c=25.0,
            energy_efficiency_ratio=0.95,
        )
        assert severity == "low"
        assert "routine" in rec.lower()

    def test_진동_가중치_045(self):
        """진동만 높은 경우 점수 확인."""
        score1, *_ = MaintenanceService._evaluate(
            vibration_mm_s=12.0,
            temperature_c=24.0,
            energy_efficiency_ratio=1.0,
        )
        # 진동 12/12=1.0 × 0.45 + 온도 0 × 0.30 + 효율 0 × 0.25 = 0.45
        assert score1 == pytest.approx(0.45, abs=0.01)

    def test_온도_가중치_030(self):
        """온도만 높은 경우."""
        score, *_ = MaintenanceService._evaluate(
            vibration_mm_s=0.0,
            temperature_c=42.0,
            energy_efficiency_ratio=1.0,
        )
        # 온도 (42-24)/18 = 1.0 × 0.30 = 0.30
        assert score == pytest.approx(0.30, abs=0.01)

    def test_효율_가중치_025(self):
        """효율만 낮은 경우."""
        score, *_ = MaintenanceService._evaluate(
            vibration_mm_s=0.0,
            temperature_c=24.0,
            energy_efficiency_ratio=0.55,
        )
        # 효율 (1.0-0.55)/0.45 = 1.0 × 0.25 = 0.25
        assert score == pytest.approx(0.25, abs=0.01)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
