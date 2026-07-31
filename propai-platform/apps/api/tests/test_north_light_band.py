"""정북 일조 이격 밴드(W3-b) — site_layout_service의 north_light 계약.

★왜 이 웨이브가 있나: 계획서 W3는 "일조 사선 + 배치 3안"인데 배치만 인도되고 **일조 밴드가
  빠진 채** 완료로 보고됐다(W4 회고에서 적발). 그 갭을 메운다.

★무엇을 잠그는가:
  ① 적용 용도지역(전용·일반주거)에서만 밴드가 생긴다 — 그 밖에서는 **만들지 않고 사유를 말한다**
     (빈 밴드를 그리면 "제약 없음"으로 오독된다).
  ② 용도지역 **판정 불가**(빈 문자열)면 적용하지 않는다 — 모르는데 그리면 없는 제약을 보여준다.
  ③ 이격 거리가 공용 산식 SSOT와 일치한다(여기서 다시 구현하지 않았다는 증거).
  ④ 밴드는 **선택 대안의 높이**에 따라 달라진다(높이가 높을수록 넓다).
  ⑤ 밴드는 필지 **안**에 있고 **북쪽**에 붙는다(엉뚱한 데 그리지 않는다).
  ⑥ 한계·사유가 honest_notes로 나간다(화면이 그대로 고지하는 계약).
"""
from __future__ import annotations

import pytest

from app.services.cad.site_layout_service import (
    build_site_layout,
    compute_north_light_band,
    north_light_applies,
)

# 약 100m × 100m 정사각 필지(서울 근방). d는 위경도 도 단위.
_D = 0.0009
PARCEL = {
    "type": "Polygon",
    "coordinates": [[
        [127.0, 37.5], [127.0 + _D, 37.5], [127.0 + _D, 37.5 + _D], [127.0, 37.5 + _D], [127.0, 37.5],
    ]],
}


def _layout(zone_type: str):
    return build_site_layout(
        parcel_geojson=PARCEL, land_area_sqm=10000, far_pct=200, bcr_pct=60,
        zone_type=zone_type, building_type="아파트",
    )


# ── ① ② 적용 범위 ────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "zone,expected",
    [
        ("제2종일반주거지역", True), ("제1종전용주거지역", True), ("3R", True), ("2r", True),
        ("일반상업지역", False), ("준공업지역", False), ("자연녹지지역", False),
        ("", False), ("   ", False),
    ],
)
def test_north_light_applies_scope(zone, expected):
    assert north_light_applies(zone) is expected


def test_unknown_zone_does_not_draw_band():
    """★판정 불가면 **적용하지 않는다** — 모르는데 그리면 없는 제약을 보여준다."""
    r = _layout("")
    assert r["north_light"]["applies"] is False
    assert "판정할 수 없습니다" in r["north_light"]["reason"]
    assert all(o["north_light_band_geojson"] is None for o in r["options"])
    assert all(o["north_light_setback_m"] is None for o in r["options"])


def test_non_sunlight_zone_says_why_instead_of_empty_band():
    """★밴드를 안 그리는 것으로 끝내지 않는다 — 사유를 말한다(빈 밴드=제약 없음 오독 방지)."""
    r = _layout("일반상업지역")
    assert r["north_light"]["applies"] is False
    assert "전용·일반주거지역에만" in r["north_light"]["reason"]
    assert any("전용·일반주거지역에만" in n for n in r["honest_notes"])


# ── ③ 산식 SSOT 일치 ─────────────────────────────────────────────────────────
@pytest.mark.parametrize("height", [3.0, 9.9, 10.0, 10.1, 30.0, 48.0])
def test_setback_matches_shared_formula(height):
    """★공용 산식 SSOT와 일치 — 여기서 다시 구현했다면 값이 갈라진다(법 개정 시 한쪽만 바뀜)."""
    from shapely.geometry import box

    from app.services.common.sunlight_setback import required_north_setback_m

    _, d = compute_north_light_band(box(0, 0, 100, 100), height_m=height)
    assert d == pytest.approx(required_north_setback_m(height))


