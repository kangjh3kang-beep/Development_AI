"""★/zoning/parcel-boundaries 실효한도 SSOT 수렴 회귀 테스트(7번째 표면).

배경: routers/auto_zoning.py의 parcel_boundaries()가 integrated_analysis.effective_bcr_pct/
effective_far_pct를 법정상한(zone_limits.max_*_pct)으로 면적가중해 산출했다 — 이미 SSOT
(far_tier_service.calc_effective_far)로 단일화된 6표면(규제·인허가·90초진단·파이프라인·수지·
종합, tests/test_far_cross_surface_parity.py)과 달리, 자연녹지 등 구조상한(건폐율×층수) 대상
용도지역에서 법정상한(100%)을 그대로 노출해 과대표시했다.

수정: _enrich_effective_and_special(공용헬퍼)로 필지별 실효값을 부착 후, /zoning/integrated-analysis
와 동일한 순수함수 _aggregate_integrated_zoning으로 면적가중 집계한다(로직 복제 없음).

hermetic: 외부 I/O(VWorld 지적/토지특성/용도지구, 건축물대장, 조례조회)만 mock — calc_effective_far와
집계 로직은 실물을 태운다.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio

_PNU = "4146025021100010000"
_GEOMETRY = {
    "type": "Polygon",
    "coordinates": [[[127.1, 37.3], [127.1001, 37.3], [127.1001, 37.3001],
                      [127.1, 37.3001], [127.1, 37.3]]],
}


def _stub_external_io(monkeypatch):
    """VWorld·건축물대장·조례 조회를 hermetic 대역(자연녹지 1000㎡ 단일필지)."""
    import apps.api.routers.auto_zoning as az
    from apps.api.app.services.external_api.building_registry_service import (
        BuildingRegistryService,
    )
    from apps.api.app.services.external_api.vworld_service import VWorldService
    from apps.api.app.services.land_intelligence.ordinance_service import OrdinanceService

    async def _fake_land_info(self, pnu):  # noqa: ANN001
        return {"geometry": _GEOMETRY, "properties": {"area": 1000.0}}

    async def _fake_land_characteristics(self, pnu):  # noqa: ANN001
        return {
            "area_sqm": 1000.0, "zone_type": "자연녹지지역", "zone_type_2": None,
            "official_price_per_sqm": 500_000, "land_category": "임야",
            "land_use_situation": None, "terrain_form": None,
        }

    async def _fake_title(self, pnu):  # noqa: ANN001
        return None, "no_data"  # 건물 없음(나대지) — 노후도 무자료 사유만 부착, 값 왜곡 없음.

    async def _fake_districts(self, pnu):  # noqa: ANN001
        return []  # 용도지구/구역 미확보(특이부지 게이트는 이 테스트의 관심사 아님).

    async def _fake_ordinance(self, address, zone_type, force_refresh=False):  # noqa: ANN001
        return {}  # 조례 미확보 — SSOT는 구조상한만으로 자연녹지 100%→80%를 정정해야 한다.

    monkeypatch.setattr(VWorldService, "get_land_info", _fake_land_info, raising=True)
    monkeypatch.setattr(
        VWorldService, "get_land_characteristics", _fake_land_characteristics, raising=True,
    )
    monkeypatch.setattr(VWorldService, "get_land_use_districts", _fake_districts, raising=True)
    monkeypatch.setattr(
        BuildingRegistryService, "get_title_with_status_by_pnu", _fake_title, raising=True,
    )
    monkeypatch.setattr(OrdinanceService, "get_ordinance_limits", _fake_ordinance, raising=True)
    return az


async def test_parcel_boundaries_effective_far_matches_ssot_natural_green(monkeypatch):
    """자연녹지 단일필지 — SSOT 구조상한(80%)을 반영해야 한다(법정상한 100% 과대표시 회귀 방지)."""
    az = _stub_external_io(monkeypatch)

    req = az.ParcelBoundariesRequest(parcels=[{"pnu": _PNU}])
    result = await az.parcel_boundaries(req)

    ia = result["integrated_analysis"]
    assert ia is not None, "단일필지도 integrated_analysis를 산출해야 함"
    # SSOT 앵커(test_far_cross_surface_parity.py와 동일 절대값) — 자연녹지 실효 = 구조상한 80%.
    assert ia["effective_far_pct"] == 80.0, (
        f"자연녹지 SSOT 구조상한(80%) 미반영 — 법정상한(100%) 과대표시 회귀: {ia['effective_far_pct']}"
    )
    assert ia["effective_bcr_pct"] == 20.0
    assert ia["effective_far_pct"] != 100.0, "법정상한 그대로 노출되던 과거 버그"

    # 통합 연면적/건축면적도 SSOT 실효치 기반(법정상한 기반 과대산정 금지).
    assert ia["total_gfa_sqm"] == pytest.approx(800.0, abs=0.5)  # 1000㎡ × 80%
    assert ia["buildable_area_sqm"] == pytest.approx(200.0, abs=0.5)  # 1000㎡ × 20%

    # 응답 계약 무변경 — SSOT 보강용 내부 전용 키(_far_eff 등)는 features에 노출되지 않는다.
    feat = result["features"][0]
    for k in ("_far_eff", "_bcr_eff", "_far_legal", "_bcr_legal", "_far_basis", "_special"):
        assert k not in feat, f"내부 SSOT 전용 키 {k}가 응답에 누출됨(계약 위반)"


async def test_parcel_boundaries_effective_far_no_regression_for_uncapped_zone(monkeypatch):
    """구조상한 미적용 용도지역(제2종일반주거)은 실효=법정(무변화) — 회귀 없음 확인."""
    az = _stub_external_io(monkeypatch)

    from apps.api.app.services.external_api.vworld_service import VWorldService

    async def _fake_land_characteristics(self, pnu):  # noqa: ANN001
        return {
            "area_sqm": 1000.0, "zone_type": "제2종일반주거지역", "zone_type_2": None,
            "official_price_per_sqm": 3_000_000, "land_category": "대",
            "land_use_situation": None, "terrain_form": None,
        }

    monkeypatch.setattr(
        VWorldService, "get_land_characteristics", _fake_land_characteristics, raising=True,
    )

    req = az.ParcelBoundariesRequest(parcels=[{"pnu": _PNU}])
    result = await az.parcel_boundaries(req)

    ia = result["integrated_analysis"]
    assert ia["effective_far_pct"] == 250.0  # 법정상한 그대로(구조상한 비클램프)
    assert ia["effective_bcr_pct"] == 60.0
