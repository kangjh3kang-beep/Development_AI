"""R3 — 신뢰도 합성(WB6/B). 독립 단계는 곱, 하드 게이트는 min-rule. 충돌 플래그는 하향 반영.

입력 confidence(추출/분류/산정/ledger 충돌)를 합성하여 composite 산출. 충돌 패널티 계수는 파라미터.
"""
from __future__ import annotations

from collections.abc import Iterable

from app.core.confidence import clamp01, combine
from app.core.parameters import param


class ConfidenceComposer:
    def compose(
        self,
        inputs: Iterable[float],
        conflicts: list | None = None,
        hard_gates: Iterable[float] | None = None,
    ) -> float:
        conflicts = conflicts or []
        composite = combine(inputs)  # 독립 단계 곱
        for gate in hard_gates or []:
            composite = min(composite, clamp01(gate))  # 하드 게이트 min-rule
        if conflicts:
            composite *= float(param("conflict_penalty_factor")) ** len(conflicts)
        return clamp01(composite)
