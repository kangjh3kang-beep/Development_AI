"""R3 — 판정 결과 계약. 3값 verdict + 완화 + 합성 신뢰도 + 게이팅(INV-16/18).

완화 여지가 있으면 NON_COMPLIANT 단정 금지(거짓 불합격 금지). 임계 미달/충돌 → NEEDS_REVIEW.
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from app.contracts._types import FiniteFloat, Probability


class Verdict(str, Enum):
    COMPLIANT = "COMPLIANT"
    NON_COMPLIANT = "NON_COMPLIANT"
    CONDITIONAL = "CONDITIONAL"


class GatedStatus(str, Enum):
    CONFIRMED = "CONFIRMED"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class Finding(BaseModel):
    rule_id: str
    verdict: Verdict
    conditional_relaxations: list[str] = Field(default_factory=list)
    requires_committee: bool = False
    composite_confidence: Probability = 0.0
    # 미게이트 기본값 = NEEDS_REVIEW(보수적). FindingGate 통과 전엔 확정 아님(무음 오통과 금지).
    gated_status: GatedStatus = GatedStatus.NEEDS_REVIEW
    conflicts: list[str] = Field(default_factory=list)
    basis_article: str | None = None
    measured_value: FiniteFloat | None = None
    limit_value: FiniteFloat | None = None
