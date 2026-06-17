"""P-C — 유사사례 벡터검색 배선. issue → (코퍼스 적재) → Qdrant 검색 → 유사사례만 선별.

기존 파이프라인은 corpus 전체를 무차별 집계(벡터검색 우회)했다. 본 서비스는 임베딩 유사도로
관련 사례만 선별(INV-24 후보 표기 보존). client 격리(분석마다 자체 저장소 — 전역 오염 방지),
임계값 미만 제외(보수). 실 Qdrant는 동일 인터페이스로 client 주입만 교체.
"""
from __future__ import annotations

from app.adapters.vector.qdrant_client import build_qdrant
from app.contracts.precedent import PrecedentCase, PrecedentMatch
from app.services.precedent.corpus_ingest import CorpusIngest
from app.services.precedent.embedder import Embedder, build_embedder
from app.services.precedent.matcher import Matcher

_OPENAI_DIM = 1536  # text-embedding-3-small
_HASH_DIM = 16


class PrecedentSearch:
    def __init__(self, client=None, embedder: Embedder | None = None) -> None:
        self.embedder = embedder or build_embedder()  # 실 의미 임베더 또는 해시 폴백
        # 분석마다 격리 저장소(전역 누적 오염 방지). QDRANT_URL 설정 시 실 Qdrant(차원=임베더에 맞춤).
        dim = _OPENAI_DIM if self.embedder.is_semantic else _HASH_DIM
        self.client = client or build_qdrant(dim)
        self.ingest = CorpusIngest(self.client, self.embedder)
        self.matcher = Matcher(self.client, self.embedder)

    def search_cases(
        self, issue: object, corpus: list[PrecedentCase],
        top: int = 50, min_similarity: float | None = None,
    ) -> tuple[list[PrecedentCase], list[PrecedentMatch]]:
        """corpus 제공 시 즉석 적재 후 검색. 임계값 이상 유사사례만 반환(+매칭 메타).

        임계 자동: 실 의미 임베더면 0.75(의미유사), 해시 폴백이면 0.99(정확 쟁점일치 —
        양수벡터라 변별력 낮음). min_similarity 명시 시 그 값을 사용.
        """
        if min_similarity is None:
            min_similarity = 0.75 if self.embedder.is_semantic else 0.99
        if corpus:
            self.ingest.ingest(corpus)
        matches = [m for m in self.matcher.search(issue, top=top) if m.similarity >= min_similarity]
        by_id = {c.case_id: c for c in corpus}
        matched = [by_id[m.case_id] for m in matches if m.case_id in by_id]
        return matched, matches
