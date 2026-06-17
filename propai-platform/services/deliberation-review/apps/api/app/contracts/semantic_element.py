"""R0.5 — 요소 의미분류 계약(L1.1). 불확실 시 임의 타입 금지 → UNKNOWN + confidence 하향(INV-9).

cross-sheet 매칭 결과는 identity_status로 표면화(매칭 실패=UNMATCHED, 날조 금지).
하류(R1.5 산정계층)는 semantic_type 태그를 소비.
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class SemanticType(str, Enum):
    """요소 의미타입. UNKNOWN은 불확실의 명시(임의 기본값 금지)."""

    PILOTIS = "PILOTIS"
    BALCONY = "BALCONY"
    EAVE = "EAVE"
    BASEMENT = "BASEMENT"
    PARKING = "PARKING"
    CORE_STAIR = "CORE_STAIR"
    EXT_WALL = "EXT_WALL"
    PLOT_BOUNDARY = "PLOT_BOUNDARY"
    BUILDING_LINE = "BUILDING_LINE"
    UNKNOWN = "UNKNOWN"


class IdentityStatus(str, Enum):
    """cross-sheet 동일성 상태."""

    MATCHED = "MATCHED"
    UNMATCHED = "UNMATCHED"
    SINGLE = "SINGLE"


class SemanticElement(BaseModel):
    """의미 분류된 요소 1건(confidence/provenance 동반)."""

    element_id: str
    semantic_type: SemanticType
    confidence: float = 0.0
    identity_status: IdentityStatus = IdentityStatus.SINGLE
    source_sheets: list[str] = Field(default_factory=list)
    provenance: dict = Field(default_factory=dict)
