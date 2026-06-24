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


# ── 6종 spec 누적(금융·세무·회계·설계·BIM·심의) ──

_EXPECTED_KEYS = {
    "senior_urban_planner", "senior_financial_advisor", "senior_architect",
    "senior_bim_specialist", "senior_deliberation_member", "senior_tax_advisor",
    "senior_accountant",
}


def test_all_seven_specs_registered():
    keys = {s.key for s in list_senior_agents()}
    assert keys == _EXPECTED_KEYS
    assert validate_registry() == {}  # 전 spec 판단자격(basis+tradeoff) 통과 = citation 게이트


@pytest.mark.parametrize("key", sorted(_EXPECTED_KEYS))
def test_spec_substance_all(key):
    spec = get_senior_agent(key)
    assert spec is not None
    # 결정규칙 ≥2·전부 판단자격(분류기 배제)·전부 basis(verified 근거) 부착
    assert len(spec.decision_rules) >= 2
    assert all(r.is_judgment() for r in spec.decision_rules)
    assert all(r.basis.strip() for r in spec.decision_rules)
    # 실패모드(할루시네이션 가드 포함)·체크리스트·역추적 단계 존재
    assert spec.failure_modes and spec.checklist
    assert any(s.backtrack_to for s in spec.reasoning_steps)
    # 면허책임 게이트 명시(정직성)
    assert "최종" in spec.license_gate and "책임" in spec.license_gate
    # 콜드스타트 정직: 골든사례 0 → junior(시니어 분장 금지)
    assert spec.maturity_for(0) == Maturity.JUNIOR_ASSIST


def test_financial_spec_domain_facts():
    spec = get_senior_agent("senior_financial_advisor")
    rules = {r.rule_id: r for r in spec.decision_rules}
    # 한국 PF 자기자본 단계규제 26/27/28 = 10/15/20%
    eq = rules["fin.equity_ratio_reg"].judgment
    assert "2026" in eq and "10%" in eq and "2027" in eq and "15%" in eq and "2028" in eq and "20%" in eq
    # DSCR 1.25x 게이트
    assert "1.25" in rules["fin.dscr_gate"].judgment
    # ICR 선언-구현 일치(거치단계 이자보상배율)
    assert "ICR" in rules["fin.icr_gate"].judgment
    # Development Spread <150bp 경고·<0 BLOCK
    ds = rules["fin.development_spread"].judgment
    assert "150bp" in ds and "BLOCK" in ds


def test_architect_spec_domain_facts():
    spec = get_senior_agent("senior_architect")
    rules = {r.rule_id: r for r in spec.decision_rules}
    # 정북후퇴 현행 10m 임계(구법 9m 아님)
    assert "10m" in rules["design.bukchuk_setback"].judgment
    # 동지 일조: 법정 2시간 reject 게이트 + 판례 4시간 AND 2시간 분쟁경고 분리(OR 회귀 차단)
    daylight = rules["design.winter_daylight_gate"].judgment
    assert "2시간" in daylight and "4시간" in daylight and "reject" in daylight
    assert "AND" in daylight  # 판례 수인한도는 4h AND 2h(OR 아님)


def test_tax_spec_domain_facts():
    spec = get_senior_agent("senior_tax_advisor")
    bases = " ".join(r.basis for r in spec.decision_rules)
    for law in ("지방세법", "소득세법", "종합부동산세법", "국세기본법"):
        assert law in bases


def test_accountant_spec_domain_facts():
    spec = get_senior_agent("senior_accountant")
    bases = " ".join(r.basis for r in spec.decision_rules)
    assert "1115" in bases and "1116" in bases and "1023" in bases


def test_deliberation_spec_domain_facts():
    spec = get_senior_agent("senior_deliberation_member")
    rules = {r.rule_id: r for r in spec.decision_rules}
    prob = rules["delib.outcome_probability"]
    # 강행규정 위반은 확률 아닌 BLOCK 단정(judgment 또는 exception)
    assert "BLOCK" in (prob.judgment + prob.exception)
    # 다조항 동시(CSP) 검증
    assert "동시" in rules["delib.multi_clause_csp"].judgment


# ── SeniorOrchestrator(자문 라우팅·게이팅 코어) ──

def _orch():
    from app.services.senior_agents.orchestrator import SeniorOrchestrator
    return SeniorOrchestrator()


def test_orchestrator_route_domain_and_key():
    o = _orch()
    assert o.route("금융") == "senior_financial_advisor"
    assert o.route("urban") == "senior_urban_planner"
    assert o.route("BIM") == "senior_bim_specialist"
    # 이미 키면 그대로 통과
    assert o.route("senior_tax_advisor") == "senior_tax_advisor"
    # 미해당
    assert o.route("우주항공") is None
    assert o.route("") is None


def test_orchestrator_consult_structure_and_citation_gate():
    o = _orch()
    c = o.consult("도시계획")
    assert c.agent_key == "senior_urban_planner"
    # citation 게이트: 프레임워크 전 룰이 basis(근거) 동반 + 판단자격
    assert c.decision_framework
    assert all(r["basis"].strip() for r in c.decision_framework)
    assert all(r.get("tradeoff", "").strip() for r in c.decision_framework)
    # citations 집합이 basis에서 도출
    assert c.citations and all(s.strip() for s in c.citations)
    # 콜드스타트 정직: junior + 면허게이트 + 정직 노트
    assert "보조" in c.maturity
    assert "최종" in c.license_gate
    assert any("골든사례" in n for n in c.honest_notes)
    assert 0.0 <= c.confidence <= 1.0
    # 직렬화
    assert c.to_dict()["agent_key"] == "senior_urban_planner"


def test_orchestrator_high_risk_threshold():
    o = _orch()
    # 금융·세무·심의 = 고위험(임계 상향)
    fin = o.consult("금융", context={"data_completeness": 0.7, "rule_fit": 0.7,
                                     "rag_strength": 0.7, "correction_rate": 0.3})
    assert fin.high_risk is True
    # 동일 신호라도 고위험은 신뢰컷 높아 전문가확인 강등되기 쉬움
    assert fin.needs_expert_review is True
    # 비고위험(도시계획)은 같은 신호에서 통과
    urb = o.consult("도시계획", context={"data_completeness": 0.7, "rule_fit": 0.7,
                                        "rag_strength": 0.7, "correction_rate": 0.3})
    assert urb.high_risk is False
    assert urb.needs_expert_review is False


def test_orchestrator_matched_rules_filter_and_rule_fit():
    o = _orch()
    c = o.consult("도시계획", context={"matched_rule_ids": ["urban.upzone_potential"]})
    ids = [r["rule_id"] for r in c.decision_framework]
    assert ids == ["urban.upzone_potential"]  # 부분집합 필터


def test_orchestrator_unknown_raises():
    o = _orch()
    with pytest.raises(ValueError):
        o.consult("존재하지않는도메인")


def test_orchestrator_consult_multi_dedup():
    o = _orch()
    res = o.consult_multi(["도시계획", "금융", "urban", "우주"])  # urban 중복·우주 무시
    keys = [c.agent_key for c in res]
    assert keys == ["senior_urban_planner", "senior_financial_advisor"]


def test_orchestrator_available_lists_all():
    o = _orch()
    av = o.available()
    assert {a["key"] for a in av} == _EXPECTED_KEYS
    # 고위험 플래그 정합
    hr = {a["key"] for a in av if a["high_risk"]}
    assert hr == {"senior_financial_advisor", "senior_tax_advisor", "senior_deliberation_member"}
