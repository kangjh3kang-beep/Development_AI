"""리스크 등급화 테스트 (ISO 31000)."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.lifecycle.risk.risk_service import RiskService


class TestRiskScores:
    """리스크 점수 계산."""

    def setup_method(self):
        self.svc = RiskService()

    def test_risk_count(self):
        """10개 리스크 항목 모두 반환."""
        result = self.svc.calculate_risk_scores()
        assert result["total_risks"] == 10

    def test_risk_score_formula(self):
        """Risk = likelihood × impact."""
        result = self.svc.calculate_risk_scores()
        for risk in result["risks"]:
            expected = risk["likelihood"] * risk["impact"]
            assert risk["risk_score"] == pytest.approx(expected, abs=0.001)

    def test_risk_levels_assigned(self):
        """모든 리스크에 레벨 지정."""
        result = self.svc.calculate_risk_scores()
        valid_levels = {"critical", "high", "medium", "low"}
        for risk in result["risks"]:
            assert risk["risk_level"] in valid_levels

    def test_sorted_by_score_desc(self):
        """점수 내림차순 정렬."""
        result = self.svc.calculate_risk_scores()
        scores = [r["risk_score"] for r in result["risks"]]
        assert scores == sorted(scores, reverse=True)

    def test_standard_iso_31000(self):
        """ISO 31000:2018 표준."""
        result = self.svc.calculate_risk_scores()
        assert result["standard"] == "ISO 31000:2018"

    def test_critical_high_counts(self):
        """critical/high 카운트 합산 확인."""
        result = self.svc.calculate_risk_scores()
        actual_critical = len([r for r in result["risks"] if r["risk_level"] == "critical"])
        actual_high = len([r for r in result["risks"] if r["risk_level"] == "high"])
        assert result["critical_count"] == actual_critical
        assert result["high_count"] == actual_high
