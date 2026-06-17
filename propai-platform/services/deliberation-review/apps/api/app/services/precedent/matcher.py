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
        method = f"{'semantic' if self.embedder.is_semantic else 'hash-fallback'} embed + cosine"
        caveats = [
            "코사인 부동소수 오차로 [-1,1] 클램프 보정",
            f"상위 {top}건만 반환(절단) — 그 외 사례 미표시",
            "후보일 뿐 적용 단정 금지(INV-24)",
        ]
        return [
            PrecedentMatch(
                case_id=cid,
                # 부동소수 오차로 |cos|가 1을 미세 초과(예: 1.0000000000000002)할 수 있어 [-1,1]로 보정.
                similarity=max(-1.0, min(1.0, float(score))),
                is_candidate=True,  # 적용 단정 금지 — 후보 표기
                source=payload["source"],
                method=method, caveats=caveats,
            )
            for score, cid, payload in results
            if payload.get("source")  # 출처 없는 사례는 소비 경계에서 제외(INV-23 방어)
        ]
