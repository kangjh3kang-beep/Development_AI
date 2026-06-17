"""P1 — BIM/IFC 계약. BimElement/BimModel + 추출 출처(BIM↔VLLM 이중경로).

BIM(IFC) 있으면 구조화 추출(2D 도면 한계 보완), 없으면 VLLM 추출. 미매핑 IFC타입 → UNKNOWN(INV-9).
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.contracts.semantic_element import SemanticType


class BimElement(BaseModel):
    ifc_type: str
    semantic_type: SemanticType = SemanticType.UNKNOWN
    name: str | None = None
    guid: str | None = None
    storey: str | None = None
    area: float | None = None
    length: float | None = None


class BimModel(BaseModel):
    elements: list[BimElement] = Field(default_factory=list)
    source: str = "BIM"


class ExtractionResult(BaseModel):
    """이중경로 추출 결과. source = BIM | VLLM | none."""

    source: str
    bim: BimModel | None = None
    semantic_elements: list = Field(default_factory=list)  # SemanticElement[]
    note: str | None = None
