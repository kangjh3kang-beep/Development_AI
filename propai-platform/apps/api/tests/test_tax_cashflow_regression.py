"""2026-06 코드리뷰 Critical 수정 회귀 테스트 — 정답값 고정 수치 검증.

C-1: 양도세 장기보유특별공제 이중차감 (D04는 정보성, 합산 제외)
C-2: 취득세·전용부담금 이중계상 (토지비 엔진 include_taxes_and_fees 플래그)
C-3: 현금흐름 net_profit에 자기자본 합산 (equity 제외)
H-6: 재건축초과이익환수 2024.3.27 개정법 구간
H-8: 단기보유 중과세율 (1년 미만 70%/50%, 1~2년 60%/40%)
"""

import pytest

from app.services.feasibility.cashflow_generator import (
    CashflowGenerator,
    build_tax_schedule_from_integrated,
)
from app.services.feasibility.land_cost_engine import calculate_total_land_cost
from app.services.tax.disposal_stage_engine import (
    calculate_all_disposal_stage,
    calculate_d01_capital_gains_tax,
    calculate_d05_reconstruction_levy,
)


class TestD01CapitalGains:
    def test_known_value_10eok_5yr(self):
        """양도차익 10억·5년 보유 주거용: LTDC 10% → 과세표준 9억 → 42% 구간.

        9억(90,000만) × 0.42 − 3,594만 = 34,206만 = 342,060,000원
        """
        r = calculate_d01_capital_gains_tax(
            gain_10k_won=100_000, holding_years=5, is_residential=True
        )
        assert r["amount_won"] == 342_060_000
        assert r["detail"]["deduction_rate"] == 0.10
        assert r["detail"]["taxable_10k"] == 90_000

    def test_short_term_under_1yr_residential(self):
        """1년 미만 주거용: 70% 단일세율 (소득세법 104조). 5억 × 0.7 = 3.5억."""
        r = calculate_d01_capital_gains_tax(
            gain_10k_won=50_000, holding_years=0, is_residential=True
        )
        assert r["amount_won"] == 350_000_000
        assert r["rate"] == 0.70

    def test_short_term_1to2yr_residential(self):
        """1~2년 주거용: 60% 단일세율. 5억 × 0.6 = 3억."""
        r = calculate_d01_capital_gains_tax(
            gain_10k_won=50_000, holding_years=1, is_residential=True
        )
        assert r["amount_won"] == 300_000_000
        assert r["rate"] == 0.60

    def test_short_term_under_1yr_land(self):
        """1년 미만 토지: 50% 단일세율. 5억 × 0.5 = 2.5억."""
        r = calculate_d01_capital_gains_tax(
            gain_10k_won=50_000, holding_years=0, is_residential=False
        )
        assert r["amount_won"] == 250_000_000
        assert r["rate"] == 0.50


class TestDisposalStageTotal:
    def test_no_double_deduction_total(self):
        """C-1 회귀: 10억·5년 → D01 3.4206억 + D03 0.34206억, D04는 합산 제외.

        총액 = 342,060,000 + 34,206,000 = 376,266,000원
        (수정 전 버그: D04 −1억이 합산되어 276,266,000원으로 과소계상)
        """
        result = calculate_all_disposal_stage(
            gain_10k_won=100_000,
            gain_won=1_000_000_000,
            holding_years=5,
            is_residential=True,
        )
        assert result["total_won"] == 376_266_000

        d04 = next(it for it in result["items"] if it["code"] == "D04")
        assert d04["amount_won"] == 0  # 정보성 항목
        assert d04["detail"]["taxable_reduction_won"] == 100_000_000

    def test_total_never_negative_with_high_deduction(self):
        """공제율이 높아도 합계가 음수가 되지 않는다 (수정 전 가능했던 케이스)."""
        result = calculate_all_disposal_stage(
            gain_10k_won=10_000,
            gain_won=100_000_000,
            holding_years=15,
            is_residential=True,
        )
        assert result["total_won"] >= 0


class TestReconstructionLevy2024:
    """H-6 회귀: 재건축이익환수법 2024.3.27 개정 (면제 8천만, 5천만 단위 10~50%)."""

    def test_exempt_under_80m(self):
        assert calculate_d05_reconstruction_levy(excess_gain_won=80_000_000)["amount_won"] == 0

    def test_100m(self):
        """1억: (1억−8천만) × 10% = 200만."""
        assert calculate_d05_reconstruction_levy(excess_gain_won=100_000_000)["amount_won"] == 2_000_000

    def test_300m_top_bracket(self):
        """3억: 5천만×(10+20+30+40)% + 2천만×50% = 6,000만."""
        assert calculate_d05_reconstruction_levy(excess_gain_won=300_000_000)["amount_won"] == 60_000_000


