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
        # ★R1 MEDIUM-3 회귀락: "종"만으로 걸리면 **주거가 아닌** 용도지역에 법적 금지구역을
        #   칠한다. 이 둘은 종전 구현에서 True였다.
        ("제2종근린생활시설", False), ("제2종지구단위계획구역", False), ("제3종", False),
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
    """부정형 필지에서도 **열마다 자기 북측 경계**를 따른다(전역 maxy 한 줄이 아니다)."""
    from shapely.geometry import Polygon

    # 북쪽이 뾰족한 오각형 — 모든 열이 d보다 두꺼우므로 밴드는 '열별 상단 d'의 합이다.
    parcel = Polygon([(0, 0), (100, 0), (100, 60), (50, 100), (0, 60)])
    band, d = compute_north_light_band(parcel, height_m=40.0)
    assert band is not None
    assert band.difference(parcel).area == pytest.approx(0.0, abs=1e-6)
    width = parcel.bounds[2] - parcel.bounds[0]
    assert band.area == pytest.approx(d * width, rel=0.02)
    # 밴드 아래 경계가 **평평하지 않다** = 전역 maxy 직선 근사가 아니라는 직접 증거.
    assert band.bounds[1] < parcel.bounds[3] - d


def test_band_covers_every_arm_of_an_L_shaped_parcel():
    """★R1 HIGH-3 회귀락 — L자 필지에서 **각 팔이 자기 북측 경계** 기준으로 밴드를 갖는다.

    종전 구현은 전역 maxy 한 줄로 띠를 만들어, 북으로 뻗은 팔에만 밴드가 생기고 자기 정북
    경계가 더 남쪽인 다른 팔에는 **0**이었다(위치가 무관하고 방향이 비보수적).
    """
    from shapely.geometry import Polygon, box

    # 서쪽 팔은 y=30까지, 동쪽 팔의 북측 경계는 y=-10.
    parcel = Polygon([(0, -35), (100, -35), (100, -10), (50, -10), (50, 30), (0, 30)])
    # 이격(20m)이 동쪽 팔 두께(25m)보다 **작은** 높이를 쓴다 — 그래야 "팔 상단에만 붙는가"를
    # 관측할 수 있다(이격이 더 크면 팔 전체가 금지가 되어 위치 판정이 공허해진다).
    band, d = compute_north_light_band(parcel, height_m=40.0)
    assert d == pytest.approx(20.0)
    assert band is not None
    assert band.difference(parcel).area == pytest.approx(0.0, abs=1e-6)

    # ★공유 모서리(x=50)를 피해 팔 **내부**로 좁힌다 — 경계선에서 0면적 선분이 섞이면
    #   bounds가 옆 팔의 값을 물어와 엉뚱한 것을 재게 된다(실제로 한 번 그렇게 틀렸다).
    west = band.intersection(box(-1, -40, 49.5, 40))
    east = band.intersection(box(50.5, -40, 101, 40))
    assert west.area > 0, "서쪽 팔에 밴드가 없다"
    assert east.area > 0, "★동쪽 팔에 밴드가 0 — 자기 북측 경계를 무시한다(전역 maxy 회귀)"
    # 각 팔은 **자기** 북단에 붙는다(동쪽 -10, 서쪽 30).
    assert east.bounds[3] == pytest.approx(-10.0, abs=1e-6)
    assert west.bounds[3] == pytest.approx(30.0, abs=1e-6)


def test_thin_column_becomes_fully_forbidden():
    """열 두께가 이격보다 얇으면 그 열은 **통째로** 금지다(그 높이로는 못 짓는다)."""
    from shapely.geometry import box

    parcel = box(0, 0, 100, 10)  # 남북 폭 10m
    band, d = compute_north_light_band(parcel, height_m=40.0)  # d = 20m > 10m
    assert d > 10.0
    assert band is not None
    assert band.area == pytest.approx(parcel.area, rel=1e-6)


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


# ── ★R1 HIGH-1 회귀락: 밴드는 장식이 아니라 **배치 제약**이다 ─────────────────────
import math  # noqa: E402

from shapely.geometry import shape  # noqa: E402


