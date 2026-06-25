"""시니어 도시계획전문가 정량 평가기 — 정비사업 비례율·권리가액·분담금(실수치).

urban_planner spec(urban.redevelopment_proportion)을 실제 입력으로 평가. 무목업: 입력 미비 생략.
입력(context['inputs']·원): post_appraisal_total(종후자산총평가)·total_project_cost(총사업비)·
prior_appraisal_total(종전자산총평가)·prior_appraisal_individual(개별 종전평가)·member_sale_price(조합원분양가).
비례율(%)=(종후−총사업비)/종전×100, 권리가액=종전개별×(비례율/100), 분담금=조합원분양가−권리가액.
"""

from __future__ import annotations

from app.services.senior_agents.evaluators.base import (
    BLOCK,
    PASS,
    WARN,
    RuleEvaluation,
    num,
)


def evaluate_urban(inputs: dict) -> list[RuleEvaluation]:
    """정비사업 비례율 평가(권리가액·분담금 detail 동반). 분모(종전평가) 0/음수·결측은 생략."""
    out: list[RuleEvaluation] = []
    post = num(inputs, "post_appraisal_total")
    cost = num(inputs, "total_project_cost")
    prior = num(inputs, "prior_appraisal_total")
    if post is not None and cost is not None and prior and prior > 0:
        rate = (post - cost) / prior * 100  # 비례율(%)
        verdict = BLOCK if rate <= 0 else (WARN if rate < 100 else PASS)
        detail = (f"비례율=(종후 {post:,.0f}−총사업비 {cost:,.0f})/종전 {prior:,.0f}×100 = {rate:.1f}%")
        # 권리가액·분담금(개별 종전평가·조합원분양가 제공 시)
        indiv = num(inputs, "prior_appraisal_individual")
        sale = num(inputs, "member_sale_price")
        if indiv is not None:
            right = indiv * (rate / 100)
            detail += f" · 권리가액={indiv:,.0f}×{rate:.1f}%={right:,.0f}"
            if sale is not None:
                burden = sale - right
                kind = "환급" if burden < 0 else "분담"
                detail += f" · 분담금=분양가 {sale:,.0f}−권리가액={burden:,.0f}({kind})"
        out.append(RuleEvaluation(
            rule_id="urban.redevelopment_proportion", label="비례율", value=round(rate, 1), unit="%",
            verdict=verdict, threshold="≥100% 양호 (≤0 BLOCK·<100 분담부담 WARN)",
            basis="도시정비법 관리처분계획(비례율·권리가액 산정 기준)",
            detail=detail))
    return out
