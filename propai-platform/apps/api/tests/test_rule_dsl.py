"""Rule DSL 공용 승격(v4 계약층 W3-7) 단위 테스트.

심의엔진 CalcRule 파일럿 설계(app/services/rules/)의 핵심 계약을 검증한다:
- VariableRegistry 바인딩 강제(미등록 변수 참조 → RuleContractError, 등록 거부).
- 구조화 산식(eval_expr) 결정론 평가 + 0나눔/입력결손 UNKNOWN 전파(날조 금지).
- evaluate(): 산식/한도/비교 오케스트레이션 + 감사가능 trace.
- evaluate_many(): 같은 target_variable에 상충하는 값 → CONFLICT(임의 승자 선정 금지),
  UNKNOWN 혼재 → target 전체 UNKNOWN 보수화(순서 불변 — R1 봉합).
- effective_date 미시행 규칙 → UNKNOWN, base_date 미제공 시에도 fail-safe로 UNKNOWN(R1 봉합).
- formula/limit AST 유령 참조(수기 inputs/params와 괴리) → RuleContractError(R1 봉합).
"""
from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from app.services.provenance.fact_status import FactStatus
from app.services.rules.contracts import (
    CanonicalVariable,
    Comparator,
    RuleContractError,
    Unit,
    VariableRegistry,
    build_default_registry,
)
from app.services.rules.evaluate import evaluate, evaluate_many
from app.services.rules.expr import BinOp, Const, ParamRef, VarRef, eval_expr
from app.services.rules.rule_def import RuleDef


@pytest.fixture
def registry() -> VariableRegistry:
    return build_default_registry([
        CanonicalVariable(id="building_area_sqm", name="building_area_sqm", unit=Unit.M2, required=True),
        CanonicalVariable(id="land_area_sqm", name="land_area_sqm", unit=Unit.M2, required=True),
        CanonicalVariable(id="max_bcr_pct", name="max_bcr_pct", unit=Unit.PERCENT, required=True),
        CanonicalVariable(id="bcr_pct", name="bcr_pct", unit=Unit.PERCENT, required=True),
    ])


def _bcr_rule(**overrides) -> RuleDef:
    base = dict(
        rule_id="BL-001",
        target_variable="bcr_pct",
        basis_article="국토의 계획 및 이용에 관한 법률 시행령 제84조",
        inputs=["building_area_sqm", "land_area_sqm", "max_bcr_pct"],
        formula=BinOp(
            op="mul",
            left=BinOp(op="div", left=VarRef(name="building_area_sqm"), right=VarRef(name="land_area_sqm")),
            right=Const(value=100),
        ),
        limit=VarRef(name="max_bcr_pct"),
        comparator=Comparator.LE,
        unit=Unit.PERCENT,
    )
    base.update(overrides)
    return RuleDef(**base)


# ── VariableRegistry 바인딩 강제 ──────────────────────────────────────────

def test_registry_rejects_unregistered_variable(registry: VariableRegistry) -> None:
    with pytest.raises(RuleContractError):
        registry.bind_rule(["nonexistent_var"])


def test_registry_lookup_unregistered_raises(registry: VariableRegistry) -> None:
    with pytest.raises(RuleContractError):
        registry.lookup("nonexistent_var")


def test_evaluate_rejects_rule_with_unregistered_input(registry: VariableRegistry) -> None:
    rule = _bcr_rule(inputs=["building_area_sqm", "land_area_sqm", "max_bcr_pct", "unknown_var"])
    with pytest.raises(RuleContractError):
        evaluate(rule, {"building_area_sqm": 1, "land_area_sqm": 2, "max_bcr_pct": 3}, registry)


def test_evaluate_rejects_unregistered_target_variable(registry: VariableRegistry) -> None:
    rule = _bcr_rule(target_variable="unregistered_target", inputs=[])
    with pytest.raises(RuleContractError):
        evaluate(rule, {}, registry)


# ── 구조화 산식 평가(eval_expr) — 결정론 + UNKNOWN 전파 ──────────────────

def test_eval_expr_pure_deterministic() -> None:
    node = BinOp(op="mul", left=VarRef(name="x"), right=Const(value=2))
    assert eval_expr(node, {"x": 21.0}, {}) == 42.0
    assert eval_expr(node, {"x": 21.0}, {}) == 42.0  # 같은 입력 → 같은 결과


