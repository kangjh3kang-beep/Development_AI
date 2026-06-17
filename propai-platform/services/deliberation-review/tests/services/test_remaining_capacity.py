"""잔여 개발용량 — 용도지역 법정한도 매핑·잔여 FAR 산정·초과 판정·대지카드 통합."""
from app.services.land.remaining_capacity import remaining_capacity
from app.services.land.zone_limits import lookup_zone_limit


def test_zone_limit_lookup():
    z = lookup_zone_limit("제1종일반주거지역")
    assert z["far_limit_pct"] == 200 and z["bcr_limit_pct"] == 60
    assert lookup_zone_limit("일반상업지역")["far_limit_pct"] == 1300
    assert lookup_zone_limit("없는지역") is None


def test_remaining_far_normal():
    # 제2종일반(250%), 대지 1000㎡, 기존 연면적 1500㎡ → 기존 150%, 잔여 100%.
    rc = remaining_capacity("제2종일반주거지역", 1000.0, 1500.0)
    assert rc["far_limit_pct"] == 250
    assert rc["existing_far_pct"] == 150.0
    assert rc["remaining_far_pct"] == 100.0
    assert rc["max_total_floor_area"] == 2500.0
    assert rc["remaining_floor_area"] == 1000.0
    assert rc["over_limit"] is False


def test_remaining_over_limit():
    # 제1종일반(200%), 대지 15622㎡, 기존 50551㎡ → 기존 ~324% > 200% → 초과(잔여 음수).
    rc = remaining_capacity("제1종일반주거지역", 15622.1, 50551.9)
    assert rc["existing_far_pct"] > 200
    assert rc["remaining_far_pct"] < 0
    assert rc["over_limit"] is True


def test_vacant_lot_full_capacity():
    # 나대지(기존 0) → 잔여 = 법정 상한.
    rc = remaining_capacity("제3종일반주거지역", 1000.0, None)
    assert rc["existing_far_pct"] == 0.0
    assert rc["remaining_far_pct"] == 300.0
    assert rc["remaining_floor_area"] == 3000.0


def test_no_zone_or_area_none():
    assert remaining_capacity(None, 1000.0, 0) is None
    assert remaining_capacity("제1종일반주거지역", None, 0) is None
    assert remaining_capacity("미지정구역", 1000.0, 0) is None  # 매칭 실패
