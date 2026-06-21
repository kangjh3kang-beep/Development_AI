"""실무 전문가 페르소나 레지스트리 — 선언만(실행은 runner).

각 페르소나는 '무엇을 보고(체크리스트)·무슨 서비스를 조립하고(bound_services)·
어떤 전문가 렌즈로 교차검증하는지(expert_lens)'를 정적으로 선언한다. 실행 로직은
runner.run_persona 가 담당해 선언/실행을 분리한다(R9 단위테스트 용이).

확장: 디벨로퍼·설계·시공 등 후속 페르소나는 PERSONA_REGISTRY 에 PersonaSpec 추가만 하면 된다.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ChecklistSpec:
    """체크리스트 1단계 선언 — judge_key 는 checklist.py 의 규칙기반 판정 함수 키."""

    step: str
    label: str
    judge_key: str
    kpi: str | None = None


@dataclass(frozen=True)
class PersonaSpec:
    """페르소나 정적 명세."""

    key: str
    name_ko: str
    system_prompt: str            # LLM 내러티브용(use_llm=True 시만). 규칙기반 경로는 불필요.
    checklist: tuple[ChecklistSpec, ...]
    bound_services: tuple[str, ...]   # runner 가 dispatch 하는 서비스 식별자
    expert_lens: str              # ExpertPanelService analysis_type ("sales"/"permit"/"legal")
    # runner 의 파이프라인 함수 식별자. run_persona 가 if/elif 분기 대신 이 키로
    # registry-driven dispatch 한다(P2에서 분기 추가 시 등록만 하면 됨). 기본은 key 와 동일.
    runner_key: str = ""
    output_keys: tuple[str, ...] = field(default_factory=tuple)  # artifacts 의 주요 키(문서화)
    billing_key: str = ""         # service_fees.analysis_modules 키(미설정=무료, R4)

    @property
    def dispatch_key(self) -> str:
        """runner 가 dispatch 할 파이프라인 키(미설정 시 key 와 동일)."""
        return self.runner_key or self.key


# ── 분양대행 전문가 ──
_SALES = PersonaSpec(
    key="sales_agent",
    name_ko="분양대행 전문가",
    system_prompt=(
        "당신은 분양대행·마케팅 18년 차 전문가입니다. 주변 실거래 시세를 앵커로 한 적정분양가, "
        "지불여력(PIR/DSR/LTV) 검증, 분양전략(프리미엄 tier·청약 가능성), 계약구조를 실무 관점에서 "
        "제시합니다. 데이터에 있는 수치만 사용하고, 미확보 항목은 정직하게 고지합니다."
    ),
    checklist=(
        ChecklistSpec("price", "적정분양가 책정(거래사례+지불여력)", "sales_price", "신뢰도·tier"),
        ChecklistSpec("cost", "원가 회수 가능성(2차 가드)", "sales_cost", "원가비율"),
        ChecklistSpec("strategy", "분양전략(프리미엄 tier)", "sales_strategy", "tier 선택"),
        ChecklistSpec("subscription", "청약·계약 구조 가능성", "sales_subscription", "수요 시그널"),
    ),
    bound_services=("suggest_base_price", "market_report", "market_interpreter"),
    expert_lens="sales",
    output_keys=("price_tiers", "market_reference", "cost_validation", "strategy"),
    billing_key="persona_sales_agent",
)

# ── 도시계획 전문가 ──
_URBAN = PersonaSpec(
    key="urban_planner",
    name_ko="도시계획 전문가",
    system_prompt=(
        "당신은 도시계획·건축 인허가 전문가(도시계획 15년)입니다. 용도지역·특이부지 게이트, "
        "개발방식 판정(지구단위·정비·도시개발·가로주택·모아주택·역세권), 인센티브(종상향·용적완화), "
        "인허가 로드맵·리스크를 분석합니다. 법정/조례/실효 한도를 분리하고 미확보는 정직 고지합니다."
    ),
    checklist=(
        ChecklistSpec("zone", "용도지역·특이부지 게이트", "urban_zone", "developability"),
        ChecklistSpec("method", "개발방식 판정(AHP)", "urban_method", "최적 방식"),
        ChecklistSpec("incentive", "인센티브(종상향·용적완화)", "urban_incentive", "상향 잠재"),
        ChecklistSpec("permit", "인허가 리스크·로드맵", "urban_permit", "리스크 등급"),
    ),
    bound_services=(
        "permit_analysis", "development_method", "regulation_analysis", "special_parcel",
    ),
    expert_lens="permit",
    output_keys=("zone_limits", "dev_methods", "incentives", "permit_roadmap", "gate"),
    billing_key="persona_urban_planner",
)


# ── 디벨로퍼(사업타당성) 전문가 ──
_DEVELOPER = PersonaSpec(
    key="developer",
    name_ko="디벨로퍼(사업타당성) 전문가",
    system_prompt=(
        "당신은 부동산 개발 PF·수지분석 20년 차 디벨로퍼입니다. 사업타당성(매출·원가·순이익·"
        "ROI/ROE/NPV), 리스크 매트릭스(시장·인허가·자금·공사), Go/No-Go 의사결정을 시행사 관점에서 "
        "제시합니다. 데이터에 있는 수치만 사용하고, DSCR 등 미산출 지표는 정직하게 고지합니다."
    ),
    checklist=(
        ChecklistSpec("viability", "사업타당성(Top3 수지·ROI)", "dev_viability", "ROI·등급"),
        ChecklistSpec("risk", "리스크 매트릭스(시장·인허가·자금·공사)", "dev_risk", "리스크 등급"),
        ChecklistSpec("irr_npv", "IRR/NPV/DSCR 수익성", "dev_irr_npv", "NPV·DSCR"),
        ChecklistSpec("go_nogo", "Go/No-Go 판정", "dev_go_nogo", "투자 결정"),
    ),
    bound_services=("feasibility_v2", "auto_recommend_top3", "feasibility_interpreter"),
    expert_lens="feasibility",   # ROSTERS 보유 키(business/developer 강등 회피)
    runner_key="developer",
    output_keys=("recommendations", "risk_matrix", "kpi", "go_nogo"),
    billing_key="persona_developer",
)

# ── 설계(CAD/BIM) 전문가 ──
_DESIGNER = PersonaSpec(
    key="designer",
    name_ko="설계(건축·BIM) 전문가",
    system_prompt=(
        "당신은 건축사·BIM 설계 18년 차 전문가입니다. 매스 배치(건폐율·용적률·층수), 유닛믹스 "
        "(수익 극대화 평형 배분), 법규 준수(건폐/용적/높이 한도), 세대수·전용률 효율을 실무 관점에서 "
        "검토합니다. 데이터에 있는 수치만 사용하고, 미확보 항목은 정직하게 고지합니다."
    ),
    checklist=(
        ChecklistSpec("layout", "매스 배치(건폐·용적·층수)", "design_layout", "매스 규모"),
        ChecklistSpec("unit_mix", "유닛믹스(수익 극대 평형배분)", "design_unit_mix", "세대수·매출"),
        ChecklistSpec("compliance", "법규 준수(건폐/용적/높이)", "design_compliance", "한도 여유"),
        ChecklistSpec("efficiency", "세대수·전용률 효율", "design_efficiency", "효율"),
    ),
    bound_services=("design_mass", "unit_mix_optimizer", "design_interpreter"),
    expert_lens="design",
    runner_key="designer",
    output_keys=("mass", "unit_mix", "compliance", "efficiency"),
    billing_key="persona_designer",
)

# ── 시공(공사비·적산) 전문가 ──
_CONSTRUCTOR = PersonaSpec(
    key="constructor",
    name_ko="시공(공사비·적산) 전문가",
    system_prompt=(
        "당신은 건설 원가관리·VE(가치공학) 20년 차 전문가입니다. 공사비 견적(지상·지하·조경·간접·"
        "최저~최대 레인지), QTO 물량(레미콘·철근·거푸집 등), 평단가 적정성, 원가비율·안전마진을 "
        "실무 관점에서 검토합니다. 데이터에 있는 수치만 사용하고, 미확보 항목은 정직하게 고지합니다."
    ),
    checklist=(
        ChecklistSpec("unit_cost", "공사비 견적(평단가·레인지)", "const_unit_cost", "평단가"),
        ChecklistSpec("qto", "QTO 물량 적산(부위별)", "const_qto", "물량 항목수"),
        ChecklistSpec("schedule", "공기·구조 적정성", "const_schedule", "구조계수"),
        ChecklistSpec("cost_safety", "원가비율·안전마진", "const_cost_safety", "레인지 폭"),
    ),
    bound_services=("estimate_overview", "cost_interpreter"),
    expert_lens="cost",
    runner_key="constructor",
    output_keys=("estimate", "qto", "range", "safety"),
    billing_key="persona_constructor",
)


PERSONA_REGISTRY: dict[str, PersonaSpec] = {
    _SALES.key: _SALES,
    _URBAN.key: _URBAN,
    _DEVELOPER.key: _DEVELOPER,
    _DESIGNER.key: _DESIGNER,
    _CONSTRUCTOR.key: _CONSTRUCTOR,
}


def get_persona(key: str) -> PersonaSpec | None:
    return PERSONA_REGISTRY.get(key)


def list_personas() -> list[dict]:
    """레지스트리 메타(키·이름·체크리스트·렌즈·과금키) — /personas 목록 응답용."""
    out: list[dict] = []
    for spec in PERSONA_REGISTRY.values():
        out.append({
            "key": spec.key,
            "name_ko": spec.name_ko,
            "checklist": [
                {"step": c.step, "label": c.label, "kpi": c.kpi} for c in spec.checklist
            ],
            "expert_lens": spec.expert_lens,
            "output_keys": list(spec.output_keys),
            "billing_key": spec.billing_key,
        })
    return out
