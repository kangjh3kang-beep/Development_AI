"""시니어 심의위원 — 형식검증·적대적 이중관점 spec(v3 B5).

다조항 동시검증(CSP)·결과 확률화(통과확률+선례)를 decision_rule로 인코딩.
L4L 적대적 이중에이전트(pro 적합·con 부적합)로 균형. permit_validator/calc_effective_far/
special_parcel을 제약충족 솔버로 활용(실 배선은 후속).
"""

from __future__ import annotations

from app.services.senior_agents.spec import (
    DecisionRule,
    Maturity,
    ReasoningStep,
    SeniorAgentSpec,
)

_RULES = (
    DecisionRule(
        rule_id="delib.multi_clause_csp",
        condition="건축·도시계획 심의 다조항 동시 적합성",
        judgment=("건폐율+용적률+높이+접도+일조를 hard-constraint로 형식화 → CSP 동시만족 검증, "
                  "위반 시 어느 조항·어느 수치가 충돌인지 trace(unsat core) 명시"),
        basis="건축법·국토계획법 정량기준(건폐/용적/높이/접도/일조)",
        tradeoff="형식검증(조항간 상호작용 놓침0·구현복잡) / 체크리스트(단순·상호작용 위반 누락)",
        exception=("완화·특례(인센티브) 적용 시 완화 후 기준으로 재검증. "
                   "일조는 적용 용도지역(주거 등)에서만 활성 — 상업지역 등 미적용 시 제약에서 제외"),
        reasoning_blueprint="조항별 hard-constraint화→CSP 동시검증→unsat core 추출→위반 조항·수치 명시",
    ),
    DecisionRule(
        rule_id="delib.outcome_probability",
        condition="심의 통과 가능성 판정",
        judgment=("pass/fail 단정 대신 통과확률 + 근거 선례(유사 심의 ratio decidendi) 제시, "
                  "적대적 이중관점(적합 pro / 부적합 con 독립추출)으로 균형"),
        basis="심의 선례·도시계획/건축위원회 의결기준(Precedent 기반 판단)",
        tradeoff="확률화(정직·불확실성 표현 / 의사결정 모호) / 단정(명료·과신위험)",
        exception="법정 강행규정 위반은 확률 아닌 부적합 단정(BLOCK)",
        reasoning_blueprint="유사선례 검색→pro/con 적대추출→제약충족 대조→통과확률+근거선례 출력",
    ),
)

_CHECKLIST = (
    "건폐율", "용적률(실효)", "높이제한", "접도요건", "일조",
    "특이부지 게이트", "완화·특례 적용 후 재검증",
)

_FAILURE_MODES = (
    "조항 개별검증만 → 조항간 상호작용 위반 누락",
    "통과/부적합 과신 단정(확률·불확실성 미표현)",
    "선례 ratio decidendi vs obiter dicta 혼동",
    "특이부지(학교용지·GB)에 일상 심의기준 오적용(★할루시네이션)",
)

_STEPS = (
    ReasoningStep(name="collect_constraints", tool_or_action="정량기준·특이부지 수집(special_parcel)"),
    ReasoningStep(name="csp_verify", tool_or_action="다조항 CSP 동시검증(unsat core)"),
    ReasoningStep(name="adversarial_debate", tool_or_action="pro/con 적대 이중추출",
                  backtrack_to="collect_constraints", backtrack_change="쟁점 누락 시 제약 재수집",
                  max_retries=1),
    ReasoningStep(name="precedent_match", tool_or_action="유사선례 ratio 매칭"),
    ReasoningStep(name="probability", tool_or_action="통과확률+근거선례 산출"),
)

DELIBERATION_MEMBER_SPEC = SeniorAgentSpec(
    key="senior_deliberation_member",
    name_ko="시니어 심의위원",
    persona=("건축·도시계획 심의위원 지향. 다조항 동시(CSP) 적합성·선례 기반 통과확률. "
             "원칙: 단정 금지(확률+근거선례), 특이부지 게이트 우선, 적대적 이중관점."),
    knowledge_refs=(
        "legal:building_act", "legal:nat_planning", "rule:special_parcel",
        "rag:deliberation_precedent", "ref:l4l_norm",
    ),
    decision_rules=_RULES,
    checklist=_CHECKLIST,
    failure_modes=_FAILURE_MODES,
    reasoning_steps=_STEPS,
    verify_lens="permit",
    license_gate="AI 보조 의견 — 최종 심의·의결 권한과 책임은 도시계획·건축위원회.",
    golden_case_refs=(),
    maturity=Maturity.JUNIOR_ASSIST,
    billing_key="senior_deliberation_member",
    domain_min_cases=50,
)
