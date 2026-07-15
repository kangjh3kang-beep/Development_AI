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

    def test_soft_cost_flows_out_in_unlevered_stream(self):
        """리뷰 R1-HIGH-2: 소프트비 주입 시 무차입 스트림 총액 = 수입 − (토지+공사+소프트비).
        누락 시 총사업비의 ~13%가 빠져 NPV 3배 과대·IRR 216% 왜곡이 실측됐던 결함의 고정."""
        land, constr, soft, rev = 5e9, 10e9, 2e9, 25e9
        dcf = assemble_monthly_dcf(
            land_cost_won=land, construction_cost_won=constr, revenue_won=rev,
            project_months=36, discount_rate=0.06, soft_cost_won=soft,
        )
        assert dcf is not None
        total = sum(dcf["cf"]["unlevered_netflows"])
        assert total == pytest.approx(rev - land - constr - soft, abs=5)

    def test_soft_cost_none_keeps_legacy_design_ratio(self):
        """미지정(None)은 기존 내부 3% 설계비 동작 완전 동일(무회귀)."""
        land, constr, rev = 5e9, 10e9, 25e9
        dcf = assemble_monthly_dcf(
            land_cost_won=land, construction_cost_won=constr, revenue_won=rev,
            project_months=36, discount_rate=0.06,
        )
        total = sum(dcf["cf"]["unlevered_netflows"])
        assert total == pytest.approx(rev - land - constr - constr * 0.03, abs=5)

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

    def test_payback_ignores_loan_drawdown_spike(self):
        """리뷰 R1-HIGH-1 반증 케이스: 착공월 PF 인출로 누적이 순간 +로 튀어도 회수 아님 —
        최대 자금소요(트로프) 이후 첫 누적≥0이 회수월(원본 rough 로직)."""
        rows = [
            {"month": 0, "inflow": 0, "cumulative": -100},
            {"month": 4, "inflow": 1_000, "cumulative": 50},    # PF 인출 스파이크(가짜 +)
            {"month": 10, "inflow": 0, "cumulative": -500},     # 공사비 유출로 트로프
            {"month": 30, "inflow": 700, "cumulative": 20},     # 분양수입으로 실회수
        ]
        assert payback_month(rows) == 30  # 4가 아님(스파이크 무시)

    def test_payback_total_loss_is_none(self):
        """대손(최종 누적 음수) 사업은 회수월 None — '4개월 회수' 오판 금지."""
        rows = [
            {"month": 0, "inflow": 0, "cumulative": -100},
            {"month": 4, "inflow": 1_000, "cumulative": 50},    # 인출 스파이크
            {"month": 36, "inflow": 100, "cumulative": -300},   # 트로프이자 최종(미회수)
        ]
        assert payback_month(rows) is None


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
        # ★R1-HIGH-2 상한 정합: 무차입 NPV ≤ (수입−토지−공사−소프트비−세금) 미할인 총액
        #   (할인은 값을 줄이는 방향 — 상한 초과는 비용 누락 신호).
        undiscounted = (
            out.total_revenue_won - out.total_land_cost_won
            - out.total_construction_cost_won - out.total_other_cost_won
            - out.total_tax_cost_won
        )
        assert out.npv_won <= undiscounted
        # IRR: 존재 + 유입 스케줄 정직 라벨. ★재기준(소소잔여): W5(#318)로 분할 유입
        # (계약10/중도60/잔금30)이 엔진 기본이 됐는데 종전 라벨("조기 유입 가정·분할
        # 미모델링")이 stale 거짓 표기로 남아 있었다 — 실제 스케줄을 서술하는 라벨로 교정.
        assert cs["irr_pct"] is not None
        assert any("분할 유입" in a for a in cs["assumptions"])
        assert not any("조기 유입" in a for a in cs["assumptions"])  # stale 표기 재발 방지
        assert "월별 DCF" in cs["npv_basis"]

    def test_income_dcf_noi_zero_edge_replaced(self):
        """★D6-부속(NOI=0 엣지): M08이 NOI 미입력이면 special_detail.dcf는 존재하나
        npv=0(모듈이 소득 DCF를 채택하지 않음) — 월별 DCF로 정상 교체되고
        '소득접근 보존' 거짓 표기가 없어야 한다."""
        inp = _sale_input("M08")
        inp.params = {}  # annual_noi_won 미입력 → NOI=0
        out = FeasibilityServiceV2().calculate(inp)
        cs = out.cashflow_summary
        assert cs is not None
        dcf_sd = (out.special_detail or {}).get("dcf")
        assert dcf_sd is not None and (dcf_sd.get("npv_won") or 0) == 0
        assert out.npv_won == cs["npv_won"]  # 월별 DCF로 교체(단일기간 근사 잔존 방지)
        assert "소득접근" not in cs["npv_basis"]  # 거짓 '보존' 표기 없음

    def test_income_dcf_module_npv_preserved(self):
        """리뷰 R1-MEDIUM-1: 보유형(M08 소득접근 DCF 보유) 모듈의 고유 npv는 보존 —
        개발현금흐름 NPV는 cashflow_summary에 병기."""
        inp = _sale_input("M08")
        inp.params = {"annual_noi_won": 1_500_000_000, "holding_years": 10}
        out = FeasibilityServiceV2().calculate(inp)
        if (out.special_detail or {}).get("dcf"):
            assert out.cashflow_summary is not None
            assert out.npv_won != out.cashflow_summary["npv_won"]  # 고유 소득 DCF 보존
            assert "소득접근" in out.cashflow_summary["npv_basis"]

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
