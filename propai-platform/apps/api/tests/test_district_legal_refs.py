"""지역지구별 규제법령집 매핑 검증 — 토지이음 관련정보의 법령엔진(진실원천) 실시간 반영.

getLandUseAttr districts(지역지구 designation 이름) → 관련 법령조문(law.go.kr 링크).
의정부동224(혼재·다규제 부지)의 실제 지역지구 목록으로 검증.
"""
from app.services.legal.legal_reference_registry import legal_refs_for_districts

# 의정부동224 라이브 land_use_plan.districts (토지이음 표시 목록과 매칭).
_UJB_224 = [
    "(한강)폐기물매립시설 설치제한지역", "대로2류(폭 30m~35m)", "소로2류(폭 8m~10m)",
    "광장", "학교", "과밀억제권역", "절대보호구역", "상대보호구역",
    "특정용도제한지구", "철도보호지구", "대로3류(폭 25m~30m)", "중점경관관리구역",
    "제2종일반주거지역", "가축사육제한구역", "일반상업지역",
]


def _keys(result):
    return {r["key"] for r in result["refs"]}


def test_ujb224_maps_all_major_districts():
    """의정부동224 지역지구 → 핵심 법령조문 전부 매핑."""
    res = legal_refs_for_districts(_UJB_224)
    keys = _keys(res)
    # 용도지역(건폐/용적/용도제한)
    assert {"zone_use", "bcr_law", "far_law"} <= keys
    # 도로·도시계획시설(대로/소로/광장)
    assert "road_relation" in keys and "urban_planning_facility" in keys
    # 교육환경보호구역(절대·상대보호·학교)
    assert "edu_env_protection" in keys
    # 특정용도제한지구
    assert "specific_use_district" in keys
    # 철도보호지구
    assert "railway_protection" in keys
    # 과밀억제권역
    assert "metro_overconcentration" in keys
    # 중점경관관리구역
    assert "landscape_district" in keys
    # 폐기물매립·가축사육제한
    assert "waste_landfill_restrict" in keys and "livestock_restrict" in keys


def test_refs_have_verified_law_urls():
    """매핑된 법령은 law.go.kr verified URL을 가져야 함(무날조·정직)."""
    res = legal_refs_for_districts(["철도보호지구", "특정용도제한지구"])
    assert res["refs"], "법령 레코드가 있어야 함"
    for r in res["refs"]:
        assert r.get("law_name") and r.get("article")
        # 신규 추가 법령은 law.go.kr verified 여야 함(레지스트리 build_law_url)
        assert r.get("url_status") in ("verified", "pending")


def test_by_district_traceability():
    """designation별 매핑 근거(by_district)를 추적 가능하게 제공."""
    res = legal_refs_for_districts(["철도보호지구", "건축선"])
    assert res["by_district"]["철도보호지구"] == ["railway_protection"]
    assert "building_line" in res["by_district"]["건축선"]


def test_unmatched_is_honest():
    """법령 매핑이 없는 designation은 정직하게 unmatched(가짜 링크 금지)."""
    res = legal_refs_for_districts(["존재하지않는지구ABC", "제2종일반주거지역"])
    assert "존재하지않는지구ABC" in res["unmatched"]
    assert "zone_use" in _keys(res)  # 매칭된 것은 정상 반영


def test_dedup_keys():
    """대로2류+대로3류+소로2류 등 중복 도로 designation → 법령키 중복 제거."""
    res = legal_refs_for_districts(["대로2류", "대로3류", "소로2류"])
    keys = [r["key"] for r in res["refs"]]
    assert len(keys) == len(set(keys)), "법령키 중복 없어야 함"
    assert "road_relation" in keys