def _rect_parcel(width_m: float, depth_m: float, lat0: float = 37.5, lon0: float = 127.0):
    """동서 width_m × 남북 depth_m 직사각 필지(위경도)."""
    dy = depth_m / 110540.0
    dx = width_m / (111320.0 * math.cos(math.radians(lat0)))
    return {
        "type": "Polygon",
        "coordinates": [[
            [lon0, lat0], [lon0 + dx, lat0], [lon0 + dx, lat0 + dy], [lon0, lat0 + dy], [lon0, lat0],
        ]],
    }


def _worst_overlap_pct(result) -> float:
    """★R2 HIGH-3 봉합 — **공허 통과를 구조적으로 불가능**하게 만든다.

    종전엔 options가 비거나 밴드가 null이면 조용히 0.0을 돌려줘, 배치가 사라지거나 밴드가
    꺼지는 순간 이 불변식이 **무음 소멸**했다. 가설이 아니다: 이 PR 자체가 어떤 필지를
    `ok:True → ok:false`로 바꿨다. 관측 대상이 실재함을 먼저 단언한다.
    """
    options = result.get("options") or []
    assert options, "옵션이 없어 겹침을 관측할 수 없다(불변식이 공허해진다)"
    assert result.get("north_light", {}).get("applies") is True, "정북 미적용 픽스처로는 잠기지 않는다"
    banded = 0
    dongs = 0
    worst = 0.0
    for o in options:
        band = shape(o["north_light_band_geojson"]) if o.get("north_light_band_geojson") else None
        if band is None:
            continue
        banded += 1
        total = viol = 0.0
        for f in (o.get("buildings_geojson") or {}).get("features", []):
            g = shape(f["geometry"])
            total += g.area
            viol += g.intersection(band).area
            dongs += 1
        if total:
            worst = max(worst, 100.0 * viol / total)
    assert banded > 0, "밴드가 실린 대안이 하나도 없다(관측 대상 부재)"
    assert dongs > 0, "배치된 동이 하나도 없다(겹침이 공허하게 0이 된다)"
    return worst


# ★R2 HIGH-3: 종전 픽스처 4개는 **리뷰어가 준 케이스**뿐이었다(전부 이미 고쳐진 것들).
#   내 탐색으로 찾은 케이스가 없어 진동(60×90)·크래시(100×24 far400)를 스스로 못 찾았다.
#   → 스윕에서 실제로 문제를 냈던 형상을 픽스처에 넣는다.
@pytest.mark.parametrize(
    "width,depth,far",
    [
        (120.0, 120.0, 200.0), (40.0, 60.0, 200.0), (100.0, 60.0, 300.0), (60.0, 100.0, 250.0),
        (60.0, 90.0, 200.0),    # ★R2 H2 진동 케이스(겹침 33.75%가 살아남던 형상)
        (80.0, 40.0, 250.0), (140.0, 30.0, 200.0), (60.0, 120.0, 500.0),
    ],
)
def test_no_building_sits_inside_the_forbidden_band(width, depth, far):
    """★★ 밴드 안에는 **단 한 동도** 앉지 않는다.

    종전엔 밴드를 계산해 응답에 얹기만 하고 배치로 되먹이지 않아, 같은 응답이 "이 높이로
    건축 불가"라고 칠한 자리에 그 높이의 건물을 그렸다(실측 겹침 80%). 화면은 그 위에
    "일조권 충족"이라고 썼다 — **밴드가 없던 때보다 나쁜 상태**(플랫폼이 자기 권장안의
    위법을 그려놓고 적법하다고 말한다). 이 불변식이 그 상태로의 회귀를 막는다.
    """
    r = build_site_layout(
        parcel_geojson=_rect_parcel(width, depth), land_area_sqm=width * depth,
        far_pct=far, bcr_pct=60, zone_type="제3종일반주거지역", building_type="아파트",
    )
    assert _worst_overlap_pct(r) == pytest.approx(0.0, abs=0.01), (
        "권장 배치가 정북 금지 띠를 침범한다 — 밴드가 배치로 되먹여지지 않는다"
    )


def test_shallow_parcel_says_why_instead_of_illegal_layout():
    """★이격을 확보하면 동이 안 들어가는 얕은 필지는 **위법 배치 대신 사유**를 말한다."""
    r = build_site_layout(
        parcel_geojson=_rect_parcel(100.0, 24.0), land_area_sqm=2400,
        far_pct=300, bcr_pct=60, zone_type="제3종일반주거지역", building_type="아파트",
    )
    assert r["ok"] is False
    assert not (r.get("options") or [])
    assert any("정북 일조 이격을 확보하면" in n for n in r["honest_notes"]), r["honest_notes"]


