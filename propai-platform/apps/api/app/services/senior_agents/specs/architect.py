"""시니어 설계사 — 인허가 부합 매스/배치 spec(v3 B3·외부엔진 BFF 탈피).

정북일조 사선후퇴(건축법 시행령 86조)·동지 일조 게이트·buildable envelope 우선순위를
decision_rule로 인코딩. 정북후퇴를 envelope 한도로 직접 반영.
★현 엔진(auto_design_engine·solar_envelope_service·building_code_rules)은 구법 9m 임계를 쓰므로
현행 10m(2023.9.12 개정)로 교정 필요 — 본 spec이 그 기준선(후속 공용헬퍼 일원화 대상).
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
        rule_id="design.buildable_envelope",
        condition="대지 가용 건축영역(buildable envelope) 산정 순서",
        judgment=("이격거리(setback)+정북일조 사선후퇴(시행령 86조)+법정주차대수를 먼저 고정 → "
                  "잔여 envelope 산출 → envelope 내에서 unit_mix 최적화(목적=Yield-on-Cost)"),
        basis="건축법 시행령 제86조(일조 높이제한)·주차장법 부설주차장 설치기준",
        tradeoff="구조효율(정형·시공비↓·평면자유도↓) vs 평면자유도(상품성↑·구조비↑)",
        exception="준주거·상업지역은 정북방향 일조 사선후퇴 미적용(단 채광방향 인동간격은 별도 적용)",
        reasoning_blueprint="setback→정북후퇴→주차고정→잔여 envelope→unit_mix(YoC 목적함수)",
    ),
    DecisionRule(
        rule_id="design.bukchuk_setback",
        condition="전용/일반주거지역 정북방향 일조 사선제한",
        judgment=("정북방향 인접대지경계선에서 높이 10m 이하는 1.5m 이상, "
                  "10m 초과 부분은 해당 높이의 1/2 이상 이격(고저차 시 평균수평면 기준)"),
        basis="건축법 시행령 제86조 제1항(정북방향 일조 높이제한·2023.9.12 개정 완화)",
        tradeoff="후퇴 준수(일조분쟁↓·법적합) / 미적용 시 가용 envelope↑·층수↑이나 위법",
        exception="전용/일반주거지역에만 적용(준주거·상업지역 제외)",
        reasoning_blueprint="용도지역 확인→정북 경계 식별→10m 구간별 후퇴량→envelope 한도 반영",
    ),
    DecisionRule(
        rule_id="design.winter_daylight_gate",
        condition="주거동 동지 일조 확보 검증(법정 인허가 게이트 + 분쟁 리스크)",
        judgment=("인허가 게이트: 동지일 09~15시 연속 2시간 이상 미충족 시 reject"
                  "(채광방향 인동간격 예외요건). "
                  "분쟁 경고(별도): 동지 08~16시 총 4시간 AND 09~15시 연속 2시간"
                  "(판례 수인한도) 미충족 시 일조분쟁 위험 고지"),
        basis=("건축법 시행령 제86조 제3항(채광 인동간격 예외=동지 09~15시 2시간)·"
               "일조방해 수인한도 판례(동지 08~16시 4시간 AND 09~15시 2시간)"),
        tradeoff="일조 우선(저밀·이격↑·세대수↓) / 밀도 우선(세대수↑·일조 미달·분쟁 위험)",
        exception="도시형생활주택·오피스텔 등 일조기준 비적용 용도는 게이트 완화",
        reasoning_blueprint="배치안→동지 음영 시뮬→연속 2h(법정 reject 게이트)→4h AND 2h(판례 분쟁경고)",
    ),
)

_CHECKLIST = (
    "용도지역·건폐/용적 실효(조례)", "정북일조 후퇴", "이격거리(인동간격)",
    "법정 주차대수", "동지 일조", "피난·방화", "unit_mix(YoC)",
)

_FAILURE_MODES = (
    "정북일조 후퇴 임계높이를 구법 9m로 산정(현행 10m 미반영) → 9~10m 구간 후퇴 과대 → "
    "envelope 과소추정(★현 엔진 결함: auto_design_engine·solar_envelope_service·building_code_rules)",
    "동지 일조 미충족 배치를 '가능'으로 제시(법정 2h 게이트 누락)",
    "주차대수 사후고려로 envelope 재산정 누락",
    "준주거/상업에 정북후퇴 오적용",
    "용적률 법정 사용(실효 조례·특이부지 미반영)",
)

_STEPS = (
    ReasoningStep(name="setback_gate", tool_or_action="이격·용도지역 게이트"),
    ReasoningStep(name="bukchuk_envelope", tool_or_action="정북후퇴 반영 envelope(solar_envelope)",
                  backtrack_to="setback_gate", backtrack_change="용도지역/이격 재확인", max_retries=1),
    ReasoningStep(name="parking_fix", tool_or_action="법정 주차대수 고정"),
    ReasoningStep(name="unit_mix", tool_or_action="envelope 내 unit_mix 최적화(YoC)"),
    ReasoningStep(name="daylight_verify", tool_or_action="동지 일조 검증",
                  backtrack_to="bukchuk_envelope", backtrack_change="일조 미달 시 배치/층수 재조정",
                  max_retries=2),
)

ARCHITECT_SPEC = SeniorAgentSpec(
    key="senior_architect",
    name_ko="시니어 설계사",
    persona=("건축사 지향. 인허가 부합 매스·배치 우선, 정북일조·동지 일조를 envelope 한도로 선반영. "
             "원칙: envelope 과대추정 금지, 실효(조례) 용적률, 근거(법조문) 동반."),
    knowledge_refs=(
        "legal:building_act", "rule:bukchuk_setback", "rule:winter_daylight",
        "rule:parking_standard", "rag:design_modules",
    ),
    decision_rules=_RULES,
    checklist=_CHECKLIST,
    failure_modes=_FAILURE_MODES,
    reasoning_steps=_STEPS,
    verify_lens="design",
    license_gate="AI 보조 초안 — 최종 설계·인허가 책임은 건축사.",
    golden_case_refs=(),
    maturity=Maturity.JUNIOR_ASSIST,
    billing_key="senior_architect",
    domain_min_cases=50,
)
