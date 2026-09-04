"""시니어 정량 평가기(금융) 단위테스트 — 실수치 PASS/WARN/BLOCK·방어적 파싱."""

from app.services.senior_agents.evaluators import (
    BLOCK,
    EVALUATORS,
    PASS,
    WARN,
    evaluate_accounting,
    evaluate_appraisal,
    evaluate_architect,
    evaluate_bim,
    evaluate_deliberation,
    evaluate_financial,
    evaluate_legal,
    evaluate_qs,
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
    # 미인식 property_type → 주택 가정이되 detail에 정직 표기(침묵 폴백 금지)
    e_land = _by_id(evaluate_tax({"acquisition_price": 5e8, "property_type": "land"}))["tax.acquisition_tax"]
    assert e_land.value == 1.0 and "미인식" in e_land.detail


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


def test_bim_clash_and_recall():
    # clash: critical>0 BLOCK·acceptable만 WARN·0 PASS
    assert _by_id(evaluate_bim({"clash_count": 5, "critical_clash_count": 2}))[
        "bim.clash_triage"].verdict == BLOCK
    assert _by_id(evaluate_bim({"clash_count": 3, "critical_clash_count": 0}))[
        "bim.clash_triage"].verdict == WARN
    assert _by_id(evaluate_bim({"clash_count": 0}))["bim.clash_triage"].verdict == PASS
    # 법규 recall: 위반>0 BLOCK·미검증<100% WARN·전수충족 PASS
    assert _by_id(evaluate_bim({"total_rules": 100, "checked_rules": 100, "failed_rules": 3}))[
        "bim.code_compliance_recall"].verdict == BLOCK
    warn = _by_id(evaluate_bim({"total_rules": 100, "checked_rules": 80, "failed_rules": 0}))[
        "bim.code_compliance_recall"]
    assert warn.verdict == WARN and warn.value == 80.0
    assert _by_id(evaluate_bim({"total_rules": 100, "checked_rules": 100, "failed_rules": 0}))[
        "bim.code_compliance_recall"].verdict == PASS
    # 결측/분모0 생략
    assert evaluate_bim({}) == [] and "bim.code_compliance_recall" not in _by_id(
        evaluate_bim({"total_rules": 0, "checked_rules": 0}))
    # recall clamp: checked>total → 100% PASS(과대 검토수 클램프)
    over = _by_id(evaluate_bim({"total_rules": 100, "checked_rules": 150, "failed_rules": 0}))[
        "bim.code_compliance_recall"]
    assert over.value == 100.0 and over.verdict == PASS
    # critical>clash 비정합 → clash로 클램프(안전측 BLOCK)
    cl = _by_id(evaluate_bim({"clash_count": 2, "critical_clash_count": 5}))["bim.clash_triage"]
    assert cl.value == 2.0 and cl.verdict == BLOCK


def test_deliberation_csp_unsat_core():
    # 전 조항 충족 → PASS
    ok = _by_id(evaluate_deliberation({"bcr_actual": 50, "bcr_limit": 60, "far_actual": 200,
        "far_limit": 250, "height_actual": 30, "height_limit": 35, "road_width_actual": 6,
        "road_width_required": 4}))["delib.multi_clause_csp"]
    assert ok.verdict == PASS and ok.value == 0
    # 용적률 초과 + 접도 미달 → BLOCK·unsat core 2건
    bad = _by_id(evaluate_deliberation({"far_actual": 300, "far_limit": 250,
        "road_width_actual": 3, "road_width_required": 4}))["delib.multi_clause_csp"]
    assert bad.verdict == BLOCK and bad.value == 2
    assert "용적률" in bad.detail and "접도" in bad.detail
    # 조항 미제공 → 생략(무목업)
    assert evaluate_deliberation({}) == []
    # 부분 제공(건폐율만) → 그 조항만 검증. value는 float 통일
    one = _by_id(evaluate_deliberation({"bcr_actual": 70, "bcr_limit": 60}))["delib.multi_clause_csp"]
    assert one.verdict == BLOCK and one.value == 1.0 and isinstance(one.value, float)
    # ★MED: limit 0·음수(미확보) → 해당 조항 생략(거짓 위반 방지·무목업)
    assert evaluate_deliberation({"bcr_actual": 60, "bcr_limit": 0}) == []
    # 경계: actual==limit → 충족(PASS)
    assert _by_id(evaluate_deliberation({"bcr_actual": 60, "bcr_limit": 60}))[
        "delib.multi_clause_csp"].verdict == PASS


def test_appraisal_prior_valuation():
    # 토지+건물 → 종전평가 합·PASS
    e = _by_id(evaluate_appraisal({"land_appraised_total": 8e8, "building_appraised_total": 2e8}))[
        "appraisal.prior_valuation"]
    assert e.verdict == PASS and e.value == 1_000_000_000.0
    # 건물 미반영(토지만) → WARN(과소평가 주의)
    e2 = _by_id(evaluate_appraisal({"land_appraised_total": 8e8}))["appraisal.prior_valuation"]
    assert e2.verdict == WARN and e2.value == 8e8 and "과소" in e2.detail
    # 토지 결측 → 생략(무목업)
    assert evaluate_appraisal({}) == []


def test_legal_union_consent():
    # 재개발: 소유자 80%≥75 + 면적 60%≥50 → 충족 PASS
    base = {"redevelopment_type": "재개발", "consent_owner_count": 80, "total_owner_count": 100}
    e = _by_id(evaluate_legal({**base, "consent_area_sqm": 600, "total_area_sqm": 1000}))[
        "legal.union_consent"]
    assert e.verdict == PASS and e.value == 80.0
    # 재건축: 면적 요건 3/4 → 면적 60%<75 → 미달 WARN
    e2 = _by_id(evaluate_legal({**base, "redevelopment_type": "재건축",
                               "consent_area_sqm": 600, "total_area_sqm": 1000}))["legal.union_consent"]
    assert e2.verdict == WARN
    # 소유자 70%<75 → 미달 WARN
    e3 = _by_id(evaluate_legal({"redevelopment_type": "재개발", "consent_owner_count": 70,
                               "total_owner_count": 100}))["legal.union_consent"]
    assert e3.verdict == WARN
    # ★재건축: 소유자 80%·면적 80% 충족이나 동별 과반 미입력 → 미검증 WARN(거짓 PASS 방지)
    e4 = _by_id(evaluate_legal({"redevelopment_type": "재건축", "consent_owner_count": 80,
                                "total_owner_count": 100, "consent_area_sqm": 800,
                                "total_area_sqm": 1000}))["legal.union_consent"]
    assert e4.verdict == WARN and "동별 과반 미검증" in e4.detail
    # 동별 과반 입력(True) → 충족 PASS
    e5 = _by_id(evaluate_legal({"redevelopment_type": "재건축", "consent_owner_count": 80,
                                "total_owner_count": 100, "consent_area_sqm": 800,
                                "total_area_sqm": 1000, "building_consent_majority": True}))[
        "legal.union_consent"]
    assert e5.verdict == PASS


def test_legal_rights_takeover_appraisal_integration():
    # ★통합: 감정가 10억 − 인수권리 3억 = 실효 7억·인수율 30% → WARN
    e = _by_id(evaluate_legal({"appraised_value": 1e9, "senior_liens_total": 3e8}))[
        "legal.rights_takeover"]
    assert e.verdict == WARN and e.value == 30.0 and "실효가치" in e.detail
    # 인수권리 0(clean) → PASS
    assert _by_id(evaluate_legal({"appraised_value": 1e9, "senior_liens_total": 0}))[
        "legal.rights_takeover"].verdict == PASS
    # 인수권리 ≥ 감정가(경제성 없음) → BLOCK
    assert _by_id(evaluate_legal({"appraised_value": 1e9, "senior_liens_total": 11e8}))[
        "legal.rights_takeover"].verdict == BLOCK
    # 감정가 결측 → 권리분석 생략(무목업·통합 입력 의존)
    assert "legal.rights_takeover" not in _by_id(evaluate_legal({"senior_liens_total": 3e8}))


def test_all_domains_have_evaluator():
    # 10개 시니어 도메인 전부 평가기 보유(법무사·감정평가사 통합 + 적산(QS) 추가)
    assert set(EVALUATORS) == {
        "senior_financial_advisor", "senior_urban_planner", "senior_architect",
        "senior_tax_advisor", "senior_accountant", "senior_bim_specialist",
        "senior_deliberation_member", "senior_legal_scrivener", "senior_appraiser",
        "senior_quantity_surveyor",
    }


def test_worst_verdict():
    evals = evaluate_financial({"noi": 90, "debt_service": 100,            # DSCR BLOCK
                               "stabilized_noi": 70, "total_cost": 1000, "market_cap_rate": 0.045})  # spread PASS
    assert worst_verdict(evals) == BLOCK
    assert worst_verdict([]) is None


# ── D-B: 시니어 평면 성립성 게이트(복도·피난·코어·전용률) ──

def test_architect_corridor_width_gate():
    # 중복도(기본): 2.4m 미만 BLOCK, 2.4m 이상 PASS
    assert _by_id(evaluate_architect({"corridor_width_m": 2.0}))[
        "design.corridor_width"].verdict == BLOCK
    assert _by_id(evaluate_architect({"corridor_width_m": 2.4}))[
        "design.corridor_width"].verdict == PASS
    # 편복도: 1.8m 이상이면 PASS(중복도 기준 2.4 오적용 금지)
    assert _by_id(evaluate_architect({"corridor_width_m": 1.8, "corridor_type": "single"}))[
        "design.corridor_width"].verdict == PASS
    assert _by_id(evaluate_architect({"corridor_width_m": 1.7, "corridor_type": "single"}))[
        "design.corridor_width"].verdict == BLOCK
    # 복도폭 결측 → 생략(무목업)
    assert "design.corridor_width" not in _by_id(evaluate_architect({"floor_count": 3}))


def test_architect_egress_gate():
    # 6층(5층↑) 직통계단 1개 → BLOCK, 2개 → PASS
    assert _by_id(evaluate_architect({"floor_count": 6, "direct_stair_count": 1}))[
        "design.egress"].verdict == BLOCK
    assert _by_id(evaluate_architect({"floor_count": 6, "direct_stair_count": 2}))[
        "design.egress"].verdict == PASS
    # 층당 거실 200㎡ 초과(저층이라도) → 직통계단 2개 의무
    assert _by_id(evaluate_architect({"floor_count": 2, "floor_area_per_floor_sqm": 250,
                                      "direct_stair_count": 1}))["design.egress"].verdict == BLOCK
    # 4층·층당 150㎡(둘 다 미달) → egress 룰 미적용(생략)
    assert "design.egress" not in _by_id(evaluate_architect(
        {"floor_count": 4, "floor_area_per_floor_sqm": 150, "direct_stair_count": 1}))
    # 보행거리: 내화 50m 초과 BLOCK / 비내화 30m 이하 PASS
    assert _by_id(evaluate_architect({"travel_distance_m": 55, "fire_resistant": True}))[
        "design.egress_travel"].verdict == BLOCK
    assert _by_id(evaluate_architect({"travel_distance_m": 28, "fire_resistant": False}))[
        "design.egress_travel"].verdict == PASS
    assert _by_id(evaluate_architect({"travel_distance_m": 31, "fire_resistant": False}))[
        "design.egress_travel"].verdict == BLOCK


def test_architect_core_adequacy_gate():
    # 6층↑ EV 누락 → WARN
    assert _by_id(evaluate_architect({"floor_count": 8, "has_elevator": False}))[
        "design.core_adequacy"].verdict == WARN
    # 5층(6 미만) EV 누락 → 미적용(생략)
    assert "design.core_adequacy" not in _by_id(evaluate_architect(
        {"floor_count": 5, "has_elevator": False}))
    # 코어당 세대 과다(200세대/2코어=100>60) → WARN, 적정(100/2=50) → PASS
    assert _by_id(evaluate_architect({"total_units": 200, "num_cores": 2}))[
        "design.core_load"].verdict == WARN
    assert _by_id(evaluate_architect({"total_units": 100, "num_cores": 2}))[
        "design.core_load"].verdict == PASS


def test_architect_unit_efficiency_gate():
    # 전용률 >100% → BLOCK(물리 불가)
    assert _by_id(evaluate_architect({"unit_efficiency": 1.05}))[
        "design.unit_efficiency"].verdict == BLOCK
    # 전형(70~85%) → PASS
    assert _by_id(evaluate_architect({"unit_efficiency": 0.78}))[
        "design.unit_efficiency"].verdict == PASS
    # 70 미만 / 85 초과 → WARN
    assert _by_id(evaluate_architect({"unit_efficiency": 0.65}))[
        "design.unit_efficiency"].verdict == WARN
    assert _by_id(evaluate_architect({"unit_efficiency": 0.90}))[
        "design.unit_efficiency"].verdict == WARN
    # % 입력(78)도 0~1 비율(0.78)과 동일 판정
    assert _by_id(evaluate_architect({"unit_efficiency": 78}))[
        "design.unit_efficiency"].value == 78.0


def test_architect_empty_inputs_still_empty():
    # ★회귀방어: 신규 게이트 추가 후에도 빈 입력은 [](평가 생략·무목업)
    assert evaluate_architect({}) == []


# ── 적산(QS): 기준선편차·법정요율·단가신뢰도·예비비·공종구성비(P3) ──


def test_qs_baseline_deviation():
    # 기본형건축비 기준선 시드 구간(16~25층·전용 60~85㎡) = 2,220,000원/㎡
    # 편차 5%(<15%) → PASS
    e = _by_id(evaluate_qs({"cost_per_sqm": 2_220_000 * 1.05, "floors": 20, "avg_unit_sqm": 75}))[
        "qs.baseline_deviation"]
    assert e.verdict == PASS
    # 편차 20%(15~30%) → WARN
    e2 = _by_id(evaluate_qs({"cost_per_sqm": 2_220_000 * 1.20, "floors": 20, "avg_unit_sqm": 75}))[
        "qs.baseline_deviation"]
    assert e2.verdict == WARN
    # 편차 35%(>30%) → BLOCK
    e3 = _by_id(evaluate_qs({"cost_per_sqm": 2_220_000 * 1.35, "floors": 20, "avg_unit_sqm": 75}))[
        "qs.baseline_deviation"]
    assert e3.verdict == BLOCK and e3.basis
    # 비주택(is_housing=False) → 생략(무목업)
    assert "qs.baseline_deviation" not in _by_id(evaluate_qs(
        {"cost_per_sqm": 2_220_000, "floors": 20, "avg_unit_sqm": 75, "is_housing": False}))
    # 기준선 미시드 구간(예: 5층) → 생략(정직 — 수치 발명 금지)
    assert "qs.baseline_deviation" not in _by_id(evaluate_qs(
        {"cost_per_sqm": 2_000_000, "floors": 5, "avg_unit_sqm": 75}))
    # 결측 → 생략
    assert evaluate_qs({}) == []


def test_qs_indirect_rate_compliance():
    # 일반관리비율 5.5%(≤6%) → PASS, 7%(>6%) → BLOCK
    assert _by_id(evaluate_qs({"general_mgmt_rate": 0.055}))["qs.general_mgmt_cap"].verdict == PASS
    assert _by_id(evaluate_qs({"general_mgmt_rate": 0.07}))["qs.general_mgmt_cap"].verdict == BLOCK
    # 이윤율 정확히 15%(경계) → PASS, 16%(>15%) → BLOCK
    assert _by_id(evaluate_qs({"profit_rate": 0.15}))["qs.profit_cap"].verdict == PASS
    assert _by_id(evaluate_qs({"profit_rate": 0.16}))["qs.profit_cap"].verdict == BLOCK
    # 결측 → 생략
    assert evaluate_qs({}) == []


def test_qs_unit_price_reliability():
    # T3 60%(>50%) → WARN
    e = _by_id(evaluate_qs({"tier_t3_count": 6, "tier_item_count": 10}))["qs.unit_price_reliability"]
    assert e.verdict == WARN and e.value == 60.0
    # T3 30%(≤50%) → PASS
    assert _by_id(evaluate_qs({"tier_t3_count": 3, "tier_item_count": 10}))[
        "qs.unit_price_reliability"].verdict == PASS
    # 분모 0/결측 → 생략
    assert "qs.unit_price_reliability" not in _by_id(evaluate_qs({"tier_t3_count": 0, "tier_item_count": 0}))
    assert evaluate_qs({}) == []


def test_qs_contingency_reserve():
    # 예비비율 1%(<3%) → WARN, 5%(≥3%) → PASS
    e = _by_id(evaluate_qs({"contingency_reserve_won": 1_000_000, "total_project_cost_won": 100_000_000}))[
        "qs.contingency_reserve"]
    assert e.verdict == WARN and e.value == 1.0
    assert "몬테카를로" in e.basis
    assert _by_id(evaluate_qs({"contingency_reserve_won": 5_000_000, "total_project_cost_won": 100_000_000}))[
        "qs.contingency_reserve"].verdict == PASS
    # 분모 0/결측 → 생략
    assert evaluate_qs({}) == []


def test_qs_category_composition():
    # 골조(WB04) 65%(>60%) → WARN
    e = _by_id(evaluate_qs({"category_totals": {"WB04": 65, "WB07": 20, "WB11": 15}}))[
        "qs.category_composition"]
    assert e.verdict == WARN and e.value == 65.0
    # 균형 구성(최대 40%) → PASS
    assert _by_id(evaluate_qs({"category_totals": {"WB04": 40, "WB07": 30, "WB11": 30}}))[
        "qs.category_composition"].verdict == PASS
    # 항목 1개(집계 불충분) → 생략(무목업)
    assert "qs.category_composition" not in _by_id(evaluate_qs({"category_totals": {"WB04": 100}}))
    # 결측/비dict → 생략
    assert evaluate_qs({}) == []
    assert "qs.category_composition" not in _by_id(evaluate_qs({"category_totals": "bad"}))


def test_qs_all_rules_combined_worst_verdict():
    # 5개 룰 동시 입력 — general_mgmt BLOCK이 최악판정
    evals = evaluate_qs({
        "cost_per_sqm": 2_220_000, "floors": 20, "avg_unit_sqm": 75,
        "general_mgmt_rate": 0.08, "profit_rate": 0.10,
        "tier_t3_count": 1, "tier_item_count": 10,
        "contingency_reserve_won": 5_000_000, "total_project_cost_won": 100_000_000,
        "category_totals": {"WB04": 40, "WB07": 30, "WB11": 30},
    })
    assert len(evals) == 6  # baseline·general_mgmt·profit·tier·contingency·composition
    assert worst_verdict(evals) == BLOCK
    assert all(e.basis.strip() for e in evals)  # citation 게이트: 전부 근거 동반
    assert evaluate_qs({}) == []
