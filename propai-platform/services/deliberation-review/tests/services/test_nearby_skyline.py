"""VWORLD 주변 건물/스카이라인 — 수집·통계(평균/최고 층수)·파이프라인 배선."""
from datetime import date

from app.adapters.regulation.vworld_nearby import VworldNearbyBuildings
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


def _bldg(*floors):
    feats = [{"properties": {"bld_nm": f"건물{i}", "grnd_flr": str(fl), "ugrnd_flr": "1",
                             "height": "0", "vl_rat": "0"}} for i, fl in enumerate(floors)]
    return _Resp({"response": {"status": "OK",
                              "result": {"featureCollection": {"features": feats}}}})


def test_no_key_none(monkeypatch):
    monkeypatch.setenv("VWORLD_API_KEY", "")
    assert VworldNearbyBuildings().skyline_context(126.9, 37.5) is None


def test_skyline_stats(monkeypatch):
    monkeypatch.setenv("VWORLD_API_KEY", "test-key")
    import httpx
    monkeypatch.setattr(httpx, "get",
                        lambda url, params=None, headers=None, timeout=None: _bldg(3, 5, 4, 10, 2))
    sc = VworldNearbyBuildings().skyline_context(126.9684, 37.5912, 150)
    assert sc["building_count"] == 5
    assert sc["avg_floors"] == 4.8 and sc["max_floors"] == 10
    assert sc["radius_m"] == 150


def test_pipeline_surrounding(monkeypatch):
    monkeypatch.setenv("VWORLD_API_KEY", "test-key")
    import httpx

    def _get(url, params=None, headers=None, timeout=None):
        if "/address" in url:
            return _Resp({"response": {"status": "OK", "result": {"point": {"x": "126.9684", "y": "37.5912"}}}})
        if "GetFeature" in str(params.get("request", "")) and params.get("data") == "LP_PA_CBND_BUBUN":
            return _Resp({"response": {"result": {"featureCollection": {"features": [
                {"properties": {"pnu": _PNU}}]}}}})
        if params.get("data") == "lt_c_bldginfo":
            return _bldg(3, 5, 12)
        return _Resp({"response": {"status": "OK", "result": {"featureCollection": {"features": []}}}})

    monkeypatch.setattr(httpx, "get", _get)
    r = run_analysis(AnalysisInput(pnu="unknown", application_date=date(2026, 1, 1),
                                   address="서울특별시 종로구 청운동 1", collect_surrounding=True))
    assert r.surrounding_context is not None
    assert r.surrounding_context["building_count"] == 3
    assert r.surrounding_context["max_floors"] == 12
