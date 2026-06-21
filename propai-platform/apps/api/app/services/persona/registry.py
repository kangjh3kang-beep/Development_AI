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
    output_keys: tuple[str, ...] = field(default_factory=tuple)  # artifacts 의 주요 키(문서화)
    billing_key: str = ""         # service_fees.analysis_modules 키(미설정=무료, R4)


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


PERSONA_REGISTRY: dict[str, PersonaSpec] = {
    _SALES.key: _SALES,
    _URBAN.key: _URBAN,
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
