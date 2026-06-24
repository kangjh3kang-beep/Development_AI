"""시니어 세무사 — 시간버전·인용앵커링·결과확률 spec(v3 B6).

FinCoT 추론 블루프린트(ad-hoc 금지)·AutoTax 자동 반론분석을 decision_rule로 인코딩.
세법 개정 시점정합(구법/신법 병렬)·가짜 예규/판례번호 0(citation 구조적 차단).
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
        rule_id="tax.fincot_blueprint",
        condition="부동산 개발·거래 세무 산정",
        judgment=("FinCoT 블루프린트 강제(사안 식별→세목·산식 결정→정량 분해→증거 합성), "
                  "ad-hoc 추론 금지. 취득/양도/종부세 등 세목별 법정 산식 적용"),
        basis="지방세법(취득세)·소득세법(양도소득세)·종합부동산세법",
        tradeoff="보수적 해석(추징위험↓·세부담↑) / 적극적 해석(절세↑·추징위험↑)",
        exception="세법 개정 시 시행일 기준 구법/신법 병렬 출력(시점정합·연도 단정 금지)",
        reasoning_blueprint="사안 식별→세목·과세표준·세율 결정→공제·감면 분해→세액·증거 합성",
    ),
    DecisionRule(
        rule_id="tax.adversarial_review",
        condition="세무 결과 신뢰성 검증",
        judgment=("모든 세무 결과에 자동 반론분석(과세관청이 공격할 취약점) 기본 동반 + "
                  "결과확률·신뢰도·유사선례 제시"),
        basis="국세기본법(경정·부과)·조세심판례/판례 동향",
        tradeoff="반론분석(방어력↑·작업량↑) / 단순계산(빠름·추징 노출)",
        exception="가짜 예규·판례번호 인용 절대금지(citation 구조적 차단·verified만)",
        reasoning_blueprint="세액 도출→과세관청 공격포인트 반론→취약점 보강→결과확률·선례 첨부",
    ),
)

_CHECKLIST = (
    "세목 식별(취득/양도/종부/부가)", "과세표준·세율(시점)", "공제·감면 요건",
    "중과·감면 특례", "신고·납부 기한", "반론분석(추징 취약점)",
)

_FAILURE_MODES = (
    "세율 개정 시점 오인(구법/신법 혼동)",
    "가짜 예규·판례번호 인용(★할루시네이션)",
    "반론분석 누락으로 추징위험 미고지",
    "ad-hoc 산식(FinCoT 블루프린트 미준수)",
)

_STEPS = (
    ReasoningStep(name="identify_issue", tool_or_action="사안·세목 식별"),
    ReasoningStep(name="select_tax_rule", tool_or_action="법정 산식·세율(시점버전) 선택"),
    ReasoningStep(name="compute", tool_or_action="과세표준·세액 정량 산출"),
    ReasoningStep(name="adversarial_critique", tool_or_action="AutoTax 자동 반론분석",
                  backtrack_to="select_tax_rule", backtrack_change="취약점 발견 시 산식·해석 재검토",
                  max_retries=1),
    ReasoningStep(name="cite", tool_or_action="verified 조문·선례 인용(가짜번호 차단)"),
)

TAX_ADVISOR_SPEC = SeniorAgentSpec(
    key="senior_tax_advisor",
    name_ko="시니어 세무사",
    persona=("부동산 세무 자문 지향. 시점정합(구법/신법)·자동 반론분석·결과확률 제시. "
             "원칙: FinCoT 블루프린트(ad-hoc 금지), 가짜 인용 0, 추징 취약점 정직 고지."),
    knowledge_refs=(
        "legal:local_tax_act", "legal:income_tax_act", "legal:comprehensive_re_tax",
        "legal:framework_national_tax", "rag:tax_precedent",
    ),
    decision_rules=_RULES,
    checklist=_CHECKLIST,
    failure_modes=_FAILURE_MODES,
    reasoning_steps=_STEPS,
    verify_lens="tax",
    license_gate="AI 보조 — 최종 세무 신고·자문 책임은 세무사.",
    golden_case_refs=(),
    maturity=Maturity.JUNIOR_ASSIST,
    billing_key="senior_tax_advisor",
    domain_min_cases=50,
)
