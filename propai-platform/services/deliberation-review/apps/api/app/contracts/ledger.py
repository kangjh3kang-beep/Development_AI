"""R0 — 사실원장 계약(evidence ledger). 수량 레코드와 해소 결과 스키마.

충돌은 conflicts로 명시 기록, 해소 결과는 status(AGREED/HELD/MISSING)로 표면화(INV-2).
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.contracts.enums import Method, RecordStatus, Unit


class QuantityRecord(BaseModel):
    """단일 출처에서 적재된 수량 1건."""

    variable_id: str
    value: float
    unit: Unit = Unit.NONE
    source_sheet: str | None = None
    method: Method
    confidence: float = 1.0


class ConflictNote(BaseModel):
    """채택값과 불일치한 레코드의 충돌 기록."""

    method: Method
    value: float
    delta: float


class ResolvedQuantity(BaseModel):
    """원장 해소 결과(채택값 + 상태 + 충돌 + 신뢰도)."""

    variable_id: str
    value: float | None = None
    unit: Unit | None = None
    status: RecordStatus
    confidence: float = 0.0
    method: Method | None = None
    conflicts: list[ConflictNote] = Field(default_factory=list)
