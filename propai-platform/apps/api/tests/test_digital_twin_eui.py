"""DigitalTwinService EUI 벤치마크 + Z-score 단위 테스트.

ASHRAE 기준 EUI 등급 판정, Z-score 이상 감지,
외기온도 기반 에너지 예측 (단순 선형회귀)을 검증한다.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from apps.api.services.digital_twin_service import (
    EUI_BENCHMARKS,
    EUI_GRADES,
    DigitalTwinService,
)


# ── EUI 계산 테스트 ──


class TestCalculateEUI:
    """calculate_eui 정적 메서드 테스트."""

    def test_eui_계산_정상(self):
        """20000kWh / 100sqm = 200 kWh/m²/yr"""
        result = DigitalTwinService.calculate_eui(20000, 100)
        assert result == pytest.approx(200.0)

    def test_eui_면적_0(self):
        """면적이 0이면 0.0 반환."""
        result = DigitalTwinService.calculate_eui(20000, 0)
        assert result == 0.0

    def test_eui_면적_음수(self):
        """면적이 음수이면 0.0 반환."""
        result = DigitalTwinService.calculate_eui(20000, -10)
        assert result == 0.0

    def test_eui_소수점_반올림(self):
        """소수점 2자리로 반올림."""
        result = DigitalTwinService.calculate_eui(10000, 300)
        assert result == pytest.approx(33.33)


# ── EUI 등급 판정 테스트 ──


class TestGradeEUI:
    """grade_eui 정적 메서드 테스트."""

    def test_eui_등급_A_plus(self):
        """eui=80, office → A+ (excellent=100 이하)"""
        result = DigitalTwinService.grade_eui(80, "office")
        assert result["grade"] == "A+"
        assert result["eui"] == 80
        assert result["benchmark"] == 200
        assert result["label"] == "오피스"

    def test_eui_등급_A(self):
        """eui=130, office → A (good=150 이하)"""
        result = DigitalTwinService.grade_eui(130, "office")
        assert result["grade"] == "A"

    def test_eui_등급_B(self):
        """eui=180, office → B (benchmark=200 이하)"""
        result = DigitalTwinService.grade_eui(180, "office")
        assert result["grade"] == "B"

    def test_eui_등급_C(self):
        """eui=250, office → C (benchmark*1.5=300 이하)"""
        result = DigitalTwinService.grade_eui(250, "office")
        assert result["grade"] == "C"

    def test_eui_등급_D(self):
        """eui=350, office → D (benchmark*1.5=300 초과)"""
        result = DigitalTwinService.grade_eui(350, "office")
        assert result["grade"] == "D"

    def test_eui_주거_벤치마크(self):
        """residential benchmark=150 확인."""
        result = DigitalTwinService.grade_eui(120, "residential")
        assert result["benchmark"] == 150
        assert result["building_type"] == "residential"
        assert result["label"] == "주거"
        # 120은 residential의 good(100) 초과, benchmark(150) 이하 → B
        assert result["grade"] == "B"

    def test_eui_ratio_계산(self):
        """ratio = eui / benchmark."""
        result = DigitalTwinService.grade_eui(100, "office")
        assert result["ratio"] == pytest.approx(0.5)

    def test_eui_미지원_건물유형_기본값(self):
        """미지원 건물 유형은 office 기본값 사용."""
        result = DigitalTwinService.grade_eui(100, "unknown_type")
        assert result["benchmark"] == 200  # office 기본값


# ── Z-score 이상 감지 테스트 ──


class TestDetectAnomalyZscore:
    """detect_anomaly_zscore 정적 메서드 테스트."""

    def test_zscore_이상없음(self):
        """정상 데이터에서는 이상이 감지되지 않는다."""
        readings = [100, 101, 99, 100, 102]
        result = DigitalTwinService.detect_anomaly_zscore(readings)
        assert result == []

    def test_zscore_이상감지(self):
        """극단값 500은 이상으로 감지된다 (충분한 정상 데이터 필요)."""
        readings = [100] * 20 + [500]
        result = DigitalTwinService.detect_anomaly_zscore(readings)
        assert len(result) >= 1
        # 500이 이상으로 감지되어야 함
        anomaly_values = [a["value"] for a in result]
        assert 500 in anomaly_values
        # 모든 결과의 is_anomaly는 True
        for anomaly in result:
            assert anomaly["is_anomaly"] is True

    def test_zscore_빈_리스트(self):
        """빈 리스트 → 빈 결과."""
        result = DigitalTwinService.detect_anomaly_zscore([])
        assert result == []

    def test_zscore_단일값(self):
        """단일 값 → 빈 결과 (stdev 계산 불가)."""
        result = DigitalTwinService.detect_anomaly_zscore([100])
        assert result == []

    def test_zscore_threshold_2(self):
        """threshold=2.0으로 더 민감하게 감지."""
        # 표준편차가 작은 데이터에 약간의 이상치
        readings = [100, 100, 100, 100, 100, 100, 100, 100, 100, 115]
        result_default = DigitalTwinService.detect_anomaly_zscore(readings, threshold=3.0)
        result_sensitive = DigitalTwinService.detect_anomaly_zscore(readings, threshold=2.0)
        # 더 민감한 threshold는 같거나 더 많은 이상치를 감지해야 함
        assert len(result_sensitive) >= len(result_default)

    def test_zscore_결과_구조(self):
        """감지된 이상치는 올바른 dict 구조를 갖는다."""
        readings = [100] * 20 + [500]
        result = DigitalTwinService.detect_anomaly_zscore(readings)
        if result:
            anomaly = result[0]
            assert "index" in anomaly
            assert "value" in anomaly
            assert "z_score" in anomaly
            assert "is_anomaly" in anomaly

    def test_zscore_동일값_리스트(self):
        """모든 값이 동일하면 stdev=0 → 빈 결과."""
        readings = [100, 100, 100, 100, 100]
        result = DigitalTwinService.detect_anomaly_zscore(readings)
        assert result == []


# ── 에너지 예측 테스트 ──


class TestPredictEnergy:
    """predict_energy 정적 메서드 테스트."""

    def test_에너지_예측_선형(self):
        """온도↑ → 에너지↑ (냉방 부하 증가) 선형 관계 확인."""
        temps = [20.0, 25.0, 30.0, 35.0]
        energy = [100.0, 150.0, 200.0, 250.0]
        # 40도에서의 예측 → 약 300
        result = DigitalTwinService.predict_energy(temps, energy, 40.0)
        assert result == pytest.approx(300.0, rel=0.01)

    def test_에너지_예측_데이터부족(self):
        """데이터 포인트가 2개 미만이면 0.0 반환."""
        result = DigitalTwinService.predict_energy([20.0], [100.0], 25.0)
        assert result == 0.0

    def test_에너지_예측_길이_불일치(self):
        """온도/에너지 리스트 길이 불일치 시 0.0 반환."""
        result = DigitalTwinService.predict_energy([20.0, 25.0], [100.0], 30.0)
        assert result == 0.0

    def test_에너지_예측_음수_방지(self):
        """예측 결과가 음수이면 0.0으로 클램핑."""
        # 온도와 에너지가 양의 상관관계일 때, 매우 낮은 온도
        temps = [25.0, 30.0, 35.0]
        energy = [200.0, 250.0, 300.0]
        result = DigitalTwinService.predict_energy(temps, energy, -100.0)
        assert result >= 0.0


# ── 상수 검증 테스트 ──


class TestEUIConstants:
    """EUI 벤치마크/등급 상수 테스트."""

    def test_벤치마크_7개_건물유형(self):
        """7개 건물 유형이 정의되어 있다."""
        assert len(EUI_BENCHMARKS) == 7

    def test_등급_5개(self):
        """5개 등급이 정의되어 있다."""
        assert len(EUI_GRADES) == 5

    def test_벤치마크_필수_키(self):
        """각 벤치마크에 필수 키가 있다."""
        for btype, data in EUI_BENCHMARKS.items():
            assert "benchmark" in data, f"{btype}: benchmark 누락"
            assert "good" in data, f"{btype}: good 누락"
            assert "excellent" in data, f"{btype}: excellent 누락"
            assert "label" in data, f"{btype}: label 누락"

    def test_벤치마크_순서_일관성(self):
        """excellent < good < benchmark 순서가 보장된다."""
        for btype, data in EUI_BENCHMARKS.items():
            assert data["excellent"] < data["good"] < data["benchmark"], (
                f"{btype}: excellent < good < benchmark 위반"
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
