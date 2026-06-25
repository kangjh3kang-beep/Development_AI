"""시니어 심의위원 정량 평가기 — 다조항 동시검증(CSP)·unsat core.

deliberation_member spec(delib.multi_clause_csp)을 실제 입력으로 평가. 무목업: 결측 조항 생략.
입력(context['inputs']·각 쌍 제공 시 검증): bcr_actual/bcr_limit(건폐율%)·far_actual/far_limit(용적률%)·
height_actual/height_limit(높이m)·road_width_actual/road_width_required(접도m).
건폐/용적/높이=actual≤limit(초과 위반), 접도=actual≥required(미달 위반). 하나라도 위반 시 BLOCK.
"""

from __future__ import annotations

from app.services.senior_agents.evaluators.base import (
    BLOCK,
    PASS,
    RuleEvaluation,
    num,
)

# (입력 prefix, 라벨, 방향) — 방향 'max'=actual≤limit, 'min'=actual≥required.
_MAX_CLAUSES = (("bcr", "건폐율"), ("far", "용적률"), ("height", "높이"))


def evaluate_deliberation(inputs: dict) -> list[RuleEvaluation]:
    """건폐/용적/높이/접도 동시 적합성(CSP). 위반 조항을 unsat core로 명시."""
    checked: list[str] = []
    violations: list[str] = []

    # max-제약: actual ≤ limit (초과=위반).
    for key, label in _MAX_CLAUSES:
        a = num(inputs, f"{key}_actual")
        lim = num(inputs, f"{key}_limit")
        if a is not None and lim is not None:
            checked.append(label)
            if a > lim:
                violations.append(f"{label} {a:g}>{lim:g}")

    # min-제약(접도): actual ≥ required (미달=위반).
    rw_a = num(inputs, "road_width_actual")
    rw_r = num(inputs, "road_width_required")
    if rw_a is not None and rw_r is not None:
        checked.append("접도")
        if rw_a < rw_r:
            violations.append(f"접도 {rw_a:g}<{rw_r:g}")

    if not checked:
        return []

    verdict = BLOCK if violations else PASS
    detail = (f"동시검증 {len(checked)}개({'·'.join(checked)}): "
              + (f"위반(unsat core): {', '.join(violations)}" if violations else "전 조항 동시 충족"))
    return [RuleEvaluation(
        rule_id="delib.multi_clause_csp", label="다조항 동시검증", value=len(violations), unit="건",
        verdict=verdict, threshold="전 조항 동시 충족(위반 0)",
        basis="건축법·국토계획법 정량기준(건폐/용적/높이/접도)",
        detail=detail)]