class TestLandCostNoDoubleCounting:
    """C-2 회귀: 모듈 파이프라인 경로에서 취득세·전용부담금은 세금엔진 단일 계상."""

    def test_exclude_taxes_flag(self):
        r = calculate_total_land_cost(
            total_area_sqm=1_000,
            official_price_per_sqm=1_000_000,
            price_multiplier=1.0,
            land_category="farmland",
            compensation_won=50_000_000,
            include_taxes_and_fees=False,
        )
        # 매입비 10억 + 보상비 0.5억만 — 취득세·농지전용부담금 제외
        assert r["total_land_cost_won"] == 1_050_000_000
        assert r["taxes_and_fees_included"] is False
        # 참고 정보는 여전히 반환
        assert r["acquisition_tax"]["tax_amount_won"] > 0
        assert r["conversion_fee"]["total_fee_won"] > 0

    def test_include_taxes_default(self):
        """기본값(True)은 기존 동작 유지 — 단독 사용 경로 호환."""
        r = calculate_total_land_cost(
            total_area_sqm=1_000,
            official_price_per_sqm=1_000_000,
        )
        assert r["total_land_cost_won"] == (
            1_000_000_000
            + r["acquisition_tax"]["tax_amount_won"]
            + r["conversion_fee"]["total_fee_won"]
        )


class TestAcquisitionStageUpgrades:
    """Phase 2 고도화 회귀: A05 이중과세 제거, A04 인지세 하위구간, 취득세 슬라이딩."""

    def test_a05_no_double_taxation(self):
        """등록면허세: 소유권이전분 2% 부과 제거 (2011년 취득세 통합)."""
        from app.services.tax.acquisition_stage_engine import calculate_a05_registration_tax
        r = calculate_a05_registration_tax(10_000_000_000)
        assert r["amount_won"] == 0
        # 저당권 설정 등기는 채권금액의 0.2%
        r2 = calculate_a05_registration_tax(10_000_000_000, mortgage_amount_won=5_000_000_000)
        assert r2["amount_won"] == 10_000_000

    def test_a04_stamp_tax_brackets(self):
        """인지세법 제3조 구간: 1천만 이하 0 / 3천만 2만 / 5천만 4만 / 1억 7만 / 10억 15만 / 초과 35만."""
        from app.services.tax.acquisition_stage_engine import calculate_a04_stamp_tax
        assert calculate_a04_stamp_tax(10_000_000)["amount_won"] == 0
        assert calculate_a04_stamp_tax(30_000_000)["amount_won"] == 20_000
        assert calculate_a04_stamp_tax(50_000_000)["amount_won"] == 40_000
        assert calculate_a04_stamp_tax(100_000_000)["amount_won"] == 70_000
        assert calculate_a04_stamp_tax(500_000_000)["amount_won"] == 150_000
        assert calculate_a04_stamp_tax(2_000_000_000)["amount_won"] == 350_000

    def test_housing_acquisition_sliding(self):
        """주택 유상취득 1~3% 슬라이딩 (지방세법 11조1항8호)."""
        from app.services.tax.regional_tax_data import get_acquisition_tax_rates
        # 6억 이하: 1%
        assert get_acquisition_tax_rates("land", 1, False, purchase_won=500_000_000)["base_rate"] == 0.01
        # 7.5억: (7.5 × 2/3 − 3)% = 2%
        assert get_acquisition_tax_rates("land", 1, False, purchase_won=750_000_000)["base_rate"] == 0.02
        # 9억 초과: 3%
        assert get_acquisition_tax_rates("land", 1, False, purchase_won=1_200_000_000)["base_rate"] == 0.03
        # 조정지역 2주택 중과 8%는 슬라이딩 미적용
        assert get_acquisition_tax_rates("land", 2, True, purchase_won=1_200_000_000)["base_rate"] == 0.08
        # 가액 미전달 시 기존 동작 유지 (하위호환)
        assert get_acquisition_tax_rates("land", 1, False)["base_rate"] == 0.01


