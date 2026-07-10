"""P0-2(RC2·RC3·RC4) build_integrated_context 최소봉합 — 인접성 + usable 결합 회귀 테스트.

검증 포인트:
  - geometry 보유 다필지가 비인접이면 adjacency.contiguous=False + components(그룹 수).
  - land_category(도로 등) 필지는 usable_confirmed에서 제외되고 land_area_effective_sqm이
    그만큼 줄어든다(gross 는 total_area_sqm 로 하위호환 보존).
  - 연접·정상(비제외) 세트는 land_area_effective_sqm == total_area_sqm(무회귀).

모든 필지에 farPct/bcrPct/farLegalPct/bcrLegalPct를 이미 채워 전달해
_enrich_effective_and_special(외부 API 호출)이 트리거되지 않게 한다(결정론·네트워크 0).
"""
from __future__ import annotations

from app.services.land_intelligence.comprehensive_analysis_service import (
    build_integrated_context,
)


def _square(lon0: float, lat0: float, size: float = 0.001) -> dict:
    lon1, lat1 = lon0 + size, lat0 + size
    return {
        "type": "Polygon",
        "coordinates": [[[lon0, lat0], [lon1, lat0], [lon1, lat1], [lon0, lat1], [lon0, lat0]]],
    }


def _parcel(pnu: str, area: float, geometry: dict | None = None, land_category: str | None = None) -> dict:
    p: dict = {
        "pnu": pnu, "zone_type": "자연녹지지역", "area_sqm": area,
        "farPct": 100.0, "bcrPct": 20.0, "farLegalPct": 100.0, "bcrLegalPct": 20.0,
    }
    if geometry is not None:
        p["geometry"] = geometry
    if land_category is not None:
        p["land_category"] = land_category
    return p


async def test_non_contiguous_parcels_flagged_and_components_counted():
    """서로 멀리 떨어진 두 필지(비인접) — contiguous=False, components=2."""
    parcels = [
        _parcel("A", 500.0, geometry=_square(127.0, 37.0)),
        _parcel("B", 500.0, geometry=_square(128.0, 38.0)),  # ~140km 이상 떨어진 좌표
    ]
    out = await build_integrated_context(parcels)
    assert out is not None
    assert out["adjacency"]["contiguous"] is False
    assert out["adjacency"]["components"] == 2


async def test_contiguous_parcels_flagged_true():
    """맞닿은 두 필지 — contiguous=True, components=1(무회귀 기준값)."""
    parcels = [
        _parcel("A", 500.0, geometry=_square(127.000, 37.000)),
        _parcel("B", 500.0, geometry=_square(127.001, 37.000)),  # 인접(경계 접함)
    ]
    out = await build_integrated_context(parcels)
    assert out is not None
    assert out["adjacency"]["contiguous"] is True
    assert out["adjacency"]["components"] == 1


async def test_geometry_missing_adjacency_is_honest_none():
    """geometry 미보유(2개 미만) — True를 지어내지 않고 None+사유 표기."""
    parcels = [_parcel("A", 500.0), _parcel("B", 500.0)]
    out = await build_integrated_context(parcels)
    assert out is not None
    assert out["adjacency"]["contiguous"] is None
    assert out["adjacency"]["components"] is None
    assert "인접성" in out["adjacency"]["basis"]


async def test_road_land_category_excluded_from_usable_area():
    """지목 '도로' 필지는 usable_confirmed에서 제외되고 land_area_effective_sqm이 감소한다."""
    parcels = [
        _parcel("A", 8066.0, land_category="대"),
        _parcel("B", 100.0, land_category="도로"),
    ]
    out = await build_integrated_context(parcels)
    assert out is not None
    assert out["usable"]["confirmed_sqm"] == 8066.0
    assert out["usable"]["excluded_sqm"] == 100.0
    assert out["land_area_effective_sqm"] == 8066.0
    # gross(total_area_sqm)는 하위호환 그대로 보존(additive — 삭제/변경 없음).
    assert out["total_area_sqm"] == 8166.0


async def test_no_exclusion_land_area_effective_equals_gross():
    """제외 사유 없는 정상 세트는 land_area_effective_sqm == total_area_sqm(무회귀)."""
    parcels = [_parcel("A", 500.0, land_category="대"), _parcel("B", 300.0, land_category="대")]
    out = await build_integrated_context(parcels)
    assert out is not None
    assert out["land_area_effective_sqm"] == out["total_area_sqm"] == 800.0
