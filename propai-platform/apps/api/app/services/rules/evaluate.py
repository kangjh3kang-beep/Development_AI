"""evaluate() — RuleDef 순수 평가 함수(입력→결과+trace). 같은 입력→같은 결과(결정론).

바인딩 검증(VariableRegistry.bind_rule)·산식 평가(expr.eval_expr)·한도 비교(Comparator)를
한 곳에서 오케스트레이션한다(심의엔진 CalcEngine.compute의 오케스트레이션 역할 계승).
입력 결손·미시행 규칙은 조용히 0/기본값으로 대체하지 않고 status=UNKNOWN으로 정직하게
표면화한다(무날조 원칙, INV-12 계승).
"""
from __future__ import annotations

from datetime import date

from app.services.provenance.fact_status import FactStatus
from app.services.rules.contracts import Comparator, RuleContractError, VariableRegistry
from app.services.rules.expr import ExprTraceStep, eval_expr
from app.services.rules.result import RuleResult, RuleTrace, RuleTraceEntry
from app.services.rules.rule_def import RuleDef

_COMPARATOR_FN = {
    Comparator.LE: lambda measured, limit: measured <= limit,
    Comparator.GE: lambda measured, limit: measured >= limit,
    Comparator.LT: lambda measured, limit: measured < limit,
    Comparator.GT: lambda measured, limit: measured > limit,
    Comparator.EQ: lambda measured, limit: measured == limit,
}


def _steps_to_note(label: str, steps: list[ExprTraceStep]) -> str:
    return f"{label}: " + " → ".join(f"{s.node}={s.value}" for s in steps)


def evaluate(
    rule: RuleDef,
    inputs: dict[str, float | None],
    registry: VariableRegistry,
    *,
    base_date: date | None = None,
) -> RuleResult:
    """규칙 1건을 평가한다.

    - 참조 변수 전부 미등록이면 RuleContractError(등록 거부 — 무음 통과 금지).
    - base_date가 주어지고 규칙 시행일(effective_date)보다 이전이면 미시행 → UNKNOWN.
    - inputs에 필수 입력이 결손(None/부재)이면 → UNKNOWN(0/기본값 대체 금지).
    - formula가 있으면 그 산식으로 target_variable 값을 산출, 없으면 inputs[target_variable]을
      측정값으로 간주(심의엔진 CalcRule처럼 산정 규칙과 준수판정 규칙 둘 다 표현 가능).
    - limit·comparator가 있으면 준수 여부(compliant)를 판정한다.
    """
    registry.bind_rule(rule.inputs)  # 미등록 변수 참조 시 RuleContractError(등록 거부).
    if not registry.is_registered(rule.target_variable):
        raise RuleContractError(f"rule target_variable not registered: {rule.target_variable}")

    trace = RuleTrace()

    if base_date is not None and rule.effective_date is not None and rule.effective_date > base_date:
        trace.entries.append(RuleTraceEntry(
            rule_id=rule.rule_id, basis_article=rule.basis_article,
            note=f"규칙 미시행(effective_date={rule.effective_date} > base_date={base_date}) — UNKNOWN",
        ))
        return RuleResult(
            rule_id=rule.rule_id, target_variable=rule.target_variable, value=None,
            unit=rule.unit, status=FactStatus.UNKNOWN, compliant=None,
            basis_article=rule.basis_article, trace=trace,
        )

    missing = [name for name in rule.inputs if inputs.get(name) is None]
    if missing:
        trace.entries.append(RuleTraceEntry(
            rule_id=rule.rule_id, basis_article=rule.basis_article,
            note=f"입력 결손(무날조 — 0/기본값 대체 금지): {missing}",
        ))
        return RuleResult(
            rule_id=rule.rule_id, target_variable=rule.target_variable, value=None,
            unit=rule.unit, status=FactStatus.UNKNOWN, compliant=None,
            basis_article=rule.basis_article, trace=trace,
        )

    if rule.formula is not None:
        steps: list[ExprTraceStep] = []
        value = eval_expr(rule.formula, inputs, rule.params, steps)
        trace.entries.append(RuleTraceEntry(
            rule_id=rule.rule_id, basis_article=rule.basis_article,
            note=_steps_to_note("산식평가", steps),
        ))
    else:
        # formula 없음 — target_variable 자체가 측정값(준수판정 전용 규칙).
        value = inputs.get(rule.target_variable)
        trace.entries.append(RuleTraceEntry(
            rule_id=rule.rule_id, basis_article=rule.basis_article,
            note=f"측정값 직접사용: {rule.target_variable}={value}",
        ))

    if value is None:
        trace.entries.append(RuleTraceEntry(
            rule_id=rule.rule_id, basis_article=rule.basis_article,
            note="산식 평가 결손(0나눔/입력결손) — UNKNOWN",
        ))
        return RuleResult(
            rule_id=rule.rule_id, target_variable=rule.target_variable, value=None,
            unit=rule.unit, status=FactStatus.UNKNOWN, compliant=None,
            basis_article=rule.basis_article, trace=trace,
        )

    compliant: bool | None = None
    if rule.limit is not None and rule.comparator is not None:
        limit_steps: list[ExprTraceStep] = []
        limit_value = eval_expr(rule.limit, inputs, rule.params, limit_steps)
        trace.entries.append(RuleTraceEntry(
            rule_id=rule.rule_id, basis_article=rule.basis_article,
            note=_steps_to_note("한도평가", limit_steps),
        ))
        if limit_value is None:
            trace.entries.append(RuleTraceEntry(
                rule_id=rule.rule_id, basis_article=rule.basis_article,
                note="한도 결손 — 준수판정 불가(compliant=None, 임의판정 금지)",
            ))
        else:
            compliant = _COMPARATOR_FN[rule.comparator](value, limit_value)
            trace.entries.append(RuleTraceEntry(
                rule_id=rule.rule_id, basis_article=rule.basis_article,
                note=f"판정: {value} {rule.comparator.value} {limit_value} → {compliant}",
            ))

    return RuleResult(
        rule_id=rule.rule_id, target_variable=rule.target_variable, value=value,
        unit=rule.unit, status=FactStatus.DERIVED, compliant=compliant,
        basis_article=rule.basis_article, trace=trace,
    )