class TestProgressiveDrawdown:
    """Phase 2 고도화 회귀: PF·중도금 분할실행 이자 (전액·전기간 가정 ~2배 과대 해소)."""

    def test_drawdown_interest_about_half_of_lump_sum(self):
        from app.services.feasibility.finance_cost_engine import (
            calculate_balloon_interest,
            calculate_drawdown_interest,
        )
        principal, rate, months = 100_000_000_000, 0.05, 30
        lump = calculate_balloon_interest(principal, rate, months)
        drawdown = calculate_drawdown_interest(principal, rate, months)
        # 균등 분할실행 평균잔액 ≈ 원금의 ~52% → 이자도 그 수준
        assert 0.45 * lump < drawdown < 0.60 * lump

    def test_total_finance_cost_uses_progressive_for_pf_midpay(self):
        from app.services.feasibility.finance_cost_engine import calculate_total_finance_cost
        r = calculate_total_finance_cost(
            bridge_amount_won=10_000_000_000, bridge_rate=0.05, bridge_months=12,
            pf_amount_won=100_000_000_000, pf_rate=0.05, pf_months=30,
            midpay_amount_won=50_000_000_000, midpay_rate=0.04, midpay_months=18,
        )
        assert r["pf"]["disbursement"] == "progressive"
        assert r["midpay"]["disbursement"] == "progressive"
        # 내부 일관성: 총합 = 부분합
        assert r["total_finance_cost_won"] == (
            r["bridge"]["total_bridge_cost_won"]
            + r["pf"]["total_pf_cost_won"]
            + r["midpay"]["total_midpay_cost_won"]
        )
        # 하위호환: progressive_drawdown=False면 기존 전액 기준
        r2 = calculate_total_finance_cost(
            pf_amount_won=100_000_000_000, pf_rate=0.05, pf_months=30,
            progressive_drawdown=False,
        )
        assert "disbursement" not in r2["pf"]
        assert r2["pf"]["total_pf_cost_won"] > r["pf"]["total_pf_cost_won"]


class TestSaleStageBuyerSplit:
    """Phase 2 고도화 회귀: 분양자 부담 세금(C04-C06)은 시행사 사업비에서 제외 (M-6)."""

    def test_buyer_items_excluded_from_total(self):
        from app.services.tax.sale_stage_engine import calculate_all_sale_stage
        r = calculate_all_sale_stage(
            total_sale_amount_won=100_000_000_000,
            total_units=500, avg_area_sqm=100, total_gfa_sqm=50_000,
        )
        dev_total = sum(it["amount_won"] for it in r["items"] if it["borne_by"] == "developer")
        buyer_total = sum(it["amount_won"] for it in r["items"] if it["borne_by"] == "buyer")
        assert r["total_won"] == dev_total
        assert r["buyer_borne_total_won"] == buyer_total
        assert buyer_total > 0  # C04~C06은 여전히 참고 정보로 산출
        # C04(1.1%) + C05(0.2%) + C06(0.25%) ≈ 분양가의 1.55%
        assert buyer_total == pytest.approx(1_550_000_000, rel=0.01)


class TestZoneLimitsCoverage:
    """Phase 2 고도화 회귀: 관리·농림·자연환경보전지역 법규검증 커버리지 (M-7)."""

    def test_management_zones_have_limits(self):
        from app.services.zoning.legal_zone_limits import legal_limits_for
        for zone in ("보전관리지역", "생산관리지역", "계획관리지역", "농림지역", "자연환경보전지역"):
            limits = legal_limits_for(zone)
            assert limits is not None, f"{zone} 한도 누락"
            assert limits["max_far_pct"] > 0

    def test_management_zone_violation_detected(self):
        """계획관리지역 용적률 300% 주장 → 위반 적발 (이전: 빈 리스트로 통과)."""
        from app.services.zoning.legal_zone_limits import check_against_legal
        issues = check_against_legal("계획관리지역", far_pct=300)
        assert len(issues) >= 1
        assert issues[0]["severity"] == "high"

    def test_first_exclusive_residential_bcr_50(self):
        """제1종전용주거 건폐율 법정 상한 50% (시행령 84조)."""
        from app.services.zoning.legal_zone_limits import legal_limits_for
        assert legal_limits_for("제1종전용주거지역")["max_bcr_pct"] == 50


