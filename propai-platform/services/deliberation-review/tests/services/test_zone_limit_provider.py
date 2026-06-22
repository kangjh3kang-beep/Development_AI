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


def test_partial_override_consistent_across_resolve_and_all():
    # ★부분 override(far만 강화)는 나머지 지표(bcr)를 데이터파일에서 보존(키 병합) — resolve_zone_limit과
    # all_zone_limits 두 경로가 **동치**여야 read 표면(P5 divergence)이 엔진 실 계산값을 정직 반영.
    try:
        zlp.set_zone_override("제2종일반주거지역", {"far_pct": 220})
        far = zlp.resolve_zone_limit("제2종일반주거지역", "far_floor_area")
        bcr = zlp.resolve_zone_limit("제2종일반주거지역", "building_area")
        z = zlp.all_zone_limits()["zones"]["제2종일반주거지역"]
        assert far[0] == 220.0 and z["far_floor_area"]["value"] == 220.0          # override 반영(양 경로)
        assert bcr is not None and bcr[0] == 60.0                                  # bcr 미override → base 보존
        assert z["building_area"]["value"] == 60.0                                # 양 경로 동치(거짓 None/matched 아님)
    finally:
        zlp._override.pop("제2종일반주거지역", None)


def test_override_rejects_nonnumeric_limit():
    # override의 잘못된 타입(bool 등)은 거짓 한도(True→1.0)로 통과 금지 → None(날조 방지).
    try:
        zlp.set_zone_override("제2종일반주거지역", {"far_pct": True})
        assert zlp.resolve_zone_limit("제2종일반주거지역", "far_floor_area") is None
        assert "far_floor_area" not in zlp.all_zone_limits()["zones"].get("제2종일반주거지역", {})
    finally:
        zlp._override.pop("제2종일반주거지역", None)