def evaluate_many(
    rules: list[RuleDef],
    inputs: dict[str, float | None],
    registry: VariableRegistry,
    *,
    base_date: date | None = None,
    conflict_tolerance: float = 1e-6,
) -> dict[str, RuleResult]:
    """규칙 여러 건을 평가하고, 같은 target_variable에 상충하는 DERIVED 값이 나오면
    CONFLICT로 표면화한다(임의 승자 선정 금지 — 심의엔진 CrossValidation.CONFLICT 관례 계승).

    ★연계 접점(이월, 이번 승격 범위 아님): 법령 위계에 따른 CONFLICT 해소는
    ``app.services.legal.precedence_resolver.resolve_precedence``(W1-E #421)가 이미
    5단계(시행일→위임→특정성→상위법→신법우선)로 담당한다. 이 함수는 "값이 상충함"만
    표면화하고, 그 상충을 법령 위계로 해소하는 것은 여기서 재구현하지 않는다 — 호출부가
    필요 시 두 결과를 LegalSource로 변환해 resolve_precedence에 넘기는 것을 상정한다.
    """
    by_target: dict[str, list[RuleResult]] = {}
    for rule in rules:
        result = evaluate(rule, inputs, registry, base_date=base_date)
        by_target.setdefault(rule.target_variable, []).append(result)

    out: dict[str, RuleResult] = {}
    for target, results in by_target.items():
        derived = [r for r in results if r.status == FactStatus.DERIVED and r.value is not None]
        if len(derived) >= 2:
            values = [r.value for r in derived]
            if max(values) - min(values) > conflict_tolerance:
                conflicted = derived[0].model_copy(update={
                    "status": FactStatus.CONFLICT,
                    "trace": RuleTrace(entries=[
                        *derived[0].trace.entries,
                        RuleTraceEntry(
                            rule_id=derived[0].rule_id, basis_article=derived[0].basis_article,
                            note=(
                                f"상충(CONFLICT) — 규칙 {[r.rule_id for r in derived]}가 "
                                f"target_variable={target}에 서로 다른 값 {values} 산출. "
                                "임의 승자 선정 금지(양측 보존 — 법령위계 해소는 "
                                "precedence_resolver.resolve_precedence 연계 접점, 이번 범위 아님)."
                            ),
                        ),
                    ]),
                })
                out[target] = conflicted
                continue
        out[target] = results[-1]
    return out


__all__ = ["evaluate", "evaluate_many"]
