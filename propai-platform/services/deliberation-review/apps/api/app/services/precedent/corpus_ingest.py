"""L4 — 의결서 코퍼스 적재/정규화(공급측, 비동기). 출처/일자/관할/쟁점 라벨 부여.

출처 없는 사례는 적재 거부(emit, INV-23). 임베딩하여 벡터 저장소에 upsert. 소비측은 적재분만 읽음.
"""
from __future__ import annotations

from app.adapters.vector.qdrant_client import QdrantClientAdapter, default_qdrant
from app.contracts.precedent import PrecedentCase, emit
from app.services.precedent.embedder import Embedder


class CorpusIngest:
    def __init__(self, client: QdrantClientAdapter | None = None, embedder: Embedder | None = None) -> None:
        self.client = client or default_qdrant()
        self.embedder = embedder or Embedder()

    def ingest(self, cases: list[PrecedentCase]) -> int:
        count = 0
        for case in cases:
            emit(case)  # 출처 강제(INV-23)
            key = case.issue_labels[0] if case.issue_labels else case.case_id
            vector = self.embedder.embed(key)
            self.client.upsert(
                case_id=case.case_id,
                vector=vector,
                payload={"source": case.source, "issue_labels": case.issue_labels},
            )
            count += 1
        return count
