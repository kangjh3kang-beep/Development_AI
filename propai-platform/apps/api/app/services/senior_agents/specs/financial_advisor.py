"""시니어 금융전문가 — PF/대주 관점 spec(v3 B2·P0 최대갭 해소).

대주지표(DSCR·ICR·Debt Yield·YoC·Development Spread)·한국 PF 자기자본 단계규제·
자본스택/워터폴을 decision_rule로 인코딩. basis는 verified 기준(A2 citation 게이트 대상).
※상관 몬테카를로(fin.atypical_distribution)는 공사비 확률변수 승격·상관행렬 출처 명시 전제(미확보 시 정직고지).
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
        rule_id="fin.dscr_gate",
        condition="PF 대출 상환능력(부채상환계수) 평가",
        judgment=("DSCR=NOI/원리금. 1.25x 미만은 보수가정으로 거절 권고, "
                  "스트레스(금리+2%p) 후에도 미달이면 BLOCK"),
        basis="대주 표준약정 DSCR 커버넌트·금융권 PF 여신심사기준",
        tradeoff="엄격 DSCR(부도위험↓·레버리지↓·자기자본부담↑) / 완화(레버리지↑·부도위험↑)",
        exception="선분양 사업장은 분양대금 에스크로로 상환재원 보강 시 별도 판정",
        reasoning_blueprint="NOI 산정→원리금 스케줄→DSCR→스트레스 금리 재계산→1.25x 게이트",
    ),
    DecisionRule(
        rule_id="fin.icr_gate",
        condition="거치기간·브릿지론 이자상환능력(이자보상배율)",
        judgment=("ICR=NOI/이자비용. 원금 거치(이자만 납입) 단계에서 ICR<1.0이면 이자조차 미충당 → 위험. "
                  "본PF 전환·거치 구조에서 DSCR과 병행 평가"),
        basis="대주 표준 이자보상배율(ICR) 커버넌트(거치·브릿지 단계)",
        tradeoff="ICR 병행(거치기간 위험 포착·평가 복잡) / DSCR 단독(원리금만·거치단계 사각)",
        exception="준공 전 이자 자본화(사업비 산입) 구조는 현금 ICR 대신 자본화 반영 후 평가",
        reasoning_blueprint="거치/상환 구조 식별→NOI·이자비용→ICR(거치 1.0 게이트)+DSCR(상환) 병행",
    ),
    DecisionRule(
        rule_id="fin.development_spread",
        condition="개발 수익성(Yield-on-Cost 대비 시장 cap rate)",
        judgment=("Development Spread=YoC(안정화NOI/총사업비)−시장 cap rate. "
                  "<150bp 경고(목표 150~250bp)·<0 BLOCK(개발 비경제)"),
        basis="부동산개발 표준 수익성 지표(Yield-on-Cost·cap rate spread)",
        tradeoff="넓은 spread(개발마진↑·시장변동에 안전) / 좁은 spread(exit cap 상승에 취약)",
        exception="임대형 아닌 분양형은 분양마진(분양매출−총원가)으로 대체 평가",
        reasoning_blueprint="안정화 NOI→YoC→시장 cap 비교→spread→150bp/0 게이트",
    ),
    DecisionRule(
        rule_id="fin.equity_ratio_reg",
        condition="한국 PF 자기자본비율 단계 규제 적합성",
        judgment=("총사업비 대비 자기자본비율 단계 유도기준(인센티브 차등): "
                  "2026년 10%·2027년 15%·2028년 20%. "
                  "미달 시 경고(위험가중치·충당금↑·보증료·도시규제 완화 불리)"),
        basis="금융당국 부동산 PF 제도 개선방안(2024) 자기자본비율 단계 상향 유도(2026~2028)",
        tradeoff="자기자본↑(금융조달 유리·규제충족 / 자본효율 ROE↓) / 자기자본↓(ROE↑·규제미달 페널티)",
        exception="시행연도·경과조치는 최신 규정으로 시점정합 확인(연도 단정 금지)",
        reasoning_blueprint="총사업비→자기자본 투입액→비율→사업 착수연도 규제기준 대조→경고",
    ),
    DecisionRule(
        rule_id="fin.debt_sizing",
        condition="최대 대출가능액(debt sizing) 산정",
        judgment=("LTV·DSCR·Debt Yield(NOI/대출액) 세 제약으로 각각 대출액 역산 → "
                  "가장 보수적인 binding 제약을 채택"),
        basis="대주 표준 debt sizing(LTV·DSCR·Debt Yield 3제약 중 최소)",
        tradeoff="binding이 DSCR/Debt Yield(현금흐름 기반·보수) vs LTV(담보가치 기반·낙관)",
        exception="변동금리는 스트레스 금리로 DSCR·Debt Yield 재계산 후 binding 재판정",
        reasoning_blueprint="LTV한도·DSCR한도·DebtYield한도별 대출액 산출→최소값=binding→대출액 확정",
    ),
    DecisionRule(
        rule_id="fin.atypical_distribution",
        condition="비전형·고불확실 사업의 수익성 분포 추정",
        judgment=("단일 ROI 점추정 금지 → 상관 몬테카를로(분양가↔공사비↔금리 상관·공사비를 "
                  "확률변수로 승격)로 DSCR/IRR 분포·P5·적자확률을 구간(make_interval)으로 산출"),
        basis="PF 리스크 분석 표준(상관 시뮬레이션·하방꼬리 반영)",
        tradeoff="독립표집(단순·하방위험 과소추정) / 상관표집(현실적·상관행렬 출처 필요)",
        exception=("상관행렬 ρ 출처(실거래/과거 PF/전문가 prior) 미확보 시 "
                   "'상관 가정·민감도 동반'으로 정직 고지(임의가정 전락 금지)"),
        reasoning_blueprint="확률변수·상관행렬 정의→Cholesky 상관표집→DSCR/IRR 분포→P5·적자확률 구간",
    ),
)

_CHECKLIST = (
    "NOI 산정(공실·운영비 반영)", "DSCR·ICR(거치단계)", "원리금 스케줄·금리 스트레스",
    "총사업비 완전성(금융비·소프트비 포함)", "자기자본비율 규제연도",
    "자본스택(선순위/메자닌/에쿼티)", "HUG/HF 보증 적격", "exit cap·분양률 가정",
)

_FAILURE_MODES = (
    "DSCR·Development Spread 점추정 과신(분포·스트레스 누락)",
    "자기자본비율 규제 시행연도 오인(★시점 부정합)",
    "공사비를 상수로 둔 독립표집 → 적자확률 과소추정(과낙관)",
    "reason-code laundering(go/no-go 기여 왜곡)",
    "비현실 ROI(금융비·소프트비 0 가정 — 플랫폼 기지 결함)",
)

_STEPS = (
    ReasoningStep(name="capital_stack", tool_or_action="자본스택·총사업비 구성(feasibility)"),
    ReasoningStep(name="cashflow_noi", tool_or_action="현금흐름·안정화 NOI 산정",
                  backtrack_to="capital_stack", backtrack_change="사업비/자본 재구성", max_retries=1),
    ReasoningStep(name="debt_sizing", tool_or_action="LTV/DSCR/Debt Yield binding 역산",
                  backtrack_to="cashflow_noi", backtrack_change="NOI 가정 재검토", max_retries=2),
    ReasoningStep(name="stress_test", tool_or_action="상관 몬테카를로·동시충격 스트레스",
                  backtrack_to="debt_sizing", backtrack_change="대출액 보수화", max_retries=1),
    ReasoningStep(name="recommend", tool_or_action="Go/No-Go·조건부 권고(SHAP reason-code)"),
)

FINANCIAL_ADVISOR_SPEC = SeniorAgentSpec(
    key="senior_financial_advisor",
    name_ko="시니어 금융전문가",
    persona=("부동산 PF·구조화금융 자문 지향. 대주(여신) 관점 우선, 보수적 스트레스, "
             "한국 PF 자기자본 규제·자본스택/워터폴 정통. 원칙: 점추정 금지(분포·스트레스), 근거 동반."),
    knowledge_refs=(
        "rule:dscr", "rule:development_spread", "reg:pf_equity_ratio",
        "ref:hug_hf_guarantee", "rag:pf_finance",
    ),
    decision_rules=_RULES,
    checklist=_CHECKLIST,
    failure_modes=_FAILURE_MODES,
    reasoning_steps=_STEPS,
    verify_lens="feasibility",
    license_gate="AI 보조 — 최종 여신·투자 결정 책임은 금융기관·심사역.",
    golden_case_refs=(),  # 콜드스타트: 면허전문가 시드 후 채움(현재 0 → maturity=junior_assist)
    maturity=Maturity.JUNIOR_ASSIST,
    billing_key="senior_financial_advisor",
    domain_min_cases=50,
)
