"""R3 — 매핑 게이트(WB5). 지자체 기준 → 표준 심의항목 매핑. 신뢰도 < 임계 → 정성 보류(HELD).

무음 오통과 금지: 저신뢰 매핑은 silent_pass=False로 명시하고 HELD로 분리.
"""
from __future__ import annotations

from pydantic import BaseModel

from app.contracts.enums import RecordStatus
from app.core.parameters import param


class MappingResult(BaseModel):
    source_criterion: str | None = None
    standard_item: str | None = None
    status: RecordStatus = RecordStatus.AGREED
    confidence: float = 0.0
    silent_pass: bool = False


class MappingGate:
    def __init__(self, threshold: float | None = None) -> None:
        self.threshold = (
            threshold if threshold is not None else float(param("mapping_confidence_threshold"))
        )

    def map(self, mapping: dict) -> MappingResult:
        confidence = float(mapping.get("confidence", 0.0))
        held = confidence < self.threshold
        return MappingResult(
            source_criterion=mapping.get("source_criterion"),
            standard_item=mapping.get("standard_item"),
            status=RecordStatus.HELD if held else RecordStatus.AGREED,
            confidence=confidence,
            silent_pass=False,  # 저신뢰든 아니든 무음 통과 금지.
        )
