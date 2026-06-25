"""시니어 회계사 정량 평가기 — K-IFRS 1116 리스 분류·리스부채 현재가치.

accountant spec(acct.lease_classification)을 실제 입력으로 평가. 무목업: 결측 생략.
입력(context['inputs']): lease_term_months(리스기간 개월)·is_low_value(소액리스 여부 bool)·
annual_payment(연간 리스료 원)·discount_rate(내재이자율·분율 예 0.05).
단기(≤12개월) 또는 소액(is_low_value·기간 무관) → 면제(비용처리). 장기 → 사용권자산·리스부채 인식(연금현가).
"""

from __future__ import annotations

from app.services.senior_agents.evaluators.base import (
    PASS,
    RuleEvaluation,
    num,
)


def evaluate_accounting(inputs: dict) -> list[RuleEvaluation]:
    """리스 분류(단기/소액 면제) + 장기리스 리스부채 PV(연금현가). 결측 생략."""
    out: list[RuleEvaluation] = []
    term = num(inputs, "lease_term_months")
    if term is None or term < 0:
        return out

    is_low = bool(inputs.get("is_low_value"))
    if term <= 12 or is_low:
        reason = "단기리스(≤12개월)" if term <= 12 else "소액리스"
        out.append(RuleEvaluation(
            rule_id="acct.lease_classification", label="리스 분류(면제)", value=round(term, 0), unit="개월",
            verdict=PASS, threshold="단기(≤12개월)/소액 인식 면제",
            basis="K-IFRS 1116(리스) 단기·소액 리스 인식 면제",
            detail=f"{reason} → 사용권자산·리스부채 미인식, 리스료 비용처리"))
        return out

    # 장기리스 → 사용권자산·리스부채 인식. 리스부채=연간리스료의 연금현가(기말 지급 가정).
    years = term / 12
    payment = num(inputs, "annual_payment")
    rate = num(inputs, "discount_rate")
    detail = f"리스기간 {term:.0f}개월(>12) → 사용권자산·리스부채 인식"
    value: float | None = None
    if payment is not None and payment >= 0 and rate is not None and rate >= 0:
        pv = payment * years if rate == 0 else payment * (1 - (1 + rate) ** (-years)) / rate
        value = round(pv, 0)
        detail += f" · 리스부채 PV=연리스료 {payment:,.0f}의 연금현가({rate*100:.1f}%·{years:.1f}년)={pv:,.0f}"
    else:
        detail += " (연간리스료·할인율 입력 시 리스부채 현재가치 산출)"
    out.append(RuleEvaluation(
        rule_id="acct.lease_classification", label="리스 인식(리스부채 PV)", value=value, unit="원",
        verdict=PASS, threshold="장기리스 사용권자산·리스부채 인식",
        basis="K-IFRS 1116(리스) 사용권자산·리스부채 인식·현재가치 측정",
        detail=detail))
    return out
