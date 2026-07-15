"""2026-07-15 감사 잔여 결함 즉효 봉합(W1+W2) 회귀 테스트.

W1 — 금융비·소프트비 자동추정 공용화(감사 수지10·수지9):
  generic_module에만 있던 자동추정이 M01 재개발·M02 재건축·M04 지역주택·M08 오피스텔에
  미적용 → params 미입력 시 finance=0·other=0으로 총사업비 과소·ROI 과대("ROI 566%" 잔존).
  cost_blocks.apply_auto_estimates 공용 추출로 5개 모듈 동일 표준 가정.

W2 — 정확성 가드·테스트 공백(감사 적산2·테스트 공백 3종):
  (a) T2 표준품셈 0단가 무검증 → labor=0 행을 결측 취급·T3 폴백(T1 가드와 대칭).
  (b) 제비율 11~12단계(일반관리비 5.5%·이윤 15%) 절대값 검산.
  (c) NPV/IRR 기지 현금흐름 절대값 골든.
  (d) QTO 물량 산식 검산(감사: geometry/standard estimator 무테스트).

갭 감사(신선한 눈, 2026-07-15) 편입 2건:
  (e) P1 임대 보증금 이중계상 — 레거시(활성) 경로가 환급부채인 보증금을 수입에 합산
      (보증금 제외 수정이 신규 경로에만 반영·소비처 미도달) → 임대수입 ~2배 과대.
  (f) P3 등급 경계 — 무수입·비용 발생(전손)이 profit_rate 강제 0.0으로 E(손익분기) 오판.
"""

from __future__ import annotations

import pytest

from app.services.cost.origin_cost_calculator import OriginCostCalculator
from app.services.cost.standard_quantity_estimator import StandardQuantityEstimator
from app.services.cost.unit_price_repository import UnitPriceRepository
from app.services.feasibility.cashflow_generator import CashflowGenerator, npv_from_netflows
from app.services.feasibility.modules.base_module import ModuleInput
from app.services.feasibility.modules.m01_redevelopment import M01Redevelopment
from app.services.feasibility.modules.m02_reconstruction import M02Reconstruction
from app.services.feasibility.modules.m04_union_housing import M04UnionHousing
from app.services.feasibility.modules.m08_officetel import M08Officetel


# ─────────────────────────────────────────────────────────────────────────────
# W1) 자동추정 공용화 — 4개 특화 모듈
# ─────────────────────────────────────────────────────────────────────────────
def _default_input(dev_type: str) -> ModuleInput:
    """금융·소프트비 params 미입력(자동추정 발동 조건)의 표준 입력."""
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
        sido_name="서울특별시",
    )


_MODULES = [
    ("M01", M01Redevelopment()),
    ("M02", M02Reconstruction()),
    ("M04", M04UnionHousing()),
    ("M08", M08Officetel()),
]


