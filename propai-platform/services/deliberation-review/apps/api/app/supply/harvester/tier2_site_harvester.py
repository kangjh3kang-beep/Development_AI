"""R2 — Tier2 수집(화이트리스트 사이트 전용 크롤러/다운로더). 비화이트리스트 차단.

라이브 호출은 LiveNetwork 경유. 화이트리스트 외 도메인은 거부(보안/INV-13 공급경계).
"""
from __future__ import annotations

from app.adapters.network import LiveNetwork, NetworkError, host_allowed
from app.contracts.source_document import DocTier, SourceDocument
from app.core.hashing import input_hash


class Tier2SiteHarvester:
    def __init__(self, network: LiveNetwork | None = None) -> None:
        self.network = network or LiveNetwork()

    def harvest(self, url: str, jurisdiction: str = "") -> list[SourceDocument]:
        # hostname 정확/접미사 매칭(host_allowed) — substring 우회(law.go.kr.evil.com) 차단.
        if not host_allowed(url):
            raise NetworkError(f"non-whitelisted source rejected: {url}")
        raw = self.network.get(url)
        return [
            SourceDocument(
                doc_id=f"tier2-{jurisdiction}",
                tier=DocTier.TIER2,
                uri=url,
                content_hash=input_hash(raw),
                jurisdiction=jurisdiction,
            )
        ]
