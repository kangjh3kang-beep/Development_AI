"""빌더블 인벨로프 — 현실 최고층 산정(ceil) 회귀. 데이터흐름 SSOT 정합 Q1.

현실 최고층 = 유효 연면적을 '담는 데 필요한' 최소 층수(올림). round 내림이면 표시 연면적을 담지 못하는
과소산정(예 29,938㎡/7,185㎡=4.167 → round 4층은 28,740㎡만 수용 < 29,938)이 되므로 ceil이어야 한다.
정북일조 적용(주거) 경로와 미적용(상업 등) 경로 둘 다 동일 ceil 정책.
"""
import math

from app.services.site_score.solar_envelope_service import compute_buildable_envelope


def test_realistic_floors_holds_gfa_north_light_zone():
    # 제2종일반주거(정북일조 적용) 11,975㎡·FAR250·BCR60 → 층수×건폐율바닥이 유효 연면적 수용(round면 미달).
    r = compute_buildable_envelope(land_area_sqm=11975, zone="제2종일반주거지역",
                                   bcr_limit_pct=60, far_limit_pct=250, floor_height_m=3.0)
    floors = r["max_floors"]
    footprint = 11975 * 0.60  # 건폐율 바닥
    egfa = r["effective_gfa_sqm"]
    assert floors * footprint >= egfa, f"{floors}층×{footprint}㎡ < 유효 {egfa}㎡(과소산정)"
    assert (floors - 1) * footprint < egfa  # 최소성(과대 아님)


def test_realistic_floors_ceil_non_north_light_zone():
    # 정북일조 미적용 경로(zone 미지정/상업) → floors=ceil(FAR/BCR). 4.167→5(round 내림 4 회귀 가드).
    r = compute_buildable_envelope(land_area_sqm=11975, bcr_limit_pct=60, far_limit_pct=250, floor_height_m=3.0)
    assert r["applies_north_light"] is False
    assert r["max_floors"] == math.ceil(2.50 / 0.60) == 5  # round였으면 4


def test_realistic_floors_at_least_one():
    r = compute_buildable_envelope(land_area_sqm=300, bcr_limit_pct=60, far_limit_pct=100, floor_height_m=3.0)
    assert r["max_floors"] >= 1
