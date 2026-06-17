"""R3 — 완화/특례 전제 자동검증(WB8). 전제 룰 결과를 DAG로 참조하여 완화 적용 여부 산출.

전제 상태: MET(검증 충족)/PROVIDED(제공·확인 대기)/UNVERIFIABLE(검증 불가)/UNMET(검증 불충족).
- MET → 완화 해소(COMPLIANT). PROVIDED → CONDITIONAL. UNVERIFIABLE → CONDITIONAL+위원확인.
- 전부 UNMET → 완화 적용 불가(NON_COMPLIANT 허용). 완화 여지 있으면 거짓 불합격 금지(INV-16).
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.contracts.rule import Rule

MET = "MET"
PROVIDED = "PROVIDED"
UNVERIFIABLE = "UNVERIFIABLE"
UNMET = "UNMET"


class RelaxationOutcome(BaseModel):
    applies: bool = False
    resolves_to_compliant: bool = False
    requires_committee: bool = False
    applied_relaxations: list[str] = Field(default_factory=list)


def evaluate_relaxations(rule: Rule, states: dict[str, str]) -> RelaxationOutcome:
    if not rule.relaxations:
        return RelaxationOutcome()

    any_met = any_provided = any_unverifiable = False
    applied: list[str] = []

    for relax in rule.relaxations:
        key = relax.prerequisite_rule_id or relax.relaxation_id
        # 상태 미상 = UNMET 단정 금지 → UNVERIFIABLE(위원확인). 거짓 불합격 방지(INV-16).
        state = states.get(key, UNVERIFIABLE)
        if state == MET:
            any_met = True
            applied.append(relax.relaxation_id)
        elif state == PROVIDED:
            any_provided = True
            applied.append(relax.relaxation_id)
        elif state == UNVERIFIABLE:
            any_unverifiable = True
            applied.append(relax.relaxation_id)

    if any_met:
        return RelaxationOutcome(applies=True, resolves_to_compliant=True, applied_relaxations=applied)
    if any_provided:
        return RelaxationOutcome(applies=True, resolves_to_compliant=False, applied_relaxations=applied)
    if any_unverifiable:
        return RelaxationOutcome(
            applies=True, resolves_to_compliant=False, requires_committee=True, applied_relaxations=applied
        )
    return RelaxationOutcome()  # 전부 UNMET — 완화 미적용
