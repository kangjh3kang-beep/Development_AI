"""W3(100% 캠페인) 회귀 테스트 — 경로A 현금흐름화(진짜 상세수지).

감사 결함 수지5(상세수지 경로 부재)·수지7(경로A NPV 단일기간 근사)·수지6(DSCR 부재) 봉합:
1. DCF 조립 공용 SSOT(dcf_assembly) — rough §8 인라인과 동일 규칙(표준 근사·무차입 NPV·
   세금 주입 시 after-tax IRR 선택). rough는 리팩토링으로 소비(수치 무회귀 — 기존
   test_rough_feasibility_orchestrator가 관류 검증).
2. service.calculate가 NPV를 월별 DCF 기저로 교체 + cashflow_summary(IRR·회수기간·
   DSCR·기저·가정) 부착. 실패 시 기존 npv 유지(무손상).
3. DSCR은 임대수입(NOI 근사) 있을 때만 — 분양형은 사유와 함께 정직 null(무날조).
"""

from __future__ import annotations

import pytest

from app.services.feasibility.cashflow_generator import CashflowGenerator, npv_from_netflows
from app.services.feasibility.dcf_assembly import assemble_monthly_dcf, payback_month
from app.services.feasibility.feasibility_service_v2 import FeasibilityServiceV2
from app.services.feasibility.modules.base_module import ModuleInput


def _sale_input(dev_type: str = "M06") -> ModuleInput:
    return ModuleInput(
        development_type=dev_type,
        total_land_area_sqm=2_000.0,
        official_price_per_sqm=3_000_000,
        price_multiplier=1.1,
        total_gfa_sqm=8_000.0,
        building_type="apartment",
        total_households=80,
        avg_sale_price_per_pyeong=15_000_000,
        avg_area_pyeong=34.0,
        sale_ratio=0.95,
        project_months=36,
        discount_rate=0.08,
        sido_name="서울특별시",
    )


# ─────────────────────────────────────────────────────────────────────────────
# 1) 공용 조립 — 표준 근사·기저 선택이 rough 종전 인라인과 동일
# ─────────────────────────────────────────────────────────────────────────────
class TestAssembleMonthlyDcf:
    def test_standard_approximations_match_legacy_inline(self):
        """미제공 입력의 표준 근사(공사=max(6,pm-6)·분양개시=min(6,cm-1)·6개월)가 종전과 동일."""
        dcf = assemble_monthly_dcf(
            land_cost_won=5_000_000_000, construction_cost_won=10_000_000_000,
            revenue_won=20_000_000_000, project_months=36,
            equity_won=3_000_000_000, discount_rate=0.06,
            total_cost_won=17_000_000_000,
        )
        assert dcf is not None
        assert dcf["construction_months"] == 30          # max(6, 36-6)
        assert dcf["sale_start_month"] == 6              # min(6, 29)
        assert dcf["sale_duration_months"] == 6
        assert dcf["equity_ratio"] == pytest.approx(3 / 17, abs=1e-9)
        # NPV = 무차입 스트림 할인(직접 재계산 대조 — 자기입력 되읽기 아님)
        cf = CashflowGenerator().generate_monthly_cashflow(
            land_cost=5_000_000_000, construction_cost=10_000_000_000,
            construction_months=30, total_revenue=20_000_000_000,
            sale_start_month=6, sale_duration_months=6,
            equity_ratio=3 / 17,
        )
        assert dcf["npv_won"] == npv_from_netflows(cf["unlevered_netflows"], 0.06)
        assert dcf["irr_pct"] == cf["summary"]["irr_annual_pct"]  # 세금 미주입 → 세전 IRR

    def test_tax_schedule_switches_to_after_tax_basis(self):
        schedule = {"acquisition_won": 500_000_000, "construction_won": 300_000_000,
                    "sale_won": 200_000_000, "disposal_settlement_won": 0,
                    "d06_annual_won": 0, "d06_years": 0}
        dcf = assemble_monthly_dcf(
            land_cost_won=5_000_000_000, construction_cost_won=10_000_000_000,
            revenue_won=20_000_000_000, project_months=36, discount_rate=0.06,
            tax_schedule=schedule,
        )
        assert dcf is not None
        # 세금 주입 시 IRR은 after-tax 기저(세전과 달라야 함) — cf_summary에 양쪽 존재
        assert dcf["cf_summary"]["after_tax_irr_annual_pct"] == dcf["irr_pct"]
        assert dcf["cf_summary"]["irr_annual_pct"] != dcf["irr_pct"]

    def test_insufficient_inputs_return_none(self):
        assert assemble_monthly_dcf(
            land_cost_won=0, construction_cost_won=0, revenue_won=10, project_months=36,
        ) is None
        assert assemble_monthly_dcf(
            land_cost_won=10, construction_cost_won=10, revenue_won=0, project_months=36,
        ) is None

    def test_payback_month_helper(self):
        rows = [
            {"month": 0, "inflow": 0, "cumulative": -100},
            {"month": 1, "inflow": 50, "cumulative": -50},
            {"month": 2, "inflow": 80, "cumulative": 30},
        ]
        assert payback_month(rows) == 2
        assert payback_month([{"month": 0, "inflow": 0, "cumulative": -1}]) is None


# ─────────────────────────────────────────────────────────────────────────────
# 2) 경로A(/calculate 서비스) — NPV 교체 + cashflow_summary 부착
# ─────────────────────────────────────────────────────────────────────────────
class TestPathADetailedDcf:
    def test_npv_replaced_with_dcf_basis(self):
        out = FeasibilityServiceV2().calculate(_sale_input())
        cs = out.cashflow_summary
        assert cs is not None
        assert out.npv_won == cs["npv_won"]
        # 종전 단일기간 근사와 다름을 확인(결함 수지7의 실교체 증명)
        legacy_npv = int(out.net_profit_won / ((1 + 0.08) ** (36 / 12)))
        assert out.npv_won != legacy_npv
        assert "월별 DCF" in cs["npv_basis"]
        assert cs["irr_pct"] is not None
        assert cs["assumptions"]

    def test_sale_project_dscr_honest_null(self):
        """분양형(임대 0) — DSCR은 사유와 함께 정직 null(무날조)."""
        out = FeasibilityServiceV2().calculate(_sale_input())
        cs = out.cashflow_summary
        assert cs["dscr"] is None
        assert "분양형" in cs["dscr_basis"]

    def test_rental_project_dscr_computed(self):
        """임대혼합(sale_ratio<1 + 임대 params) — DSCR = 연 순임대수입 ÷ 연평균 이자."""
        inp = _sale_input("M14")
        inp.sale_ratio = 0.0  # 전량 임대(M14 공공임대)
        inp.params = {"avg_deposit_per_pyeong": 5_000_000, "avg_monthly_rent_per_pyeong": 50_000}
        out = FeasibilityServiceV2().calculate(inp)
        cs = out.cashflow_summary
        assert cs is not None
        rental = out.revenue_detail.get("rental") or {}
        annual_net = float(rental.get("annual_net_rent_won") or 0)
        assert annual_net > 0
        annual_interest = float(out.total_finance_cost_won) / (36 / 12)
        assert cs["dscr"] == pytest.approx(round(annual_net / annual_interest, 2))
        assert "이자보상" in cs["dscr_basis"]

    def test_validation_error_still_raised(self):
        """입력 검증 실패 경로는 DCF 부착과 무관하게 종전대로 ValueError(무회귀)."""
        bad = _sale_input()
        bad.total_land_area_sqm = 0
        with pytest.raises(ValueError):
            FeasibilityServiceV2().calculate(bad)
