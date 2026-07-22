"""W2-5 ParcelGraph → /zoning/integrated-analysis 배선 회귀(additive) — TDD.

검증 포인트:
  · 응답에 신규 "parcel_graph" 필드가 additive로 추가된다(기존 키·값은 무회귀).
  · geometry 보유 2필지(인접) — component_count=1, articulation/critical 정보 포함.
  · geometry 미보유 — status="ok"(그래프는 비었지만 실패 아님) + geometry_unknown_pnus로
    정직 표기(간선 날조 없음). 기존 응답 표면(adjacency 등)은 전혀 손상되지 않는다.
  · 그래프 산출 자체가 예외를 던져도 통합집계(integrated/adjacency 등 기존 필드)는 손상되지
    않고 parcel_graph만 "unavailable"로 degrade한다.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio


def _square(lon0: float, lat0: float, size: float = 0.001) -> dict:
    lon1, lat1 = lon0 + size, lat0 + size
    return {
        "type": "Polygon",
        "coordinates": [[[lon0, lat0], [lon1, lat0], [lon1, lat1], [lon0, lat1], [lon0, lat0]]],
    }


async def _run(monkeypatch, parcels):
    import apps.api.routers.auto_zoning as az
    from app.services.feasibility.feasibility_service_v2 import FeasibilityServiceV2
    from apps.api.app.services.land_intelligence.parcel_excel_service import ParcelExcelService

    async def _passthrough_enrich(self, items, with_building=True):
        return [dict(p) for p in items]

    async def _noop_enrich_effective(enriched):
        return None

    async def _fake_top3(self, **kwargs):
        return {"recommendations": [], "all_results": []}

    monkeypatch.setattr(ParcelExcelService, "enrich_parcel_list", _passthrough_enrich)
    monkeypatch.setattr(az, "_enrich_effective_and_special", _noop_enrich_effective)
    monkeypatch.setattr(FeasibilityServiceV2, "auto_recommend_top3", _fake_top3)

    req = az.IntegratedAnalysisRequest(parcels=parcels, use_llm=False)
    return await az.integrated_analysis(req)


async def test_parcel_graph_field_present_and_additive_with_geometry(monkeypatch):
    parcels = [
        {"pnu": "P-A", "address": "A", "land_category": "대", "zone_type": "자연녹지지역",
         "area_sqm": 500, "_far_eff": 80.0, "_bcr_eff": 20.0, "_far_legal": 100, "_bcr_legal": 20,
         "geometry": _square(127.000, 37.000), "road_contact": True},
        {"pnu": "P-B", "address": "B", "land_category": "대", "zone_type": "자연녹지지역",
         "area_sqm": 500, "_far_eff": 80.0, "_bcr_eff": 20.0, "_far_legal": 100, "_bcr_legal": 20,
         "geometry": _square(127.001, 37.000), "road_contact": False},
    ]
    result = await _run(monkeypatch, parcels)

    # 기존 표면 무회귀(값 그대로 유지).
    assert result["integrated"]["blended_far_eff_pct"] == 80.0
    assert result["dominant_zone"] == "자연녹지지역"

    pg = result["parcel_graph"]
    assert pg["status"] == "ok"
    assert pg["component_count"] == 1
    assert pg["geometry_unknown_pnus"] == []
    assert "P-A" in pg["landlocked_risk"]["confirmed_pnus"] or pg["landlocked_risk"]["confirmed_pnus"] == []
    assert "n_minus_1" in pg and "P-A" in pg["n_minus_1"]


async def test_parcel_graph_honest_unknown_without_geometry(monkeypatch):
    """geometry 미보유 세트 — parcel_graph.status는 'ok'(실패 아님)이나 그래프는 비어 UNKNOWN.

    기존 adjacency(별도 표면, _parcel_adjacency 기반)는 이 배선과 무관하게 그대로 동작해야 한다
    (무회귀 — parcel_graph 신설이 기존 인접성 판정 표면을 대체/훼손하지 않는다).
    """
    parcels = [
        {"pnu": "P-A", "address": "A", "land_category": "대", "zone_type": "자연녹지지역",
         "area_sqm": 500, "_far_eff": 80.0, "_bcr_eff": 20.0, "_far_legal": 100, "_bcr_legal": 20},
        {"pnu": "P-B", "address": "B", "land_category": "대", "zone_type": "자연녹지지역",
         "area_sqm": 500, "_far_eff": 80.0, "_bcr_eff": 20.0, "_far_legal": 100, "_bcr_legal": 20},
    ]
    result = await _run(monkeypatch, parcels)

    # 기존 adjacency 표면 — geometry 없음 → None(정직, 무회귀 — 이 필드는 parcel_graph 배선과 무관).
    assert result["adjacency"]["contiguous"] is None

    pg = result["parcel_graph"]
    assert pg["status"] == "ok"
    assert sorted(pg["geometry_unknown_pnus"]) == ["P-A", "P-B"]
    assert pg["component_count"] == 0
    assert pg["articulation_points"] == []


async def test_parcel_graph_failure_degrades_without_damaging_integrated_block(monkeypatch):
    """parcel_graph 산출 자체가 예외를 던져도 integrated/adjacency 등 기존 집계는 손상되지 않는다."""

    def _boom(parcels):
        raise RuntimeError("의도된 실패")

    monkeypatch.setattr("app.services.zoning.parcel_graph.build_parcel_graph", _boom)

    parcels = [
        {"pnu": "P-A", "address": "A", "land_category": "대", "zone_type": "자연녹지지역",
         "area_sqm": 500, "_far_eff": 80.0, "_bcr_eff": 20.0, "_far_legal": 100, "_bcr_legal": 20},
        {"pnu": "P-B", "address": "B", "land_category": "대", "zone_type": "자연녹지지역",
         "area_sqm": 500, "_far_eff": 80.0, "_bcr_eff": 20.0, "_far_legal": 100, "_bcr_legal": 20},
    ]
    result = await _run(monkeypatch, parcels)

    assert result["integrated"]["blended_far_eff_pct"] == 80.0  # 기존 집계 무손상
    assert result["parcel_graph"]["status"] == "unavailable"
