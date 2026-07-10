"""F4(QA REQUEST CHANGES) 블라스트 격리 회귀 테스트.

이전엔 adjacency/usable 신규 블록이 build_integrated_context의 큰 try 안에 그대로
딸려 있어, 그 블록에서 예외가 나면 바깥 except가 이미 완성된 _aggregate_integrated_zoning
결과(blended_far_eff_pct 등)까지 통째로 버리고 None을 반환했다(33필지→대표 763㎡ 단일필지
폴백 회귀 재현 경로). 이 테스트는 adjacency/usable 계산에 강제로 예외를 주입해도
blended 통합집계는 보존되고(해당 키만 None+사유), None 전체폐기가 일어나지 않는지 검증한다.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio


def _parcels_with_geometry() -> list[dict]:
    def _square(lon0: float, lat0: float, size: float = 0.001) -> dict:
        lon1, lat1 = lon0 + size, lat0 + size
        return {
            "type": "Polygon",
            "coordinates": [[[lon0, lat0], [lon1, lat0], [lon1, lat1], [lon0, lat1], [lon0, lat0]]],
        }

    return [
        {
            "pnu": "A", "zone_type": "자연녹지지역", "area_sqm": 500.0,
            "farPct": 100.0, "bcrPct": 20.0, "farLegalPct": 100.0, "bcrLegalPct": 20.0,
            "geometry": _square(127.000, 37.000),
        },
        {
            "pnu": "B", "zone_type": "자연녹지지역", "area_sqm": 500.0,
            "farPct": 100.0, "bcrPct": 20.0, "farLegalPct": 100.0, "bcrLegalPct": 20.0,
            "geometry": _square(127.001, 37.000),
        },
    ]


async def test_usable_failure_preserves_blended_aggregate(monkeypatch):
    """compute_usable_area가 예외를 던져도 blended 통합집계(far/bcr)는 그대로 반환된다."""
    import app.services.zoning.usable_area as usable_area_mod

    def _boom(parcels):
        raise RuntimeError("usable 계산 강제 실패(F4 회귀 재현)")

    monkeypatch.setattr(usable_area_mod, "compute_usable_area", _boom)

    from app.services.land_intelligence.comprehensive_analysis_service import (
        build_integrated_context,
    )

    out = await build_integrated_context(_parcels_with_geometry())

    assert out is not None, "usable 실패가 통합집계 전체를 버림(F4 회귀) — None 반환은 실패"
    # 핵심 회귀 방지 대상: blended 값은 usable 블록과 무관하게 보존돼야 한다.
    assert out["blended_far_eff_pct"] == 100.0, out
    assert out["total_area_sqm"] == 1000.0, out
    # usable만 정직 누락(None) — 다른 키에 영향 없음.
    assert out["usable"] is None
    assert out["land_area_effective_sqm"] is None
    # adjacency는 usable과 독립 — 정상 산출돼 있어야 한다(맞닿은 두 필지 → contiguous=True).
    assert out["adjacency"]["contiguous"] is True


async def test_adjacency_failure_preserves_blended_aggregate(monkeypatch):
    """_parcel_adjacency가 예외를 던져도 blended 통합집계(far/bcr)와 usable은 그대로 반환된다."""
    import apps.api.routers.auto_zoning as auto_zoning_mod

    def _boom(geoms):
        raise RuntimeError("인접성 계산 강제 실패(F4 회귀 재현)")

    monkeypatch.setattr(auto_zoning_mod, "_parcel_adjacency", _boom)

    from app.services.land_intelligence.comprehensive_analysis_service import (
        build_integrated_context,
    )

    out = await build_integrated_context(_parcels_with_geometry())

    assert out is not None, "adjacency 실패가 통합집계 전체를 버림(F4 회귀) — None 반환은 실패"
    assert out["blended_far_eff_pct"] == 100.0, out
    # adjacency만 정직 누락(None) — usable은 영향 없이 정상 산출.
    assert out["adjacency"]["contiguous"] is None
    assert out["usable"]["confirmed_sqm"] == 1000.0
