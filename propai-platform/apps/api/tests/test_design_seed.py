"""mass_backbone — design_seed.mass_seed_targets(매스 레퍼런스→설계 목표강도) 단위테스트(순수)."""
from app.services.mass_backbone.design_seed import mass_seed_targets


def test_mass_seed_targets_valid():
    ref = {"region": "분당구", "building_type": "공동주택", "sample_count": 84,
           "median_bcr_pct": 16.8, "median_far_pct": 89.2, "median_floors": 5.0}
    t = mass_seed_targets(ref)
    assert t["target_bcr_percent"] == 16.8 and t["target_far_percent"] == 89.2
    assert t["target_floors"] == 5.0 and t["building_type"] == "공동주택"
    assert t["sample_count"] == 84 and t["source"].startswith("mass_backbone")


def test_mass_seed_targets_missing_or_zero_is_none():
    # 건폐/용적 결측·0이면 None(시드 미적용·법정 최대만)
    assert mass_seed_targets(None) is None
    assert mass_seed_targets({"median_bcr_pct": None, "median_far_pct": None}) is None
    assert mass_seed_targets({"median_bcr_pct": 0, "median_far_pct": 200}) is None
    assert mass_seed_targets({"median_bcr_pct": 50, "median_far_pct": 0}) is None
