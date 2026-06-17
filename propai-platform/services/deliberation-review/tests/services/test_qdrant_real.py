"""실 Qdrant 어댑터 — qdrant-client 임베디드(:memory:) upsert/search·팩토리 폴백·파이프라인."""
from app.adapters.vector.qdrant_client import (
    QdrantClientAdapter,
    RealQdrantClient,
    build_qdrant,
)
from app.contracts.precedent import PrecedentCase
from app.services.precedent.precedent_search import PrecedentSearch


def test_real_qdrant_embedded_upsert_search(monkeypatch):
    monkeypatch.setenv("QDRANT_URL", ":memory:")
    c = build_qdrant(dim=4)
    assert isinstance(c, RealQdrantClient)  # 실 qdrant-client 경로(임베디드)
    c.upsert("c1", [1.0, 0.0, 0.0, 0.0], {"source": "의결서-1"})
    c.upsert("c2", [0.0, 1.0, 0.0, 0.0], {"source": "의결서-2"})
    res = c.search([0.9, 0.1, 0.0, 0.0], top=2)
    assert res[0][1] == "c1"  # 가장 유사한 사례가 상위
    assert res[0][2]["source"] == "의결서-1"


def test_build_qdrant_fallback_to_mock(monkeypatch):
    monkeypatch.setenv("QDRANT_URL", "")
    assert isinstance(build_qdrant(), QdrantClientAdapter)  # 미설정 → in-memory mock


def test_precedent_search_over_real_qdrant(monkeypatch):
    # :memory: 실 Qdrant + 해시 임베더(16dim)로 벡터검색 파이프라인 동작.
    monkeypatch.setenv("QDRANT_URL", ":memory:")
    monkeypatch.setenv("EMBEDDER", "hash")
    corpus = [PrecedentCase(case_id=f"c{i}", source=f"의결서-{i}", decision_type="CONDITIONAL",
                            issue_labels=["FAR_DISPUTE"], conditions=[]) for i in range(5)]
    matched, matches = PrecedentSearch().search_cases("FAR_DISPUTE", corpus)
    assert len(matched) == 5  # 동일 쟁점 전부 매칭(실 Qdrant 코사인)
    assert all(m.is_candidate for m in matches)
