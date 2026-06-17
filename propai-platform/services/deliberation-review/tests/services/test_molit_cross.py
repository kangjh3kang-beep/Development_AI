"""국토부 건축물대장(MOLIT) 어댑터 + 교차검증 합류 — PNU분해·resultCode·키없음·파이프라인."""
from datetime import date

from app.adapters.regulation.molit_building import MolitBuildingSource
from app.contracts.analysis import AnalysisInput
from app.contracts.cross_validation import CrossStatus
from app.services.pipeline.analysis_pipeline import run_analysis

_PNU = "1111010100100010000"  # 종로구 청운동 1번지 류


class _Resp:
    def __init__(self, data):
        self._d = data

    def raise_for_status(self):  # noqa: D102
        ...

    def json(self):
        return self._d


def _ok(far, bcr):
    return _Resp({"response": {"header": {"resultCode": "00"},
                              "body": {"items": {"item": [{"vlRat": far, "bcRat": bcr, "totArea": "1234.5",
                                                           "mainPurpsCdNm": "공동주택"}]}}}})


def test_no_key_none(monkeypatch):
    monkeypatch.setenv("MOLIT_API_KEY", "")
    s = MolitBuildingSource()
    assert not s.available
    assert s.building_basis(_PNU) is None


def test_pnu_parts():
    sg, bj, bun, ji = MolitBuildingSource._pnu_parts(_PNU)
    assert sg == "11110" and bj == "10100" and bun == "0001" and ji == "0000"


def test_building_basis_parses(monkeypatch):
    monkeypatch.setenv("MOLIT_API_KEY", "test-key")
    captured = {}

    def _get(url, params=None, timeout=None):
        captured.update(url=url, params=params)
        return _ok("250.5", "59.9")

    import httpx
    monkeypatch.setattr(httpx, "get", _get)
    d = MolitBuildingSource().building_basis(_PNU)
    assert d["far_pct"] == 250.5 and d["bcr_pct"] == 59.9
    assert captured["params"]["serviceKey"] == "test-key"
    assert captured["params"]["sigunguCd"] == "11110"


def test_unauthorized_resultcode_none(monkeypatch):
    monkeypatch.setenv("MOLIT_API_KEY", "test-key")
    import httpx
    monkeypatch.setattr(httpx, "get",
                        lambda url, params=None, timeout=None: _Resp({"response": {"header": {"resultCode": "30"}}}))
    assert MolitBuildingSource().building_basis(_PNU) is None  # 미승인 → None(무음 단정 금지)


def test_pipeline_molit_cross_unanimous(monkeypatch):
    # MOLIT 건축물대장 용적률(250) + 미러(250) → 합의 UNANIMOUS.
    monkeypatch.setenv("MOLIT_API_KEY", "test-key")
    import httpx
    monkeypatch.setattr(httpx, "get", lambda url, params=None, timeout=None: _ok("250.0", "60.0"))
    r = run_analysis(AnalysisInput(
        pnu=_PNU, application_date=date(2026, 1, 1),
        cross_facts=[{"fact_key": "far_현황", "building_pnu": _PNU, "building_metric": "far_pct",
                      "sources": [{"source": "mirror", "value": 250.0}]}]))
    cv = r.cross_validations[0]
    assert "molit_building" in cv.by_source        # 자동 합류
    assert cv.status == CrossStatus.UNANIMOUS
    assert cv.sources_present == 2


def test_pipeline_molit_cross_conflict(monkeypatch):
    # 건축물대장 250 vs 미러 200 → 불일치 → NEEDS_REVIEW(무음 오판 0).
    monkeypatch.setenv("MOLIT_API_KEY", "test-key")
    import httpx
    monkeypatch.setattr(httpx, "get", lambda url, params=None, timeout=None: _ok("250.0", "60.0"))
    r = run_analysis(AnalysisInput(
        pnu=_PNU, application_date=date(2026, 1, 1),
        cross_facts=[{"fact_key": "far_현황", "building_pnu": _PNU, "building_metric": "far_pct",
                      "sources": [{"source": "mirror", "value": 200.0}]}]))
    cv = r.cross_validations[0]
    assert cv.status == CrossStatus.CONFLICT and cv.needs_review
    assert set(cv.by_source.values()) == {200.0, 250.0}
