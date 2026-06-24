"""시니어 금융전문가 정량 평가기 — 대주지표 실수치 PASS/WARN/BLOCK.

financial_advisor spec의 decision_rule을 실제 입력으로 평가. 입력 미비 평가는 생략(무목업).
입력(context['inputs']) 키(원/배수/분율): noi, debt_service, interest, stabilized_noi,
total_cost, market_cap_rate(분율 예 0.045), equity, project_year, loan_amount, debt_yield_min(분율).
근거는 spec과 동일 출처(citation 게이트 대상). market_cap_rate·금리·비율은 분율(0~1)로 받는다.
"""

from __future__ import annotations

from app.services.senior_agents.evaluators.base import (
    BLOCK,
    PASS,
    WARN,
    RuleEvaluation,
    num,
    num_or,
)

# 한국 PF 자기자본비율 단계 규제(2024 부동산 PF 제도 개선방안) — 연도별 기준.
EQUITY_REQ_BY_YEAR = {2026: 0.10, 2027: 0.15, 2028: 0.20}
DSCR_MIN = 1.25
DEV_SPREAD_WARN = 0.015   # 150bp
DEBT_YIELD_MIN_DEFAULT = 0.08


def evaluate_financial(inputs: dict) -> list[RuleEvaluation]:
    """입력 수치로 대주지표 평가. 계산 가능한 룰만 반환(분모 0/음수·결측은 생략)."""
    out: list[RuleEvaluation] = []

    # DSCR = NOI / 원리금. <1.0 BLOCK·<1.25 거절권고(WARN)·이상 PASS.
    noi, ds = num(inputs, "noi"), num(inputs, "debt_service")
    if noi is not None and ds and ds > 0:
        dscr = noi / ds
        verdict = BLOCK if dscr < 1.0 else (WARN if dscr < DSCR_MIN else PASS)
        out.append(RuleEvaluation(
            rule_id="fin.dscr_gate", label="DSCR(부채상환계수)", value=round(dscr, 3), unit="x",
            verdict=verdict, threshold=f"≥{DSCR_MIN} (1.0 미만 BLOCK)",
            basis="대주 표준약정 DSCR 커버넌트·금융권 PF 여신심사기준",
            detail=f"NOI {noi:,.0f} / 원리금 {ds:,.0f} = {dscr:.3f}x"))

    # ICR = NOI / 이자. <1.0 BLOCK(거치 이자 미충당)·이상 PASS.
    interest = num(inputs, "interest")
    if noi is not None and interest and interest > 0:
        icr = noi / interest
        out.append(RuleEvaluation(
            rule_id="fin.icr_gate", label="ICR(이자보상배율)", value=round(icr, 3), unit="x",
            verdict=BLOCK if icr < 1.0 else PASS, threshold="≥1.0 (거치단계)",
            basis="대주 표준 이자보상배율(ICR) 커버넌트(거치·브릿지 단계)",
            detail=f"NOI {noi:,.0f} / 이자 {interest:,.0f} = {icr:.3f}x"))

    # Development Spread = YoC(안정화NOI/총사업비) − 시장 cap rate. <0 BLOCK·<150bp WARN.
    snoi, tc, cap = num(inputs, "stabilized_noi"), num(inputs, "total_cost"), num(inputs, "market_cap_rate")
    if snoi is not None and tc and tc > 0 and cap is not None:
        yoc = snoi / tc
        spread = yoc - cap
        verdict = BLOCK if spread < 0 else (WARN if spread < DEV_SPREAD_WARN else PASS)
        out.append(RuleEvaluation(
            rule_id="fin.development_spread", label="Development Spread", value=round(spread * 10000, 1),
            unit="bp", verdict=verdict, threshold="≥150bp 권장 (음수 BLOCK)",
            basis="부동산개발 표준 수익성 지표(Yield-on-Cost·cap rate spread)",
            detail=f"YoC {yoc*100:.2f}% − 시장 cap {cap*100:.2f}% = {spread*10000:.1f}bp"))

    # 자기자본비율 = 자기자본 / 총사업비. 연도 규제(26/27/28=10/15/20%) 미달 WARN.
    equity, year = num(inputs, "equity"), num(inputs, "project_year")
    if equity is not None and tc and tc > 0:
        ratio = equity / tc
        req = EQUITY_REQ_BY_YEAR.get(int(year), 0.20) if year is not None else 0.20
        yr_txt = f"{int(year)}년" if year is not None else "기본(최신)"
        out.append(RuleEvaluation(
            rule_id="fin.equity_ratio_reg", label="자기자본비율", value=round(ratio * 100, 1), unit="%",
            verdict=WARN if ratio < req else PASS, threshold=f"≥{req*100:.0f}% ({yr_txt})",
            basis=("금융당국 부동산 PF 제도 개선방안(2024) 자기자본비율 단계 유도기준"
                   "(인센티브 차등·강제 최저선 아님, 2026~2028)"),
            detail=f"자기자본 {equity:,.0f} / 총사업비 {tc:,.0f} = {ratio*100:.1f}% vs 기준 {req*100:.0f}%"))

    # Debt Yield = NOI / 대출액. 최소(기본 8%) 미달 WARN.
    loan = num(inputs, "loan_amount")
    if noi is not None and loan and loan > 0:
        dy = noi / loan
        dy_min = num_or(inputs, "debt_yield_min", DEBT_YIELD_MIN_DEFAULT)
        out.append(RuleEvaluation(
            rule_id="fin.debt_sizing", label="Debt Yield", value=round(dy * 100, 2), unit="%",
            verdict=WARN if dy < dy_min else PASS, threshold=f"≥{dy_min*100:.0f}%",
            basis="대주 표준 debt sizing(Debt Yield=NOI/대출액)",
            detail=f"NOI {noi:,.0f} / 대출액 {loan:,.0f} = {dy*100:.2f}% vs 최소 {dy_min*100:.0f}%"))

    return out
