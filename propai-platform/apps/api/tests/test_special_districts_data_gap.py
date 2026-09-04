"""레인C(P0) — 규제구역(special_districts) 미수집 vs 확인완료·규제없음 구분 정직화.

근본원인: far_tier_service.calc_upzoning이 `base.get("special_districts") or (...)`로
명시 빈 리스트([])까지 falsy 취급해 "미수집"과 "확인 결과 규제구역 없음"을 구분하지
못했다 — UpzoningPotentialAnalyzer.analyze()는 이 둘을 구분해 data_gaps로 표기할 수
있는데(special_districts: list|None), 진입점에서 신호 자체가 소실됐었다.
"""
from __future__ import annotations

from app.services.land_intelligence import far_tier_service
from app.services.zoning.upzoning_potential import UpzoningPotentialAnalyzer

ZONE = "자연녹지지역"


class TestAnalyzerDataGaps:
    """UpzoningPotentialAnalyzer.analyze() 직접 단위 테스트."""

    def test_special_districts_none_yields_data_gap_note(self):
        r = UpzoningPotentialAnalyzer().analyze(ZONE, land_area_sqm=20000, special_districts=None)
        assert r["data_gaps"], "미수집(None)이면 data_gaps가 비어있으면 안 됨"
        assert "미수집" in r["data_gaps"][0]
        assert "규제구역" in r["data_gaps"][0]

    def test_special_districts_empty_list_no_data_gap(self):
        """확인 결과 규제구역 없음([])은 미수집과 달리 data_gaps를 남기지 않는다."""
        r = UpzoningPotentialAnalyzer().analyze(ZONE, land_area_sqm=20000, special_districts=[])
        assert r["data_gaps"] == []

    def test_special_districts_present_no_data_gap(self):
        r = UpzoningPotentialAnalyzer().analyze(
            ZONE, land_area_sqm=20000, special_districts=["개발제한구역"],
        )
        assert r["data_gaps"] == []

    def test_no_scenario_path_still_reports_data_gaps(self):
        """정형화 종상향 경로가 없는 용도지역(조기 return)도 data_gaps 키를 담아 반환한다."""
        r = UpzoningPotentialAnalyzer().analyze("중심상업지역", land_area_sqm=5000, special_districts=None)
        assert r["scenarios"] == []
        assert r["data_gaps"], "조기 return 분기도 data_gaps 키를 담아야 함(계약 일관성)"


class TestCalcUpzoningSpecialDistrictsPreservesNone:
    """far_tier_service.calc_upzoning — None(미수집)과 [](확인완료)을 구분 보존하는지."""

    def test_missing_key_becomes_none_not_empty_list(self, monkeypatch):
        captured: dict = {}

        class _FakeAnalyzer:
            def analyze(self, **kwargs):
                captured.update(kwargs)
                return {"scenarios": [], "potential_far_range": None, "data_gaps": []}

        monkeypatch.setattr(
            "app.services.zoning.upzoning_potential.UpzoningPotentialAnalyzer", _FakeAnalyzer,
        )
        far_tier_service.calc_upzoning({}, ZONE, 20000.0)
        assert captured["special_districts"] is None

    def test_explicit_empty_list_preserved_as_empty_not_none(self, monkeypatch):
        captured: dict = {}

        class _FakeAnalyzer:
            def analyze(self, **kwargs):
                captured.update(kwargs)
                return {"scenarios": [], "potential_far_range": None, "data_gaps": []}

        monkeypatch.setattr(
            "app.services.zoning.upzoning_potential.UpzoningPotentialAnalyzer", _FakeAnalyzer,
        )
        far_tier_service.calc_upzoning({"special_districts": []}, ZONE, 20000.0)
        assert captured["special_districts"] == []

    def test_explicit_list_passed_through(self, monkeypatch):
        captured: dict = {}

        class _FakeAnalyzer:
            def analyze(self, **kwargs):
                captured.update(kwargs)
                return {"scenarios": [], "potential_far_range": None, "data_gaps": []}

        monkeypatch.setattr(
            "app.services.zoning.upzoning_potential.UpzoningPotentialAnalyzer", _FakeAnalyzer,
        )
        far_tier_service.calc_upzoning({"special_districts": ["개발제한구역"]}, ZONE, 20000.0)
        assert captured["special_districts"] == ["개발제한구역"]
