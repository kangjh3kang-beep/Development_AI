"""L3-C — 정성 평가 계약. QualAssessment(등급+인용+상태) + RubricCitation.

INV-31: 인용 없는 정성 판단 금지(emit). INV-33: 등급만 표현, 법적 단정 금지(asserts_legal_verdict=False).
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel

from app.contracts._types import Probability
from app.core.errors import CitationRequired


class QualGrade(str, Enum):
    HIGH = "HIGH"      # 부합도 높음
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    NONE = "NONE"


class QualStatus(str, Enum):
    GRADED = "GRADED"
    HELD = "HELD"                    # 매핑 저신뢰 — 평가 보류
    DISCRETION_HELD = "DISCRETION_HELD"  # 기준 미존재 — 재량영역


class RubricCitation(BaseModel):
    rubric_item: str
    source: str  # 공표 심의기준 출처
    effective: bool = True


class QualAssessment(BaseModel):
    assessment_id: str | None = None
    item: str | None = None
    grade: QualGrade | None = None
    citation: RubricCitation | None = None
    confidence: Probability = 0.0
    status: QualStatus = QualStatus.GRADED
    is_grade: bool = True               # 등급 표현(INV-33)
    asserts_legal_verdict: bool = False  # 법적 단정 금지(항상 False, INV-33)
    snapshot_id: str | None = None
    model_version: str | None = None


def emit(assessment: QualAssessment) -> QualAssessment:
    """등급 판단(GRADED)에 기준 항목 인용(비어있지 않은 rubric_item) 부재 시 거부(INV-31)."""
    if assessment.status == QualStatus.GRADED and (
        assessment.citation is None or not assessment.citation.rubric_item
    ):
        raise CitationRequired(f"qualitative assessment '{assessment.item}' graded without citation")
    return assessment
