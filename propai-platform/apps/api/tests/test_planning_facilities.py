"""개발계획(도시계획시설) kinds=all 배선 계약 테스트 — UPIS 실필드 파싱·rail 필터·좌표.

픽스처는 2026-07-04 동탄역 반경 라이브 프로브에서 캡처한 실제 VWorld UPIS 응답 형태
(LT_C_UPISUQ151/153 — mls_nam·lcl_nam·exc_nam·dgm_nm 필드). 무날조: 실데이터 기반.

계약:
- kinds="all": 전 시설 통과, type=mls_nam(→lcl_nam 폴백), status=exc_nam(집행/미집행),
  lat/lon(geometry 첫 좌표) 포함 — 지도 마커용.
- kinds="rail"(기본): 기존 철도 필터 유지(도로·광장 배제) — 기존 소비처 무회귀.
"""
from __future__ import annotations

import httpx

from app.services.external_api.vworld_service import VWorldService


def _upis_feature(props: dict, lon: float = 127.09, lat: float = 37.20) -> dict:
    return {
        "properties": props,
        "geometry": {"type": "MultiPolygon",
                     "coordinates": [[[[lon, lat], [lon + 0.001, lat], [lon, lat + 0.001]]]]},
    }


# 동탄 라이브 캡처 형태(요약) — 도로(중로2류)·교통광장·철도 가상 1건(필터 검증용)
_FIXTURE_FEATURES = [
    _upis_feature({"dgm_nm": "중로2-34", "lcl_nam": "중로2류", "mls_nam": "", "exc_nam": "집행"}),
    _upis_feature({"dgm_nm": "기타 교통광장시설", "lcl_nam": "광장", "mls_nam": "교통광장", "exc_nam": "미집행"}),
    _upis_feature({"dgm_nm": "동탄 도시철도", "lcl_nam": "철도", "mls_nam": "도시철도", "exc_nam": "미집행"}),
]


def _mock_transport(features_by_call: list[list[dict]]):
    """호출 순서대로 features를 돌려주는 MockTransport(레이어 순차 시도 대응)."""
    calls = {"i": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        i = min(calls["i"], len(features_by_call) - 1)
        calls["i"] += 1
        return httpx.Response(200, json={
            "response": {"status": "OK",
                         "result": {"featureCollection": {"features": features_by_call[i]}}}})

    return httpx.MockTransport(handler)


async def _run(monkeypatch, kinds: str, features_by_call: list[list[dict]]):
    monkeypatch.setenv("VWORLD_API_KEY", "TESTKEY")
    # settings 캐시 우회 — 서비스는 settings.VWORLD_API_KEY를 읽으므로 직접 패치.
    from app.core import config as _cfg
    monkeypatch.setattr(_cfg.settings, "VWORLD_API_KEY", "TESTKEY")
    transport = _mock_transport(features_by_call)
    _orig = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient",
                        lambda **kw: _orig(transport=transport,
                                           headers=kw.get("headers")))
    vw = VWorldService()
    return await vw.get_planning_facilities(37.2039, 127.0952, radius_m=1500, kinds=kinds)


async def test_all_returns_every_facility_with_upis_fields(monkeypatch):
    # kinds=all: 7개 레이어 순차 호출 — 첫 호출만 픽스처, 나머지 빈 응답.
    out = await _run(monkeypatch, "all", [_FIXTURE_FEATURES] + [[]] * 6)
    names = {f["name"] for f in out}
    assert {"중로2-34", "기타 교통광장시설", "동탄 도시철도"} <= names  # 전 시설 통과
    by_name = {f["name"]: f for f in out}
    # type: mls_nam 우선, 비면 lcl_nam 폴백
    assert by_name["기타 교통광장시설"]["type"] == "교통광장"
    assert by_name["중로2-34"]["type"] == "중로2류"
    # status: exc_nam(집행/미집행) 그대로
    assert by_name["중로2-34"]["status"] == "집행"
    assert by_name["기타 교통광장시설"]["status"] == "미집행"
    # 지도 마커용 좌표 포함
    assert isinstance(by_name["중로2-34"]["lat"], float)
    assert isinstance(by_name["중로2-34"]["lon"], float)
    assert by_name["중로2-34"]["distance_m"] is not None


async def test_rail_keeps_legacy_filter(monkeypatch):
    # kinds=rail(기본): 도로·광장은 배제, 철도만 통과 — 기존 소비처 동작 보존.
    out = await _run(monkeypatch, "rail", [_FIXTURE_FEATURES] + [[]] * 3)
    names = {f["name"] for f in out}
    assert "동탄 도시철도" in names
    assert "중로2-34" not in names
    assert "기타 교통광장시설" not in names


async def test_no_key_returns_empty(monkeypatch):
    from app.core import config as _cfg
    monkeypatch.setattr(_cfg.settings, "VWORLD_API_KEY", "")
    vw = VWorldService()
    assert await vw.get_planning_facilities(37.2, 127.1, kinds="all") == []
