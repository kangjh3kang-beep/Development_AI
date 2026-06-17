"""R3 — finding 게이팅(INV-18). composite < 임계(param) 또는 충돌 플래그 → NEEDS_REVIEW 분리.

단정 금지: 임계 미달/충돌은 확정(CONFIRMED) 대신 '확인 필요'로 분리한다.
"""
from __future__ import annotations

from app.contracts.finding import Finding, GatedStatus
from app.core.parameters import param


class FindingGate:
    def __init__(self, threshold: float | None = None) -> None:
        self.threshold = (
            threshold if threshold is not None else float(param("finding_confidence_threshold"))
        )

    def apply(self, finding: Finding) -> Finding:
        needs_review = finding.composite_confidence < self.threshold or bool(finding.conflicts)
        status = GatedStatus.NEEDS_REVIEW if needs_review else GatedStatus.CONFIRMED
        return finding.model_copy(update={"gated_status": status})
