"""P3+ — 용도지역 국가 규제 상한 제공자(INV-3 데이터파일 1차출처). 결정론·코드 하드코딩 0."""
from app.services.legal_calc import zone_limit_provider as zlp


def test_resolve_far_and_bcr_from_datafile():
    far = zlp.resolve_zone_limit("제2종일반주거지역", "far_floor_area")
    assert far[0] == 250.0 and "시행령" in far[1]
    assert zlp.resolve_zone_limit("제2종일반주거지역", "building_area")[0] == 60.0  # 건폐율
    assert zlp.resolve_zone_limit("일반상업지역", "far_floor_area")[0] == 1300.0
    assert zlp.resolve_zone_limit("제3종일반주거", "far_floor_area")[0] == 300.0  # '지역' 접미 보정


def test_resolve_none_for_unknown_or_nontarget():
    assert zlp.resolve_zone_limit(None, "far_floor_area") is None
    assert zlp.resolve_zone_limit("미지지역", "far_floor_area") is None
    assert zlp.resolve_zone_limit("제2종일반주거지역", "building_height") is None  # 국가상한 비대상
    assert zlp.resolve_zone_limit("제2종일반주거지역", None) is None


def test_db_override_takes_precedence():
    # 조례 강화/개정을 코드 변경 없이 주입(데이터파일 < override). 테스트 후 원복.
    try:
        zlp.set_zone_override("제2종일반주거지역", {"far_pct": 220})
        assert zlp.resolve_zone_limit("제2종일반주거지역", "far_floor_area")[0] == 220.0
    finally:
        zlp._override.pop("제2종일반주거지역", None)
