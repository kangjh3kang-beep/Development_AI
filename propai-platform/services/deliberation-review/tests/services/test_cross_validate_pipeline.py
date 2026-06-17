"""교차검증 파이프라인 배선 — cross_facts → 합의 결과 표면화·불일치 분리·law.go.kr 자동합류."""
from datetime import date

from app.contracts.analysis import AnalysisInput
from app.contracts.cross_validation import CrossStatus
from app.services.pipeline.analysis_pipeline import run_analysis

_PNU = "1111010100100000002"


def test_pipeline_unanimous():
    r = run_analysis(AnalysisInput(
        pnu=_PNU, application_date=date(2026, 1, 1),
        cross_facts=[{"fact_key": "far_limit", "sources": [
            {"source": "mirror", "value": 200.0}, {"source": "molit", "value": 200.0}]}]))
    assert len(r.cross_validations) == 1
    assert r.cross_validations[0].status == CrossStatus.UNANIMOUS
    assert r.cross_validations[0].confidence == 1.0


def test_pipeline_conflict_surfaced():
    r = run_analysis(AnalysisInput(
        pnu=_PNU, application_date=date(2026, 1, 1),
        cross_facts=[{"fact_key": "far_limit", "sources": [
            {"source": "mirror", "value": 200.0}, {"source": "molit", "value": 250.0}]}]))
    cvr = r.cross_validations[0]
    assert cvr.status == CrossStatus.CONFLICT
    assert cvr.needs_review  # 불일치 → 재검토(무음 오판 0)
    assert set(cvr.by_source.values()) == {200.0, 250.0}  # 출처별 값 보존


def test_pipeline_law_auto_join(monkeypatch):
    # MOLEG 키 있으면 law.go.kr이 출처로 자동 합류(law_exists 모킹).
    monkeypatch.setenv("MOLEG_API_KEY", "test-oc")

    class _Resp:
        def raise_for_status(self): ...
        def json(self):
            return {"LawSearch": {"totalCnt": "1", "law": [{"법령명한글": "건축법"}]}}

    import httpx
    monkeypatch.setattr(httpx, "get", lambda url, params=None, timeout=None: _Resp())
    r = run_analysis(AnalysisInput(
        pnu=_PNU, application_date=date(2026, 1, 1),
        cross_facts=[{"fact_key": "건축법_존재", "law_query": "건축법", "law_expect": True,
                      "sources": [{"source": "mirror", "value": True}]}]))
    cvr = r.cross_validations[0]
    assert "law_go_kr" in cvr.by_source           # 자동 합류
    assert cvr.status == CrossStatus.UNANIMOUS      # mirror+law 일치
    assert cvr.sources_present == 2


def test_pipeline_no_cross_facts():
    r = run_analysis(AnalysisInput(pnu=_PNU, application_date=date(2026, 1, 1)))
    assert r.cross_validations == []
