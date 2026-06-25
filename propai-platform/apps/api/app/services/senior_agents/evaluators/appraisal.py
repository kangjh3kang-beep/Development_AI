"""시니어 감정평가사 정량 평가기 — 종전자산 감정(토지+건물) → 비례율 기초.

desk_appraisal_service 산출(토지 공시지가기준·건물 원가법)을 consume(무목업·결측 생략).
★통합: 종전평가(prior)·감정가가 법무사 권리분석·도시계획 비례율로 전파.
입력(context['inputs']·원): land_appraised_total(토지 감정)·building_appraised_total(건물 감정·원가법).
"""

from __future__ import annotations

from app.services.senior_agents.evaluators.base import (
    PASS,
    WARN,
    RuleEvaluation,
    num,
)


def evaluate_appraisal(inputs: dict) -> list[RuleEvaluation]:
    """종전자산 감정 합산(토지+건물). 건물 미반영 시 과소평가 경고(무목업·정직)."""
    out: list[RuleEvaluation] = []
    land = num(inputs, "land_appraised_total")
    if land is not None and land >= 0:
        bldg_raw = num(inputs, "building_appraised_total")
        has_bldg = bldg_raw is not None and bldg_raw >= 0
        bldg = bldg_raw if has_bldg else 0.0
        prior = land + bldg
        # 음수 입력(감정가는 음수 불가)은 결측과 구분해 입력 오류 고지(데이터 신뢰).
        bldg_note = (" (건물 감정가 음수 — 입력 확인·토지만 반영·탁상 추정)"
                     if (bldg_raw is not None and bldg_raw < 0)
                     else " (건물 감정 미반영·토지만 → 종전평가 과소 주의·탁상 추정)")
        out.append(RuleEvaluation(
            rule_id="appraisal.prior_valuation", label="종전자산 감정(토지+건물)",
            value=round(prior, 0), unit="원",
            verdict=PASS if has_bldg else WARN,  # 건물 감정 미반영=과소평가 위험
            threshold="토지(공시지가기준)+건물(원가법) 합",
            basis="감정평가에 관한 규칙(제14·15조)·도시정비법(종전자산평가)",
            detail=(f"토지 {land:,.0f}원"
                    + (f" + 건물 {bldg:,.0f}원 = 종전평가 {prior:,.0f}원" if has_bldg
                       else bldg_note))))
    return out
