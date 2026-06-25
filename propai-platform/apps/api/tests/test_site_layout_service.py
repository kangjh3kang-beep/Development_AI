"""Stage 4 — 토지모양 기반 배치도(site_layout_service) 결정론 테스트.

폴리곤 buildable footprint(세트백)·그리드 동배치·일조준수·건폐율 캡·yield·정직 경계를 검증.
shapely 필요(가용 환경). 외부 네트워크·DB 불필요(순수 기하).
"""

from __future__ import annotations

import math

import pytest

from app.services.cad.site_layout_service import (
    attach_layout_llm_advice,
    build_site_layout,
    compute_buildable_footprint,
)

_LAT0, _LON0 = 37.5, 127.0


def _rect_parcel(width_m: float, depth_m: float) -> dict:
    """서울(37.5,127.0) 부근 width×depth(m) 직사각 대지 GeoJSON."""
    dlon = width_m / (111_320 * math.cos(math.radians(_LAT0)))
    dlat = depth_m / 110_540
    return {
        "type": "Polygon",
        "coordinates": [[
            [_LON0, _LAT0], [_LON0 + dlon, _LAT0],
            [_LON0 + dlon, _LAT0 + dlat], [_LON0, _LAT0 + dlat], [_LON0, _LAT0],
        ]],
    }


def test_no_polygon_is_honest() -> None:
    out = build_site_layout(parcel_geojson=None, zone_type="제2종일반주거지역")
    assert out["ok"] is False
    assert out["best"] is None
    assert "미확보" in out["honest_notes"][0]


def test_malformed_geojson_is_honest() -> None:
    out = build_site_layout(parcel_geojson={"type": "Nonsense", "coordinates": "bad"})
    assert out["ok"] is False
    assert out["options"] == []


def test_rectangular_layout_produces_buildings() -> None:
    out = build_site_layout(
        parcel_geojson=_rect_parcel(90, 70), zone_type="제3종일반주거지역",
        building_type="공동주택", far_pct=250, bcr_pct=50, land_area_sqm=6300,
    )
    assert out["ok"] is True
    # buildable < parcel(세트백 내측 오프셋).
    assert out["buildable_area_sqm"] < 6300
    best = out["best"]
    assert best["buildings"] >= 1 and best["floors"] >= 1
    # 배치도 GeoJSON FeatureCollection 유효.
    fc = best["buildings_geojson"]
    assert fc["type"] == "FeatureCollection"
    assert len(fc["features"]) == best["buildings"]
    assert fc["features"][0]["geometry"]["type"] == "Polygon"
    # guidance·parcel/buildable geojson 존재.
    assert out["guidance"] and out["parcel_geojson"] and out["buildable_geojson"]


def test_south_aligned_meets_daylight() -> None:
    """남향 정렬(angle 0) 판상은 동지 일조권 충족(meets_daylight_right 키 회귀가드)."""
    out = build_site_layout(
        parcel_geojson=_rect_parcel(100, 80), building_type="공동주택",
        far_pct=250, bcr_pct=50, land_area_sqm=8000, priority="daylight",
    )
    best = out["best"]
    # angle 0 후보가 존재하고 일조권 충족.
    south_opt = next((o for o in out["options"] if o["angle_deg"] == 0.0), None)
    assert south_opt is not None
    assert south_opt["daylight"]["meets_sunlight"] is True
    assert south_opt["daylight"]["direct_sun_hours"] > 4


def test_bcr_caps_dong_count() -> None:
    """건폐율 상한이 동수를 캡한다 — 낮은 bcr은 동수↓·총 바닥면적 ≤ 건폐 budget."""
    out_low = build_site_layout(
        parcel_geojson=_rect_parcel(120, 100), building_type="공동주택",
        far_pct=250, bcr_pct=10, land_area_sqm=12000,
    )
    out_high = build_site_layout(
        parcel_geojson=_rect_parcel(120, 100), building_type="공동주택",
        far_pct=250, bcr_pct=60, land_area_sqm=12000,
    )
    low_b = out_low["best"]["buildings"]
    high_b = out_high["best"]["buildings"]
    assert low_b <= high_b
    # 건폐율 준수: 동 바닥 합 ≤ 건폐 budget(area×bcr/100). 타워 22×22=484.
    assert low_b * 484 <= 12000 * 0.10 + 484  # 캡 + 1동 허용오차


def test_tiny_parcel_setback_collapse_is_honest() -> None:
    """세트백 적용 후 가용 대지 소멸(초소형) → 정직 고지."""
    out = build_site_layout(
        parcel_geojson=_rect_parcel(4, 4), building_type="공동주택",
        far_pct=200, bcr_pct=60, land_area_sqm=16,
    )
    assert out["ok"] is False
    assert any("소멸" in n or "들어가지" in n for n in out["honest_notes"])


def test_priority_changes_score_weights() -> None:
    """우선순위별 점수 가중이 달라진다(동일 배치라도 score 산식 분기)."""
    kwargs = dict(
        parcel_geojson=_rect_parcel(100, 80), building_type="공동주택",
        far_pct=250, bcr_pct=50, land_area_sqm=8000,
    )
    bal = build_site_layout(priority="balanced", **kwargs)["best"]["score"]
    day = build_site_layout(priority="daylight", **kwargs)["best"]["score"]
    den = build_site_layout(priority="density", **kwargs)["best"]["score"]
    # 적어도 한 쌍은 가중 차이로 점수가 다르다(완전 동일이면 산식 미분기 의심).
    assert len({bal, day, den}) >= 2


def test_buildable_footprint_inward_offset() -> None:
    """compute_buildable_footprint는 내측 오프셋(면적 축소)."""
    from shapely.geometry import box

    parcel = box(0, 0, 50, 40)  # 2000㎡
    inner = compute_buildable_footprint(parcel, 3.0)
    assert inner is not None
    assert inner.area < parcel.area
    assert abs(inner.area - 44 * 34) < 1.0  # (50-6)×(40-6)


async def test_llm_advice_noop_when_disabled() -> None:
    """use_llm=False면 기하·결과 불변(LLM 조언 미첨부)."""
    layout = build_site_layout(
        parcel_geojson=_rect_parcel(90, 70), building_type="공동주택",
        far_pct=250, bcr_pct=50, land_area_sqm=6300,
    )
    out = await attach_layout_llm_advice(layout, use_llm=False)
    assert "llm_advice" not in out
    assert out["best"] == layout["best"]