def test_eval_expr_missing_var_propagates_unknown() -> None:
    node = BinOp(op="mul", left=VarRef(name="missing"), right=Const(value=2))
    assert eval_expr(node, {}, {}) is None  # 0으로 대체하지 않음(무날조)


def test_eval_expr_div_by_zero_propagates_unknown_not_crash() -> None:
    node = BinOp(op="div", left=VarRef(name="a"), right=VarRef(name="b"))
    assert eval_expr(node, {"a": 10.0, "b": 0.0}, {}) is None


def test_eval_expr_div_by_negative_denominator_propagates_unknown() -> None:
    """면적 등 정량 도메인에서 분모(예: 대지면적)가 음수인 것은 비물리 — 0나눔과 동일하게
    UNKNOWN 처리한다(날조 방지 확장, R1 LOW-1)."""
    node = BinOp(op="div", left=VarRef(name="a"), right=VarRef(name="b"))
    assert eval_expr(node, {"a": 10.0, "b": -5.0}, {}) is None


def test_eval_expr_param_ref() -> None:
    node = ParamRef(name="threshold")
    assert eval_expr(node, {}, {"threshold": 60.0}) == 60.0


# ── nan/inf 게이트(R1 LOW-2) ──────────────────────────────────────────────

def test_eval_expr_var_nan_propagates_unknown() -> None:
    node = VarRef(name="x")
    assert eval_expr(node, {"x": float("nan")}, {}) is None


def test_eval_expr_var_inf_propagates_unknown() -> None:
    node = VarRef(name="x")
    assert eval_expr(node, {"x": float("inf")}, {}) is None


def test_eval_expr_binop_overflow_to_inf_propagates_unknown() -> None:
    node = BinOp(op="mul", left=Const(value=1e308), right=Const(value=1e308))
    assert eval_expr(node, {}, {}) is None  # 1e308*1e308 → float overflow(inf) → UNKNOWN


def test_const_rejects_nan_at_construction() -> None:
    with pytest.raises(ValidationError):
        Const(value=float("nan"))


def test_const_rejects_inf_at_construction() -> None:
    with pytest.raises(ValidationError):
        Const(value=float("inf"))


# ── evaluate(): 오케스트레이션 + trace ───────────────────────────────────

def test_evaluate_compliant_case(registry: VariableRegistry) -> None:
    rule = _bcr_rule()
    result = evaluate(rule, {"building_area_sqm": 120.0, "land_area_sqm": 200.0, "max_bcr_pct": 60.0}, registry)
    assert result.status == FactStatus.DERIVED
    assert result.value == pytest.approx(60.0)
    assert result.compliant is True
    assert len(result.trace.entries) >= 2  # 산식평가 + 판정 최소 2단계 기록(감사가능)


def test_evaluate_noncompliant_case(registry: VariableRegistry) -> None:
    rule = _bcr_rule()
    result = evaluate(rule, {"building_area_sqm": 150.0, "land_area_sqm": 200.0, "max_bcr_pct": 60.0}, registry)
    assert result.value == pytest.approx(75.0)
    assert result.compliant is False


def test_evaluate_missing_input_is_unknown_not_zero(registry: VariableRegistry) -> None:
    rule = _bcr_rule()
    result = evaluate(rule, {"building_area_sqm": None, "land_area_sqm": 200.0, "max_bcr_pct": 60.0}, registry)
    assert result.status == FactStatus.UNKNOWN
    assert result.value is None  # 0으로 조용히 대체하지 않음
    assert result.compliant is None


def test_evaluate_not_yet_effective_rule_is_unknown(registry: VariableRegistry) -> None:
    rule = _bcr_rule(effective_date=date(2099, 1, 1))
    result = evaluate(
        rule, {"building_area_sqm": 120.0, "land_area_sqm": 200.0, "max_bcr_pct": 60.0}, registry,
        base_date=date(2026, 7, 23),
    )
    assert result.status == FactStatus.UNKNOWN


def test_evaluate_future_effective_rule_without_base_date_is_unknown_not_derived(
    registry: VariableRegistry,
) -> None:
    """HIGH-2 fail-open 봉합: base_date를 생략하면(과거엔 시제 검증 자체가 스킵되어 미래
    시행 규칙도 DERIVED로 오적용됐음) 이제는 "시제 미해소"로 UNKNOWN 처리한다 —
    base_date 누락을 "임의로 이미 시행 중"이라 간주하지 않는다."""
    rule = _bcr_rule(effective_date=date(2099, 1, 1))
    result = evaluate(
        rule, {"building_area_sqm": 120.0, "land_area_sqm": 200.0, "max_bcr_pct": 60.0}, registry,
    )  # base_date 생략(기본값 None)
    assert result.status == FactStatus.UNKNOWN
    assert result.value is None
    assert any("시제 미해소" in e.note for e in result.trace.entries)


