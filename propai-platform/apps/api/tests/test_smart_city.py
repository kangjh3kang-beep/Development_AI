"""스마트시티 입지 분석 테스트 (스마트도시법)."""

import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.smart_city.smart_city_service import SmartCityService


class TestLocationScore:
    """입지 점수 계산."""

    def setup_method(self):
        self.svc = SmartCityService()

    def test_high_scores_grade_a(self):
        """모든 지표 90점 → A등급."""
        data = {k: 90.0 for k in SmartCityService.SCORE_WEIGHTS}
        result = self.svc.calculate_location_score(data)
        assert result["grade"] == "A"
        assert result["total_location_score"] >= 80

    def test_low_scores_grade_d(self):
        """모든 지표 30점 → D등급."""
        data = {k: 30.0 for k in SmartCityService.SCORE_WEIGHTS}
        result = self.svc.calculate_location_score(data)
        assert result["grade"] == "D"
        assert result["total_location_score"] < 40

    def test_default_50_for_missing(self):
        """미제공 지표 → 기본값 50."""
        result = self.svc.calculate_location_score({})
        assert result["total_location_score"] == pytest.approx(50.0, rel=0.01)

    def test_weight_sum_1(self):
        """가중치 합 = 1.0."""
        total_weight = sum(SmartCityService.SCORE_WEIGHTS.values())
        assert total_weight == pytest.approx(1.0, abs=0.01)

    def test_breakdown_has_all_indicators(self):
        """breakdown에 6개 지표 모두 포함."""
        result = self.svc.calculate_location_score({})
        assert len(result["breakdown"]) == 6

    def test_legal_basis(self):
        """법적 근거 확인."""
        result = self.svc.calculate_location_score({})
        assert "스마트도시" in result["legal_basis"]
