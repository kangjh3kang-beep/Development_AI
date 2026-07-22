"""W3-1(수익 KPI 완성 — GAP_v4 P10) 테스트 — MOIC·Equity IRR·LTV/LTC·break-even·RLV·covenant.

스파이크 확증: cashflow_generator·dcf_assembly에는 월별 waterfall·무차입 NPV/IRR만 있고
이 티켓의 KPI는 전무했다(전역 grep, 명칭 변형 포함 재확증). return_kpi.py는 그 위에서
파생만 한다(재계산 0) — 이 테스트는:
  1) golden(손계산) 대조 — 100% 자기자본·무차입 시나리오로 MOIC·equity 현금흐름·최종회수액을
     엔진 호출 없이 손으로 미리 유도한 값과 대조(구현 출력 복사 아님).
  2) sources=uses·opening+inflow-outflow=closing 월별 불변식 전건 검증.
  3) break-even·RLV — 이분법 결과를 다시 assemble_monthly_dcf에 넣어 NPV≈0 자기정합성 확인
     (근을 '만든' 게 아니라 실제로 근인지 독립 검증).
  4) LTV/LTC·covenant — 레버리지 시나리오에서 peak 부채=총사업비×(1−equity_ratio) 항등식으로
     교차검증(엔진 출력 재사용이 아니라 자금구조 정의로부터 독립 유도).
"""

from __future__ import annotations

import pytest

from app.services.feasibility.cashflow_generator import irr_annual_pct_from_netflows
from app.services.feasibility.dcf_assembly import assemble_monthly_dcf
from app.services.feasibility.modules.common.cost_blocks import _STANDARD_PF_LTC_RATIO
from app.services.finance.return_kpi import (
    DEFAULT_LTV_COVENANT_THRESHOLD_PCT,
    _bisect_for_zero,
    check_ledger_invariants,
    compute_return_kpi,
    detect_multiple_irr_risk,
)


# ─────────────────────────────────────────────────────────────────────────────
# 0) 이분법 유틸 자체 검증(엔진 무관 — 순수 수학)
# ─────────────────────────────────────────────────────────────────────────────
class TestBisectForZero:
    def test_increasing_root_below_x0(self):
        """f(x)=x-10, x0=100 → f0=90>0 → increasing=True이면 아래로 탐색해 근 10을 찾는다."""
        result = _bisect_for_zero(lambda x: x - 10, 100.0, increasing=True)
        assert result["converged"] is True
        assert result["value"] == pytest.approx(10, abs=1)

    def test_decreasing_root_above_x0(self):
        """f(x)=100-x, x0=10 → f0=90>0 → decreasing이면 위로 탐색해 근 100을 찾는다."""
        result = _bisect_for_zero(lambda x: 100 - x, 10.0, increasing=False)
        assert result["converged"] is True
        assert result["value"] == pytest.approx(100, abs=1)

    def test_already_at_root(self):
        result = _bisect_for_zero(lambda x: x - 100, 100.0, increasing=True)
        assert result["converged"] is True
        assert result["iterations"] == 0

    def test_invalid_x0_returns_failure(self):
        result = _bisect_for_zero(lambda x: x, 0.0, increasing=True)
        assert result["converged"] is False
        assert result["value"] is None

    def test_evaluate_failure_reports_reason(self):
        result = _bisect_for_zero(lambda x: None, 10.0, increasing=True)
        assert result["converged"] is False
        assert result["value"] is None
        assert "실패" in result["reason"]


