"""시니어 에이전트 코어 구조체·confidence·registry 단위테스트(P0 foundation)."""

import pytest

from app.services.senior_agents.confidence import (
    THRESHOLD_HIGH_RISK,
    THRESHOLD_REVIEW,
    compute_confidence,
    confidence_label,
    make_interval,
    needs_expert_review,
)
from app.services.senior_agents.registry import (
    get_senior_agent,
    list_senior_agents,
    validate_registry,
)
from app.services.senior_agents.spec import DecisionRule, Maturity

# ── DecisionRule: 판단 vs 분류기(critic C1) ──

def test_decision_rule_is_judgment_requires_tradeoff_and_basis():
    good = DecisionRule(rule_id="r1", condition="c", judgment="j", basis="법§1", tradeoff="A vs B")
    assert good.is_judgment() is True
    # tradeoff 비면 분류기 → 판단 자격 미달
    classifier = DecisionRule(rule_id="r2", condition="c", judgment="j", basis="법§1", tradeoff="")
    assert classifier.is_judgment() is False
    # basis 비면(근거없음) 미달
    nobasis = DecisionRule(rule_id="r3", condition="c", judgment="j", basis="", tradeoff="A vs B")
    assert nobasis.is_judgment() is False


# ── 성숙도(critic C2): 사례 부족 시 junior(정직) ──

def test_maturity_for_case_count():
    spec = get_senior_agent("senior_urban_planner")
    assert spec is not None
    assert spec.maturity_for(0) == Maturity.JUNIOR_ASSIST
    assert spec.maturity_for(49) == Maturity.JUNIOR_ASSIST
    assert spec.maturity_for(50) == Maturity.SENIOR_ASSIST
    # 라벨 정직 노출
    assert "검증 보조" in Maturity.JUNIOR_ASSIST.label
    assert "시니어 보조" in Maturity.SENIOR_ASSIST.label


# ── confidence 캘리브레이션(critic M2) ──

def test_compute_confidence_bounds_and_weights():
    assert compute_confidence(data_completeness=1, rule_fit=1, rag_strength=1, correction_rate=0) == 1.0
    # correction_rate=1(과거 교정 잦음) → track_record 0
    low = compute_confidence(data_completeness=0, rule_fit=0, rag_strength=0, correction_rate=1)
    assert low == 0.0
    # 결측은 중립 0.5 보수처리
    mid = compute_confidence(data_completeness=None, rule_fit=None, rag_strength=None, correction_rate=None)
    assert 0.49 <= mid <= 0.51
    # 범위 클립
    assert 0.0 <= compute_confidence(data_completeness=5, rule_fit=-3, rag_strength=0.5, correction_rate=0.2) <= 1.0


def test_selective_prediction_threshold():
    assert needs_expert_review(0.59) is True and needs_expert_review(0.61) is False
    # 고위험 임계 상향
    assert needs_expert_review(0.7, high_risk=True) is True
    assert THRESHOLD_HIGH_RISK > THRESHOLD_REVIEW
    assert "전문가 확인" in confidence_label(0.5)


def test_make_interval_requires_basis_and_orders():
    iv = make_interval(0.8, 0.3, basis="실거래 기반")
    assert iv.low == 0.3 and iv.high == 0.8  # 자동 정렬
    with pytest.raises(ValueError):
        make_interval(0.1, 0.2, basis="")  # 근거 없으면 무목업 위반 → 거부


# ── registry·spec 무결성 ──

def test_registry_all_rules_are_judgments_not_classifiers():
    # ★전 spec의 decision_rule이 판단 자격(basis+tradeoff) 충족 = citation/basis 게이트
    assert validate_registry() == {}


def test_urban_spec_substance():
    spec = get_senior_agent("senior_urban_planner")
    assert spec in list_senior_agents()
    # 실제 트레이드오프 룰 ≥3(비례율·종상향·개발방식)
    assert len(spec.decision_rules) >= 3
    # 전 룰 basis(법조문) 비어있지 않음 = A2 citation 게이트 대상
    assert all(r.basis.strip() for r in spec.decision_rules)
    # 비례율 룰의 판단에 산식 포함
    prop = next(r for r in spec.decision_rules if r.rule_id == "urban.redevelopment_proportion")
    assert "비례율" in prop.judgment and prop.is_judgment()
    # 실패모드에 할루시네이션 가드(특이부지) 포함
    assert any("할루시네이션" in f or "특이부지" in f for f in spec.failure_modes)
    # 면허책임 게이트 명시
    assert "최종" in spec.license_gate and "책임" in spec.license_gate


def test_reasoning_steps_have_backtrack_gate():
    # critic M1: 단선 아닌 역추적(최소 1개 단계에 backtrack_to)
    spec = get_senior_agent("senior_urban_planner")
    assert any(s.backtrack_to for s in spec.reasoning_steps)


# ── 리뷰 반영: NaN 게이트·registry 불변·label 임계·산식 차원 ──

def test_confidence_nan_inf_does_not_bypass_gate():
    import math
    c = compute_confidence(data_completeness=math.nan, rule_fit=1, rag_strength=1, correction_rate=0)
    assert 0.0 <= c <= 1.0 and not math.isnan(c)  # NaN이 confidence로 전파되지 않음
    with pytest.raises(ValueError):
        make_interval(math.nan, 0.5, basis="x")
    with pytest.raises(ValueError):
        make_interval(0.1, math.inf, basis="x")


def test_confidence_label_tracks_threshold():
    assert confidence_label(0.85) == "신뢰"                  # 일반 신뢰컷 0.8
    assert confidence_label(0.85, high_risk=True) == "보통"   # 고위험 신뢰컷 0.95 미달


def test_registry_immutable_and_register_gate():
    from types import MappingProxyType

    from app.services.senior_agents.registry import SENIOR_AGENT_REGISTRY, register
    from app.services.senior_agents.spec import SeniorAgentSpec

    assert isinstance(SENIOR_AGENT_REGISTRY, MappingProxyType)
    with pytest.raises(TypeError):
        SENIOR_AGENT_REGISTRY["hack"] = None  # 읽기전용 — 외부 변조 차단
    with pytest.raises(ValueError):
        register(get_senior_agent("senior_urban_planner"))  # 중복 키 거부
    bad = SeniorAgentSpec(
        key="t_bad", name_ko="x", persona="p", knowledge_refs=(),
        decision_rules=(DecisionRule(rule_id="b", condition="c", judgment="j", basis="", tradeoff=""),),
        checklist=(), failure_modes=(), reasoning_steps=(), verify_lens="x", license_gate="x",
    )
    with pytest.raises(ValueError):
        register(bad)  # 판단자격 미달(분류기) 거부


def test_redevelopment_formula_dimension():
    # ★HIGH 수정: 비례율(%)과 권리가액(÷100) 차원 정합
    spec = get_senior_agent("senior_urban_planner")
    prop = next(r for r in spec.decision_rules if r.rule_id == "urban.redevelopment_proportion")
    assert "비례율/100" in prop.judgment or "비례율(%)" in prop.judgment
    assert "권리가액" in prop.judgment