# ── formula/limit AST 유령 참조 검증(R1 MEDIUM-1) ────────────────────────

def test_evaluate_rejects_ghost_var_ref_not_in_registry(registry: VariableRegistry) -> None:
    """formula가 참조하는 VarRef가 registry에 미등록이면(수기 inputs와 산식의 괴리) 등록
    거부 — bind_rule은 rule.inputs 목록 자체만 보므로 이 유령 참조는 놓친다."""
    rule = _bcr_rule(
        formula=BinOp(
            op="mul",
            left=BinOp(op="div", left=VarRef(name="building_area_sqm"), right=VarRef(name="ghost_var_xyz")),
            right=Const(value=100),
        ),
    )
    with pytest.raises(RuleContractError):
        evaluate(rule, {"building_area_sqm": 120.0, "land_area_sqm": 200.0, "max_bcr_pct": 60.0}, registry)


def test_evaluate_rejects_ghost_param_ref_not_declared(registry: VariableRegistry) -> None:
    """limit이 참조하는 ParamRef가 rule.params에 미선언이면 등록 거부(무음 UNKNOWN 강등 금지)."""
    rule = _bcr_rule(limit=ParamRef(name="undeclared_threshold"))
    with pytest.raises(RuleContractError):
        evaluate(rule, {"building_area_sqm": 120.0, "land_area_sqm": 200.0, "max_bcr_pct": 60.0}, registry)


def test_evaluate_is_pure_same_input_same_output(registry: VariableRegistry) -> None:
    rule = _bcr_rule()
    inputs = {"building_area_sqm": 120.0, "land_area_sqm": 200.0, "max_bcr_pct": 60.0}
    r1 = evaluate(rule, inputs, registry)
    r2 = evaluate(rule, inputs, registry)
    assert r1.value == r2.value
    assert r1.status == r2.status
    assert r1.compliant == r2.compliant


# ── evaluate_many(): CONFLICT 표면화 ─────────────────────────────────────

def test_evaluate_many_conflicting_rules_surface_conflict() -> None:
    reg = build_default_registry([
        CanonicalVariable(id="far_pct", name="far_pct", unit=Unit.PERCENT),
        CanonicalVariable(id="a", name="a", unit=Unit.PERCENT),
        CanonicalVariable(id="b", name="b", unit=Unit.PERCENT),
    ])
    r1 = RuleDef(rule_id="R1", target_variable="far_pct", basis_article="법률A",
                 inputs=["a"], formula=VarRef(name="a"), unit=Unit.PERCENT)
    r2 = RuleDef(rule_id="R2", target_variable="far_pct", basis_article="법률B",
                 inputs=["b"], formula=VarRef(name="b"), unit=Unit.PERCENT)
    out = evaluate_many([r1, r2], {"a": 100.0, "b": 150.0}, reg)
    assert out["far_pct"].status == FactStatus.CONFLICT
    assert "임의 승자 선정 금지" in out["far_pct"].trace.entries[-1].note


def test_evaluate_many_agreeing_rules_no_conflict() -> None:
    reg = build_default_registry([
        CanonicalVariable(id="far_pct", name="far_pct", unit=Unit.PERCENT),
        CanonicalVariable(id="a", name="a", unit=Unit.PERCENT),
    ])
    r1 = RuleDef(rule_id="R1", target_variable="far_pct", basis_article="법률A",
                 inputs=["a"], formula=VarRef(name="a"), unit=Unit.PERCENT)
    r2 = RuleDef(rule_id="R2", target_variable="far_pct", basis_article="법률B",
                 inputs=["a"], formula=VarRef(name="a"), unit=Unit.PERCENT)
    out = evaluate_many([r1, r2], {"a": 100.0}, reg)
    assert out["far_pct"].status == FactStatus.DERIVED
    assert out["far_pct"].value == 100.0