# ─────────────────────────────────────────────────────────────────────────────
# 1) golden(손계산) — 100% 자기자본·무차입(interest=0) 단순 시나리오
# ─────────────────────────────────────────────────────────────────────────────
# 손계산(엔진 호출 없이 유도):
#   design_cost = construction × 3%(내부 기본 design_cost_ratio) = 2e9×0.03 = 60,000,000
#   total_project_cost = land+design+construction = 1e9+0.06e9+2e9 = 3.06e9
#   equity_ratio=1.0(전액 자기자본) → 브릿지·PF=0 → interest_total=0
#   net_profit = revenue − land − design − construction = 4e9 − 3.06e9 = 940,000,000
#     (자기자본 100%·무차입이면 net_profit = cumulative_inflow−outflow−equity_in_total 항등식이
#      이 단순식으로 축약됨 — cashflow_generator.py 주석의 회계항등을 그대로 적용)
#   equity_in_total = total_project_cost = 3.06e9(100% 조달)
#   최종 잔존현금(=자본반환+이익) = net_profit+equity_in_total = revenue = 4e9
#   MOIC = revenue/total_project_cost = 4e9/3.06e9 = 1.307189...
_GOLDEN_LAND = 1_000_000_000.0
_GOLDEN_CONSTR = 2_000_000_000.0
_GOLDEN_REVENUE = 4_000_000_000.0
_GOLDEN_PM = 24
_GOLDEN_TOTAL_COST = _GOLDEN_LAND + _GOLDEN_CONSTR * 0.03 + _GOLDEN_CONSTR  # = 3.06e9
_GOLDEN_DISCOUNT = 0.08


def _golden_dcf():
    return assemble_monthly_dcf(
        land_cost_won=_GOLDEN_LAND, construction_cost_won=_GOLDEN_CONSTR,
        revenue_won=_GOLDEN_REVENUE, project_months=_GOLDEN_PM,
        equity_won=_GOLDEN_TOTAL_COST,  # 100% equity
        discount_rate=_GOLDEN_DISCOUNT, total_cost_won=_GOLDEN_TOTAL_COST,
    )


class TestGoldenAllEquityScenario:
    def test_engine_reproduces_hand_derived_net_profit_and_equity_ratio(self):
        """엔진 산출이 손계산 전제(무차입·net_profit)와 일치하는지 먼저 확인(픽스처 유효성)."""
        dcf = _golden_dcf()
        assert dcf is not None
        assert dcf["equity_ratio"] == pytest.approx(1.0)
        cs = dcf["cf_summary"]
        assert cs["interest_total"] == 0
        assert cs["bridge_loan_amount"] == 0
        assert cs["pf_loan_amount"] == 0
        expected_net_profit = _GOLDEN_REVENUE - _GOLDEN_TOTAL_COST
        assert cs["net_profit"] == pytest.approx(expected_net_profit, abs=5)

    def test_moic_matches_hand_calculation(self):
        dcf = _golden_dcf()
        kpi = compute_return_kpi(
            dcf=dcf, land_cost_won=_GOLDEN_LAND, construction_cost_won=_GOLDEN_CONSTR,
            revenue_won=_GOLDEN_REVENUE, discount_rate=_GOLDEN_DISCOUNT,
            total_cost_won=_GOLDEN_TOTAL_COST,
        )
        assert kpi is not None
        expected_moic = _GOLDEN_REVENUE / _GOLDEN_TOTAL_COST  # 1.307189...
        assert kpi["moic"]["value"] == pytest.approx(round(expected_moic, 3), abs=1e-3)

    def test_equity_cash_flow_matches_hand_derived_amounts(self):
        """자기자본 현금흐름 3점(월0 토지분·착공월 시공분·최종월 회수)이 손계산과 일치."""
        dcf = _golden_dcf()
        kpi = compute_return_kpi(
            dcf=dcf, land_cost_won=_GOLDEN_LAND, construction_cost_won=_GOLDEN_CONSTR,
            revenue_won=_GOLDEN_REVENUE, discount_rate=_GOLDEN_DISCOUNT,
            total_cost_won=_GOLDEN_TOTAL_COST,
        )
        cash_flow = kpi["equity_irr_pct"]["cash_flow_won"]
        values = list(cash_flow.values())
        # 월0 = -토지비(equity_ratio=1.0 → 전액 토지비만큼 자기자본 투입)
        assert values[0] == pytest.approx(-_GOLDEN_LAND, abs=1)
        # 착공월 = -(총사업비-토지비) = -(설계비+공사비)
        assert values[1] == pytest.approx(-(_GOLDEN_TOTAL_COST - _GOLDEN_LAND), abs=1)
        # 최종월 = 총분양수입(100% 자기자본·무차입이면 최종 잔존현금=revenue 그 자체)
        assert values[2] == pytest.approx(_GOLDEN_REVENUE, abs=5)
        # 세 값의 합 = net_profit(할인 전 단순 합산 항등식)
        assert sum(values) == pytest.approx(_GOLDEN_REVENUE - _GOLDEN_TOTAL_COST, abs=10)

    def test_equity_irr_is_independently_verified_as_npv_root(self):
        """구현이 반환한 equity_irr_pct를, 구현의 이분법과 무관하게 이 테스트가 직접 코딩한
        NPV-at-rate 공식으로 재검증한다(독립 산출값과 대조 — 구현 출력 복사 아님)."""
        dcf = _golden_dcf()
        kpi = compute_return_kpi(
            dcf=dcf, land_cost_won=_GOLDEN_LAND, construction_cost_won=_GOLDEN_CONSTR,
            revenue_won=_GOLDEN_REVENUE, discount_rate=_GOLDEN_DISCOUNT,
            total_cost_won=_GOLDEN_TOTAL_COST,
        )
        equity_irr = kpi["equity_irr_pct"]
        assert equity_irr is not None
        annual_rate_pct = equity_irr["value_pct"]
        cash_flow = equity_irr["cash_flow_won"]

        # 독립 NPV 공식(이 테스트 자체 코드 — production의 irr_annual_pct_from_netflows를
        # 호출하지 않는다): 월 실효할인율로 각 시점 현금을 할인한 합이 0에 근접해야 한다.
        monthly_rate = (1 + annual_rate_pct / 100) ** (1 / 12) - 1
        npv_check = 0.0
        for key, amount in cash_flow.items():
            month = int(key.split("_")[1])
            npv_check += amount / ((1 + monthly_rate) ** month)
        # 반올림된 연이율(소수점 2자리)의 잔차 — 4e9 규모 대비 0.1% 이내면 자기정합.
        assert abs(npv_check) < abs(_GOLDEN_REVENUE) * 0.001

    def test_ledger_invariants_hold_for_golden_scenario(self):
        dcf = _golden_dcf()
        result = check_ledger_invariants(dcf["rows"])
        assert result["ok"] is True
        assert result["violations"] == []
        assert result["rows_checked"] == len(dcf["rows"])


