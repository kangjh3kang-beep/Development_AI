"""W5(2026-07-16 승인) 회귀 테스트 — 분양대금 분할 유입 + 금융 자동추정 분할실행 기저.

배경(W3 R2·갭 감사 P2):
- 종전 분양수입 '초기 집중 전액' 유입은 무차입 IRR을 비현실적으로 끌어올렸다(214%대).
- 금융 자동추정(전액·단리)은 정밀입력(분할실행 ~절반)의 2배 — "정밀 입력할수록
  ROI가 좋아지는" 역설.

계약:
1. installment(기본): 계약금 10%(분양기간 초기집중) + 중도금 60%(분양개시 익월~공사종료
   균등) + 잔금 30%(정산월). 총액 보존.
2. front_loaded 옵션은 종전 동작 완전 동일(무회귀 — 세금 주입 골든이 사용).
3. IRR(installment) < IRR(front_loaded) — 유입 후행화의 필연 방향.
4. 자동추정 = 전액 기저 × 평균잔액 50%(분할실행 근사).
"""

from __future__ import annotations

import pytest

from app.services.feasibility.cashflow_generator import CashflowGenerator

KW = dict(
    land_cost=10_000_000_000,
    construction_cost=20_000_000_000,
    construction_months=24,
    total_revenue=45_000_000_000,
    sale_start_month=3,
    sale_duration_months=6,
    equity_ratio=0.3,
)


class TestInstallmentSchedule:
    def test_total_revenue_preserved(self):
        """분할 유입 총액 보존 — 무차입 스트림 총합 = 수입 − (토지+공사+설계 3%).

        (양수합은 월 순액이라 비용과 상계 — 총합 등식이 유일한 정확 검증. 등식 성립
        = 계약금·중도금·잔금 전액이 스트림에 유입·누락/이중 없음.)"""
        cf = CashflowGenerator().generate_monthly_cashflow(**KW)
        expected = KW["total_revenue"] - (
            KW["land_cost"] + KW["construction_cost"] + KW["construction_cost"] * 0.03
        )
        assert sum(cf["unlevered_netflows"]) == pytest.approx(expected, abs=5)

    def test_balloon_is_30pct_at_settlement(self):
        """잔금 30%가 정산월(공사종료+1)에 유입."""
        cf = CashflowGenerator().generate_monthly_cashflow(**KW)
        construction_end = 3 + 1 + KW["construction_months"] - 1  # design 3 + start
        settle = next(r for r in cf["rows"] if r["month"] == construction_end + 1)
        assert "잔금 수령" in settle["items"]
        assert settle["inflow"] == pytest.approx(KW["total_revenue"] * 0.30, rel=0.02)

    def test_front_loaded_option_preserves_legacy(self):
        """front_loaded 옵션 = 종전 초기집중 분포 완전 동일(무회귀 앵커)."""
        legacy = CashflowGenerator().generate_monthly_cashflow(**KW, revenue_schedule="front_loaded")
        # 종전 특성: 분양기간(6개월) 내 유입 + 정산월 잔여 0(전액 스케줄 유입)
        gen = CashflowGenerator()
        dist = gen._revenue_distribution(KW["total_revenue"], KW["sale_duration_months"])
        assert sum(dist) == pytest.approx(KW["total_revenue"], rel=1e-9)
        construction_end = 3 + 1 + KW["construction_months"] - 1
        settle = next(r for r in legacy["rows"] if r["month"] == construction_end + 1)
        assert "잔금 수령" not in settle["items"]  # 전액 선유입 — 잔금 없음

    def test_irr_lower_than_front_loaded(self):
        """유입 후행화 → 무차입 IRR 하락(방향 필연) — 조기유입 IRR 고평가 해소 증명."""
        inst = CashflowGenerator().generate_monthly_cashflow(**KW)
        front = CashflowGenerator().generate_monthly_cashflow(**KW, revenue_schedule="front_loaded")
        assert inst["summary"]["irr_annual_pct"] < front["summary"]["irr_annual_pct"]


class TestInstallmentTaxInteraction:
    def test_sale_tax_total_preserved_with_installment(self):
        """리뷰 R1-MEDIUM-1: 기본(installment)에서 C(분양 비례) 세금이 새 스케줄에 비례
        배분되고 잔금 30% 대응분은 정산월로 흡수 — 총액 보존."""
        schedule = {"acquisition_won": 460_000_000, "construction_won": 200_000_000,
                    "sale_won": 1_200_000_000, "disposal_settlement_won": 0,
                    "d06_annual_won": 0, "d06_years": 0}
        base = CashflowGenerator().generate_monthly_cashflow(**KW)
        taxed = CashflowGenerator().generate_monthly_cashflow(**KW, tax_schedule=schedule)
        assert taxed["summary"]["total_tax_won"] == pytest.approx(
            sum(v for v in schedule.values()), abs=2)
        # 정산월에 잔금 + 잔여 C세금이 함께 위치(시점 일치)
        construction_end = 3 + 1 + KW["construction_months"] - 1
        settle_taxed = next(r for r in taxed["rows"] if r["month"] == construction_end + 1)
        settle_base = next(r for r in base["rows"] if r["month"] == construction_end + 1)
        assert settle_taxed["outflow"] > settle_base["outflow"]  # 잔여 C세금 유출 존재


class TestAutoEstimateDrawdownBasis:
    def test_estimate_half_of_full_balance(self):
        """자동추정 = 전액 기저 × 0.5(평균잔액) — 정밀입력 역설 해소(갭 P2)."""
        from app.services.feasibility.modules.base_module import ModuleInput
        from app.services.feasibility.modules.common.cost_blocks import apply_auto_estimates

        inp = ModuleInput(development_type="M06", project_months=36)
        land = {"total_land_cost_won": 10_000_000_000}
        constr = {"total_construction_cost_won": 10_000_000_000}
        finance, other = apply_auto_estimates(inp, land, constr, {}, {})
        base = 20_000_000_000
        assert finance["total_finance_cost_won"] == round(base * 0.70 * 0.055 * 3.0 * 0.5)
        assert "평균잔액 50%" in finance["estimate_basis"]
        assert other["total_other_cost_won"] == round(base * 0.07)
