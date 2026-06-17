"""R1.5 — 법정 산정 계약. LegalQuantity + CalcTrace(근거조문/제외규정) + CalcElement.

INV-10: 값 보유 산정값은 calc_trace 필수(emit가 강제). INV-12: 분류 confidence 상속/HELD.
CalcElement는 R0.5 SemanticElement(타입+confidence)를 산정 계층 입력으로 투영(+측정치).
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from app.contracts._types import FiniteFloat, Probability
from app.contracts.enums import RecordStatus, Unit
from app.contracts.semantic_element import SemanticElement, SemanticType
from app.core.errors import CalcTraceMissing


class CalcTraceEntry(BaseModel):
    """단일 산정 규칙 적용 기록(근거조문 + 제외 요소 + 정량 근거)."""

    rule_id: str
    basis_article: str
    excluded_elements: list[SemanticType] = Field(default_factory=list)
    note: str | None = None
    # 제외 정량 근거(설명가능성) — 적용 임계·단위·실측·차감량. 재현·검증 가능하게.
    threshold: float | None = None
    threshold_unit: str | None = None
    measured: float | None = None
    excluded_amount: float | None = None


class CalcTrace(BaseModel):
    """산정 근거 추적(적용 규칙들의 누적)."""

    entries: list[CalcTraceEntry] = Field(default_factory=list)

    def has(self, semantic_type: SemanticType, art: str | None = None) -> bool:
        """특정 요소타입이 (선택적으로 근거조문 art 포함) 제외 기록됐는지."""
        for e in self.entries:
            if semantic_type in e.excluded_elements and (art is None or art in e.basis_article):
                return True
        return False


class CalcTarget(str, Enum):
    """산정 대상 변수(변수사전 id와 1:1)."""

    BUILDING_AREA = "building_area"
    GROSS_FLOOR_AREA = "gross_floor_area"
    FAR_FLOOR_AREA = "far_floor_area"
    PLOT_AREA = "plot_area"
    BUILDING_HEIGHT = "building_height"
    FLOOR_COUNT = "floor_count"


class CalcElement(BaseModel):
    """산정 입력 요소 — 의미타입 + 제외 측정치 + 분류 신뢰도(상속용)."""

    semantic_type: SemanticType
    confidence: Probability = 1.0
    area: float = 0.0
    length: float = 0.0
    depth: float = 0.0
    element_id: str | None = None

    @classmethod
    def from_semantic(
        cls,
        se: SemanticElement,
        area: float = 0.0,
        length: float = 0.0,
        depth: float = 0.0,
    ) -> "CalcElement":
        return cls(
            semantic_type=se.semantic_type,
            confidence=se.confidence,
            area=area,
            length=length,
            depth=depth,
            element_id=se.element_id,
        )


class LegalQuantity(BaseModel):
    """법정 산정값 1건(변수사전 id 바인딩 + 근거추적 + 상태)."""

    variable_id: str
    value: FiniteFloat | None = None
    unit: Unit = Unit.M2
    status: RecordStatus = RecordStatus.AGREED
    confidence: Probability = 0.0
    calc_trace: CalcTrace | None = None
    calc_rule_version: str | None = None
    snapshot_id: str | None = None


def emit(q: LegalQuantity) -> LegalQuantity:
    """출력 게이트 — 값 보유 산정값에 calc_trace 부재 시 거부(INV-10)."""
    if q.value is not None and q.calc_trace is None:
        raise CalcTraceMissing(f"legal quantity '{q.variable_id}' has value without calc_trace")
    return q
