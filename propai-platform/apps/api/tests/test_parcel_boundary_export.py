"""구획도 export(GeoJSON·PNG) 검증 — P3 다필지 구획도 다운로드.

parcel_boundaries() 결과(features+merged_geometry)를 다운로드 산출물로 변환하는 직렬화/렌더.
"""
from app.services.land_intelligence.parcel_boundary_export import (
    export_geojson, export_png, zone_fill,
)

# 합성 result(2필지 인접 사각형 + 통합 외곽선) — parcel_boundaries() 반환 형태.
_SQ1 = {"type": "Polygon", "coordinates": [[[126.97, 37.57], [126.971, 37.57],
                                            [126.971, 37.571], [126.97, 37.571], [126.97, 37.57]]]}
_SQ2 = {"type": "Polygon", "coordinates": [[[126.971, 37.57], [126.972, 37.57],
                                            [126.972, 37.571], [126.971, 37.571], [126.971, 37.57]]]}
_MERGED = {"type": "Polygon", "coordinates": [[[126.97, 37.57], [126.972, 37.57],
                                               [126.972, 37.571], [126.97, 37.571], [126.97, 37.57]]]}
_RESULT = {
    "features": [
        {"pnu": "1" * 19, "address": "서울 종로구 사직동 1-1", "area_sqm": 330,
         "zone_type": "제2종일반주거지역", "jimok": "대", "geometry": _SQ1},
        {"pnu": "2" * 19, "address": "서울 종로구 사직동 1-2", "area_sqm": 245,
         "zone_type": "제2종일반주거지역", "jimok": "대", "geometry": _SQ2},
    ],
    "merged_geometry": _MERGED,
    "total_area_sqm": 575, "parcel_count": 2,
}


def test_geojson_feature_collection():
    """필지 2개 + 통합 외곽선 = 3 features, properties 포함."""
    gj = export_geojson(_RESULT)
    assert gj["type"] == "FeatureCollection"
    assert len(gj["features"]) == 3  # 2 필지 + merged
    p0 = gj["features"][0]["properties"]
    assert p0["index"] == 1 and p0["area_sqm"] == 330
    assert abs(p0["area_pyeong"] - 99.8) < 1.0
    assert p0["address"] == "서울 종로구 사직동 1-1"
    merged = gj["features"][-1]
    assert merged["properties"]["role"] == "merged_boundary"
    assert gj["properties"]["total_area_sqm"] == 575


def test_geojson_skips_missing_geometry():
    """geometry 없는 필지는 제외(가짜 도형 금지)."""
    res = {"features": [{"pnu": "x", "area_sqm": 100, "geometry": None}],
           "merged_geometry": None, "total_area_sqm": 100, "parcel_count": 1}
    gj = export_geojson(res)
    assert gj["features"] == []


def test_png_renders_bytes():
    """PNG 렌더 → 유효한 PNG 바이트(매직 헤더)."""
    png = export_png(_RESULT)
    assert isinstance(png, bytes) and len(png) > 1000
    assert png[:8] == b"\x89PNG\r\n\x1a\n", "PNG 매직 헤더"


def test_png_single_parcel():
    """단일 필지(merged 없음)도 렌더."""
    res = {"features": [_RESULT["features"][0]], "merged_geometry": None,
           "total_area_sqm": 330, "parcel_count": 1}
    png = export_png(res)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"


def test_zone_fill_colors():
    """용도지역별 색상 매핑 + 미상 폴백."""
    assert zone_fill("제2종일반주거지역") == "#C0D8B0"
    assert zone_fill("자연녹지지역") == "#90C890"
    assert zone_fill(None) == "#cccccc"
    assert zone_fill("알수없는지역") == "#cbd5e1"
