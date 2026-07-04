"""자연재해 리스크 분석 테스트 (자연재해대책법)."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.disaster_risk.disaster_risk_service import DisasterRiskService


class TestDisasterRisk:
    """자연재해 리스크."""

    def setup_method(self):
        self.svc = DisasterRiskService()

    def test_known_region(self):
        """등록 지역(서울) → 해당 위험지수 사용."""
        result = self.svc.assess_disaster_risk("서울", "주거", 15)
        assert result["region"] == "서울"
        assert result["legal_basis"] == "자연재해대책법"
        assert 0 <= result["total_risk_score"] <= 1

    def test_unknown_region_uses_default(self):
        """미등록 지역 → default 위험지수."""
        result = self.svc.assess_disaster_risk("제주", "상업", 10)
        assert result["region"] == "제주"
        assert result["total_risk_score"] > 0

    def test_river_proximity_increases_flood_risk(self):
        """하천 가까울수록 홍수 리스크 증가."""
        near_river = self.svc.assess_disaster_risk("부산", "주거", 10, distance_to_river_m=100)
        far_river = self.svc.assess_disaster_risk("부산", "주거", 10, distance_to_river_m=900)
        assert near_river["flood_risk_score"] > far_river["flood_risk_score"]

    def test_high_floor_count_increases_seismic(self):
        """고층 건물 → 지진 취약성 증가."""
        low = self.svc.assess_disaster_risk("대구", "주거", 5)
        high = self.svc.assess_disaster_risk("대구", "주거", 20)
        assert high["earthquake_risk_score"] > low["earthquake_risk_score"]

    def test_evacuation_routes_provided(self):
        """대피 경로 3개 제공."""
        result = self.svc.assess_disaster_risk("서울", "주거", 10)
        assert len(result["evacuation_routes"]) == 3

    def test_risk_levels(self):
        """리스크 레벨 유효한 값."""
        result = self.svc.assess_disaster_risk("서울", "주거", 10)
        assert result["risk_level"] in {"critical", "high", "medium", "low"}