def test_non_applying_zone_keeps_previous_placement_behaviour():
    """★무회귀: 정북 미적용 용도지역에서는 배치가 종전과 같다(밴드 차감 없음)."""
    parcel = _rect_parcel(100.0, 24.0)
    r = build_site_layout(
        parcel_geojson=parcel, land_area_sqm=2400, far_pct=300, bcr_pct=60,
        zone_type="일반상업지역", building_type="아파트",
    )
    assert r["ok"] is True, "미적용 지역인데 배치가 사라졌다 — 밴드가 잘못 차감됐다"
    assert r["north_light"]["applies"] is False


def test_band_geometry_differs_per_option_not_just_the_number():
    """★B1 회귀락 — 대안별로 **기하 자체가** 달라야 한다(숫자만 다르면 지도는 틀린 띠를 그린다)."""
    r = build_site_layout(
        parcel_geojson=_rect_parcel(120.0, 120.0), land_area_sqm=14400,
        far_pct=200, bcr_pct=60, zone_type="제2종일반주거지역", building_type="아파트",
    )
    by_h: dict[float, float] = {}
    for o in r["options"]:
        band = shape(o["north_light_band_geojson"])
        by_h.setdefault(o["height_m"], band.area)
    if len(by_h) < 2:
        pytest.skip("이 픽스처에서는 대안 높이가 모두 같아 기하 차이를 관측할 수 없다")
    assert len(set(round(a, 9) for a in by_h.values())) > 1, (
        f"높이가 다른데 밴드 **면적**이 같다 = 기하가 고정 높이로 계산된다: {by_h}"
    )


def test_band_width_matches_the_reported_setback():
    """★B3 회귀락 — 지도 띠의 **폭**과 패널이 표시하는 **수치**가 묶여 있다.

    (단위 테스트에만 있으면 통합 응답에서 둘이 갈라져도 통과한다.)
    """
    r = build_site_layout(
        parcel_geojson=_rect_parcel(120.0, 120.0), land_area_sqm=14400,
        far_pct=200, bcr_pct=60, zone_type="제2종일반주거지역", building_type="아파트",
    )
    for o in r["options"]:
        band = shape(o["north_light_band_geojson"])
        # 직사각 필지이므로 밴드 폭(위도 범위)을 미터로 환산하면 표시 이격과 같아야 한다.
        width_m = (band.bounds[3] - band.bounds[1]) * 110540.0
        assert width_m == pytest.approx(o["north_light_setback_m"], rel=0.02), (
            f"{o['kind']}: 띠 폭 {width_m:.1f}m vs 표시 {o['north_light_setback_m']}m"
        )


def test_unknown_zone_note_states_why_band_is_missing():
    """★B6 회귀락 — 판정 불가 사유가 **honest_notes로도** 나간다(화면이 그대로 고지한다)."""
    r = build_site_layout(
        parcel_geojson=_rect_parcel(120.0, 120.0), land_area_sqm=14400,
        far_pct=200, bcr_pct=60, zone_type="", building_type="아파트",
    )
    assert any("판정하지 못했습니다" in n for n in r["honest_notes"]), r["honest_notes"]


@pytest.mark.parametrize(
    "width,depth,far,bcr",
    [(100.0, 24.0, 400.0, 60.0), (100.0, 24.0, 500.0, 60.0), (80.0, 16.0, 300.0, 50.0),
     (40.0, 16.0, 200.0, 60.0), (160.0, 20.0, 500.0, 60.0)],
)
def test_shallow_parcel_never_crashes(width, depth, far, bcr):
    """★R2 HIGH-1 회귀락 — 금지 띠를 빼면 배치 영역이 **통째로 비는** 필지에서 죽지 않는다.

    빈 geometry의 `centroid.x`는 shapely가 `GEOSException: getX called on empty Point`로
    던지고, 라우터가 무가드라 **프로덕션 500**이 됐다(스윕 910건 중 62건). 배치 불가는
    예외가 아니라 **빈 결과 + 사유**여야 한다.
    """
    r = build_site_layout(
        parcel_geojson=_rect_parcel(width, depth), land_area_sqm=width * depth,
        far_pct=far, bcr_pct=bcr, zone_type="제3종일반주거지역", building_type="아파트",
    )
    assert isinstance(r, dict) and "ok" in r
    if not r["ok"]:
        assert r["honest_notes"], "불가인데 사유가 없다"


