"""L5 — 정량 이중경로 재검증. 명기(면적표) vs 기하(산정) 두 경로 대조. 허용오차 밴드(param).

밴드 내 → AGREED, 초과 → HELD(보류) + L5 전파. 무음 합치 금지.
"""
from __future__ import annotations

from pydantic import BaseModel

from app.contracts.enums import RecordStatus


class DualPathResult(BaseModel):
    table_value: float
    geom_value: float
    status: RecordStatus
    delta: float


class DualPathCheck:
    def __init__(self, tol: float) -> None:
        self.tol = tol

    def check(self, table: float, geom: float) -> DualPathResult:
        delta = abs(table - geom)
        ref = abs(table) or 1.0
        status = RecordStatus.AGREED if (delta / ref) <= self.tol else RecordStatus.HELD
        return DualPathResult(table_value=table, geom_value=geom, status=status, delta=delta)
