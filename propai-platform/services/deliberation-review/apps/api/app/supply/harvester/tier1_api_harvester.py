"""R2 — Tier1 수집(자치법규/행정규칙 공동활용 API + ELIS). 변경이력 diff(전량 재수집 회피).

라이브 호출은 LiveNetwork choke point 경유(공급측). 실패는 호출자(Harvester)가 fallback으로 흡수.
"""
from __future__ import annotations

from app.adapters.network import LiveNetwork
from app.contracts.source_document import DocTier, SourceDocument
from app.core.hashing import input_hash


class Tier1ApiHarvester:
    def __init__(self, network: LiveNetwork | None = None) -> None:
        self.network = network or LiveNetwork()

    def harvest(self, jurisdiction: str = "") -> list[SourceDocument]:
        # 변경분만 diff 수집. dev/mock에서는 LiveNetwork가 NetworkError → Harvester가 fallback.
        raw = self.network.get(f"https://api.elis.go.kr/diff?region={jurisdiction}")
        return [
            SourceDocument(
                doc_id=f"tier1-{jurisdiction}",
                tier=DocTier.TIER1,
                uri="https://api.elis.go.kr",
                content_hash=input_hash(raw),
                jurisdiction=jurisdiction,
            )
        ]
