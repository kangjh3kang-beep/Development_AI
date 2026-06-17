"""L5 — 주장-근거 매핑 강제(INV-26). 정성/판정 주장은 근거 링크 동반. 무근거 주장 자동 제거.

(정량 주장은 calc_trace/method_trace가 근거.) 제거분은 removed로 표면화(무음 통과 금지).
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class ClaimEnforced(BaseModel):
    claims: list[str] = Field(default_factory=list)
    removed: list[str] = Field(default_factory=list)


class ClaimEvidence:
    def enforce(self, item: dict) -> ClaimEnforced:
        kept: list[str] = []
        removed: list[str] = []
        for claim in item.get("claims", []):
            text = claim.get("text")
            if claim.get("evidence_refs"):
                kept.append(text)
            else:
                removed.append(text)  # 무근거 → 제거
        return ClaimEnforced(claims=kept, removed=removed)
