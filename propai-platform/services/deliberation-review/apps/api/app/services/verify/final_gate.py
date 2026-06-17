"""L5 — 최종 게이팅 단일화(INV-27). 합성 신뢰도 + 검증상태 결합 → CONFIRMED/NEEDS_REVIEW/BLOCKED.

미검증 인용 → BLOCKED. 미검증(verification 부재) 또는 임계 미달/충돌 → NEEDS_REVIEW. 단정 금지.
임계는 param. L6로는 이 분류로만 진입.
"""
from __future__ import annotations

from app.contracts.verification import FinalStatus, GateItem, GateResult
from app.core.parameters import param


class FinalGate:
    def __init__(self, threshold: float | None = None) -> None:
        self.threshold = (
            threshold if threshold is not None else float(param("finding_confidence_threshold"))
        )

    def apply(self, item: GateItem) -> GateResult:
        verification = item.verification

        if verification is not None and not verification.passed:
            return GateResult(
                status=FinalStatus.BLOCKED,
                composite_confidence=item.composite_confidence,
                reason="citation_unverified",
            )

        # 검증 결과 부재 = 미확정 → 확정 불가(보수적으로 NEEDS_REVIEW). 강등 사유 라벨(무음 강등 금지).
        reasons: list[str] = []
        status = FinalStatus.CONFIRMED if verification is not None else FinalStatus.NEEDS_REVIEW
        if verification is None:
            reasons.append("unverified(검증결과 부재)")

        # 정량 이중경로 불일치(HELD)/임계 미달/충돌 → 확정 불가(무음 오판 금지).
        if item.composite_confidence < self.threshold:
            status = FinalStatus.NEEDS_REVIEW
            reasons.append(f"below_threshold({round(item.composite_confidence, 2)}<{self.threshold})")
        if item.conflicts:
            status = FinalStatus.NEEDS_REVIEW
            reasons.append("conflict")
        if item.dual_path_status == "HELD":
            status = FinalStatus.NEEDS_REVIEW
            reasons.append("dual_path_HELD")

        return GateResult(
            status=status, composite_confidence=item.composite_confidence,
            reason="; ".join(reasons) if reasons else None)
