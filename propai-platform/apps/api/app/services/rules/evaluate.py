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
from app.services.rules.expr import ExprTraceStep, collect_refs, eval_expr
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


def _validate_ast_refs(rule: RuleDef, registry: VariableRegistry) -> None:
    """formula/limit 산식이 실제로 참조하는 VarRef/ParamRef가 선언(등록 registry/rule.params)과
    일치하는지 대조한다 — 유령 참조(수기 작성한 inputs/params와 산식의 괴리)를 무음 UNKNOWN
    강등이 아니라 등록 거부(RuleContractError)로 표면화한다(bind_rule의 사각지대 보완).
    """
    var_refs: set[str] = set()
    param_refs: set[str] = set()
    for node in (rule.formula, rule.limit):
        if node is not None:
            v, p = collect_refs(node)
            var_refs |= v
            param_refs |= p

    unregistered_vars = sorted(name for name in var_refs if not registry.is_registered(name))
    if unregistered_vars:
        raise RuleContractError(
            f"rule formula/limit references unregistered variable(s): {unregistered_vars}"
        )
    undeclared_params = sorted(name for name in param_refs if name not in rule.params)
    if undeclared_params:
        raise RuleContractError(
            f"rule formula/limit references param(s) not declared in rule.params: {undeclared_params}"
        )


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
    _validate_ast_refs(rule, registry)  # formula/limit 유령 참조(수기 inputs/params와 괴리) 등록 거부.

    trace = RuleTrace()

    if rule.effective_date is not None and base_date is None:
        # fail-open 차단: base_date를 안 주면 "시제 검증을 생략"이 아니라 "시제 미해소"로
        # 취급한다 — 그렇지 않으면 미래 시행 규칙이 base_date 누락만으로 DERIVED로 오적용될
        # 수 있다(HIGH-2). 임의로 "이미 시행 중"이라 간주하지 않는다.
        trace.entries.append(RuleTraceEntry(
            rule_id=rule.rule_id, basis_article=rule.basis_article,
            note="시제 미해소 — base_date 미제공, 임의 시행 간주 금지",
        ))
        return RuleResult(
            rule_id=rule.rule_id, target_variable=rule.target_variable, value=None,
            unit=rule.unit, status=FactStatus.UNKNOWN, compliant=None,
            basis_article=rule.basis_article, trace=trace,
        )

    if rule.effective_date is not None and base_date is not None and rule.effective_date > base_date:
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


def _pick_representative(results: list[RuleResult]) -> RuleResult:
    """리스트 순서(위치)가 아니라 rule_id 사전순으로 대표값을 고른다 — 호출부가 같은 규칙
    집합을 다른 순서로 넘겨도 항상 같은 대표가 뽑힌다(순서 불변성, HIGH-1)."""
    return min(results, key=lambda r: r.rule_id)


def _merge_conservative_unknown(target: str, results: list[RuleResult]) -> RuleResult:
    """같은 target_variable에 UNKNOWN이 하나라도 섞여 있으면 target 전체를 UNKNOWN으로
    보수화한다(부분근거로 확정 금지 — 어떤 규칙이 UNKNOWN인지는 위치가 아니라 상태로
    판정하므로, 규칙 나열 순서를 뒤바꿔도 항상 동일하게 UNKNOWN이 된다).

    단, 정보 소실을 막기 위해 DERIVED로 산출됐던 후보값·rule_id는 trace에 남긴다(완전히
    버리지 않음 — 감사 가능성 보존).
    """
    merged_entries = [entry for r in results for entry in r.trace.entries]
    derived_candidates = sorted(
        (r for r in results if r.status == FactStatus.DERIVED and r.value is not None),
        key=lambda r: r.rule_id,
    )
    if derived_candidates:
        candidates_desc = ", ".join(f"{r.rule_id}={r.value}" for r in derived_candidates)
        note = (
            f"target_variable={target}: 규칙 중 UNKNOWN이 있어 부분근거 확정 금지 — target "
            f"전체를 UNKNOWN으로 보수화(DERIVED 후보 보존, 정보 소실 방지: {candidates_desc})"
        )
    else:
        note = f"target_variable={target}: 규칙 중 UNKNOWN이 있어 target 전체 UNKNOWN 보수화"

    representative = _pick_representative(results)
    merged_entries.append(RuleTraceEntry(
        rule_id=representative.rule_id, basis_article=representative.basis_article, note=note,
    ))
    return representative.model_copy(update={
        "status": FactStatus.UNKNOWN, "value": None, "compliant": None,
        "trace": RuleTrace(entries=merged_entries),
    })


