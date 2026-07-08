"""terrain_service._resolve_location — VWorld 예외 정직게이트 계약 테스트.

결함(P1): VWorldService 호출(get_parcel_by_pnu/geocode_address/get_parcel_by_point)
예외가 그대로 전파되어 analyze_terrain의 "좌표/DEM 전부 실패시 ok:false" 계약
(정직게이트)을 우회한다. comprehensive_analysis_service._fetch_terrain_facts는
dict 반환을 전제하므로 예외 전파는 계약 위반.

수선 계약: _resolve_location은 VWorld 어떤 예외(타임아웃/500/malformed)에도
raise 하지 않고 None을 반환 → analyze_terrain은 항상 dict(ok:false)를 반환.
"""

from __future__ import annotations

import app.services.external_api.vworld_service as vworld_mod
from app.services.terrain import terrain_service as ts


class _ExplodingVWorld:
    """모든 조회가 예외를 던지는 VWorldService 대역(타임아웃/500/파싱오류 재현)."""

    def __init__(self, *args, **kwargs) -> None:  # noqa: D401
        pass

    async def get_parcel_by_pnu(self, pnu):
        raise RuntimeError("VWorld timeout (재현)")

    async def geocode_address(self, address):
        raise RuntimeError("VWorld 500 (재현)")

    async def get_parcel_by_point(self, lat, lon):
        raise RuntimeError("VWorld malformed response (재현)")


class _PointLookupExplodingVWorld(_ExplodingVWorld):
    """지오코딩은 성공하되 점→필지 폴백만 실패하는 부분장애 재현."""

    async def geocode_address(self, address):
        return {"lat": 37.5665, "lon": 126.9780, "pnu": None}


async def test_resolve_location_returns_none_on_pnu_lookup_exception(monkeypatch):
    monkeypatch.setattr(vworld_mod, "VWorldService", _ExplodingVWorld)
    loc = await ts._resolve_location(None, "1111010100100010000")
    assert loc is None


async def test_resolve_location_returns_none_on_geocode_exception(monkeypatch):
    monkeypatch.setattr(vworld_mod, "VWorldService", _ExplodingVWorld)
    loc = await ts._resolve_location("서울특별시 종로구 세종로 1", None)
    assert loc is None


async def test_resolve_location_returns_none_on_point_fallback_exception(monkeypatch):
    monkeypatch.setattr(vworld_mod, "VWorldService", _PointLookupExplodingVWorld)
    loc = await ts._resolve_location("서울특별시 종로구 세종로 1", None)
    assert loc is None


async def test_analyze_terrain_returns_ok_false_dict_on_vworld_exception(monkeypatch):
    """정직게이트: 예외 대신 항상 dict(ok:false) — 호출측(dict 전제) 계약 보존."""
    monkeypatch.setattr(vworld_mod, "VWorldService", _ExplodingVWorld)
    result = await ts.analyze_terrain(
        "서울특별시 종로구 세종로 1", "1111010100100010000", None, None
    )
    assert isinstance(result, dict)
    assert result["ok"] is False
    assert result.get("message")
    assert result.get("elevation_source") == ts.ELEVATION_SOURCE
