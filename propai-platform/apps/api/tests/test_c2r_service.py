"""C2R build_foundation 통합 테스트 — 렌더는 pending(기본 미호출)·정직 상태.

외부 네트워크/키 없이 통과하도록 부지 해석·geometry 조회를 monkeypatch로 주입한다
(인벨로프·브리프·think_before 는 실제 primitive 그대로 실행 = 진짜 통합).
"""

import app.services.c2r.c2r_service as svc
from app.services.c2r.c2r_service import build_foundation


def _fake_parcel() -> dict:
    return {
        "address": "서울특별시 강남구 역삼동 123-45",
        "pnu": "1168010100101230045",
        "zone_type": "제2종일반주거지역",
        "zone_source": "vworld_land_info",
        "zone_limits": {"max_bcr_pct": 60, "max_far_pct": 250, "max_height_m": None,
                        "max_floors": None},
        "land_area_sqm": 660.0,
        "coordinates": {"lat": 37.5, "lon": 127.03},
        "warnings": [],
    }


def _patch_resolve(monkeypatch, parcel: dict, geometry=None):
    async def _fake_resolve(_key):
        return parcel

    async def _fake_geom(_parcel):
        return geometry

    monkeypatch.setattr(svc, "_resolve_parcel", _fake_resolve)
    monkeypatch.setattr(svc, "_fetch_geometry", _fake_geom)


async def test_build_foundation_render_pending_by_default(monkeypatch):
    """기본은 렌더를 호출하지 않는다 — render.status='pending_provider'."""
    _patch_resolve(monkeypatch, _fake_parcel())
    out = await build_foundation("서울특별시 강남구 역삼동 123-45", {"building_use": "공동주택"})
    assert set(out.keys()) == {"parcel", "envelope", "brief", "think_before", "render"}
    # 정상 부지면 think_before 통과 → 렌더는 pending_provider(아직 미수행).
    assert out["think_before"]["proceed"] is True
    assert out["render"]["status"] == "pending_provider"
    # 인벨로프가 실제 primitive로 산출되어 있어야 한다(가짜 아님).
    assert out["envelope"].get("bcr_pct") == 60.0
    assert out["brief"]["program"]["building_use"] == "공동주택"
    assert out["brief"]["llm_enriched"] is False  # use_llm 기본 False


async def test_build_foundation_blocks_when_area_missing(monkeypatch):
    """대지면적 미확보 → 인벨로프 error·근거 부재 → think_before 차단."""
    parcel = _fake_parcel()
    parcel["land_area_sqm"] = None
    parcel["zone_limits"] = None  # 한도까지 미확보로 근거 부재 강제
    _patch_resolve(monkeypatch, parcel)
    out = await build_foundation("미상 주소")
    assert "error" in out["envelope"]
    assert out["think_before"]["proceed"] is False
    assert out["render"]["status"] == "blocked_by_think_before"


async def test_build_foundation_no_network_keys_needed(monkeypatch):
    """키/네트워크 없이도 파운데이션이 완성된다(geometry None 폴백)."""
    _patch_resolve(monkeypatch, _fake_parcel(), geometry=None)
    out = await build_foundation("서울특별시 강남구 역삼동 123-45")
    assert out["envelope"].get("far_pct") == 250.0
    # 향 메모(정북일조 적용 용도지역)
    assert "정북" in out["brief"]["site_context"]["orientation_note"]
