"""시니어 법무사 — 등기·권리분석·정비사업 조합·신탁 법무 spec(8번째 에이전트).

정비/개발의 권리분석(말소기준)·조합설립 동의율(도시정비법 35조)·소유권/신탁 등기를 decision_rule로
인코딩. basis는 verified 법조문(A2 citation 게이트 대상). 면허책임=법무사·변호사 인간게이트.
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
        rule_id="legal.rights_analysis",
        condition="등기부 권리관계 분석(인수/소멸 판정)",
        judgment=("말소기준권리(최선순위 (근)저당권·압류·가압류·담보가등기·강제경매개시 중 최선순위)보다 "
                  "후순위 권리는 소멸, 선순위 권리·대항력(전입+점유) 임차인은 매수인 인수"),
        basis="민사집행법(말소기준·배당순위)·주택임대차보호법(대항력)·부동산등기법",
        tradeoff="보수적 인수 가정(안전·실매입가↑) / 적극 소멸 가정(수익↑·인수위험)",
        exception="예고등기·가처분·유치권·법정지상권은 말소기준 무관 인수 가능 — 별도 정밀검토",
        reasoning_blueprint="등기부 권리 시계열→말소기준권리 식별→후순위 소멸·선순위/대항력 인수→인수금액 합산",
    ),
    DecisionRule(
        rule_id="legal.union_consent",
        condition="정비사업 조합설립 동의요건 충족 판정",
        judgment=("재개발=토지등소유자 3/4 이상 AND 토지면적 1/2 이상 동의. "
                  "재건축=각 동별 구분소유자 과반 AND 전체 구분소유자 3/4 이상 AND 토지면적 3/4 이상 동의"),
        basis="도시 및 주거환경정비법 제35조(조합설립인가 동의요건)",
        tradeoff="조기 인가 추진(속도) / 동의율 여유 확보(인가취소·소송 리스크↓)",
        exception="토지등소유자 산정: 1필지·1건물 공유는 대표 1인, 1인 다물건은 1인 — 중복 산정 금지",
        reasoning_blueprint="토지등소유자/구분소유자 수·면적 집계→동의 수집→재개발/재건축 요건 대조→충족 게이트",
    ),
    DecisionRule(
        rule_id="legal.title_registration",
        condition="소유권이전·신탁 등기 적법성·선행요건",
        judgment=("소유권이전등기는 실거래신고필증·검인계약서·취득세 납부·등기필정보 선행. "
                  "개발 자금조달 시 신탁등기(위탁자→수탁자 소유권 이전·신탁원부) 구조 검토"),
        basis="부동산등기법·부동산 거래신고 등에 관한 법률·지방세법(취득세 선납)",
        tradeoff="일반 소유등기(소유 명확·도산위험 노출) / 신탁등기(도산절연·PF조달 유리·소유권 수탁자)",
        exception="미등기·무허가 건물은 보존등기(건축물대장 등재) 선행 필요",
        reasoning_blueprint="권원·계약 확인→실거래신고·검인→취득세 납부→등기신청(일반/신탁)→등기완료 검증",
    ),
    DecisionRule(
        rule_id="legal.development_trust",
        condition="개발사업 신탁 구조 선택(자금조달·도산절연)",
        judgment=("차입형 토지신탁=신탁사가 사업비 조달·시행 / 관리형=시행사 조달·신탁사 관리 / "
                  "담보신탁=PF 담보. 도산절연·시행권·수수료로 선택"),
        basis="신탁법·자본시장과 금융투자업에 관한 법률(신탁업)",
        tradeoff="차입형(자금조달·도산절연 강·수수료↑·시행권 신탁사) / 관리형·담보(시행사 주도·수수료↓)",
        exception="분양·공사대금 우선순위(신탁계정)·위탁자 도산 시 신탁재산 절연 범위 별도 검토",
        reasoning_blueprint="자금조달 구조→신탁유형(차입/관리/담보) 비교→도산절연·시행권·수수료 평가→구조 추천",
    ),
)

_CHECKLIST = (
    "등기부 권리관계", "말소기준권리", "대항력 임차인", "조합설립 동의율(수·면적)",
    "취득세 선납·실거래신고", "신탁 도산절연", "예고등기·가처분",
)

_FAILURE_MODES = (
    "말소기준권리 오판 — 대항력 임차인·선순위 권리 인수 누락(★실매입가 과소)",
    "조합설립 동의율 산정 오류(토지등소유자 중복·1인 다물건)",
    "신탁 도산절연 범위 과신",
    "예고등기·가처분·유치권을 말소기준으로 소멸 처리(인수 간과)",
)

_STEPS = (
    ReasoningStep(name="collect_registry", tool_or_action="등기부·권리 시계열 수집"),
    ReasoningStep(name="identify_priority", tool_or_action="말소기준권리 식별",
                  backtrack_to="collect_registry", backtrack_change="권리 누락 시 재수집", max_retries=1),
    ReasoningStep(name="assess_takeover", tool_or_action="인수/소멸·대항력 판정",
                  backtrack_to="identify_priority", backtrack_change="기준권리 재확정", max_retries=1),
    ReasoningStep(name="structure", tool_or_action="조합 동의율·신탁 구조 검토"),
    ReasoningStep(name="registration_roadmap", tool_or_action="등기 절차·선행요건 로드맵"),
)

LEGAL_SCRIVENER_SPEC = SeniorAgentSpec(
    key="senior_legal_scrivener",
    name_ko="시니어 법무사",
    persona=("등기·권리분석·정비사업 조합/신탁 법무 지향. 말소기준권리 정확 판정, 동의율 정합, "
             "도산절연 보수 검토. 원칙: 인수 누락 금지(보수), 근거(법조문) 동반, 면허책임 고지."),
    knowledge_refs=(
        "legal:real_estate_registration", "legal:civil_execution", "legal:urban_renewal",
        "legal:trust_act", "rag:registry_precedent",
    ),
    decision_rules=_RULES,
    checklist=_CHECKLIST,
    failure_modes=_FAILURE_MODES,
    reasoning_steps=_STEPS,
    verify_lens="permit",
    license_gate="AI 보조 — 최종 등기·권리분석·정비/신탁 법무 책임은 법무사·변호사.",
    golden_case_refs=(),
    maturity=Maturity.JUNIOR_ASSIST,
    billing_key="senior_legal_scrivener",
    domain_min_cases=50,
)
