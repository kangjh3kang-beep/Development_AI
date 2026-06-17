"""VWORLD 지오코더 — 주소→좌표→PNU·도로명 폴백·파이프라인 address→PNU→대지카드."""
from datetime import date

from app.adapters.regulation.vworld_geocoder import VworldGeocoder
from app.contracts.analysis import AnalysisInput
from app.services.pipeline.analysis_pipeline import run_analysis

_PNU = "1111010100100010000"


class _Resp:
    def __init__(self, data):
        self._d = data

    def raise_for_status(self):  # noqa: D102
        ...

    def json(self):
        return self._d


def _coord_ok():
    return _Resp({"response": {"status": "OK", "result": {"point": {"x": "126.96845", "y": "37.59127"}}}})


def _feature_ok():
    return _Resp({"response": {"result": {"featureCollection": {"features": [
        {"properties": {"pnu": _PNU, "addr": "서울특별시 종로구 청운동 1"}}]}}}})


def test_no_key_none(monkeypatch):
    monkeypatch.setenv("VWORLD_API_KEY", "")
    assert not VworldGeocoder().available
    assert VworldGeocoder().address_to_pnu("서울 종로구 청운동 1") is None


def test_address_to_pnu(monkeypatch):
    monkeypatch.setenv("VWORLD_API_KEY", "test-key")
    captured = []

    def _get(url, params=None, headers=None, timeout=None):
        captured.append((url, params.get("request")))
        return _coord_ok() if "getcoord" in str(params.get("request", "")) or "/address" in url else _feature_ok()

    import httpx
    monkeypatch.setattr(httpx, "get", _get)
    out = VworldGeocoder().address_to_pnu("서울특별시 종로구 청운동 1")
    assert out["pnu"] == _PNU
    assert abs(out["lon"] - 126.96845) < 1e-4 and abs(out["lat"] - 37.59127) < 1e-4


def test_road_fallback(monkeypatch):
    # 지번(PARCEL) 좌표 실패 → 도로명(ROAD) 폴백.
    monkeypatch.setenv("VWORLD_API_KEY", "test-key")
    calls = {"n": 0}

    def _get(url, params=None, headers=None, timeout=None):
        if "/address" in url:
            calls["n"] += 1
            if params.get("type") == "PARCEL":
                return _Resp({"response": {"status": "NOT_FOUND"}})
            return _coord_ok()  # ROAD 성공
        return _feature_ok()

    import httpx
    monkeypatch.setattr(httpx, "get", _get)
    out = VworldGeocoder().address_to_pnu("서울특별시 종로구 자하문로 30")
    assert out["pnu"] == _PNU
    assert calls["n"] == 2  # PARCEL 실패 후 ROAD


def test_pipeline_address_to_land_card(monkeypatch):
    # address(PNU 미상) → 지오코딩 → 대지카드 자동.
    monkeypatch.setenv("VWORLD_API_KEY", "test-key")

    def _get(url, params=None, headers=None, timeout=None):
        if "/address" in url:
            return _coord_ok()
        if "GetFeature" in str(params.get("request", "")):
            return _feature_ok()
        if "getLandCharacteristics" in url:
            return _Resp({"landCharacteristicss": {"field": [{"lndcgrCodeNm": "대",
                          "prposArea1Nm": "제1종일반주거지역", "pblntfPclnd": "5150000"}]}})
        if "getLandUseAttr" in url:
            return _Resp({"landUses": {"field": [{"prposAreaDstrcCodeNm": "제1종일반주거지역"}]}})
        return _Resp({"response": {"totalCount": "0"}})  # getBuildingUse 없음

    import httpx
    monkeypatch.setattr(httpx, "get", _get)
    r = run_analysis(AnalysisInput(pnu="unknown", application_date=date(2026, 1, 1),
                                   address="서울특별시 종로구 청운동 1", collect_land_card=True))
    assert r.geocoded["pnu"] == _PNU
    assert r.land_card is not None and r.land_card.use_zone == "제1종일반주거지역"
