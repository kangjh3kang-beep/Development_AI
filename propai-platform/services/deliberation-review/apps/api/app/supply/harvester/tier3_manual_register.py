"""R2 — Tier3 수기 등록 + 외부 실패 fallback(공부/수기). 라이브 호출 없음(비차단 적재 지속, INV-15)."""
from __future__ import annotations

from app.contracts.source_document import DocTier, SourceDocument
from app.core.hashing import input_hash


class Tier3ManualRegister:
    def register(self, jurisdiction: str, payload: dict) -> list[SourceDocument]:
        return [
            SourceDocument(
                doc_id=f"tier3-{jurisdiction}",
                tier=DocTier.TIER3,
                uri="manual://register",
                content_hash=input_hash(payload),
                jurisdiction=jurisdiction,
                title=payload.get("title"),
            )
        ]

    def register_fallback(self, jurisdiction: str = "") -> list[SourceDocument]:
        # 외부 API 다운 시 공부/수기 기반 최소 적재로 수집 지속.
        return self.register(jurisdiction, {"title": "fallback(공부/수기)", "source": "cadastral_or_manual"})
