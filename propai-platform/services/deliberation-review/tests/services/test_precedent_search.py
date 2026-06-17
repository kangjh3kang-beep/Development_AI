"""P-C — 유사사례 Qdrant 벡터검색 배선: 유사사례 선별·무관사례 제외·결정론·파이프라인."""
from datetime import date

from app.contracts.analysis import AnalysisInput
from app.contracts.precedent import PrecedentCase
from app.services.pipeline.analysis_pipeline import run_analysis
from app.services.precedent.precedent_search import PrecedentSearch


def _case(cid, label):
    return PrecedentCase(case_id=cid, source=f"의결서-{cid}", decision_type="CONDITIONAL",
                         issue_labels=[label], conditions=["공개공지 확대"])


def test_vector_search_selects_relevant():
    # 동일 쟁점 라벨 → 임베딩 유사 → 전부 매칭.
    corpus = [_case(f"c{i}", "FAR_DISPUTE") for i in range(5)]
    matched, matches = PrecedentSearch().search_cases("FAR_DISPUTE", corpus)
    assert len(matched) == 5
    assert all(m.is_candidate for m in matches)  # 적용 단정 금지(INV-24)


def test_vector_search_excludes_unrelated():
    # 무관 쟁점은 유사도 낮아 제외(전체 무차별 집계가 아님 — 벡터검색의 가치).
    corpus = [_case("a", "FAR_DISPUTE"), _case("b", "FAR_DISPUTE"),
              _case("x", "PARKING_DISPUTE"), _case("y", "HEIGHT_DISPUTE")]
    matched, _ = PrecedentSearch().search_cases("FAR_DISPUTE", corpus)
    ids = {c.case_id for c in matched}
    assert ids == {"a", "b"}  # FAR_DISPUTE만 선별, 무관 2건 제외


def test_deterministic():
    corpus = [_case("c1", "FAR_DISPUTE")]
    m1, _ = PrecedentSearch().search_cases("FAR_DISPUTE", corpus)
    m2, _ = PrecedentSearch().search_cases("FAR_DISPUTE", corpus)
    assert [c.case_id for c in m1] == [c.case_id for c in m2]


def test_pipeline_precedent_vector_wired():
    r = run_analysis(AnalysisInput(
        pnu="1111010100100000002", application_date=date(2026, 1, 1),
        issue="FAR_DISPUTE",
        corpus=[{"case_id": f"c{i}", "source": f"의결서-{i}", "decision_type": "CONDITIONAL",
                 "issue_labels": ["FAR_DISPUTE"], "conditions": ["공개공지 확대"]} for i in range(8)]))
    assert r.precedent_source == "VECTOR_SEARCH"
    assert r.precedent and r.precedent.distribution.get("CONDITIONAL") == 8


def test_pipeline_precedent_filters_unrelated():
    # 무관 쟁점이 섞인 corpus → 벡터검색이 관련만 집계(무차별 아님). 임계 5건 → FAR 6건으로 성숙.
    corpus = [{"case_id": f"f{i}", "source": f"의결서-f{i}", "decision_type": "CONDITIONAL",
               "issue_labels": ["FAR_DISPUTE"], "conditions": []} for i in range(6)]
    corpus += [{"case_id": "x", "source": "의결서-x", "decision_type": "REJECTED",
                "issue_labels": ["PARKING_DISPUTE"], "conditions": []},
               {"case_id": "y", "source": "의결서-y", "decision_type": "REJECTED",
                "issue_labels": ["HEIGHT_DISPUTE"], "conditions": []}]
    r = run_analysis(AnalysisInput(pnu="1111010100100000002", application_date=date(2026, 1, 1),
                                   issue="FAR_DISPUTE", corpus=corpus))
    assert r.precedent_source == "VECTOR_SEARCH"
    assert r.precedent.distribution.get("CONDITIONAL") == 6   # FAR 6건만
    assert "REJECTED" not in r.precedent.distribution          # 무관 PARKING/HEIGHT 제외
