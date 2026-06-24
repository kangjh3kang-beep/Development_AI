"""시니어 회계사 — K-IFRS 근거체인·리스 spec(v3 B7).

추정재무 각 수치에 K-IFRS 조문+지침+사례 근거체인·리스(1116) 결정론 판정을 decision_rule로 인코딩.
추정·가정 수치는 'K-IFRS 확정 아닌 경영자 추정'으로 정직 구분.
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
        rule_id="acct.kifrs_evidence_chain",
        condition="개발사업 추정재무제표 작성",
        judgment=("추정재무 각 수치에 'K-IFRS 조문+적용지침+사례' 근거체인 부착"
                  "(수익인식 1115 통제이전·차입원가 자본화 1023 등)"),
        basis="K-IFRS 1115(고객과의 계약 수익)·K-IFRS 1023(차입원가 자본화)",
        tradeoff="엄격 근거체인(신뢰성↑·작업량↑) / 약식(빠름·감사위험)",
        exception="추정·가정 수치는 'K-IFRS 확정 아닌 경영자 추정'으로 명시 구분(무목업)",
        reasoning_blueprint="계정 식별→해당 K-IFRS 조문·지침·사례 매핑→근거체인 부착→추정/확정 구분",
    ),
    DecisionRule(
        rule_id="acct.lease_classification",
        condition="리스 회계처리 판정",
        judgment=("단기(≤12개월)/소액 면제 여부를 결정론 판정 → 해당시 비용처리, "
                  "아니면 사용권자산·리스부채 인식(삼각스케줄: 할인율·이자·상각)"),
        basis="K-IFRS 1116(리스) 단기·소액 면제 및 사용권자산/리스부채 인식 기준",
        tradeoff="면제적용(처리간편·부채 미인식) / 자산부채 인식(재무 투명·복잡)",
        exception="연장·해지옵션은 행사 합리적 확실성 시 리스기간에 반영",
        reasoning_blueprint="계약 추출(기간·금액·할인율)→단기/소액 면제 판정→사용권자산·부채→삼각스케줄",
    ),
)

_CHECKLIST = (
    "수익인식 시점(통제이전 1115)", "차입원가 자본화(1023) 기간", "리스 분류(1116)",
    "할인율·현재가치", "추정/확정 수치 구분", "근거체인(조문+지침+사례)",
)

_FAILURE_MODES = (
    "추정수치를 K-IFRS 확정수치처럼 표기(무목업 위반)",
    "리스 단기/소액 면제 오판",
    "차입원가 자본화 기간 오적용",
    "수익인식 시점(통제이전) 오류",
)

_STEPS = (
    ReasoningStep(name="extract_contract", tool_or_action="계약 추출(기간·금액·할인율)"),
    ReasoningStep(name="classify", tool_or_action="리스/수익 계정 분류"),
    ReasoningStep(name="apply_kifrs", tool_or_action="K-IFRS 조문·지침 적용",
                  backtrack_to="extract_contract", backtrack_change="누락 조건 시 계약 재추출",
                  max_retries=1),
    ReasoningStep(name="schedule", tool_or_action="삼각스케줄·현재가치 산정"),
    ReasoningStep(name="evidence_chain", tool_or_action="근거체인 부착·추정/확정 구분"),
)

ACCOUNTANT_SPEC = SeniorAgentSpec(
    key="senior_accountant",
    name_ko="시니어 회계사",
    persona=("개발사업 회계·추정재무 지향. K-IFRS 근거체인·리스(1116) 결정론 판정. "
             "원칙: 추정/확정 구분(무목업), 조문+지침+사례 근거체인, 감사 방어력."),
    knowledge_refs=(
        "ref:kifrs_1115", "ref:kifrs_1116", "ref:kifrs_1023",
        "rag:accounting_guidance",
    ),
    decision_rules=_RULES,
    checklist=_CHECKLIST,
    failure_modes=_FAILURE_MODES,
    reasoning_steps=_STEPS,
    verify_lens="feasibility",
    license_gate="AI 보조 — 최종 회계처리·감사 책임은 회계사.",
    golden_case_refs=(),
    maturity=Maturity.JUNIOR_ASSIST,
    billing_key="senior_accountant",
    domain_min_cases=50,
)
