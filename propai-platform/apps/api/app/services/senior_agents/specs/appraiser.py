"""시니어 감정평가사 — 감정평가(공시지가기준법·원가법·거래사례·수익환원)·종전평가 spec(9번째).

감정평가에 관한 규칙 기준 방법론을 decision_rule로 인코딩(desk_appraisal_service 도메인 정합).
★통합: 종전평가·감정가가 시니어 법무사 권리분석(실매입가=감정가−소멸+인수)·도시계획 비례율로 전파.
basis는 verified(감칙 조문). 정식 감정 아닌 탁상 추정 — 면허(감정평가사) 인간게이트.
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
        rule_id="appraisal.land_official_basis",
        condition="토지 감정평가(원칙 방법)",
        judgment=("공시지가기준법: 개별공시지가 × 시점수정 × 지역요인 × 개별요인(접도·면적·형상) × "
                  "그 밖의 요인(시세 괴리 보정)"),
        basis="감정평가에 관한 규칙 제14조(공시지가기준법)",
        tradeoff="공시지가 기준(객관·보수) / 그 밖의 요인 보정 과대 시 시세 추종(주관 위험)",
        exception="거래사례·수익환원으로 교차검증, 괴리 크면 신뢰도 강등·근거 명시",
        reasoning_blueprint="개별공시지가→시점수정→지역/개별요인→그 밖의 요인→토지 감정가",
    ),
    DecisionRule(
        rule_id="appraisal.building_cost",
        condition="건물 감정평가(원가법)",
        judgment=("원가법: 재조달원가(구조별 원/㎡) × 연면적 × 잔가율(1 − 경과/내용연수, 하한 20%). "
                  "구조(RC/SRC/철골/조적/목조)별 내용연수 적용"),
        basis="감정평가에 관한 규칙 제15조(원가법)·건축물대장 구조·사용승인일",
        tradeoff="원가법(신축·특수건물 적합) / 노후·임대건물은 수익환원 병행(시장가 반영↑)",
        exception="미등기·무허가는 건물가치 0 또는 정직 고지(보존등기 전 평가 불가)",
        reasoning_blueprint="구조·연면적·준공연도→재조달원가→경과연수 잔가율→건물 감정가",
    ),
    DecisionRule(
        rule_id="appraisal.method_reconcile",
        condition="감정 방법 결합·검증(신뢰도)",
        judgment=("공시지가기준법(주) + 거래사례비교법(보조) + 수익환원법(임대형) 결합. "
                  "방법 간 괴리로 신뢰도 산출, 과대·과소 이상치 배제"),
        basis="감정평가에 관한 규칙(방법 적용·검토)·거래사례비교법·수익환원법",
        tradeoff="단일법(빠름·편향) / 다방법 결합(신뢰↑·데이터 부담)",
        exception="거래사례 부족·임대료 미상 시 해당 방법 생략·신뢰도 정직 강등",
        reasoning_blueprint="방법별 추정→괴리 분석→가중 결합→신뢰도·근거",
    ),
    DecisionRule(
        rule_id="appraisal.prior_valuation",
        condition="정비사업 종전자산 평가(관리처분 기준)",
        judgment=("종전자산평가 = 토지(공시지가기준) + 건물(원가법) 합. 조합원별 개별평가 → 권리가액·비례율 "
                  "기초. ★감정가는 법무사 권리분석(실매입가)·도시계획 비례율로 전파"),
        basis="도시 및 주거환경정비법(관리처분계획 종전자산평가)·감정평가에 관한 규칙",
        tradeoff="보수 감정(분담금 보수·갈등↓) / 적극 감정(비례율↑·종후 미확정 위험)",
        exception="종후평가 미확정 시 잠정·±10% 민감도 동반(정직). 정식 감정은 감정평가사 의뢰",
        reasoning_blueprint="필지별 토지+건물 감정→종전자산총평가→권리가액·비례율 전파(법무사·도시계획)",
    ),
)

_CHECKLIST = (
    "개별공시지가·시점수정", "접도·면적·형상 개별요인", "그 밖의 요인(시세 괴리)",
    "건물 구조·연면적·준공연도", "재조달원가·잔가율", "거래사례·수익환원 교차검증", "종전자산 합산",
)

_FAILURE_MODES = (
    "그 밖의 요인 보정 과대 → 감정가 시세 추종(과대평가)",
    "건물 잔가율 미적용·내용연수 오류(노후건물 과대)",
    "미등기·무허가 건물가치 계상(★보존등기 전 평가 불가)",
    "종후평가 미확정값을 확정처럼 제시(비례율 과대)",
    "단일 방법 의존(거래사례·수익환원 교차검증 누락)",
)

_STEPS = (
    ReasoningStep(name="land_basis", tool_or_action="공시지가기준 토지 감정(desk_appraisal)"),
    ReasoningStep(name="building_cost", tool_or_action="원가법 건물 감정"),
    ReasoningStep(name="reconcile", tool_or_action="거래사례·수익환원 교차검증·신뢰도",
                  backtrack_to="land_basis", backtrack_change="괴리 크면 요인 재검토", max_retries=1),
    ReasoningStep(name="prior_total", tool_or_action="종전자산 합산·권리가액/비례율 전파"),
)

APPRAISER_SPEC = SeniorAgentSpec(
    key="senior_appraiser",
    name_ko="시니어 감정평가사",
    persona=("감정평가사 지향. 공시지가기준법(원칙)·원가법·거래사례·수익환원 결합, 그 밖의 요인 보수. "
             "원칙: 과대평가 경계, 다방법 교차검증, 탁상 추정 정직 고지, 종전평가 권리분석/비례율 전파."),
    knowledge_refs=(
        "rule:official_land_price_method", "rule:cost_method", "rule:sales_comparison",
        "legal:urban_renewal", "rag:appraisal_precedent",
    ),
    decision_rules=_RULES,
    checklist=_CHECKLIST,
    failure_modes=_FAILURE_MODES,
    reasoning_steps=_STEPS,
    verify_lens="feasibility",
    license_gate="AI 보조 탁상 추정 — 최종 감정평가 책임은 감정평가사(정식 평가 의뢰).",
    golden_case_refs=(),
    maturity=Maturity.JUNIOR_ASSIST,
    billing_key="senior_appraiser",
    domain_min_cases=50,
)
