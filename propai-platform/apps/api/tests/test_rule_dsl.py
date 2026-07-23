"""Rule DSL 공용 승격(v4 계약층 W3-7) 단위 테스트.

심의엔진 CalcRule 파일럿 설계(app/services/rules/)의 핵심 계약을 검증한다:
- VariableRegistry 바인딩 강제(미등록 변수 참조 → RuleContractError, 등록 거부).
- 구조화 산식(eval_expr) 결정론 평가 + 0나눔/입력결손 UNKNOWN 전파(날조 금지).
- evaluate(): 산식/한도/비교 오케스트레이션 + 감사가능 trace.
- evaluate_many(): 같은 target_variable에 상충하는 값 → CONFLICT(임의 승자 선정 금지).
- effective_date 미시행 규칙 → UNKNOWN.
"""
from __future__ import annotations

from datetime import date

import pytest

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


def test_eval_expr_param_ref() -> None:
    node = ParamRef(name="threshold")
    assert eval_expr(node, {}, {"threshold": 60.0}) == 60.0


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