class TestMonteCarloConvergence:
    """Phase 2 고도화 회귀: 수렴판정은 표준오차 기준 (CV 아님)."""

    def test_se_ratio_decreases_with_n(self):
        from app.services.feasibility.monte_carlo_engine import MCVariable, run_monte_carlo
        var = [MCVariable(name="x", mean=100.0, std=30.0)]
        fn = lambda v: v["x"]  # noqa: E731
        small = run_monte_carlo(calculate_fn=fn, variables=var, n_simulations=100)
        large = run_monte_carlo(calculate_fn=fn, variables=var, n_simulations=10_000)
        # CV(convergence_ratio)는 N과 무관하게 ≈0.3, SE 비율은 N 증가 시 감소
        assert abs(small["convergence_ratio"] - large["convergence_ratio"]) < 0.1
        assert large["standard_error_ratio"] < small["standard_error_ratio"]
        # 리스크 있는 분포(CV 30%)도 N=10,000이면 수렴 판정 (SE ≈ 0.003)
        assert large["converged"] is True

    def test_sensitivity_distinguishes_variables(self):
        """민감도분석이 변수별로 다른 값을 산출한다 (이전: 전부 1.0)."""
        from app.services.finance.monte_carlo_service import MonteCarloService
        svc = MonteCarloService()
        r = svc.sensitivity_analysis(
            base_cost_krw=10_000_000_000, base_revenue_krw=15_000_000_000,
            variables=["cost", "revenue", "discount_rate"],
        )
        sens = {k: v["sensitivity"] for k, v in r.items()}
        # 변수별 민감도가 서로 달라야 함
        assert len(set(sens.values())) > 1
        # 비용·매출 high/low가 실제로 비대칭 (단순 ±20% 복제가 아님)
        assert r["cost"]["high_case_npv"] != r["revenue"]["high_case_npv"]


class TestCashflowEquityExclusion:
    """C-3 회귀: 자기자본 투입은 이익이 아니다."""

    @pytest.fixture()
    def result(self):
        return CashflowGenerator().generate_monthly_cashflow(
            land_cost=10_000_000_000,
            construction_cost=20_000_000_000,
            construction_months=12,
            total_revenue=40_000_000_000,
            sale_start_month=0,
            sale_duration_months=6,
            equity_ratio=0.3,
            design_months=3,
            design_cost_ratio=0.03,
        )

    def test_equity_tracked(self, result):
        # 총사업비 = 100억 + 6억(설계) + 200억 = 306억 → equity 30% = 91.8억
        assert result["summary"]["equity_in_total"] == 9_180_000_000

    def test_net_profit_excludes_equity(self, result):
        s = result["summary"]
        # net_profit = 유입 − 유출 − 자기자본 (반올림 오차 허용)
        assert abs(s["net_profit"] - (s["total_inflow"] - s["total_outflow"] - s["equity_in_total"])) <= 2

    def test_net_profit_equals_revenue_minus_costs(self, result):
        """이익 = 분양수입 − (토지+설계+공사+이자). 대출·자본 유출입은 상쇄."""
        s = result["summary"]
        expected = 40_000_000_000 - 30_600_000_000 - s["interest_total"]
        assert abs(s["net_profit"] - expected) <= 2

    def test_revenue_conservation(self, result):
        """월별 분양수입 + 잔금 = 총분양수입 (이중계상 없음, H-4 회귀)."""
        [
            r["inflow"] for r in result["rows"]
            if r["items"] != "-" and ("분양수입" in r["items"] or "잔금" in r["items"])
        ]
        # 분양수입 행에는 대출 유입이 섞일 수 있으므로 단순합 대신 상한·하한 검증
        s = result["summary"]
        # 유입 총계 = equity + bridge + PF + 분양수입(전액) — 분양수입 보존 확인
        financing_in = s["equity_in_total"] + s["bridge_loan_amount"] * 2 + s["pf_loan_amount"]
        # bridge는 PF 전환 시 잔액이 PF에 합산 실행되므로 *2 (실행 + PF재실행분)
        assert abs(s["total_inflow"] - (financing_in + 40_000_000_000)) <= 5


