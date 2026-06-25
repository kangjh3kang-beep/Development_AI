"""시니어 정량 평가기(금융) 단위테스트 — 실수치 PASS/WARN/BLOCK·방어적 파싱."""

from app.services.senior_agents.evaluators import (
    BLOCK,
    PASS,
    WARN,
    evaluate_accounting,
    evaluate_architect,
    evaluate_financial,
    evaluate_tax,
    evaluate_urban,
    worst_verdict,
)
from app.services.senior_agents.evaluators.base import num, num_or


def _by_id(evals):
    return {e.rule_id: e for e in evals}


def test_dscr_verdicts():
    assert _by_id(evaluate_financial({"noi": 125, "debt_service": 100}))["fin.dscr_gate"].verdict == PASS
    assert _by_id(evaluate_financial({"noi": 120, "debt_service": 100}))["fin.dscr_gate"].verdict == WARN
    assert _by_id(evaluate_financial({"noi": 90, "debt_service": 100}))["fin.dscr_gate"].verdict == BLOCK
    e = _by_id(evaluate_financial({"noi": 125, "debt_service": 100}))["fin.dscr_gate"]
    assert e.value == 1.25 and e.unit == "x" and e.basis


def test_icr_verdict():
    assert _by_id(evaluate_financial({"noi": 90, "interest": 100}))["fin.icr_gate"].verdict == BLOCK
    assert _by_id(evaluate_financial({"noi": 120, "interest": 100}))["fin.icr_gate"].verdict == PASS


def test_development_spread_verdicts():
    pass_e = _by_id(evaluate_financial({"stabilized_noi": 70, "total_cost": 1000, "market_cap_rate": 0.045}))
    assert pass_e["fin.development_spread"].verdict == PASS  # YoC 7% - 4.5% = 250bp
    assert pass_e["fin.development_spread"].value == 250.0
    warn_e = _by_id(evaluate_financial({"stabilized_noi": 70, "total_cost": 1000, "market_cap_rate": 0.06}))
    assert warn_e["fin.development_spread"].verdict == WARN  # 100bp
    block_e = _by_id(evaluate_financial({"stabilized_noi": 70, "total_cost": 1000, "market_cap_rate": 0.08}))
    assert block_e["fin.development_spread"].verdict == BLOCK  # -100bp


def test_equity_ratio_by_year():
    # 10% 자기자본: 2026(기준10%) PASS, 2027(기준15%) WARN
    e26 = _by_id(evaluate_financial({"equity": 100, "total_cost": 1000, "project_year": 2026}))
    assert e26["fin.equity_ratio_reg"].verdict == PASS and e26["fin.equity_ratio_reg"].value == 10.0
    e27 = _by_id(evaluate_financial({"equity": 100, "total_cost": 1000, "project_year": 2027}))
    assert e27["fin.equity_ratio_reg"].verdict == WARN
    # 연도 미지정 → 최신(20%) 기준 → 10%는 WARN
    edef = _by_id(evaluate_financial({"equity": 100, "total_cost": 1000}))
    assert edef["fin.equity_ratio_reg"].verdict == WARN


def test_debt_yield():
    assert _by_id(evaluate_financial({"noi": 80, "loan_amount": 1000}))["fin.debt_sizing"].verdict == PASS
    assert _by_id(evaluate_financial({"noi": 70, "loan_amount": 1000}))["fin.debt_sizing"].verdict == WARN


def test_missing_or_invalid_inputs_skip_no_mockup():
    # 입력 없음 → 평가 0건(가짜 수치 금지)
    assert evaluate_financial({}) == []
    # 분모 0 → 해당 평가 생략
    assert "fin.dscr_gate" not in _by_id(evaluate_financial({"noi": 100, "debt_service": 0}))
    # 비수치/불리언 → 생략
    assert evaluate_financial({"noi": "abc", "debt_service": 100}) == []
    assert num({"x": True}, "x") is None
    assert num({"x": float("nan")}, "x") is None
    assert num({"x": "1.5"}, "x") == 1.5


def test_num_or_preserves_explicit_zero():
    # ★전역전파방지: 명시된 0(falsy 유효값)은 default로 덮이지 않음(or 버그 차단)
    assert num_or({"x": 0}, "x", 0.08) == 0.0
    assert num_or({}, "x", 0.08) == 0.08          # 결측만 default
    assert num_or({"x": "bad"}, "x", 0.08) == 0.08  # 비수치=결측 취급