# ─────────────────────────────────────────────────────────────────────────────
# 2) 불변식 위반 검출(합성 데이터) — 엔진이 깨졌을 때 이 함수가 잡아내는지
# ─────────────────────────────────────────────────────────────────────────────
class TestLedgerInvariantViolationDetection:
    def test_detects_closing_mismatch(self):
        rows = [
            {"month": 0, "inflow": 100, "outflow": 0, "net": 100, "cumulative": 100,
             "outstanding_bridge": 0, "outstanding_pf": 0},
            {"month": 1, "inflow": 0, "outflow": 50, "net": -50, "cumulative": 999,  # 오류: 50이어야 함
             "outstanding_bridge": 0, "outstanding_pf": 0},
        ]
        result = check_ledger_invariants(rows)
        assert result["ok"] is False
        assert any(v["type"] == "closing!=opening+net" for v in result["violations"])

    def test_detects_negative_loan_balance(self):
        rows = [
            {"month": 0, "inflow": 0, "outflow": 0, "net": 0, "cumulative": 0,
             "outstanding_bridge": -5, "outstanding_pf": 0},
        ]
        result = check_ledger_invariants(rows)
        assert result["ok"] is False
        assert any(v["type"] == "negative_loan_balance" for v in result["violations"])

    def test_clean_rows_pass(self):
        rows = [
            {"month": 0, "inflow": 100, "outflow": 0, "net": 100, "cumulative": 100,
             "outstanding_bridge": 0, "outstanding_pf": 0},
            {"month": 1, "inflow": 0, "outflow": 50, "net": -50, "cumulative": 50,
             "outstanding_bridge": 0, "outstanding_pf": 0},
        ]
        result = check_ledger_invariants(rows)
        assert result["ok"] is True


