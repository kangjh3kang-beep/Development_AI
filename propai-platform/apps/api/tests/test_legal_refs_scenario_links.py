"""종상향 시나리오·특이부지 요인의 verified 법령링크(legal_refs) 부착 테스트.

배경: 부지분석 화면의 종상향/종변경 잠재 시나리오 카드와 특이부지 게이트가 근거법령을
텍스트로만 표기(링크 없음)하던 결함을, legal_reference_registry(get_legal_refs)로
verified law.go.kr 딥링크를 per-scenario / per-factor에 가산해 해소했다.

원칙(절대 준수):
- verified URL(law.go.kr 등 신뢰호스트)만 클릭 링크. 미verified(지자체 운영기준·판례 등)는
  legal_basis 텍스트로만 정직 표기(가짜 링크·404 금지).
- legal_refs URL은 전적으로 레지스트리 출력만 사용(여기서 URL 조립 금지).
- 가산만(기존 legal_basis 텍스트·필드 무손상).
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from app.services.legal.legal_reference_registry import get_legal_refs  # noqa: E402
from app.services.zoning.special_parcel import detect_special_parcel  # noqa: E402
from app.services.zoning.upzoning_potential import (  # noqa: E402
    PATHS,
    UpzoningPotentialAnalyzer,
)


def _all_scenarios(zone: str, **kw) -> list[dict]:
    return UpzoningPotentialAnalyzer().analyze(zone_type=zone, **kw)["scenarios"]


class TestUpzoningScenarioLegalRefs:
    """종상향 per-scenario legal_refs — verified 딥링크 + 텍스트 폴백 정직성."""

    def test_each_scenario_has_legal_refs_list(self):
        scenarios = _all_scenarios("제2종일반주거지역", land_area_sqm=12000,
                                   near_station=True, near_station_m=300)
        assert scenarios, "종상향 경로가 있어야 한다"
        for s in scenarios:
            assert isinstance(s.get("legal_refs"), list), "legal_refs 리스트 가산"
            assert s.get("legal_basis"), "legal_basis 텍스트(기존 필드) 보존"

    def test_verified_urls_match_registry(self):
        """legal_refs의 verified url은 레지스트리 get_legal_refs 출력과 정확히 일치."""
        scenarios = _all_scenarios("제2종일반주거지역", land_area_sqm=12000,
                                   near_station=True, near_station_m=300)
        for s in scenarios:
            for ref in s["legal_refs"]:
                assert ref["url"] == "" or ref["url"].startswith("https://www.law.go.kr"), (
                    "url은 레지스트리 형식(law.go.kr) 또는 빈값 — 임의 조립 금지"
                )
                if ref["url_status"] == "verified":
                    expected = get_legal_refs([ref["key"]])[0]
                    assert ref["url"] == expected["url"], f"{ref['key']} URL 레지스트리 불일치"

    def test_district_unit_path_has_far_law_link(self):
        """지구단위계획 경로는 국토계획법(용도지역의 용적률 제78조) verified 링크를 포함."""
        scenarios = _all_scenarios("제2종일반주거지역", land_area_sqm=12000)
        dist = next((s for s in scenarios if s["path_key"] == "지구단위계획수립"), None)
        assert dist is not None
        keys = {r["key"] for r in dist["legal_refs"] if r["url_status"] == "verified"}
        assert "district_unit_plan" in keys and "far_law" in keys

    def test_ordinance_guideline_stays_text_only(self):
        """역세권 활성화는 국토계획법만 verified 링크 — 서울시 운영기준은 텍스트로만 유지(날조 링크 금지)."""
        # 카탈로그 자체에 운영기준 레지스트리 키가 없어야 한다(verified 불가 출처).
        path = PATHS["역세권활성화"]
        assert path["legal_ref_keys"] == ["far_law"]
        assert "운영기준" in path["legal_basis"]  # 텍스트로는 정직 표기

    def test_legal_basis_text_unchanged(self):
        """기존 legal_basis 텍스트(카탈로그 원문)는 그대로 보존(가산만)."""
        scenarios = _all_scenarios("제2종일반주거지역", land_area_sqm=12000,
                                   near_station=True, near_station_m=300)
        for s in scenarios:
            assert s["legal_basis"] == PATHS[s["path_key"]]["legal_basis"]


class TestSpecialParcelFactorLegalRefs:
    """특이부지 per-factor legal_refs — verified 딥링크 + 텍스트 폴백 정직성."""

    def test_greenbelt_factor_has_verified_link(self):
        sp = detect_special_parcel({"special_districts": ["개발제한구역"],
                                    "zone_type": "자연녹지지역"})
        assert sp and sp["is_special"]
        gb = next(f for f in sp["factors"] if "개발제한구역" in f["category"])
        verified = [r for r in gb["legal_refs"] if r["url_status"] == "verified"]
        assert verified, "GB는 verified 법령링크(greenbelt)를 가져야 한다"
        assert verified[0]["key"] == "greenbelt"
        assert verified[0]["url"] == get_legal_refs(["greenbelt"])[0]["url"]

    def test_farmland_and_forest_links(self):
        for cat, key in (("전", "farmland_conversion"), ("임야", "forest_conversion")):
            sp = detect_special_parcel({"land_category": cat, "zone_type": "계획관리지역"})
            assert sp, f"{cat} 특이부지 감지"
            f = sp["factors"][0]
            keys = {r["key"] for r in f["legal_refs"] if r["url_status"] == "verified"}
            assert key in keys, f"{cat} → {key} verified 링크 누락"

    def test_every_factor_has_legal_refs_list(self):
        """모든 요인에 legal_refs 리스트가 가산되고 기존 legal_basis 텍스트가 보존된다."""
        sp = detect_special_parcel({"land_category": "학교용지",
                                    "zone_type": "일반상업지역"})
        assert sp
        for f in sp["factors"]:
            assert isinstance(f.get("legal_refs"), list)
            assert isinstance(f.get("legal_basis"), list) and f["legal_basis"]

    def test_factor_urls_are_registry_or_empty(self):
        """factor legal_refs url은 레지스트리 형식(law.go.kr) 또는 빈값(임의 조립 금지)."""
        sp = detect_special_parcel({"land_category": "임야", "zone_type": "계획관리지역",
                                    "area_sqm": 8000})
        assert sp
        for f in sp["factors"]:
            for r in f["legal_refs"]:
                assert r["url"] == "" or r["url"].startswith("https://www.law.go.kr")
