"""SeniorOrchestrator — 시니어 에이전트 자문 오케스트레이션(P0 결정론 코어).

도메인/질의 → 적합 시니어 에이전트 선택(route) → decision_rule 적용(citation 게이트) →
confidence 캘리브레이션 → selective-prediction 게이트(전문가 확인 강등) →
근거(basis)·면허게이트·정직 maturity 동반 구조화 자문(consult) 산출.

LLM 추론(FinCoT·적대 debate, A6/A8)·실 서비스 배선(feasibility·expert_panel·legal KG)은
이 결정론 코어 위에 얹는 후속 계층. 본 코어는 공유서비스 미접촉 additive.

★정직성: 골든사례<50이면 maturity=junior_assist(시니어 분장 금지). 근거(basis) 미부착 또는
판단자격(tradeoff) 미달 룰은 산출에서 제외(A2 citation 구조적 차단). 고위험 도메인 임계 상향(A9).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.services.senior_agents.confidence import (
    compute_confidence,
    confidence_label,
    needs_expert_review,
)
from app.services.senior_agents.evaluators import BLOCK, EVALUATORS, WARN, worst_verdict
from app.services.senior_agents.reasoner import reason as _reason
from app.services.senior_agents.registry import get_senior_agent, list_senior_agents
from app.services.senior_agents.spec import DecisionRule, Maturity, SeniorAgentSpec

# 도메인(한/영) → 시니어 에이전트 키. 라우팅 단일 출처.
DOMAIN_ROUTES: dict[str, str] = {
    "urban": "senior_urban_planner", "도시계획": "senior_urban_planner", "정비사업": "senior_urban_planner",
    "finance": "senior_financial_advisor", "금융": "senior_financial_advisor", "pf": "senior_financial_advisor",
    "design": "senior_architect", "설계": "senior_architect", "건축설계": "senior_architect",
    "bim": "senior_bim_specialist", "BIM": "senior_bim_specialist",
    "deliberation": "senior_deliberation_member", "심의": "senior_deliberation_member",
    "tax": "senior_tax_advisor", "세무": "senior_tax_advisor", "세금": "senior_tax_advisor",
    "accounting": "senior_accountant", "회계": "senior_accountant",
    "legal": "senior_legal_scrivener", "법무사": "senior_legal_scrivener", "권리분석": "senior_legal_scrivener",
    "등기": "senior_legal_scrivener",
    "appraisal": "senior_appraiser", "감정평가": "senior_appraiser", "감정평가사": "senior_appraiser",
    "종전평가": "senior_appraiser",
    "cost": "senior_quantity_surveyor", "적산": "senior_quantity_surveyor",
    "시공": "senior_quantity_surveyor", "QS": "senior_quantity_surveyor",
}

# 고위험 도메인(A9): 오판 비용이 큼(심의·세무·PF 거절·권리 인수누락·감정 과대) → confidence 임계 상향.
HIGH_RISK_AGENT_KEYS: frozenset[str] = frozenset({
    "senior_financial_advisor", "senior_tax_advisor", "senior_deliberation_member",
    "senior_legal_scrivener", "senior_appraiser",
})


@dataclass(frozen=True)
class SeniorConsultation:
    """시니어 자문 결과(결정론 코어) — LLM 서술 전 단계의 구조화 가이드."""

    agent_key: str
    name_ko: str
    maturity: str                       # 성숙도 라벨(정직 — 골든사례 기반)
    decision_framework: tuple[dict[str, str], ...]  # citation 게이트 통과 판단(근거 동반)
    checklist: tuple[str, ...]
    risk_warnings: tuple[str, ...]      # failure_modes(시니어가 의심하는 실패모드)
    confidence: float
    confidence_label: str
    needs_expert_review: bool
    high_risk: bool
    citations: tuple[str, ...]          # 근거(basis) 집합 — A2 citation 표면
    license_gate: str
    honest_notes: tuple[str, ...] = field(default_factory=tuple)
    evaluations: tuple[dict[str, Any], ...] = field(default_factory=tuple)  # 정량 실측 판정(입력 시)
    overall_verdict: str | None = None  # 평가 종합 최악판정(PASS/WARN/BLOCK·없으면 None)
    reasoning: dict[str, Any] | None = None  # FinCoT 추론(include_reasoning 시·없으면 None)

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_key": self.agent_key,
            "name_ko": self.name_ko,
            "maturity": self.maturity,
            "decision_framework": list(self.decision_framework),
            "checklist": list(self.checklist),
            "risk_warnings": list(self.risk_warnings),
            "confidence": self.confidence,
            "confidence_label": self.confidence_label,
            "needs_expert_review": self.needs_expert_review,
            "high_risk": self.high_risk,
            "citations": list(self.citations),
            "license_gate": self.license_gate,
            "honest_notes": list(self.honest_notes),
            "evaluations": list(self.evaluations),
            "overall_verdict": self.overall_verdict,
            "reasoning": self.reasoning,
        }


def _citation_gated_rules(
    spec: SeniorAgentSpec, matched_rule_ids: set[str] | None,
) -> tuple[DecisionRule, ...]:
    """A2 citation 게이트: 판단자격(tradeoff+basis) 충족 룰만 통과. matched 지정 시 그 부분집합."""
    rules = tuple(r for r in spec.decision_rules if r.is_judgment() and r.basis.strip())
    if matched_rule_ids is not None:
        rules = tuple(r for r in rules if r.rule_id in matched_rule_ids)
    return rules


def _coerce_matched_ids(matched: Any) -> set[str] | None:
    """matched_rule_ids 방어적 정규화(외부 입력 안전).

    None/빈값→None(필터 없음), 문자열→단일 id({s})(문자분해 방지),
    list/tuple/set→문자열 집합. 그 외(정수·dict 등)→ValueError(미처리 500 차단).
    """
    if not matched:
        return None
    if isinstance(matched, str):
        return {matched}
    if isinstance(matched, (list, tuple, set)):
        return {str(x) for x in matched}
    raise ValueError(f"matched_rule_ids는 문자열 리스트여야 합니다(got {type(matched).__name__}).")


def _rule_to_dict(r: DecisionRule) -> dict[str, str]:
    d = {"rule_id": r.rule_id, "condition": r.condition, "judgment": r.judgment,
         "basis": r.basis, "tradeoff": r.tradeoff}
    if r.exception:
        d["exception"] = r.exception
    if r.reasoning_blueprint:
        d["reasoning_blueprint"] = r.reasoning_blueprint
    return d


class SeniorOrchestrator:
    """시니어 에이전트 자문 라우팅·게이팅 오케스트레이터(결정론·무상태)."""

    def route(self, domain_or_key: str) -> str | None:
        """도메인(한/영) 또는 에이전트 키 → 등록된 에이전트 키. 미해당 시 None."""
        if not domain_or_key:
            return None
        if get_senior_agent(domain_or_key) is not None:
            return domain_or_key
        return DOMAIN_ROUTES.get(domain_or_key) or DOMAIN_ROUTES.get(domain_or_key.lower())

    def available(self) -> list[dict[str, Any]]:
        """등록 에이전트 요약(키·이름·고위험·콜드스타트 성숙도)."""
        out = []
        for spec in list_senior_agents():
            out.append({
                "key": spec.key, "name_ko": spec.name_ko,
                "high_risk": spec.key in HIGH_RISK_AGENT_KEYS,
                "maturity": spec.maturity_for(len(spec.golden_case_refs)).label,
                "rule_count": len(spec.decision_rules),
            })
        return out

    def consult(
        self,
        domain_or_key: str,
        *,
        context: dict[str, Any] | None = None,
        high_risk: bool | None = None,
        golden_case_count: int | None = None,
    ) -> SeniorConsultation:
        """단일 시니어 자문. context 신호로 confidence 산정·전문가 확인 게이트.

        context(선택): data_completeness/rag_strength/correction_rate([0,1])·matched_rule_ids(set).
        """
        key = self.route(domain_or_key)
        spec = get_senior_agent(key) if key else None
        if spec is None:
            raise ValueError(f"미등록 도메인/에이전트: {domain_or_key!r}")
        ctx = context or {}

        # 성숙도(정직): 골든사례 수 기반(미지정 시 spec의 시드 수=콜드스타트 0).
        gc = golden_case_count if golden_case_count is not None else len(spec.golden_case_refs)
        maturity = spec.maturity_for(gc)

        # 고위험: 명시 우선, 미지정 시 도메인 기본.
        hr = high_risk if high_risk is not None else (spec.key in HIGH_RISK_AGENT_KEYS)

        # 적용 판단(citation 게이트). matched_rule_ids 미지정 시 전 판단 프레임워크 제시.
        matched_set = _coerce_matched_ids(ctx.get("matched_rule_ids"))
        rules = _citation_gated_rules(spec, matched_set)

        # confidence 신호: 미지정은 None(중립 0.5). rule_fit=적용 룰 비율(matched 지정 시).
        all_judgable = _citation_gated_rules(spec, None)
        rule_fit = ctx.get("rule_fit")
        if rule_fit is None and matched_set is not None and all_judgable:
            rule_fit = len(rules) / len(all_judgable)
        confidence = compute_confidence(
            data_completeness=ctx.get("data_completeness"),
            rule_fit=rule_fit,
            rag_strength=ctx.get("rag_strength"),
            correction_rate=ctx.get("correction_rate"),
        )
        needs_review = needs_expert_review(confidence, high_risk=hr)
        label = confidence_label(confidence, high_risk=hr)

        # 정량 평가(입력 수치 제공 시): decision_rule을 실측 PASS/WARN/BLOCK로 판정.
        evaluator = EVALUATORS.get(spec.key)
        inputs = ctx.get("inputs")
        evaluations: tuple[dict[str, Any], ...] = ()
        overall: str | None = None
        if evaluator and isinstance(inputs, dict):
            evals = evaluator(inputs)
            evaluations = tuple(e.to_dict() for e in evals)
            overall = worst_verdict(evals)

        notes: list[str] = []
        if maturity is Maturity.JUNIOR_ASSIST:
            notes.append(f"검증 보조 단계(골든사례 {gc}건<{spec.domain_min_cases}) — 면허전문가 검토 필수.")
        if needs_review:
            notes.append("신뢰도 임계 미달 — 전문가 확인으로 강등(selective prediction).")
        if hr:
            notes.append("고위험 도메인 — 보수적 판정·신뢰컷 상향 적용.")
        if not rules:
            notes.append("적용 가능한 판단 규칙 없음 — 입력/도메인 재확인 필요.")
        if evaluator and not evaluations:
            notes.append("정량 입력(예: noi·total_cost·market_cap_rate) 제공 시 실측 PASS/WARN/BLOCK 산출.")
        if overall == BLOCK:
            notes.append("★차단(BLOCK) 항목 존재 — 해당 지표 미충족, 사업성/요건 재검토 필요.")
        elif overall == WARN:
            notes.append("경고(WARN) 항목 존재 — 보수 가정·조건부 검토 권장.")

        citations = tuple(sorted({r.basis.strip() for r in rules}))

        # FinCoT 추론(요청 시·결정론 구조). LLM 서술은 미주입(기본 off) — 호출측이 runner 주입 시 생성.
        reasoning: dict[str, Any] | None = None
        if ctx.get("include_reasoning"):
            reasoning = _reason({
                "name_ko": spec.name_ko,
                "license_gate": spec.license_gate,
                "decision_framework": [_rule_to_dict(r) for r in rules],
                "evaluations": list(evaluations),
                "high_risk": hr,
                "needs_expert_review": needs_review,
                "overall_verdict": overall,
                "citations": list(citations),
            }).to_dict()

        return SeniorConsultation(
            agent_key=spec.key,
            name_ko=spec.name_ko,
            maturity=maturity.label,
            decision_framework=tuple(_rule_to_dict(r) for r in rules),
            checklist=spec.checklist,
            risk_warnings=spec.failure_modes,
            confidence=confidence,
            confidence_label=label,
            needs_expert_review=needs_review,
            high_risk=hr,
            citations=citations,
            license_gate=spec.license_gate,
            honest_notes=tuple(notes),
            evaluations=evaluations,
            overall_verdict=overall,
            reasoning=reasoning,
        )

    def consult_multi(
        self,
        domains_or_keys: list[str],
        *,
        context: dict[str, Any] | None = None,
    ) -> list[SeniorConsultation]:
        """다도메인(개발사업=도시+금융+설계 등) 자문 — 중복 에이전트 제거, 미해당 무시."""
        seen: set[str] = set()
        out: list[SeniorConsultation] = []
        for d in domains_or_keys:
            key = self.route(d)
            if key is None or key in seen:
                continue
            seen.add(key)
            out.append(self.consult(key, context=context))
        return out


# 무상태 싱글톤(편의).
senior_orchestrator = SeniorOrchestrator()
