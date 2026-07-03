"""토지이음 보강(건축선·도로조건·고시정보) 검증 — 결정론·근거기반·정직."""
from app.services.legal.tojieum_supplement import (
    assess_road_conditions,
    building_line_setback,
    gosi_info,
)


def test_road_condition_wide_road_ok():
    """광대소각(25m↑) + 소규모 연면적 → 접도요건 충족."""
    r = assess_road_conditions("광대소각", planned_gfa_sqm=500)
    assert r["status"] == "충족"
    assert r["required_road_width_m"] == 4.0  # 2천㎡ 미만
    assert "road_relation" in r["legal_ref_keys"]


def test_road_condition_large_gfa_needs_6m():
    """연면적 2천㎡ 이상 → 요구 도로너비 6m·접도 4m."""
    r = assess_road_conditions("중로한면", planned_gfa_sqm=3000)
    assert r["required_road_width_m"] == 6.0 and r["required_contact_m"] == 4.0
    assert r["status"] == "충족"  # 중로 12m↑ → 6m 충족


def test_road_condition_maengji_blocked():
    """맹지 → 건축 불가(도로 확보 선행)."""
    r = assess_road_conditions("맹지", planned_gfa_sqm=300)
    assert r["status"] == "불가"
    assert "맹지" in r["note"]


def test_road_condition_unknown_honest():
    """도로접면 미상 → 정직 미산정(가짜 충족 금지)."""
    r = assess_road_conditions(None)
    assert r["status"] == "미상"


def test_building_line_setback_narrow_road():
    """세로(불) 폭 2m → 소요너비 4m 미달 → 각 측 (4-2)/2=1m 후퇴."""
    r = building_line_setback("세로(불)")
    assert r["setback_m"] == 1.0
    assert "building_line" in r["legal_ref_keys"]


def test_building_line_no_setback_wide():
    """광대로(25m) → 소요너비 충족 → 후퇴 0."""
    r = building_line_setback("광대한면")
    assert r["setback_m"] == 0.0


def test_building_line_unknown():
    """도로폭 미상 → 후퇴 산정 불가(정직)."""
    r = building_line_setback(None)
    assert r["setback_m"] is None


def test_gosi_info_deeplink():
    """고시정보 — 시군구 스코프 토지이음 고시 목록 deep-link + 3종 카테고리."""
    g = gosi_info("경기도", "의정부시")
    assert "eum.go.kr" in g["list_url"]
    assert "결정고시" in g["categories"] and "지형도면고시" in g["categories"]
    assert g["region"] == "경기도 의정부시"
    assert g["available"] is False  # 부지단위 자동매칭 미연동(정직)