class TestAutoEstimateUnified:
    @pytest.mark.parametrize(("code", "module"), _MODULES)
    def test_specialized_modules_auto_estimate(self, code, module):
        """params 미입력 시 finance·other가 표준 가정 절대값으로 자동추정된다(0 금지)."""
        out = module.calculate(_default_input(code))
        base = float(out.total_land_cost_won) + float(out.total_construction_cost_won)
        # generic과 동일 산식: PF = base×LTV70%×5.5%×(months/12), 소프트비 = base×7%
        assert out.total_finance_cost_won == round(base * 0.70 * 0.055 * (36 / 12.0)), code
        assert out.total_other_cost_won == round(base * 0.07), code

    @pytest.mark.parametrize(("code", "module"), _MODULES)
    def test_explicit_inputs_still_win(self, code, module):
        """사용자 명시 입력(loan·소프트비)이 있으면 자동추정 미발동(그 값 우선)."""
        inp = _default_input(code)
        inp.pf_amount_won = 10_000_000_000
        inp.pf_rate = 0.05
        inp.pf_months = 24
        inp.params = {"marketing_cost_won": 500_000_000}
        out = module.calculate(inp)
        # 명시 금융 입력 → 실제 금융엔진 산출(자동추정 산식값과 달라야 함) / 명시 소프트비 → 그대로.
        base = float(out.total_land_cost_won) + float(out.total_construction_cost_won)
        auto_formula = round(base * 0.70 * 0.055 * (36 / 12.0))
        assert out.total_finance_cost_won > 0
        assert out.total_finance_cost_won != auto_formula, code  # 리뷰 R1-LOW: 엔진값 구별 검증
        assert out.total_other_cost_won == 500_000_000, code

    def test_all_equity_opt_out_suppresses_finance_estimate(self):
        """리뷰 R1-MEDIUM: params.all_equity=True(전액 자기자본 명시) → 금융비 자동추정 억제."""
        inp = _default_input("M01")
        inp.params = {"all_equity": True}
        out = M01Redevelopment().calculate(inp)
        assert out.total_finance_cost_won == 0  # 의도된 0 존중(강제 PF이자 계상 금지)
        base = float(out.total_land_cost_won) + float(out.total_construction_cost_won)
        assert out.total_other_cost_won == round(base * 0.07)  # 소프트비 추정은 유지

    def test_generic_module_unchanged(self):
        """공용 추출 후 generic 결과가 종전 인라인 산식과 동일(무회귀)."""
        from app.services.feasibility.modules.generic_module import GenericModule

        out = GenericModule("M06").calculate(_default_input("M06"))
        base = float(out.total_land_cost_won) + float(out.total_construction_cost_won)
        assert out.total_finance_cost_won == round(base * 0.70 * 0.055 * (36 / 12.0))
        assert out.total_other_cost_won == round(base * 0.07)


# ─────────────────────────────────────────────────────────────────────────────
# W2-a) T2 0단가 가드 — T1 가드와 대칭
# ─────────────────────────────────────────────────────────────────────────────
def _repo_with_cache(cache: dict) -> UnitPriceRepository:
    repo = UnitPriceRepository()
    repo._db_cache = cache
    return repo


class TestT2ZeroPriceGuard:
    async def test_t2_zero_labor_falls_back_to_t3(self):
        """DB의 T2 행이 노무비 0(결측)이면 채택하지 않고 T3로 폴백 — 금액 0 소실 차단."""
        repo = _repo_with_cache({
            "RC-001": {
                "spec": "레미콘(품셈)", "unit": "m3", "mat_unit": 0.0,
                "labor_unit": 0.0, "exp_unit": 0.0,
                "price_basis_year": 2025, "price_source": "표준품셈2025", "region": "경기도",
                "source_url": None,
            },
        })
        p = await repo.get_price("concrete")
        assert p["tier"] == "T3_fallback"
        assert p["mat_unit"] > 0 and p["labor_unit"] > 0

    async def test_t2_valid_row_still_used(self):
        """정상 분해 T2 행은 종전대로 채택(무회귀)."""
        repo = _repo_with_cache({
            "RC-001": {
                "spec": "레미콘(품셈)", "unit": "m3", "mat_unit": 82_000.0,
                "labor_unit": 35_000.0, "exp_unit": 8_000.0,
                "price_basis_year": 2025, "price_source": "표준품셈2025", "region": "경기도",
                "source_url": None,
            },
        })
        p = await repo.get_price("concrete")
        assert p["tier"] == "T2_standard" and p["labor_unit"] == 35_000.0


# ─────────────────────────────────────────────────────────────────────────────
# W2-b) 제비율 11~12단계 절대값 — 일반관리비 5.5%·이윤 15%(감사: 값 미검증 공백)
# ─────────────────────────────────────────────────────────────────────────────
class TestOriginCostFinalStages:
    def test_general_mgmt_and_profit_exact(self):
        items = [{
            "work_code": "01", "item_name": "테스트", "spec": "", "unit": "m3",
            "quantity": 100.0, "mat_unit": 100_000.0, "labor_unit": 50_000.0, "exp_unit": 10_000.0,
        }]
        r = OriginCostCalculator().calculate(items)
        # 11단계: 일반관리비 = 순공사원가 × 5.5%
        assert r["general_mgmt"] == round(r["net_construction_cost"] * 0.055)
        # 12단계: 이윤 = (총노무비 + 직접경비 + 일반관리비) × 15%
        profit_base = r["total_labor_cost"] + r["direct_expense_cost"] + r["general_mgmt"]
        assert r["profit"] == pytest.approx(profit_base * 0.15, abs=2)  # 개별 round 누적 ±
        # 세전 = 순공사원가 + 관리비 + 이윤, 총액 = 세전 × 1.1(VAT)
        assert r["construction_cost_pre_vat"] == pytest.approx(
            r["net_construction_cost"] + r["general_mgmt"] + r["profit"], abs=2)
        assert r["total_project_cost"] == pytest.approx(r["construction_cost_pre_vat"] * 1.1, abs=2)


