"""혼재 용도지역 면적가중 건폐율/용적률 검증 — 토지이음 인허가 사례1 등가.

국토계획법 제84조·시행령 제94조: 둘 이상 용도지역에 걸치는 대지의 건폐/용적은 면적가중,
작은 부분(≤330㎡)은 큰 용도지역에 흡수.
"""
from app.services.zoning.legal_zone_limits import mixed_zone_limits


def test_single_zone_not_mixed():
    assert mixed_zone_limits([{"zone_type": "제2종일반주거지역", "area_sqm": 500}])["is_mixed"] is False


def test_area_weighted_blend():
    """제2종일반주거(60/250) + 일반상업(80/1300) 면적가중 → 두 값 사이."""
    r = mixed_zone_limits([
        {"zone_type": "제2종일반주거지역", "area_sqm": 7869},
        {"zone_type": "일반상업지역", "area_sqm": 7089},
    ])
    assert r["is_mixed"] and r["rule"] == "면적가중"
    # 건폐율 60~80 사이, 용적률 250~1300 사이.
    assert 60 < r["blended_bcr_pct"] < 80
    assert 250 < r["blended_far_pct"] < 1300
    assert r["dominant_zone"] == "제2종일반주거지역"  # 더 넓음
    assert {"mixed_zone_rule", "mixed_zone_rule_dec"} <= set(r["legal_ref_keys"])


def test_small_part_absorbed():
    """작은 부분(≤330㎡) → 큰 용도지역에 흡수, 큰 용도지역 한도 적용."""
    r = mixed_zone_limits([
        {"zone_type": "일반상업지역", "area_sqm": 2000},
        {"zone_type": "제2종일반주거지역", "area_sqm": 200},  # ≤330 흡수
    ])
    assert r["rule"] == "330㎡이하 흡수"
    assert r["absorbed"] == "제2종일반주거지역"
    assert r["dominant_zone"] == "일반상업지역"
    assert r["blended_bcr_pct"] == 80  # 일반상업 기준


def test_no_area_honest():
    """면적 미확보 → is_mixed True, blended None, 정직 미산정."""
    r = mixed_zone_limits([
        {"zone_type": "제2종일반주거지역"},
        {"zone_type": "일반상업지역"},
    ])
    assert r["is_mixed"] and r["blended_far_pct"] is None
    assert "미산정" in r["note"] or "미확보" in r["note"]
    assert len(r["per_zone"]) == 2


def test_duplicate_zone_merged():
    """같은 용도지역 조각은 면적 합산 → 단일로 병합(혼재 아님)."""
    r = mixed_zone_limits([
        {"zone_type": "제2종일반주거지역", "area_sqm": 300},
        {"zone_type": "제2종일반주거지역", "area_sqm": 400},
    ])
    assert r["is_mixed"] is False
