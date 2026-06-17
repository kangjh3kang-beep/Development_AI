"""L4 — 유사사례 계약. PrecedentCase(출처 강제)/PrecedentMatch(후보+유사도)/PrecedentStat(성숙도).

INV-22: 사례수 < 임계 → 통계 비제시. INV-23: 출처 없는 사례 금지(emit). INV-24: 매치는 후보일 뿐.
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from app.core.errors import SourceMissing


class DecisionType(str, Enum):
    APPROVED = "APPROVED"          # 원안의결
    CONDITIONAL = "CONDITIONAL"    # 조건부의결
    REDELIBERATION = "REDELIBERATION"  # 재심의
    REJECTED = "REJECTED"          # 부결


class StatStatus(str, Enum):
    SUFFICIENT = "SUFFICIENT"
    INSUFFICIENT = "INSUFFICIENT"  # 사례 부족


class PrecedentCase(BaseModel):
    case_id: str
    source: str | None = None  # 의결서 식별/링크 — 필수(INV-23)
    jurisdiction: str | None = None
    decision_type: DecisionType | None = None
    issue_labels: list[str] = Field(default_factory=list)
    conditions: list[str] = Field(default_factory=list)  # 보완요구 조건


class PrecedentMatch(BaseModel):
    case_id: str
    similarity: float
    is_candidate: bool = True  # 항상 후보(적용 단정 금지, INV-24)
    source: str | None = None


class PrecedentStat(BaseModel):
    issue: str
    status: StatStatus
    n: int = 0
    distribution: dict | None = None        # 의결유형 분포(부족 시 None)
    common_conditions: list[str] | None = None  # 반복 보완패턴(부족 시 None)


def emit(case: PrecedentCase) -> PrecedentCase:
    """출처 없는 사례 사용 금지(INV-23)."""
    if not case.source:
        raise SourceMissing(f"precedent case '{case.case_id}' has no source")
    return case