# ─────────────────────────────────────────────────────────────────────────────
# 3) 레버리지 시나리오 — LTV/LTC·covenant (자금구조 항등식으로 독립 교차검증)
# ─────────────────────────────────────────────────────────────────────────────
# 항등식(cashflow_generator 자금구조 정의에서 독립 유도, rows 재사용 아님):
#   bridge_loan_amount + pf_loan_amount(착공월 전환 직후 peak) = total_project_cost × (1−equity_ratio)
#   → peak LTC(%) = (1−equity_ratio) × 100 (엔진 출력이 아니라 정의로부터 산출한 기대값)
_LEV_EQUITY_RATIO = 0.3
_LEV_TOTAL_COST = _GOLDEN_TOTAL_COST
_LEV_EQUITY_WON = _LEV_TOTAL_COST * _LEV_EQUITY_RATIO


def _leveraged_dcf():
    return assemble_monthly_dcf(
        land_cost_won=_GOLDEN_LAND, construction_cost_won=_GOLDEN_CONSTR,
        revenue_won=_GOLDEN_REVENUE, project_months=_GOLDEN_PM,
        equity_won=_LEV_EQUITY_WON, discount_rate=_GOLDEN_DISCOUNT,
        total_cost_won=_LEV_TOTAL_COST,
    )


class TestLtvLtcAndCovenant:
    def test_peak_ltc_matches_capital_structure_identity(self):
        dcf = _leveraged_dcf()
        kpi = compute_return_kpi(
            dcf=dcf, land_cost_won=_GOLDEN_LAND, construction_cost_won=_GOLDEN_CONSTR,
            revenue_won=_GOLDEN_REVENUE, discount_rate=_GOLDEN_DISCOUNT,
            total_cost_won=_LEV_TOTAL_COST,
        )
        expected_peak_ltc = round((1 - _LEV_EQUITY_RATIO) * 100, 2)
        assert kpi["ltv_ltc"]["peak_ltc_pct"] == pytest.approx(expected_peak_ltc, abs=0.5)

    def test_gdv_fallback_used_when_no_collateral_given(self):
        dcf = _leveraged_dcf()
        kpi = compute_return_kpi(
            dcf=dcf, land_cost_won=_GOLDEN_LAND, construction_cost_won=_GOLDEN_CONSTR,
            revenue_won=_GOLDEN_REVENUE, discount_rate=_GOLDEN_DISCOUNT,
            total_cost_won=_LEV_TOTAL_COST,
        )
        assert "GDV" in kpi["ltv_ltc"]["collateral_basis"]
        assert any("GDV" in n for n in kpi["degraded_notes"])

    def test_explicit_collateral_value_overrides_gdv_fallback(self):
        dcf = _leveraged_dcf()
        custom_collateral = 5_500_000_000.0  # revenue_won(4e9)과 다른 값 — 오버라이드 확인용
        kpi = compute_return_kpi(
            dcf=dcf, land_cost_won=_GOLDEN_LAND, construction_cost_won=_GOLDEN_CONSTR,
            revenue_won=_GOLDEN_REVENUE, discount_rate=_GOLDEN_DISCOUNT,
            total_cost_won=_LEV_TOTAL_COST, collateral_value_won=custom_collateral,
        )
        assert "사용자" in kpi["ltv_ltc"]["collateral_basis"]
        expected_peak_ltv = round((_LEV_TOTAL_COST * (1 - _LEV_EQUITY_RATIO)) / custom_collateral * 100, 2)
        assert kpi["ltv_ltc"]["peak_ltv_pct"] == pytest.approx(expected_peak_ltv, abs=0.5)

    def test_covenant_breaches_at_low_threshold_none_at_high(self):
        dcf = _leveraged_dcf()
        low = compute_return_kpi(
            dcf=dcf, land_cost_won=_GOLDEN_LAND, construction_cost_won=_GOLDEN_CONSTR,
            revenue_won=_GOLDEN_REVENUE, discount_rate=_GOLDEN_DISCOUNT,
            total_cost_won=_LEV_TOTAL_COST, ltv_covenant_threshold_pct=1.0,
        )
        high = compute_return_kpi(
            dcf=dcf, land_cost_won=_GOLDEN_LAND, construction_cost_won=_GOLDEN_CONSTR,
            revenue_won=_GOLDEN_REVENUE, discount_rate=_GOLDEN_DISCOUNT,
            total_cost_won=_LEV_TOTAL_COST, ltv_covenant_threshold_pct=99.9,
        )
        assert low["covenant"]["breach_count"] > 0
        assert high["covenant"]["breach_count"] == 0

    def test_default_covenant_threshold_matches_platform_convention(self):
        """covenant 기본 임계(70%)가 cost_blocks.py의 표준 PF LTC 관행 상수와 정합(같은 관행값)."""
        assert pytest.approx(_STANDARD_PF_LTC_RATIO * 100) == DEFAULT_LTV_COVENANT_THRESHOLD_PCT


