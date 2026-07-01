"""일조·배치 엔진 검증 — 천문 물리 정확성 + 배치 대안 다각도 산정.

사용자 요청: 토지모양·건물배치·방향·층별높이에 따른 일조 영향도 정밀분석 → 다각도 최적안.
"""

from app.services.site_score.solar_placement_service import (
    analyze_solar_placement,
    orientation_daylight,
    orientation_scores,
    sun_position,
)


# ── 천문 물리 정확성 ──────────────────────────────────────────
def test_winter_noon_altitude_seoul():
    """서울(37.5°N) 동지 정오 태양고도 ≈ 90−위도−23.44 ≈ 29°, 방위=정남(0°)."""
    sp = sun_position(0.0, 37.5)
    assert abs(sp["altitude_deg"] - 29.06) < 0.5, f"동지 정오 고도 ≈29° 여야 함 (현재 {sp['altitude_deg']})"
    assert abs(sp["azimuth_deg"]) < 1.0, "정오 태양은 정남(방위 0°)"


def test_afternoon_sun_west():
    """오후(시각각 +)면 태양 방위는 서쪽(+)."""
    sp = sun_position(45.0, 37.5)  # 15시
    assert sp["azimuth_deg"] > 0, "오후 태양은 서쪽(방위 +)"
    assert sp["altitude_deg"] > 0, "15시 태양고도 > 0"


# ── 향별 일조시간 ─────────────────────────────────────────────
def test_south_facade_best_daylight():
    """남향 입면이 동지 일조시간 최대·일조권 충족, 북향은 미달."""
    south = orientation_daylight(0.0, 37.5)
    north = orientation_daylight(180.0, 37.5)
    east = orientation_daylight(-90.0, 37.5)
    assert south["direct_sun_hours"] > east["direct_sun_hours"] > 0
    assert south["direct_sun_hours"] > north["direct_sun_hours"]
    assert south["meets_daylight_right"] is True, "남향은 일조권(2h연속/4h총) 충족"
    assert north["meets_2h_continuous"] is False, "북향은 동지 09~15시 연속 2h 불가"


def test_south_meets_continuous_2h():
    """남향은 09~15시 연속 2시간 일조 충족."""
    south = orientation_daylight(0.0, 37.5)
    assert south["longest_continuous_0915_h"] >= 2.0


def test_orientation_scores_8_directions():
    """8방위 평점 — 남향=우수, 북향=불가/미흡."""
    scores = {s["direction"]: s["grade"] for s in orientation_scores(37.5)}
    assert scores["남"] == "우수"
    assert scores["북"] in ("불가", "미흡")


# ── 배치 다각도 최적안 ────────────────────────────────────────
def test_analyze_returns_three_options_and_recommendation():
    """엔진이 3개 배치대안+8방위+최적안+음영을 반환."""
    res = analyze_solar_placement(
        land_area_sqm=3000, zone="제2종일반주거지역", address="서울특별시 강남구",
        priority="balanced",
    )
    assert "error" not in res
    assert len(res["placement_options"]) == 3
    assert len(res["orientation_scores"]) == 8
    assert res["recommended"]["type"] in [o["type"] for o in res["placement_options"]]
    assert res["shadow"]["max_shadow_len_m"] is not None
    # 점수 내림차순 정렬 확인
    scores = [o["score"] for o in res["placement_options"]]
    assert scores == sorted(scores, reverse=True)


def test_priority_daylight_favors_slab():
    """우선순위='daylight'면 남향 비율 최고인 판상형이 최적안."""
    res = analyze_solar_placement(
        land_area_sqm=5000, zone="제3종일반주거지역", address="서울특별시",
        priority="daylight",
    )
    assert res["recommended"]["type"] == "판상형 남향평행", \
        f"일조 우선이면 판상형 최적 — 현재 {res['recommended']['type']}"


def test_priority_density_favors_tower():
    """우선순위='density'면 고밀 탑상형이 유리(판상형보다 점수↑)."""
    res = analyze_solar_placement(
        land_area_sqm=8000, zone="준주거지역", address="서울특별시",
        priority="density",
    )
    by = {o["type"]: o["score"] for o in res["placement_options"]}
    assert by["탑상형(타워)"] >= by["판상형 남향평행"], "밀도 우선이면 탑상형 점수 ≥ 판상형"


def test_green_zone_floor_cap_flows_into_placement():
    """자연녹지(4층 제한)면 엔벨로프 4층이 배치 엔진에 반영(층수 SSOT 일관)."""
    res = analyze_solar_placement(
        land_area_sqm=2000, zone="자연녹지지역", address="경기도",
    )
    assert res["envelope"]["max_floors"] <= 4, "자연녹지는 4층 제한이 배치에도 반영"
