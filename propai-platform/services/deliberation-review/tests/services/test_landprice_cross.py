"""VWORLD NED 개별공시지가 어댑터 + 교차검증 합류 — 파싱·INCORRECT_KEY graceful·합류."""
from datetime import date

from app.adapters.regulation.vworld_landprice import VworldLandPriceSource
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


def _ok(price):
    return _Resp({"indvdLandPrices": {"resultCode": "NORMAL_SERVICE",
                                      "field": [{"pnu": _PNU, "stdrYear": "2024",
                                                 "pblntfPclnd": str(price)}]}})


def test_no_key_none(monkeypatch):
    monkeypatch.setenv("VWORLD_API_KEY", "")
    s = VworldLandPriceSource()
    assert not s.available
    assert s.land_price(_PNU) is None


def test_incorrect_key_graceful(monkeypatch):
    monkeypatch.setenv("VWORLD_API_KEY", "wrong")
    import httpx
    monkeypatch.setattr(httpx, "get", lambda url, params=None, headers=None, timeout=None:
                        _Resp({"indvdLandPrices": {"resultCode": "INCORRECT_KEY",
                                                   "resultMsg": "인증키 정보가 올바르지 않습니다."}}))
    assert VworldLandPriceSource().land_price(_PNU) is None  # 무음 단정 금지


def test_parses_price(monkeypatch):
    monkeypatch.setenv("VWORLD_API_KEY", "test-key")
    captured = {}

    def _get(url, params=None, headers=None, timeout=None):
        captured.update(url=url, params=params)
        return _ok(3500000)

    import httpx
    monkeypatch.setattr(httpx, "get", _get)
    assert VworldLandPriceSource().land_price(_PNU, "2024") == 3500000.0
    assert captured["params"]["key"] == "test-key"  # serviceKey 아닌 key
    assert "getIndvdLandPriceAttr" in captured["url"]
    assert captured["params"]["stdrYear"] == "2024"


def test_pipeline_landprice_cross(monkeypatch):
    # 공시지가(VWORLD NED) + 감정평가 → 합의 UNANIMOUS.
    monkeypatch.setenv("VWORLD_API_KEY", "test-key")
    import httpx
    monkeypatch.setattr(httpx, "get", lambda url, params=None, headers=None, timeout=None: _ok(3500000))
    r = run_analysis(AnalysisInput(
        pnu=_PNU, application_date=date(2026, 1, 1),
        cross_facts=[{"fact_key": "공시지가", "land_pnu": _PNU,
                      "sources": [{"source": "감정평가", "value": 3500000.0}]}]))
    cv = r.cross_validations[0]
    assert "vworld_landprice" in cv.by_source  # 자동 합류
    assert cv.status == CrossStatus.UNANIMOUS
    assert cv.sources_present == 2