# ─────────────────────────────────────────────────────────────────────────────
# 4) break-even·RLV — 이분법 결과의 자기정합성(같은 엔진에 재대입해 NPV≈0 확인)
# ─────────────────────────────────────────────────────────────────────────────
class TestBreakEvenAndRlvSelfConsistency:
    def _kpi(self):
        dcf = _leveraged_dcf()
        return compute_return_kpi(
            dcf=dcf, land_cost_won=_GOLDEN_LAND, construction_cost_won=_GOLDEN_CONSTR,
            revenue_won=_GOLDEN_REVENUE, discount_rate=_GOLDEN_DISCOUNT,
            total_cost_won=_LEV_TOTAL_COST,
        )

    def test_break_even_price_is_lower_than_assumed_and_npv_root(self):
        kpi = self._kpi()
        be = kpi["break_even"]["sale_price"]
        assert be["converged"] is True
        assert be["break_even_revenue_won"] < _GOLDEN_REVENUE  # 현재 흑자 사업 → 손익분기는 더 낮음
        check = assemble_monthly_dcf(
            land_cost_won=_GOLDEN_LAND, construction_cost_won=_GOLDEN_CONSTR,
            revenue_won=be["break_even_revenue_won"], project_months=_GOLDEN_PM,
            discount_rate=_GOLDEN_DISCOUNT, total_cost_won=_LEV_TOTAL_COST,
        )
        assert abs(check["npv_won"]) < 1000  # 손익분기점 재대입 시 NPV≈0(자기정합)

    def test_break_even_sales_rate_matches_price_lever_with_disclosed_limitation(self):
        """이 엔진은 단가·물량을 분리 모델링하지 않아 두 손익분기가 동일 배율 — 한계가 basis에 명시."""
        kpi = self._kpi()
        price_pct = kpi["break_even"]["sale_price"]["pct_of_assumed_revenue"]
        rate_pct = kpi["break_even"]["sales_rate"]["break_even_sales_rate_pct"]
        assert price_pct == rate_pct
        assert "분리 모델링하지 않아" in kpi["break_even"]["sales_rate"]["basis"]

    def test_break_even_construction_cost_is_higher_than_assumed_and_npv_root(self):
        kpi = self._kpi()
        be = kpi["break_even"]["construction_cost"]
        assert be["converged"] is True
        assert be["break_even_construction_cost_won"] > _GOLDEN_CONSTR  # 흑자 사업 → 손익분기 비용은 더 높음
        check = assemble_monthly_dcf(
            land_cost_won=_GOLDEN_LAND, construction_cost_won=be["break_even_construction_cost_won"],
            revenue_won=_GOLDEN_REVENUE, project_months=_GOLDEN_PM,
            discount_rate=_GOLDEN_DISCOUNT, total_cost_won=_LEV_TOTAL_COST,
        )
        assert abs(check["npv_won"]) < 1000

    def test_rlv_is_higher_than_assumed_land_and_npv_root(self):
        kpi = self._kpi()
        rlv = kpi["rlv"]
        assert rlv["converged"] is True
        assert rlv["residual_land_value_won"] > _GOLDEN_LAND  # 목표수익 여유가 있으면 RLV>현재 토지비
        check = assemble_monthly_dcf(
            land_cost_won=rlv["residual_land_value_won"], construction_cost_won=_GOLDEN_CONSTR,
            revenue_won=_GOLDEN_REVENUE, project_months=_GOLDEN_PM,
            discount_rate=_GOLDEN_DISCOUNT, total_cost_won=_LEV_TOTAL_COST,
        )
        assert abs(check["npv_won"]) < 1000


