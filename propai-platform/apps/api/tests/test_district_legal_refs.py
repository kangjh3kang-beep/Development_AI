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


def test_flight_safety_and_military_zone_maps_military_law():
    """WP-R2: 비행안전구역·공항·군사기지·군사시설보호 → 군사기지법(military_protection_zone)."""
    for name in ("비행안전제5구역", "공항시설보호지구", "군사기지 보호구역", "군사시설보호구역"):
        res = legal_refs_for_districts([name])
        assert "military_protection_zone" in _keys(res), f"{name} → 군사기지법 매핑 실패"


def test_land_transaction_permit_maps_realtx_report():
    """WP-R2: 토지거래허가/토지거래계약허가구역 → 부동산 거래신고법(realtx_report)."""
    for name in ("토지거래계약허가구역", "토지거래허가구역"):
        res = legal_refs_for_districts([name])
        assert "realtx_report" in _keys(res), f"{name} → 거래신고법 매핑 실패"


def test_green_zone_floor_cap_ref_is_kookto_decree_not_building_act():
    """WP-R2: 녹지 4층 근거는 건축법이 아니라 국토계획법 시행령(별표15~17)이어야 한다."""
    from app.services.legal.legal_reference_registry import get_legal_refs

    refs = get_legal_refs(["green_zone_floor_cap"])
    assert refs, "green_zone_floor_cap 근거키가 존재해야 함"
    r = refs[0]
    assert "국토의 계획 및 이용에 관한 법률 시행령" == r["law_name"]
    assert "건축법" != r["law_name"]
    assert r["url_status"] == "verified"  # 시행령 법령 루트 = law.go.kr verified
