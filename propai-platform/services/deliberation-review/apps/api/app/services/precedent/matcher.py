"""L4 — 유사사례 검색(Qdrant). 상위 N 유사사례 + 유사도 점수. 결과는 후보일 뿐(INV-24).

소비측 경로 — 적재된 벡터만 조회, 라이브 수집 인라인 금지(INV-13/24). 출처 동반.
"""
from __future__ import annotations

from app.adapters.vector.qdrant_client import QdrantClientAdapter, default_qdrant
from app.contracts.precedent import PrecedentMatch
from app.services.precedent.embedder import Embedder


class Matcher:
    def __init__(self, client: QdrantClientAdapter | None = None, embedder: Embedder | None = None) -> None:
        self.client = client or default_qdrant()
        self.embedder = embedder or Embedder()

    def search(self, issue: object, top: int = 5) -> list[PrecedentMatch]:
        vector = self.embedder.embed(issue)
        results = self.client.search(vector, top=top)
        return [
            PrecedentMatch(
                case_id=cid,
                similarity=score,
                is_candidate=True,  # 적용 단정 금지 — 후보 표기
                source=payload["source"],
            )
            for score, cid, payload in results
            if payload.get("source")  # 출처 없는 사례는 소비 경계에서 제외(INV-23 방어)
        ]