def test_urban_proportion_verdicts():
    base = {"total_project_cost": 100, "prior_appraisal_total": 1000}
    # 비례율 95% (<100) → WARN
    e = _by_id(evaluate_urban({**base, "post_appraisal_total": 1050}))["urban.redevelopment_proportion"]
    assert e.verdict == WARN and e.value == 95.0
    # 비례율 110% → PASS
    assert _by_id(evaluate_urban({**base, "post_appraisal_total": 1200}))[
        "urban.redevelopment_proportion"].verdict == PASS
    # 종후 ≤ 총사업비 → 비례율 ≤0 → BLOCK
    assert _by_id(evaluate_urban({**base, "post_appraisal_total": 100}))[
        "urban.redevelopment_proportion"].verdict == BLOCK
    # 권리가액·분담금 detail(개별 종전평가·분양가 제공 시)
    full = _by_id(evaluate_urban({**base, "post_appraisal_total": 1100,
                                  "prior_appraisal_individual": 500, "member_sale_price": 600}))
    assert "권리가액" in full["urban.redevelopment_proportion"].detail
    assert "분담금" in full["urban.redevelopment_proportion"].detail
    # 종전평가 0/결측 → 생략(무목업)
    assert evaluate_urban({"post_appraisal_total": 1, "total_project_cost": 1,
                           "prior_appraisal_total": 0}) == []


def test_architect_setback_reuses_helper():
    # 높이 8m(≤10m) → 필요 1.5m. 실 이격 2m ≥ 1.5 → PASS
    e = _by_id(evaluate_architect({"building_height_m": 8, "north_distance_m": 2.0}))
    assert e["design.bukchuk_setback"].verdict == PASS
    # 높이 30m → 필요 15m(h/2). 실 10m < 15 → BLOCK
    e2 = _by_id(evaluate_architect({"building_height_m": 30, "north_distance_m": 10}))
    assert e2["design.bukchuk_setback"].verdict == BLOCK
    # 동지 연속일조 90분 < 120 → BLOCK, 130분 → PASS
    assert _by_id(evaluate_architect({"winter_daylight_continuous_min": 90}))[
        "design.winter_daylight_gate"].verdict == BLOCK
    assert _by_id(evaluate_architect({"winter_daylight_continuous_min": 130}))[
        "design.winter_daylight_gate"].verdict == PASS
    # 결측 → 생략
    assert evaluate_architect({}) == []


def test_boundary_equality_cases():
    # ★회귀방어: 부등호 경계(<↔<=) 뒤집힘 검출
    # 비례율 정확히 100% → PASS (≥100)
    assert _by_id(evaluate_urban({"post_appraisal_total": 1100, "total_project_cost": 100,
        "prior_appraisal_total": 1000}))["urban.redevelopment_proportion"].verdict == PASS
    # 비례율 정확히 0(post==cost) → BLOCK (≤0)
    assert _by_id(evaluate_urban({"post_appraisal_total": 100, "total_project_cost": 100,
        "prior_appraisal_total": 1000}))["urban.redevelopment_proportion"].verdict == BLOCK
    # 정북: h=10 임계(≤10→1.5), nd=req 정확등가 → PASS
    assert _by_id(evaluate_architect({"building_height_m": 10, "north_distance_m": 1.5}))[
        "design.bukchuk_setback"].verdict == PASS
    # 동지 정확히 120분 → PASS (≥120)
    assert _by_id(evaluate_architect({"winter_daylight_continuous_min": 120}))[
        "design.winter_daylight_gate"].verdict == PASS
    # DSCR 정확히 1.25 → PASS
    assert _by_id(evaluate_financial({"noi": 125, "debt_service": 100}))["fin.dscr_gate"].verdict == PASS


def test_winter_daylight_dispute_warning():
    # 법정 게이트 통과(연속 130분≥120)이나 총 200분<240 → 분쟁경고 WARN(별도 룰)
    ev = _by_id(evaluate_architect({"winter_daylight_continuous_min": 130, "winter_daylight_total_min": 200}))
    assert ev["design.winter_daylight_gate"].verdict == PASS
    assert ev["design.winter_daylight_dispute"].verdict == WARN
    # 총 4h(240) 충족 → 분쟁경고 없음
    ev2 = _by_id(evaluate_architect({"winter_daylight_continuous_min": 130, "winter_daylight_total_min": 260}))
    assert "design.winter_daylight_dispute" not in ev2
    # 연속 음수 → 생략(무목업)
    assert evaluate_architect({"winter_daylight_continuous_min": -5}) == []