# ─────────────────────────────────────────────────────────────────────────────
# W2-c) NPV/IRR 절대값 골든 — 기지 현금흐름(감사: 방향성 테스트만 존재하던 공백)
# ─────────────────────────────────────────────────────────────────────────────
class TestNpvIrrGolden:
    def test_npv_clean_zero_case(self):
        """-100만 → 12개월 후 +110만, 연 10% 할인 → NPV 정확히 0(기하 실효월리 검산)."""
        flows = [-1_000_000.0] + [0.0] * 11 + [1_100_000.0]
        assert npv_from_netflows(flows, 0.10) == 0

    def test_npv_zero_rate_is_sum(self):
        flows = [-1_000_000.0, 300_000.0, 800_000.0]
        assert npv_from_netflows(flows, 0.0) == 100_000

    def test_irr_annualized_golden(self):
        """동일 현금흐름의 IRR = 연 10.00%(월 IRR 연환산 (1+m)^12−1)."""
        flows = [-1_000_000.0] + [0.0] * 11 + [1_100_000.0]
        irr = CashflowGenerator()._irr_from_netflows(flows)
        assert irr == pytest.approx(10.0, abs=0.02)

    def test_irr_undefined_without_sign_change(self):
        assert CashflowGenerator()._irr_from_netflows([100.0, 200.0]) is None


# ─────────────────────────────────────────────────────────────────────────────
# W2-d) QTO 물량 산식 검산 — 감사: estimator 무테스트 공백
# ─────────────────────────────────────────────────────────────────────────────
class TestStandardQuantityFormulas:
    def test_apartment_quantities_exact(self):
        """아파트 1,000㎡·지상10층(저층 — 고층보정 1.0)·지하1층·RC 물량 검산."""
        items = StandardQuantityEstimator().estimate(
            building_type="아파트", total_gfa_sqm=1_000.0,
            floor_count_above=10, floor_count_below=1, structure_type="RC",
        )
        by_code = {it["work_code"]: it for it in items}
        # 유효면적 = 1000 + (1000×1×0.15)×0.3 = 1045 (지하 30% 가중)
        eff = 1_000.0 + (1_000.0 * 0.15) * 0.3
        assert by_code["01-콘크리트"]["quantity"] == round(eff * 0.45, 1)
        assert by_code["02-철근"]["quantity"] == round(eff * 75 / 1000, 2)
        assert by_code["03-거푸집"]["quantity"] == round(eff * 2.8, 1)
        # 조적·방수·창호는 지하 가중 없는 총연면적 기준
        assert by_code["04-조적"]["quantity"] == round(1_000.0 * 0.5, 1)
        # 설비/전기 = 구조직접비 비율곱(식 1개) — 물량이 아님을 계약으로 고정(정직 라벨)
        structural_direct = sum(
            it["quantity"] * (it["mat_unit"] + it["labor_unit"] + it["exp_unit"])
            for it in items[:6]
        )
        mep = by_code["07-기계설비"]
        assert mep["quantity"] == 1 and mep["unit"] == "식"
        mep_total = mep["mat_unit"] + mep["labor_unit"] + mep["exp_unit"]
        assert mep_total == pytest.approx(structural_direct * 0.35, rel=0.001)

    def test_height_factor_applied_above_15f(self):
        """15층 이상 고층 구조비 보정(1.0+(층-15)×0.008)이 콘크리트 물량에 반영."""
        base = StandardQuantityEstimator().estimate(
            building_type="아파트", total_gfa_sqm=1_000.0,
            floor_count_above=10, floor_count_below=0, structure_type="RC",
        )
        tall = StandardQuantityEstimator().estimate(
            building_type="아파트", total_gfa_sqm=1_000.0,
            floor_count_above=20, floor_count_below=0, structure_type="RC",
        )
        q_base = next(i["quantity"] for i in base if i["work_code"] == "01-콘크리트")
        q_tall = next(i["quantity"] for i in tall if i["work_code"] == "01-콘크리트")
        assert q_tall == pytest.approx(q_base * (1.0 + 5 * 0.008), rel=0.001)


