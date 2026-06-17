"""VWORLD NED 토지이용계획 어댑터 + 교차검증 합류 — 용도지역 파싱·has_zone·합류."""
from datetime import date

from app.adapters.regulation.vworld_landuse import VworldLandUseSource
from app.contracts.analysis import AnalysisInput
from app.contracts.cross_validation import CrossStatus
from app.services.pipeline.analysis_pipeline import run_analysis

_PNU = "1111010100100010000"


class _Resp:
    def __init__(self, data):
        self._d = data

    def raise_for_status(self):  # noqa: D102
        ...

    def json(self):
        return self._d


def _zones(*names):
    return _Resp({"landUses": {"resultCode": "NORMAL_SERVICE",
                              "field": [{"prposAreaDstrcCodeNm": n, "cnflcAtNm": "포함"} for n in names]}})


def test_no_key_none(monkeypatch):
    monkeypatch.setenv("VWORLD_API_KEY", "")
    s = VworldLandUseSource()
    assert not s.available
    assert s.land_use_zones(_PNU) is None


def test_zones_parsed(monkeypatch):
    monkeypatch.setenv("VWORLD_API_KEY", "test-key")
    captured = {}

    def _get(url, params=None, headers=None, timeout=None):
        captured.update(url=url, headers=headers)
        return _zones("제2종일반주거지역", "최고고도지구")

    import httpx
    monkeypatch.setattr(httpx, "get", _get)
    s = VworldLandUseSource()
    zones = s.land_use_zones(_PNU)
    assert "제2종일반주거지역" in zones and "최고고도지구" in zones
    assert "getLandUseAttr" in captured["url"]
    assert captured["headers"]["Referer"]  # Referer 도메인 검증


def test_has_zone(monkeypatch):
    monkeypatch.setenv("VWORLD_API_KEY", "test-key")
    import httpx
    monkeypatch.setattr(httpx, "get",
                        lambda url, params=None, headers=None, timeout=None: _zones("제2종일반주거지역", "최고고도지구"))
    s = VworldLandUseSource()
    assert s.has_zone(_PNU, "고도") is True
    assert s.has_zone(_PNU, "상업") is False


def test_pipeline_landuse_cross(monkeypatch):
    # 토지이용계획 고도지구 포함(True) + 검토자 입력(True) → UNANIMOUS.
    monkeypatch.setenv("VWORLD_API_KEY", "test-key")
    import httpx
    monkeypatch.setattr(httpx, "get",
                        lambda url, params=None, headers=None, timeout=None: _zones("최고고도지구"))
    r = run_analysis(AnalysisInput(
        pnu=_PNU, application_date=date(2026, 1, 1),
        cross_facts=[{"fact_key": "고도지구_적용", "land_use_pnu": _PNU, "land_use_contains": "고도",
                      "sources": [{"source": "검토자", "value": True}]}]))
    cv = r.cross_validations[0]
    assert "vworld_landuse" in cv.by_source  # 자동 합류
    assert cv.status == CrossStatus.UNANIMOUS