def _merge_conflict(target: str, derived: list[RuleResult], values: list[float]) -> RuleResult:
    """DERIVED 값 2건 이상이 상충하면 CONFLICT로 표면화한다(임의 승자 선정 금지 — 심의엔진
    CrossValidation.CONFLICT 관례 계승). 상충 전 각 규칙의 산식평가 trace를 전부 병합 보존한다
    (패자 규칙의 trace를 대표 1건 것만 남기고 버리지 않음 — MEDIUM-3).

    ★연계 접점(이월, 이번 승격 범위 아님): 법령 위계에 따른 CONFLICT 해소는
    ``app.services.legal.precedence_resolver.resolve_precedence``(W1-E #421)가 이미
    5단계(시행일→위임→특정성→상위법→신법우선)로 담당한다. 이 함수는 "값이 상충함"만
    표면화하고, 그 상충을 법령 위계로 해소하는 것은 여기서 재구현하지 않는다 — 호출부가
    필요 시 두 결과를 LegalSource로 변환해 resolve_precedence에 넘기는 것을 상정한다.
    """
    merged_entries = [entry for r in derived for entry in r.trace.entries]
    representative = _pick_representative(derived)
    merged_entries.append(RuleTraceEntry(
        rule_id=representative.rule_id, basis_article=representative.basis_article,
        note=(
            f"상충(CONFLICT) — 규칙 {sorted(r.rule_id for r in derived)}가 "
            f"target_variable={target}에 서로 다른 값 {values} 산출. "
            "임의 승자 선정 금지(양측 보존 — 법령위계 해소는 "
            "precedence_resolver.resolve_precedence 연계 접점, 이번 범위 아님)."
        ),
    ))
    return representative.model_copy(update={
        "status": FactStatus.CONFLICT,
        "trace": RuleTrace(entries=merged_entries),
    })


def evaluate_many(
    rules: list[RuleDef],
    inputs: dict[str, float | None],
    registry: VariableRegistry,
    *,
    base_date: date | None = None,
    conflict_tolerance: float = 1e-6,
) -> dict[str, RuleResult]:
    """규칙 여러 건을 평가하고, 같은 target_variable의 결과들을 병합 정책에 따라 합친다.

    병합 정책(위치 기반 임의 채택 금지 — HIGH-1, 규칙 나열 순서를 바꿔도 항상 동일 결과):
    1) 결과가 1건뿐이면 그대로 반환한다.
    2) UNKNOWN이 하나라도 있으면 target 전체를 UNKNOWN으로 보수화한다(부분근거 확정 금지 —
       ``_merge_conservative_unknown``). DERIVED 후보값은 trace에 보존한다.
    3) UNKNOWN이 없고 DERIVED가 2건 이상이며 값이 상충하면 CONFLICT로 표면화한다
       (``_merge_conflict`` — 임의 승자 선정 금지, 심의엔진 CrossValidation.CONFLICT 계승).
    4) 그 외(단독 DERIVED 1건, 또는 DERIVED 다건이지만 값이 합의)에는 rule_id 사전순 대표를
       반환한다(위치가 아니라 내용 기반 결정 — 순서 불변).
    """
    by_target: dict[str, list[RuleResult]] = {}
    for rule in rules:
        result = evaluate(rule, inputs, registry, base_date=base_date)
        by_target.setdefault(rule.target_variable, []).append(result)

    out: dict[str, RuleResult] = {}
    for target, results in by_target.items():
        if len(results) == 1:
            out[target] = results[0]
            continue

        if any(r.status == FactStatus.UNKNOWN for r in results):
            out[target] = _merge_conservative_unknown(target, results)
            continue

        derived = [r for r in results if r.status == FactStatus.DERIVED and r.value is not None]
        if len(derived) >= 2:
            values = [r.value for r in derived]
            if max(values) - min(values) > conflict_tolerance:
                out[target] = _merge_conflict(target, derived, values)
                continue

        out[target] = _pick_representative(results)
    return out


__all__ = ["evaluate", "evaluate_many"]