# ─────────────────────────────────────────────────────────────────────────────
# 갭-e) 임대 보증금 이중계상(P1) — 레거시 경로도 "보증금 제외" 계약
# ─────────────────────────────────────────────────────────────────────────────
class TestRentalDepositNotRevenue:
    def test_legacy_path_excludes_deposit(self):
        """보증금 250억은 환급부채 — 수입은 자본환원가치(285억)만(종전 535억 과대)."""
        from app.services.feasibility.revenue_engine import calculate_rental_revenue

        r = calculate_rental_revenue(
            rental_units=100, avg_area_pyeong=25.0,
            avg_deposit_per_pyeong=10_000_000, avg_monthly_rent_per_pyeong=50_000,
            vacancy_rate=0.05, cap_rate=0.05, region="default",
        )
        # 연월세 = 100×25×5만×12 = 15억, 공실 5% 차감 후 14.25억, /0.05 = 285억
        assert r["total_deposit_won"] == 25_000_000_000  # 정보용 별도 반환은 유지
        assert r["capitalized_value_won"] == 28_500_000_000
        assert r["total_revenue_won"] == 28_500_000_000  # 보증금 미합산(신규 경로와 동일 계약)

    def test_new_path_contract_unchanged(self):
        from app.services.feasibility.revenue_engine import calculate_rental_revenue

        r = calculate_rental_revenue(
            rental_units=100, monthly_rent_per_unit=1_000_000,
            management_fee_per_unit=100_000, vacancy_rate=0.05, cap_rate=0.05,
        )
        assert r["total_revenue_won"] == r["capitalized_value_won"]


# ─────────────────────────────────────────────────────────────────────────────
# 갭-f) 등급 경계(P3) — 전손은 F(종전 E 오판)
# ─────────────────────────────────────────────────────────────────────────────
class TestGradeBoundary:
    def test_total_loss_is_grade_f(self):
        from app.services.feasibility.aggregation_engine import aggregate_feasibility

        agg = aggregate_feasibility(
            total_revenue_won=0, total_land_cost_won=1_000_000_000,
        )
        assert agg["profit_rate_pct"] == -100.0
        assert agg["grade"] == "F"

    def test_empty_inputs_stay_neutral(self):
        """수입·비용 모두 0(빈 입력)은 기존 동작 유지(0.0·무회귀)."""
        from app.services.feasibility.aggregation_engine import aggregate_feasibility

        agg = aggregate_feasibility(total_revenue_won=0)
        assert agg["profit_rate_pct"] == 0.0


# ─────────────────────────────────────────────────────────────────────────────
# W4 리뷰 LOW-2) MC 삼각분포 반폭 √6 — 스프레드 회귀 앵커
# ─────────────────────────────────────────────────────────────────────────────
class TestMonteCarloTriangularHalfWidth:
    def test_triangular_spread_uses_sqrt6(self):
        """대칭 삼각분포 var=(b−a)²/24 → 반폭 h=std×√6(≈2.449).

        p95−p5 = 2h(1−√0.1) = 2×std×√6×0.68377 ≈ 3.349×std — 종전 ×2 반폭이면
        ≈2.735×std로 나와 실패한다(스프레드 ~18% 과소 회귀 앵커).
        """
        from app.services.feasibility.monte_carlo_engine import MCVariable, run_monte_carlo

        var = MCVariable(name="x", mean=100.0, std=10.0, distribution="triangular")
        result = run_monte_carlo(
            calculate_fn=lambda v: v["x"], variables=[var],
            n_simulations=40_000, seed=42,
        )
        spread = result["p95"] - result["p5"]
        assert spread == pytest.approx(3.349 * 10.0, rel=0.03), spread
