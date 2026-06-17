"""R2 — 원천 문서 계약. tier(수집 계층) + uri + content_hash(재현/정합)."""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel


class DocTier(str, Enum):
    TIER1 = "TIER1"  # 자치법규/행정규칙 공동활용 API + ELIS
    TIER2 = "TIER2"  # 화이트리스트 사이트
    TIER3 = "TIER3"  # 수기 등록


class SourceDocument(BaseModel):
    doc_id: str
    tier: DocTier
    uri: str
    content_hash: str
    jurisdiction: str | None = None
    title: str | None = None