def test_urban_negative_inputs_skip():
    # 음수 총사업비/종후평가 → 비물리 입력 생략(무목업)
    assert evaluate_urban({"post_appraisal_total": -1, "total_project_cost": 100,
                           "prior_appraisal_total": 1000}) == []
    assert evaluate_urban({"post_appraisal_total": 1000, "total_project_cost": -50,
                           "prior_appraisal_total": 1000}) == []


def test_acquisition_tax_rates():
    # 주택 6억↓ 1% / 9억↑ 3% / 6~9억 누진(7.5억→2%) / 비주택 4%
    assert _by_id(evaluate_tax({"acquisition_price": 5e8}))["tax.acquisition_tax"].value == 1.0
    assert _by_id(evaluate_tax({"acquisition_price": 10e8}))["tax.acquisition_tax"].value == 3.0
    assert _by_id(evaluate_tax({"acquisition_price": 7.5e8}))["tax.acquisition_tax"].value == 2.0
    assert _by_id(evaluate_tax({"acquisition_price": 5e8, "property_type": "non_housing"}))[
        "tax.acquisition_tax"].value == 4.0
    # 경계: 정확히 6억→1%, 9억→3%
    assert _by_id(evaluate_tax({"acquisition_price": 6e8}))["tax.acquisition_tax"].value == 1.0
    assert _by_id(evaluate_tax({"acquisition_price": 9e8}))["tax.acquisition_tax"].value == 3.0


def test_acquisition_tax_heavy_warn():
    # 법인 → 12% WARN, 조정 2주택 → 8% WARN, 비조정 3주택 → 8%
    e = _by_id(evaluate_tax({"acquisition_price": 5e8, "is_corporate": True}))["tax.acquisition_tax"]
    assert e.value == 12.0 and e.verdict == WARN
    e2 = _by_id(evaluate_tax({"acquisition_price": 5e8, "multi_home_count": 2,
                              "is_adjusted_area": True}))["tax.acquisition_tax"]
    assert e2.value == 8.0 and e2.verdict == WARN
    e3 = _by_id(evaluate_tax({"acquisition_price": 5e8, "multi_home_count": 3}))["tax.acquisition_tax"]
    assert e3.value == 8.0  # 비조정 3주택
    # 1주택 표준 → PASS
    assert _by_id(evaluate_tax({"acquisition_price": 5e8}))["tax.acquisition_tax"].verdict == PASS
    # 음수/결측 생략
    assert evaluate_tax({}) == [] and evaluate_tax({"acquisition_price": -1}) == []


def test_lease_classification():
    # 단기(≤12개월) → 면제
    e = _by_id(evaluate_accounting({"lease_term_months": 12}))["acct.lease_classification"]
    assert e.verdict == PASS and "면제" in e.label
    # 소액 → 면제(기간 무관)
    assert "면제" in _by_id(evaluate_accounting({"lease_term_months": 36, "is_low_value": True}))[
        "acct.lease_classification"].label
    # 장기 + 리스료·할인율 → 리스부채 PV 산출(연금현가). 24개월·연1200·5% → 2년 연금현가≈2230
    e2 = _by_id(evaluate_accounting({"lease_term_months": 24, "annual_payment": 1200,
                                     "discount_rate": 0.05}))["acct.lease_classification"]
    assert e2.verdict == PASS and e2.value is not None and 2200 <= e2.value <= 2260
    # 할인율 0 → 단순합(payment×years)
    e3 = _by_id(evaluate_accounting({"lease_term_months": 24, "annual_payment": 1000,
                                     "discount_rate": 0}))["acct.lease_classification"]
    assert e3.value == 2000
    # 장기지만 리스료·할인율 결측 → 인식대상 표기·PV None
    e4 = _by_id(evaluate_accounting({"lease_term_months": 36}))["acct.lease_classification"]
    assert e4.value is None and "인식" in e4.detail
    # 음수/결측 생략
    assert evaluate_accounting({}) == [] and evaluate_accounting({"lease_term_months": -1}) == []


def test_worst_verdict():
    evals = evaluate_financial({"noi": 90, "debt_service": 100,            # DSCR BLOCK
                               "stabilized_noi": 70, "total_cost": 1000, "market_cap_rate": 0.045})  # spread PASS
    assert worst_verdict(evals) == BLOCK
    assert worst_verdict([]) is None
