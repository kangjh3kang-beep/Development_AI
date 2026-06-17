"""R3 — 3값 결정론 평가(L3-A). 룰 → COMPLIANT/NON_COMPLIANT/CONDITIONAL(INV-16).

입력: R1.5 LegalQuantity(measured) + R2 미러 룰셋(limit). 위반이라도 완화 여지 있으면 단정 금지.
전제 검증 불가 → requires_committee, NON_COMPLIANT 금지.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.contracts._types import Probability
from app.contracts.enums import Comparator
from app.contracts.finding import Finding, Verdict
from app.contracts.rule import Rule
from app.core.errors import RuleContractError
from app.services.judge.relaxation import evaluate_relaxations


class EvalCase(BaseModel):
    rule: Rule
    measured_value: float | None = None
    limit_value: float | None = None
    relaxation_states: dict[str, str] = Field(default_factory=dict)
    input_confidence: Probability = 1.0
    conflicts: list[str] = Field(default_factory=list)


class Evaluator:
    def eval(self, case: EvalCase) -> Finding:
        verdict, requires_committee, applied = self._decide(case)
        return Finding(
            rule_id=case.rule.rule_id,
            verdict=verdict,
            conditional_relaxations=applied,
            requires_committee=requires_committee,
            composite_confidence=case.input_confidence,
            conflicts=case.conflicts,
            basis_article=case.rule.basis_article,
            measured_value=case.measured_value,
            limit_value=case.limit_value,
        )

    def _decide(self, case: EvalCase) -> tuple[Verdict, bool, list[str]]:
        if case.measured_value is None or case.limit_value is None:
            # 측정/기준 미확정 — 단정 금지, 위원 확인.
            return Verdict.CONDITIONAL, True, []

        if not self._violates(case):
            return Verdict.COMPLIANT, False, []

        outcome = evaluate_relaxations(case.rule, case.relaxation_states)
        if not outcome.applies:
            return Verdict.NON_COMPLIANT, False, []
        if outcome.resolves_to_compliant:
            return Verdict.COMPLIANT, False, outcome.applied_relaxations
        return Verdict.CONDITIONAL, outcome.requires_committee, outcome.applied_relaxations

    @staticmethod
    def _violates(case: EvalCase) -> bool:
        measured, limit = case.measured_value, case.limit_value
        comparator = case.rule.comparator
        if comparator == Comparator.LE:
            return measured > limit
        if comparator == Comparator.GE:
            return measured < limit
        if comparator == Comparator.LT:
            return measured >= limit
        if comparator == Comparator.GT:
            return measured <= limit
        if comparator == Comparator.EQ:
            return measured != limit
        # enum이라 도달 불가 — 미정의 comparator 무음 '!=' 폴백 제거(방어).
        raise RuleContractError(f"unsupported comparator: {comparator}")
