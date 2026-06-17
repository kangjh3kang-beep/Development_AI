"""L5 — 검증 계약. VerificationResult(인용 실재/시행일/내용) + ClaimEvidenceLink + 최종 게이팅 상태.

INV-25: 미검증 인용 출력 차단. INV-26: 무근거 주장 제거. INV-27: 최종 분류 단일화.
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class VerificationResult(BaseModel):
    citation_ref: str | None = None
    passed: bool = False
    checks: dict = Field(default_factory=dict)  # exists/effective/content
    reason: str | None = None


class ClaimEvidenceLink(BaseModel):
    claim: str
    evidence_refs: list[str] = Field(default_factory=list)
    supported: bool = False


class FinalStatus(str, Enum):
    CONFIRMED = "CONFIRMED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    BLOCKED = "BLOCKED"  # 미검증 — 출력 차단


class GateItem(BaseModel):
    item_id: str | None = None
    composite_confidence: float = 0.0
    conflicts: list = Field(default_factory=list)
    verification: VerificationResult | None = None
    dual_path_status: str | None = None  # 정량 이중경로 결과(HELD면 확정 불가)


class GateResult(BaseModel):
    status: FinalStatus
    composite_confidence: float = 0.0
    reason: str | None = None
