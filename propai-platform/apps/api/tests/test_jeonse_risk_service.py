"""전세 리스크 서비스 단위 테스트.

DB/외부 API 없이 순수 계산 로직만 검증한다.
- 전세가율 기반 위험 등급 판정
- HUG 보증보험 가입 가능 여부
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from apps.api.services.jeonse_risk_service import JeonseRiskService


class TestCalculateRiskLevel:
    """_calculate_risk_level 정적 메서드 테스트."""

    def test_critical_90_percent(self):
        """전세가율 90% 이상 → CRITICAL."""
        level, score = JeonseRiskService._calculate_risk_level(0.90)
        assert level == "CRITICAL"
        assert score == 0.95

    def test_critical_95_percent(self):
        level, score = JeonseRiskService._calculate_risk_level(0.95)
        assert level == "CRITICAL"
        assert score == 0.95

    def test_high_80_percent(self):
        """전세가율 80~89% → HIGH."""
        level, score = JeonseRiskService._calculate_risk_level(0.80)
        assert level == "HIGH"
        assert score == 0.80

    def test_high_85_percent(self):
        level, score = JeonseRiskService._calculate_risk_level(0.85)
        assert level == "HIGH"
        assert score == 0.80

    def test_medium_70_percent(self):
        """전세가율 70~79% → MEDIUM."""
        level, score = JeonseRiskService._calculate_risk_level(0.70)
        assert level == "MEDIUM"
        assert score == 0.55

    def test_low_60_percent(self):
        """전세가율 60~69% → LOW."""
        level, score = JeonseRiskService._calculate_risk_level(0.60)
        assert level == "LOW"
        assert score == 0.30

    def test_safe_below_60_percent(self):
        """전세가율 60% 미만 → SAFE."""
        level, score = JeonseRiskService._calculate_risk_level(0.50)
        assert level == "SAFE"
        assert score == 0.10

    def test_safe_very_low(self):
        level, score = JeonseRiskService._calculate_risk_level(0.30)
        assert level == "SAFE"
        assert score == 0.10


class TestHUGEligibility:
    """_check_hug_eligibility 정적 메서드 테스트."""

    def test_metropolitan_under_limit(self):
        """수도권 전세금 7억 미만 → 가입 가능."""
        eligible, reason = JeonseRiskService._check_hug_eligibility(
            jeonse_price=500_000_000,
            is_metropolitan=True,
        )
        assert eligible is True

    def test_metropolitan_over_limit(self):
        """수도권 전세금 7억 초과 → 가입 불가."""
        eligible, reason = JeonseRiskService._check_hug_eligibility(
            jeonse_price=800_000_000,
            is_metropolitan=True,
        )
        assert eligible is False


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