def test_openness_denominator_excludes_the_forbidden_band():
    """★R2 MEDIUM-3 회귀락 — 오픈스페이스 분모가 **금지 띠를 뺀 영역**이다.

    buildable 전체로 나누면 지을 수 없는 띠까지 '오픈스페이스'로 계상돼 과대표시된다.
    (같은 필지를 정북 적용/미적용으로 비교해, 적용 시 분모가 줄어 openness가 달라짐을 본다.)
    """
    kw = dict(
        parcel_geojson=_rect_parcel(120.0, 120.0), land_area_sqm=14400,
        far_pct=200, bcr_pct=60, building_type="아파트",
    )
    applied = build_site_layout(zone_type="제2종일반주거지역", **kw)
    assert applied["ok"] and applied["north_light"]["applies"] is True
    for o in applied["options"]:
        band = shape(o["north_light_band_geojson"])
        # 분모가 buildable 전체라면 금지 띠 면적만큼 openness가 부풀려진다.
        # 실제 분모(배치영역)로 계산한 상한을 넘지 않아야 한다.
        assert o["openness_pct"] <= 100.0
        assert band.area > 0
    # 미적용 지역은 띠가 없으므로 분모가 buildable 전체다(대조군).
    plain = build_site_layout(zone_type="일반상업지역", **kw)
    assert plain["north_light"]["applies"] is False


def test_oscillating_parcel_is_rescued_not_dropped():
    """★R2 HIGH-2 회귀락(refit) — 진동으로 비수렴한 안을 **확정 층수로 재배치해 구제**한다.

    이 형상(60×90·FAR200)은 place_area가 3969↔3240으로 2-주기 진동해 `range(6)`이 소진되던
    케이스다(리뷰어 실측: 겹침 33.75%). 두 안전장치가 있다 —
      ① 재배치(refit): 확정 층수의 띠로 다시 앉혀 **구제**한다(대안이 살아남는다)
      ② 최종 정합 검증: 그래도 침범하면 그 안을 **폐기**한다(위법 배치를 목록에 안 올린다)
    ①이 없으면 ②가 폐기해 대안 수가 줄어든다 — 그 차이를 잠근다.
    """
    r = build_site_layout(
        parcel_geojson=_rect_parcel(60.0, 90.0), land_area_sqm=5400,
        far_pct=200, bcr_pct=60, zone_type="제3종일반주거지역", building_type="아파트",
    )
    assert r["ok"] is True
    assert _worst_overlap_pct(r) == pytest.approx(0.0, abs=0.01)
    assert len(r["options"]) >= 3, (
        f"진동 케이스가 구제되지 않고 폐기됐다(대안 {len(r['options'])}개) — 재배치가 빠졌다"
    )


def test_openness_denominator_is_the_actual_placeable_area():
    """★R2 MEDIUM-3 회귀락 — 오픈스페이스 분모가 **금지 띠를 뺀 배치 영역**이다.

    응답에 있는 기하만으로 검산한다: (buildable − band) 대비 동 면적 비율.
    위경도 면적이지만 **비율**이라 투영 계수가 상쇄돼 그대로 비교 가능하다.
    분모가 buildable 전체면 지을 수 없는 띠까지 오픈스페이스로 계상돼 값이 커진다.
    """
    r = build_site_layout(
        parcel_geojson=_rect_parcel(120.0, 120.0), land_area_sqm=14400,
        far_pct=200, bcr_pct=60, zone_type="제2종일반주거지역", building_type="아파트",
    )
    buildable = shape(r["buildable_geojson"])
    checked = 0
    for o in r["options"]:
        band = shape(o["north_light_band_geojson"])
        place_area = buildable.difference(band)
        covered = sum(
            shape(f["geometry"]).area for f in (o["buildings_geojson"] or {}).get("features", [])
        )
        if place_area.area <= 0 or covered <= 0:
            continue
        expected = round(max(0.0, (place_area.area - covered) / place_area.area * 100.0), 1)
        assert o["openness_pct"] == pytest.approx(expected, abs=1.5), (
            f"{o['kind']}: openness {o['openness_pct']} vs 배치영역 기준 {expected} "
            "— 분모가 buildable 전체(금지 띠 포함)로 보인다"
        )
        checked += 1
    assert checked > 0, "검산한 대안이 없다(공허 통과)"