def test_setback_has_the_legal_discontinuity_at_10m():
    """10m 임계에서 1.5m → 5m로 **도약**한다(법조문의 성질 — 매끄럽게 만들면 틀린다)."""
    from shapely.geometry import box

    _, low = compute_north_light_band(box(0, 0, 100, 100), height_m=10.0)
    _, high = compute_north_light_band(box(0, 0, 100, 100), height_m=10.1)
    assert low == pytest.approx(1.5)
    assert high > 5.0


# ── ④ 높이 의존 ──────────────────────────────────────────────────────────────
def test_band_grows_with_height():
    """높을수록 이격이 커지므로 밴드도 넓어진다(면적 단조 증가)."""
    from shapely.geometry import box

    parcel = box(0, 0, 100, 100)
    b_low, _ = compute_north_light_band(parcel, height_m=12.0)
    b_high, _ = compute_north_light_band(parcel, height_m=40.0)
    assert b_low is not None and b_high is not None
    assert b_high.area > b_low.area


# ── ⑤ 기하 정합 ──────────────────────────────────────────────────────────────
def test_band_is_inside_parcel_and_on_the_north_edge():
    """★밴드는 필지 **안**에 있고 **북쪽**에 붙는다 — 엉뚱한 데 그리면 설계사를 오도한다."""
    from shapely.geometry import box

    parcel = box(0, 0, 100, 100)
    band, d = compute_north_light_band(parcel, height_m=40.0)
    assert band is not None
    # 필지 밖으로 새지 않는다.
    assert band.difference(parcel).area == pytest.approx(0.0, abs=1e-6)
    # 북쪽 끝(maxy)에 접하고, 남쪽 끝(miny)에는 닿지 않는다.
    assert band.bounds[3] == pytest.approx(parcel.bounds[3])
    assert band.bounds[1] > parcel.bounds[1]
    # 폭이 이격 거리와 같다.
    assert (band.bounds[3] - band.bounds[1]) == pytest.approx(d, rel=1e-6)


def test_band_follows_irregular_parcel_shape():
    """부정형 필지에서도 필지 형상을 따른다(직사각형으로 뭉개지 않는다)."""
    from shapely.geometry import Polygon

    # 북쪽이 뾰족한 오각형.
    parcel = Polygon([(0, 0), (100, 0), (100, 60), (50, 100), (0, 60)])
    band, d = compute_north_light_band(parcel, height_m=40.0)
    assert band is not None
    assert band.difference(parcel).area == pytest.approx(0.0, abs=1e-6)
    # 뾰족한 북단이라 밴드 면적이 '폭 × 전체 너비'보다 **작다**(직사각 근사가 아니라는 증거).
    assert band.area < d * (parcel.bounds[2] - parcel.bounds[0])


def test_band_none_when_parcel_missing():
    """필지가 없으면 만들지 않는다(던지지 않는다)."""
    band, d = compute_north_light_band(None, height_m=40.0)
    assert band is None and d == 0.0


# ── ⑥ 통합: 응답 계약 ────────────────────────────────────────────────────────
def test_layout_response_carries_band_and_limits():
    """★적용 용도지역에서는 대안별 밴드가 실리고, 근사 한계가 note로 나간다."""
    r = _layout("제2종일반주거지역")
    assert r["ok"] is True
    assert r["north_light"]["applies"] is True
    assert r["north_light"]["reason"] is None
    assert "북쪽 끝 직선으로 근사" in r["north_light"]["boundary_approximation"]
    assert any("북쪽 끝 직선으로 근사" in n for n in r["honest_notes"])

    for o in r["options"]:
        assert o["north_light_band_geojson"] is not None, o["kind"]
        assert o["north_light_setback_m"] > 0
        assert o["north_light_band_geojson"]["type"] in ("Polygon", "MultiPolygon")


def test_band_is_per_option_not_global():
    """★대안마다 높이가 다르면 이격도 달라야 한다 — 전역 1개면 토글 시 틀린 밴드가 남는다."""
    r = _layout("제2종일반주거지역")
    by_height = {o["height_m"]: o["north_light_setback_m"] for o in r["options"]}
    if len(by_height) > 1:
        assert len(set(by_height.values())) > 1, (
            f"높이가 다른데 이격이 같다(전역 계산 의심): {by_height}"
        )
    else:
        pytest.skip("이 픽스처에서는 대안 높이가 모두 같아 대안별 차이를 관측할 수 없다")
