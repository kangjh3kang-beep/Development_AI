"""AT-1/AT-2/AT-3 — 3값 판정: 완화 여지→CONDITIONAL(거짓 불합격 금지), 전제 충족→COMPLIANT,
전제 검증불가→위원확인 유지."""
from app.contracts.finding import Verdict
from app.contracts.rule import Relaxation, Rule
from app.services.judge.evaluator import EvalCase, Evaluator

_FAR_RULE = Rule(
    rule_id="far_limit",
    target_variable="far_floor_area",
    comparator="<=",
    relaxations=[Relaxation(relaxation_id="far_relax_public", prerequisite_rule_id="public_space")],
    basis_article="국토계획법 시행령",
)


def _case(state: str) -> EvalCase:
    return EvalCase(
        rule=_FAR_RULE,
        measured_value=250.0,   # 용적률 초과(>200)
        limit_value=200.0,
        relaxation_states={"public_space": state},
    )


def test_relaxation_yields_conditional_not_fail():
    f = Evaluator().eval(_case("PROVIDED"))
    assert f.verdict in (Verdict.CONDITIONAL, Verdict.COMPLIANT)
    assert f.verdict != Verdict.NON_COMPLIANT


def test_relaxation_prerequisite_met_resolves():
    f = Evaluator().eval(_case("MET"))
    assert f.verdict == Verdict.COMPLIANT


def test_relaxation_unverifiable_holds():
    f = Evaluator().eval(_case("UNVERIFIABLE"))
    assert f.requires_committee is True
    assert f.verdict != Verdict.NON_COMPLIANT


def test_no_relaxation_violation_is_noncompliant():
    rule = Rule(rule_id="height_limit", comparator="<=")
    f = Evaluator().eval(EvalCase(rule=rule, measured_value=30.0, limit_value=20.0))
    assert f.verdict == Verdict.NON_COMPLIANT


def test_missing_prerequisite_state_does_not_false_fail():
    # 완화 전제 상태 미상 → 위원확인(거짓 불합격 금지, INV-16).
    f = Evaluator().eval(EvalCase(rule=_FAR_RULE, measured_value=250.0, limit_value=200.0))
    assert f.verdict != Verdict.NON_COMPLIANT
    assert f.requires_committee is True


def test_explicit_unmet_relaxation_is_noncompliant():
    # 완화 전제가 '검증된 불충족'일 때만 NON_COMPLIANT(정직).
    f = Evaluator().eval(_case("UNMET"))
    assert f.verdict == Verdict.NON_COMPLIANT


def test_within_limit_compliant():
    f = Evaluator().eval(EvalCase(rule=_FAR_RULE, measured_value=180.0, limit_value=200.0))
    assert f.verdict == Verdict.COMPLIANT
