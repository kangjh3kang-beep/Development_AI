"""L3-C — 공표 루브릭 접지(INV-31). 도면 사실 → 공표 심의기준 항목 매핑 + 인용.

R3 mapping_gate 신뢰도 게이트 적용. 저신뢰 → 평가 보류(HELD). 기준 미존재 → 재량영역(DISCRETION_HELD).
규칙 신설 금지 — 기존 공표 기준 항목만 인용.
"""
from __future__ import annotations

from pydantic import BaseModel

from app.contracts.enums import RecordStatus
from app.contracts.qualitative import QualStatus, RubricCitation
from app.services.mapping.mapping_gate import MappingGate


class GroundingResult(BaseModel):
    status: QualStatus
    citation: RubricCitation | None = None
    confidence: float = 0.0


class RubricGrounding:
    def __init__(self, threshold: float | None = None) -> None:
        self.gate = MappingGate(threshold=threshold)

    def ground(self, fact: dict) -> GroundingResult:
        if not fact.get("criterion_exists", True):
            # 공표 기준 미존재 → 재량영역(단정 금지).
            return GroundingResult(status=QualStatus.DISCRETION_HELD)

        if not fact.get("candidate_rubric"):
            # 인용할 실재 루브릭 항목 미매핑 → 평가 보류(빈 인용 등급화 금지, INV-31).
            return GroundingResult(
                status=QualStatus.HELD, confidence=float(fact.get("mapping_confidence", 0.0))
            )

        mapping = {
            "source_criterion": fact.get("feature"),
            "standard_item": fact.get("candidate_rubric"),
            "confidence": fact.get("mapping_confidence", 0.0),
        }
        result = self.gate.map(mapping)
        if result.status == RecordStatus.HELD:
            # 매핑 저신뢰 → 평가 보류(무음 평가 금지).
            return GroundingResult(status=QualStatus.HELD, confidence=result.confidence)

        citation = RubricCitation(
            rubric_item=fact.get("candidate_rubric", ""),
            source=fact.get("rubric_source", "공표 심의기준"),
        )
        return GroundingResult(status=QualStatus.GRADED, citation=citation, confidence=result.confidence)
