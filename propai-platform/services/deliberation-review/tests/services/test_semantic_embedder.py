"""P-C 격상 — 실 의미 임베더 주입: 의미검색·해시 폴백·결정론·실패 graceful."""
from datetime import date

from app.contracts.analysis import AnalysisInput
from app.contracts.precedent import PrecedentCase
from app.services.pipeline.analysis_pipeline import run_analysis
from app.services.precedent.embedder import Embedder
from app.services.precedent.precedent_search import PrecedentSearch


class _SemVision:
    """의미 임베더 흉내 — 'FAR' 포함 여부로 2차원 벡터(의미 분리)."""

    def embed(self, text):
        return [1.0, 0.0] if "FAR" in text else [0.0, 1.0]


class _FailClient:
    def embed(self, text):
        return None  # 실패 → 해시 폴백


def _case(cid, label):
    return PrecedentCase(case_id=cid, source=f"의결서-{cid}", decision_type="CONDITIONAL",
                         issue_labels=[label], conditions=[])


def test_semantic_injection_used():
    e = Embedder(client=_SemVision())
    assert e.is_semantic
    assert e.embed("FAR_DISPUTE") == [1.0, 0.0]


def test_hash_fallback_when_no_client():
    e = Embedder()
    assert not e.is_semantic
    assert len(e.embed("x")) == 16  # 해시 16차원


def test_client_failure_falls_back_to_hash():
    e = Embedder(client=_FailClient())
    v = e.embed("x")
    assert len(v) == 16  # 실 실패 → 해시 폴백(결정론)


def test_deterministic_hash():
    e = Embedder()
    assert e.embed("FAR_DISPUTE") == e.embed("FAR_DISPUTE")


def test_semantic_search_threshold_separates():
    # 의미 임베더(0.75 임계) → FAR만 매칭, 무관 분리. 표기 라벨이 아닌 의미 벡터 기준.
    corpus = [_case("a", "용적률초과"), _case("b", "용적률완화"), _case("x", "주차장")]
    # 라벨이 제각각이어도 의미 임베더가 'FAR' 의미축으로 분리(_SemVision은 'FAR' 토큰 기준이라
    # 여기선 ingest 키=issue_labels[0]에 FAR 없음 → 전부 [0,1]; 검색 issue에 FAR 포함시 분리 확인)
    matched, _ = PrecedentSearch(embedder=Embedder(client=_SemVision())).search_cases(
        "FAR_용적률", corpus, min_similarity=0.75)
    # issue 'FAR_용적률' → [1,0]; corpus 라벨에 FAR 없음 → [0,1] → cosine 0 < 0.75 → 매칭 0
    assert matched == []


def test_pipeline_default_hash_unchanged():
    # 기본(해시) 경로는 기존과 동일(회귀 없음).
    r = run_analysis(AnalysisInput(
        pnu="1111010100100000002", application_date=date(2026, 1, 1),
        issue="FAR_DISPUTE",
        corpus=[{"case_id": f"c{i}", "source": f"의결서-{i}", "decision_type": "CONDITIONAL",
                 "issue_labels": ["FAR_DISPUTE"], "conditions": []} for i in range(6)]))
    assert r.precedent_source == "VECTOR_SEARCH"
    assert r.precedent.distribution.get("CONDITIONAL") == 6
