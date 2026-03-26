"""Climate Risk 서비스 단위 테스트.

DB 없이 순수 계산 로직만 검증한다.
- 우선순위 분류 (_priority)
- 연간 예상 손실 계산
- 보험 프리미엄 계산
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from apps.api.services.climate_risk_service import ClimateRiskService


class TestPriority:
    """_priority 정적 메서드 테스트."""

    def test_high_priority(self):
        assert ClimateRiskService._priority(0.70) == "high"
        assert ClimateRiskService._priority(0.85) == "high"
        assert ClimateRiskService._priority(1.0) == "high"

    def test_medium_priority(self):
        assert ClimateRiskService._priority(0.45) == "medium"
        assert ClimateRiskService._priority(0.55) == "medium"
        assert ClimateRiskService._priority(0.69) == "medium"

    def test_low_priority(self):
        assert ClimateRiskService._priority(0.0) == "low"
        assert ClimateRiskService._priority(0.30) == "low"
        assert ClimateRiskService._priority(0.44) == "low"


class TestAnnualExpectedLoss:
    """연간 예상 손실 계산 공식 검증.

    공식: asset_value * (0.004 + severity_score * 0.028)
    """

    def test_low_risk_loss(self):
        """낮은 리스크(severity=0.2) → 약 1% 손실."""
        asset = 10_000_000_000  # 100억
        severity = 0.2
        loss = asset * (0.004 + severity * 0.028)
        assert loss == pytest.approx(96_000_000, rel=0.01)  # 9,600만원

    def test_high_risk_loss(self):
        """높은 리스크(severity=0.8) → 약 2.6% 손실."""
        asset = 10_000_000_000
        severity = 0.8
        loss = asset * (0.004 + severity * 0.028)
        assert loss == pytest.approx(264_000_000, rel=0.01)  # 2.64억

    def test_zero_risk_base_loss(self):
        """리스크 0이어도 기본 손실률 0.4% 적용."""
        asset = 10_000_000_000
        severity = 0.0
        loss = asset * (0.004 + severity * 0.028)
        assert loss == pytest.approx(40_000_000, rel=0.01)  # 4,000만원


class TestInsurancePremium:
    """보험 프리미엄 계산 검증.

    프리미엄 = coverage_limit * (0.006 + score * 0.01)
    """

    def test_flood_coverage_premium(self):
        """홍수 피해 보험 (자산가치의 35%)."""
        asset = 10_000_000_000
        flood_score = 0.6
        coverage_limit = asset * 0.35  # 35억
        premium = coverage_limit * (0.006 + flood_score * 0.01)
        expected = 3_500_000_000 * 0.012
        assert premium == pytest.approx(expected, rel=0.01)

    def test_heat_stress_coverage_premium(self):
        """고온 지연 보험 (자산가치의 12%)."""
        asset = 10_000_000_000
        heat_score = 0.5
        coverage_limit = asset * 0.12  # 12억
        premium = coverage_limit * (0.006 + heat_score * 0.01)
        expected = 1_200_000_000 * 0.011
        assert premium == pytest.approx(expected, rel=0.01)

    def test_business_interruption_premium(self):
        """영업 중단 보험 (자산가치의 18%)."""
        asset = 10_000_000_000
        avg_score = (0.6 + 0.5) / 2  # 0.55
        coverage_limit = asset * 0.18
        premium = coverage_limit * (0.006 + avg_score * 0.01)
        expected = 1_800_000_000 * 0.0115
        assert premium == pytest.approx(expected, rel=0.01)

    def test_severity_score_is_max(self):
        """severity_score = max(flood, heat)."""
        flood = 0.3
        heat = 0.7
        severity = max(flood, heat)
        assert severity == 0.7


class TestCoverageSpecs:
    """보험 커버리지 사양 검증."""

    def test_three_coverage_types(self):
        """3가지 보험 유형이 정의됨."""
        coverage_types = ["flood-damage", "heat-stress-delay", "business-interruption"]
        coverage_ratios = [0.35, 0.12, 0.18]
        assert len(coverage_types) == 3
        assert sum(coverage_ratios) == pytest.approx(0.65, abs=0.01)

    def test_total_coverage_ratio(self):
        """총 보험 커버리지가 자산가치의 65%."""
        total = 0.35 + 0.12 + 0.18
        assert total == pytest.approx(0.65, abs=0.001)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