class TestAfterTaxIRRIntegration:
    """R1 회귀: 세후 IRR 통합 현금흐름 — tax_schedule additive 주입.

    타임라인(BASE_KW 기준): 설계 3개월 → 착공월 4, 준공월 15, 정산월 16,
    총 19개월(month 0~18). 분양 6개월(month 4~9, 가중 2,2,1,1,1,0.6 — 합 7.6).
    """

    BASE_KW = dict(
        land_cost=10_000_000_000,
        construction_cost=20_000_000_000,
        construction_months=12,
        total_revenue=40_000_000_000,
        sale_start_month=0,
        sale_duration_months=6,
        equity_ratio=0.3,
        design_months=3,
        design_cost_ratio=0.03,
        # ★W5: 이 클래스의 골든은 '세금 주입 위치'(월별 비례 가중 포함) 검증이 취지 —
        #   분할 유입(기본 installment) 도입과 무관하게 종전 스케줄로 고정해 취지 보존.
        revenue_schedule="front_loaded",
    )

    SCHEDULE = {
        "acquisition_won": 460_000_000,          # A → month 0
        "construction_won": 200_000_000,         # B → 착공월(4)
        "sale_won": 1_200_000_000,               # C → 분양수입 월별 비례(4~9)
        "disposal_settlement_won": 800_000_000,  # D01·D03 → 정산월(16)
        "d06_annual_won": 50_000_000,            # D06 → 보유 연차별
        "d06_years": 2,
    }

    def test_backward_compat_none_schedule_identical(self):
        """하위호환: tax_schedule=None(기본)이면 기존 결과와 완전 동일 + 신규 키 부재."""
        legacy = CashflowGenerator().generate_monthly_cashflow(**self.BASE_KW)
        explicit_none = CashflowGenerator().generate_monthly_cashflow(
            **self.BASE_KW, tax_schedule=None
        )
        assert explicit_none == legacy
        assert "after_tax_irr_annual_pct" not in legacy["summary"]
        assert "total_tax_won" not in legacy["summary"]
        # 기존 정답값 유지 (C-3 회귀와 동일 파라미터)
        assert legacy["summary"]["equity_in_total"] == 9_180_000_000

    def test_after_tax_irr_below_pretax_and_pretax_unchanged(self):
        """방향성: 세후 IRR < 세전 IRR. 세전 irr_annual_pct는 주입과 무관하게 불변."""
        base = CashflowGenerator().generate_monthly_cashflow(**self.BASE_KW)
        taxed = CashflowGenerator().generate_monthly_cashflow(
            **self.BASE_KW, tax_schedule=self.SCHEDULE
        )
        assert taxed["summary"]["irr_annual_pct"] == base["summary"]["irr_annual_pct"]
        assert taxed["summary"]["after_tax_irr_annual_pct"] is not None
        assert (
            taxed["summary"]["after_tax_irr_annual_pct"]
            < taxed["summary"]["irr_annual_pct"]
        )
        # 총세금 정답값: 4.6억 + 2억 + 12억 + 8억 + 0.5억×2 = 27.6억
        assert taxed["summary"]["total_tax_won"] == 2_760_000_000

    def test_injection_months_fixed(self):
        """A=month0 / B=착공월 / C=분양월 비례 / D=정산월 위치 정답값 고정."""
        base = CashflowGenerator().generate_monthly_cashflow(**self.BASE_KW)
        taxed = CashflowGenerator().generate_monthly_cashflow(
            **self.BASE_KW, tax_schedule=self.SCHEDULE
        )
        delta = {
            b["month"]: t["outflow"] - b["outflow"]
            for t, b in zip(taxed["rows"], base["rows"], strict=False)
        }
        # A(취득) → month 0
        assert delta[0] == pytest.approx(460_000_000, abs=1)
        # B(공사부담금) 착공월(4) + C 비례분(가중 2/7.6): 2억 + 12억×2/7.6
        assert delta[4] == pytest.approx(200_000_000 + 1_200_000_000 * 2 / 7.6, abs=2)
        # C 비례분만 있는 분양 2개월차(month 5, 가중 2/7.6)
        assert delta[5] == pytest.approx(1_200_000_000 * 2 / 7.6, abs=2)
        # D01·D03 → 정산월(16)
        assert delta[16] == pytest.approx(800_000_000, abs=1)
        # 전월 주입 총합 = 총세금 (시점 분배가 총액을 보존)
        assert sum(delta.values()) == pytest.approx(2_760_000_000, abs=len(delta))

    def test_d06_yearly_sum_equals_annual_times_years(self):
        """D06 연차 주입 합계 = annual × 년수 정답값 고정 (12·24개월차, 말월 클램프)."""
        schedule = {"d06_annual_won": 50_000_000, "d06_years": 2}
        base = CashflowGenerator().generate_monthly_cashflow(**self.BASE_KW)
        taxed = CashflowGenerator().generate_monthly_cashflow(
            **self.BASE_KW, tax_schedule=schedule
        )
        # 정답값: 50,000,000 × 2년 = 100,000,000
        assert taxed["summary"]["total_tax_won"] == 100_000_000
        delta = {
            b["month"]: t["outflow"] - b["outflow"]
            for t, b in zip(taxed["rows"], base["rows"], strict=False)
        }
        assert delta[12] == pytest.approx(50_000_000, abs=1)   # 보유 1년차
        assert delta[18] == pytest.approx(50_000_000, abs=1)   # 2년차(24개월) → 말월(18) 클램프
        assert sum(delta.values()) == pytest.approx(100_000_000, abs=2)
        # 종부세만 주입해도 세후 IRR은 세전보다 낮다
        assert (
            taxed["summary"]["after_tax_irr_annual_pct"]
            < taxed["summary"]["irr_annual_pct"]
        )


