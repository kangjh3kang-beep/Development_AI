"""R0 — 사실원장(EvidenceLedger). 수량 적재 + 충돌 해소(파라미터화, 하드코딩 금지).

해소 정책:
- 단일 레코드: status=AGREED.
- 복수 레코드: 명기(TABLE) 우선 채택. 허용오차 밴드 내 → AGREED, 초과 → HELD(보류) +
  conflict 기록 + 신뢰도 하향(INV-2).
- 결손(레코드 0): status=MISSING("데이터 미충족"). 무음 skip 금지.
허용오차/하향계수는 파라미터(param) 주입.
"""
from __future__ import annotations

from app.contracts.enums import Method, RecordStatus, Unit
from app.contracts.ledger import ConflictNote, QuantityRecord, ResolvedQuantity
from app.core.confidence import degrade
from app.core.parameters import param

# 명기(TABLE) 우선 채택 — 방법 우선순위(법정 수치 아님, 정책 순서).
_METHOD_PRIORITY = {Method.TABLE: 0, Method.VECTOR: 1, Method.VLLM: 2, Method.OCR: 3}


class EvidenceLedger:
    def __init__(self, tol_band: float | None = None, penalty_factor: float | None = None) -> None:
        self.tol_band = tol_band
        self.penalty_factor = penalty_factor
        self._records: dict[str, list[QuantityRecord]] = {}

    def add(
        self,
        variable_id: str,
        value: float,
        method: Method,
        unit: Unit = Unit.NONE,
        source_sheet: str | None = None,
        confidence: float = 1.0,
    ) -> QuantityRecord:
        rec = QuantityRecord(
            variable_id=variable_id, value=value, unit=unit,
            method=method, source_sheet=source_sheet, confidence=confidence,
        )
        self._records.setdefault(variable_id, []).append(rec)
        return rec

    def resolve(self, variable_id: str) -> ResolvedQuantity:
        recs = self._records.get(variable_id, [])

        if not recs:
            # 결손 — 무음 skip 금지, 명시적 MISSING.
            return ResolvedQuantity(
                variable_id=variable_id, value=None, status=RecordStatus.MISSING, confidence=0.0
            )

        adopted = sorted(
            recs, key=lambda r: (_METHOD_PRIORITY.get(r.method, len(_METHOD_PRIORITY)), -r.confidence)
        )[0]

        if len(recs) == 1:
            return ResolvedQuantity(
                variable_id=variable_id, value=adopted.value, unit=adopted.unit,
                status=RecordStatus.AGREED, confidence=adopted.confidence, method=adopted.method,
            )

        values = [r.value for r in recs]
        spread = max(values) - min(values)
        ref = abs(adopted.value) or 1.0
        band = self.tol_band if self.tol_band is not None else param("area_tol")

        if spread / ref <= band:
            # 밴드 내 — 명기 채택 + 합의.
            return ResolvedQuantity(
                variable_id=variable_id, value=adopted.value, unit=adopted.unit,
                status=RecordStatus.AGREED, confidence=adopted.confidence, method=adopted.method,
            )

        # 밴드 초과 — 명기 채택 + 보류 + 충돌 기록 + 신뢰도 하향.
        penalty = self.penalty_factor if self.penalty_factor is not None else param("conflict_penalty_factor")
        conflicts = [
            ConflictNote(method=r.method, value=r.value, delta=abs(r.value - adopted.value))
            for r in recs
            if r is not adopted
        ]
        return ResolvedQuantity(
            variable_id=variable_id, value=adopted.value, unit=adopted.unit,
            status=RecordStatus.HELD, confidence=degrade(adopted.confidence, penalty),
            method=adopted.method, conflicts=conflicts,
        )
