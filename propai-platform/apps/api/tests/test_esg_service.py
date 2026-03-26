"""ESGService 단위 테스트.

GRESB 등급 판정, ESG 점수 산출 등 정적 메서드를 검증한다.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from apps.api.services.esg_service import ESGService


class TestGRESBRating:
    """_gresb_rating 정적 메서드 테스트."""

    def test_85이상_5Star(self):
        assert ESGService._gresb_rating(85) == "5 Star"

    def test_90_5Star(self):
        assert ESGService._gresb_rating(90) == "5 Star"

    def test_75_4Star(self):
        assert ESGService._gresb_rating(75) == "4 Star"

    def test_84_4Star(self):
        assert ESGService._gresb_rating(84) == "4 Star"

    def test_65_3Star(self):
        assert ESGService._gresb_rating(65) == "3 Star"

    def test_74_3Star(self):
        assert ESGService._gresb_rating(74) == "3 Star"

    def test_55_2Star(self):
        assert ESGService._gresb_rating(55) == "2 Star"

    def test_54_1Star(self):
        assert ESGService._gresb_rating(54) == "1 Star"

    def test_0_1Star(self):
        assert ESGService._gresb_rating(0) == "1 Star"


class TestDeriveScores:
    """_derive_scores 정적 메서드 테스트."""

    def _base_params(self, **overrides) -> dict:
        defaults = {
            "total_carbon_tco2e": 100,
            "gross_floor_area_sqm": 10000,
            "energy_independence_rate": 0.5,
            "climate_risk_score": 0.2,
            "lost_time_incident_rate": 0.5,
            "community_programs_count": 3,
            "board_independence_ratio": 0.6,
        }
        defaults.update(overrides)
        return defaults

    def test_6개_반환값(self):
        result = ESGService._derive_scores(**self._base_params())
        assert len(result) == 6

    def test_점수_0_100_범위(self):
        e, s, g, overall, rating, action = ESGService._derive_scores(**self._base_params())
        assert 0.0 <= e <= 100.0
        assert 0.0 <= s <= 100.0
        assert 0.0 <= g <= 100.0
        assert 0.0 <= overall <= 100.0

    def test_종합점수_가중치_합산(self):
        """overall = e*0.45 + s*0.25 + g*0.30."""
        e, s, g, overall, _, _ = ESGService._derive_scores(**self._base_params())
        expected = round(e * 0.45 + s * 0.25 + g * 0.30, 2)
        assert overall == pytest.approx(expected, abs=0.01)

    def test_높은_탄소배출_환경점수_감소(self):
        low_carbon = ESGService._derive_scores(**self._base_params(total_carbon_tco2e=10))
        high_carbon = ESGService._derive_scores(**self._base_params(total_carbon_tco2e=500))
        assert low_carbon[0] > high_carbon[0]  # e_score

    def test_높은_에너지자립률_환경점수_증가(self):
        low_indep = ESGService._derive_scores(**self._base_params(energy_independence_rate=0.1))
        high_indep = ESGService._derive_scores(**self._base_params(energy_independence_rate=0.9))
        assert high_indep[0] > low_indep[0]

    def test_높은_기후리스크_환경점수_감소(self):
        low_risk = ESGService._derive_scores(**self._base_params(climate_risk_score=0.1))
        high_risk = ESGService._derive_scores(**self._base_params(climate_risk_score=0.9))
        assert low_risk[0] > high_risk[0]

    def test_높은_사고율_사회점수_감소(self):
        low_incident = ESGService._derive_scores(**self._base_params(lost_time_incident_rate=0.1))
        high_incident = ESGService._derive_scores(**self._base_params(lost_time_incident_rate=3.0))
        assert low_incident[1] > high_incident[1]  # s_score

    def test_높은_이사회독립성_지배구조_증가(self):
        low_indep = ESGService._derive_scores(**self._base_params(board_independence_ratio=0.2))
        high_indep = ESGService._derive_scores(**self._base_params(board_independence_ratio=0.9))
        assert high_indep[2] > low_indep[2]  # g_score

    def test_rating_문자열_포함(self):
        _, _, _, _, rating, _ = ESGService._derive_scores(**self._base_params())
        assert "Star" in rating

    def test_80이상_유지_action_plan(self):
        """overall ≥ 80 → 유지 관련 액션."""
        _, _, _, overall, _, action = ESGService._derive_scores(
            **self._base_params(
                total_carbon_tco2e=10,
                energy_independence_rate=0.9,
                climate_risk_score=0.05,
                lost_time_incident_rate=0.1,
                community_programs_count=5,
                board_independence_ratio=0.9,
            )
        )
        if overall >= 80:
            assert "Maintain" in action

    def test_65미만_개선_action_plan(self):
        _, _, _, overall, _, action = ESGService._derive_scores(
            **self._base_params(
                total_carbon_tco2e=500,
                climate_risk_score=0.9,
                lost_time_incident_rate=3.0,
                board_independence_ratio=0.1,
            )
        )
        if overall < 65:
            assert "Prioritize" in action


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