class TestTaxScheduleAdapter:
    """R1 어댑터: calculate_all_taxes 출력 → tax_schedule 변환 (새 엔진 0, 총액 보존)."""

    def test_total_conservation_and_d06_decomposition(self):
        from app.services.tax.integrated_tax_engine import calculate_all_taxes

        result = calculate_all_taxes(
            purchase_won=10_000_000_000,
            area_sqm=1_000.0,
            official_price_per_sqm=10_000_000,
            total_households=400,
            total_sale_amount_won=40_000_000_000,
            total_gfa_sqm=10_000.0,
            building_type="apartment",
            total_units=400,
            avg_area_sqm=100.0,
            gain_10k_won=1_000_000,            # 양도차익 100억(만원 단위)
            gain_won=10_000_000_000,
            holding_years=3,
            assessed_value_won=2_000_000_000,  # 공제 5억 초과 → D06 > 0
        )
        sched = build_tax_schedule_from_integrated(result)
        assert sched is not None

        # D06 연차 분해 정합: annual × years = D06 amount_won (보유 3년)
        d06 = next(it for it in result["disposal"]["items"] if it["code"] == "D06")
        assert d06["amount_won"] > 0
        assert sched["d06_years"] == 3
        assert sched["d06_annual_won"] * sched["d06_years"] == d06["amount_won"]

        # 총액 보존: 어댑터 분해 합 = grand_total_won (누락·날조 없음)
        recomposed = (
            sched["acquisition_won"]
            + sched["construction_won"]
            + sched["sale_won"]
            + sched["disposal_settlement_won"]
            + sched["d06_annual_won"] * sched["d06_years"]
        )
        assert recomposed == result["grand_total_won"]

        # 단계별 매핑 정합 (summary_by_stage 그대로 — 읽기 전용 어댑터)
        assert sched["acquisition_won"] == result["summary_by_stage"]["acquisition"]
        assert sched["construction_won"] == result["summary_by_stage"]["construction"]
        assert sched["sale_won"] == result["summary_by_stage"]["sale"]
        assert sched["disposal_settlement_won"] == (
            result["summary_by_stage"]["disposal"] - d06["amount_won"]
        )

    def test_none_or_empty_returns_none(self):
        """입력 없음·세금 전무(전부 0)면 None — 주입 없이 기존 동작 유지."""
        assert build_tax_schedule_from_integrated(None) is None
        assert build_tax_schedule_from_integrated({}) is None
        zero = {
            "summary_by_stage": {
                "acquisition": 0, "construction": 0, "sale": 0, "disposal": 0,
            },
            "disposal": {"items": []},
        }
        assert build_tax_schedule_from_integrated(zero) is None

    def test_adapter_schedule_roundtrip_into_cashflow(self):
        """엔진→어댑터→생성기 왕복: total_tax_won = grand_total_won (시점 분배 총액 보존)."""
        from app.services.tax.integrated_tax_engine import calculate_all_taxes

        result = calculate_all_taxes(
            purchase_won=10_000_000_000,
            area_sqm=1_000.0,
            official_price_per_sqm=10_000_000,
            total_households=400,
            total_sale_amount_won=40_000_000_000,
            total_gfa_sqm=10_000.0,
            building_type="apartment",
            total_units=400,
            avg_area_sqm=100.0,
            gain_10k_won=1_000_000,
            gain_won=10_000_000_000,
            holding_years=3,
            assessed_value_won=2_000_000_000,
        )
        sched = build_tax_schedule_from_integrated(result)
        cf = CashflowGenerator().generate_monthly_cashflow(
            land_cost=10_000_000_000,
            construction_cost=20_000_000_000,
            construction_months=12,
            total_revenue=40_000_000_000,
            sale_start_month=0,
            sale_duration_months=6,
            tax_schedule=sched,
        )
        assert cf["summary"]["total_tax_won"] == result["grand_total_won"]
        assert cf["summary"]["after_tax_irr_annual_pct"] is not None
        assert (
            cf["summary"]["after_tax_irr_annual_pct"]
            < cf["summary"]["irr_annual_pct"]
        )