def test_evaluate_many_conflict_preserves_all_candidate_traces() -> None:
    """MEDIUM-3: 상충 시 대표 1건의 trace만이 아니라 상충한 규칙 전부의 산식평가 trace를
    병합 보존한다(패자 규칙 trace 소실 금지)."""
    reg = build_default_registry([
        CanonicalVariable(id="far_pct", name="far_pct", unit=Unit.PERCENT),
        CanonicalVariable(id="a", name="a", unit=Unit.PERCENT),
        CanonicalVariable(id="b", name="b", unit=Unit.PERCENT),
    ])
    r1 = RuleDef(rule_id="R1", target_variable="far_pct", basis_article="법률A",
                 inputs=["a"], formula=VarRef(name="a"), unit=Unit.PERCENT)
    r2 = RuleDef(rule_id="R2", target_variable="far_pct", basis_article="법률B",
                 inputs=["b"], formula=VarRef(name="b"), unit=Unit.PERCENT)
    out = evaluate_many([r1, r2], {"a": 100.0, "b": 150.0}, reg)
    notes = [e.note for e in out["far_pct"].trace.entries]
    assert any("100.0" in n for n in notes)  # R1(패자 가능) trace 값 보존
    assert any("150.0" in n for n in notes)  # R2 trace 값 보존


# ── evaluate_many(): 위치기반 임의채택 제거·순서 불변성(R1 HIGH-1) ────────

def _order_invariance_setup() -> tuple[VariableRegistry, RuleDef, RuleDef]:
    """같은 target(bcr_pct)에 DERIVED 1건(a=100.0)·UNKNOWN 1건(b 결손)을 내는 규칙 쌍.
    리뷰어 실증: 예전 구현(``results[-1]``)은 이 둘을 [DERIVED, UNKNOWN] 순으로 넘기면
    UNKNOWN이, [UNKNOWN, DERIVED] 순으로 넘기면 DERIVED가 채택돼 순서만으로 결과가
    뒤집혔다. 새 정책은 어느 순서든 target 전체를 UNKNOWN으로 보수화해야 한다."""
    reg = build_default_registry([
        CanonicalVariable(id="bcr_pct", name="bcr_pct", unit=Unit.PERCENT),
        CanonicalVariable(id="a", name="a", unit=Unit.PERCENT),
        CanonicalVariable(id="b", name="b", unit=Unit.PERCENT),
    ])
    derived_rule = RuleDef(rule_id="R-DERIVED", target_variable="bcr_pct", basis_article="법률A",
                            inputs=["a"], formula=VarRef(name="a"), unit=Unit.PERCENT)
    unknown_rule = RuleDef(rule_id="R-UNKNOWN", target_variable="bcr_pct", basis_article="법률B",
                            inputs=["b"], formula=VarRef(name="b"), unit=Unit.PERCENT)
    return reg, derived_rule, unknown_rule


def test_evaluate_many_order_flip_derived_then_unknown_is_unknown() -> None:
    reg, derived_rule, unknown_rule = _order_invariance_setup()
    out = evaluate_many([derived_rule, unknown_rule], {"a": 100.0}, reg)  # b 결손 → UNKNOWN
    assert out["bcr_pct"].status == FactStatus.UNKNOWN
    assert out["bcr_pct"].value is None


def test_evaluate_many_order_flip_unknown_then_derived_is_unknown() -> None:
    """위 테스트와 규칙 순서만 뒤바꾼 것 — 순서 불변성이라면 반드시 같은 결과(UNKNOWN)여야
    한다(예전 위치기반 구현이었다면 여기서 DERIVED로 뒤집혔을 지점)."""
    reg, derived_rule, unknown_rule = _order_invariance_setup()
    out = evaluate_many([unknown_rule, derived_rule], {"a": 100.0}, reg)  # b 결손 → UNKNOWN
    assert out["bcr_pct"].status == FactStatus.UNKNOWN
    assert out["bcr_pct"].value is None


def test_evaluate_many_mixed_unknown_preserves_derived_candidate_in_trace() -> None:
    """혼재(DERIVED+UNKNOWN) → UNKNOWN 보수화 시에도 DERIVED 후보값·rule_id는 trace에
    보존한다(부분근거 확정은 금지하되 정보 소실은 방지, HIGH-1)."""
    reg, derived_rule, unknown_rule = _order_invariance_setup()
    out = evaluate_many([derived_rule, unknown_rule], {"a": 100.0}, reg)
    result = out["bcr_pct"]
    assert result.status == FactStatus.UNKNOWN
    assert any("R-DERIVED" in e.note and "100.0" in e.note for e in result.trace.entries)
