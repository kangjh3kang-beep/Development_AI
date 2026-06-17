"""R2 — 룰 후보 계약. 자동/LLM 추출은 DRAFT, HITL 승인 시 ACTIVE(INV-14).

DRAFT/REJECTED 후보는 분석에 사용 금지. ACTIVE만 미러 적재 대상.
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class CandidateStatus(str, Enum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    REJECTED = "REJECTED"


class RuleCandidate(BaseModel):
    candidate_id: str
    status: CandidateStatus = CandidateStatus.DRAFT
    target_variable: str | None = None
    content: dict = Field(default_factory=dict)
    source_doc_id: str | None = None
    confidence: float = 0.0
    jurisdiction: str | None = None