# ─────────────────────────────────────────────────────────────────────────────
# 5) 복수 IRR 경고(부호 변화 검출) — 날조 없이 경고만
# ─────────────────────────────────────────────────────────────────────────────
class TestMultipleIrrWarning:
    def test_normal_single_sign_change_not_flagged(self):
        dcf = {"cf": {"unlevered_netflows": [-100, -50, 30, 40, 50]}}
        result = detect_multiple_irr_risk(dcf)
        assert result["flagged"] is False
        assert result["sign_changes"] == 1

    def test_multiple_sign_changes_flagged(self):
        dcf = {"cf": {"unlevered_netflows": [-100, 50, -30, 60]}}  # -,+,-,+ = 3회 변화
        result = detect_multiple_irr_risk(dcf)
        assert result["flagged"] is True
        assert result["sign_changes"] == 3

    def test_no_warning_fabricates_extra_irr_value(self):
        """경고만 — 추가 IRR 값이나 근을 만들어내지 않는다(반환 키에 irr 후보 리스트 없음)."""
        dcf = {"cf": {"unlevered_netflows": [-100, 50, -30, 60]}}
        result = detect_multiple_irr_risk(dcf)
        assert set(result.keys()) == {"flagged", "sign_changes", "basis"}


# ─────────────────────────────────────────────────────────────────────────────
# 6) 정직 강등(무날조) — 미산정 입력은 null+사유
# ─────────────────────────────────────────────────────────────────────────────
class TestHonestDegradation:
    def test_dcf_none_propagates_none(self):
        assert compute_return_kpi(
            dcf=None, land_cost_won=1, construction_cost_won=1, revenue_won=1,
            discount_rate=0.08,
        ) is None

    def test_zero_equity_yields_null_moic_and_equity_irr_with_reason(self):
        """전액 타인자본 가정(equity_won=0, total_cost_won 제공) — MOIC·Equity IRR null+사유."""
        dcf = assemble_monthly_dcf(
            land_cost_won=_GOLDEN_LAND, construction_cost_won=_GOLDEN_CONSTR,
            revenue_won=_GOLDEN_REVENUE, project_months=_GOLDEN_PM,
            equity_won=0.0, discount_rate=_GOLDEN_DISCOUNT, total_cost_won=_GOLDEN_TOTAL_COST,
        )
        kpi = compute_return_kpi(
            dcf=dcf, land_cost_won=_GOLDEN_LAND, construction_cost_won=_GOLDEN_CONSTR,
            revenue_won=_GOLDEN_REVENUE, discount_rate=_GOLDEN_DISCOUNT,
            total_cost_won=_GOLDEN_TOTAL_COST,
        )
        assert kpi["moic"] is None
        assert kpi["equity_irr_pct"] is None
        assert any("자기자본" in n for n in kpi["degraded_notes"])

    def test_missing_total_cost_still_yields_ltv_via_gdv_but_no_ltc(self):
        dcf = _golden_dcf()
        kpi = compute_return_kpi(
            dcf=dcf, land_cost_won=_GOLDEN_LAND, construction_cost_won=_GOLDEN_CONSTR,
            revenue_won=_GOLDEN_REVENUE, discount_rate=_GOLDEN_DISCOUNT,
            total_cost_won=None,
        )
        assert kpi["ltv_ltc"]["peak_ltc_pct"] is None
        assert any("LTC" in n for n in kpi["degraded_notes"])


# ─────────────────────────────────────────────────────────────────────────────
# 7) IRR 산식 승격 회귀 — irr_annual_pct_from_netflows(모듈레벨)와
#    CashflowGenerator._irr_from_netflows(private, 하위호환)가 완전 동일 결과.
# ─────────────────────────────────────────────────────────────────────────────
class TestIrrHelperPromotionRegression:
    def test_module_level_and_private_method_identical(self):
        from app.services.feasibility.cashflow_generator import CashflowGenerator

        flows = [-1_000_000, 100_000, 200_000, 300_000, 500_000, 400_000]
        assert irr_annual_pct_from_netflows(flows) == CashflowGenerator()._irr_from_netflows(flows)  # noqa: SLF001

    def test_no_sign_change_returns_none(self):
        assert irr_annual_pct_from_netflows([100.0, 200.0]) is None
