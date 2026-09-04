"""D1(2026-07-16 제품결정) 회귀 테스트 — avg_area_pyeong '전용평' 규약 통일.

배경: 생산처별 의미 분열(공급평: build_module_input·precheck / 전용평: 프론트 수동폼·
orchestration·baseline)로 ①전용평 경로의 매출 과소(전용×공급단가) ②C01 부가세 면적
기준 오염(공급 전달 시 전용 61~85㎡ 과세 뒤집힘)이 있었다.

통일 계약:
1. avg_area_pyeong = 전용면적 평(전 생산처). 공급 생산처였던 build_module_input·precheck 전환.
2. 매출 곱은 revenue_block이 공급평(전용÷전용률, unit_standards SSOT) 환산 —
   종전 공급 생산 경로는 (전용/전용률)=공급 라운드트립으로 매출 byte 무회귀.
3. C01(전용 85㎡ 판정)은 전용 그대로 — 경로A에서 마침내 정확(P2 리뷰 P2-2 목표 달성).
"""

from __future__ import annotations

import pytest

from app.services.feasibility.feasibility_service_v2 import FeasibilityServiceV2
from app.services.feasibility.modules.base_module import ModuleInput
from app.services.feasibility.modules.common.cost_blocks import compute_taxes
from app.services.feasibility.modules.common.revenue_block import compute_revenue
from app.services.feasibility.unit_standards import (
    get_avg_exclusive_area_sqm,
    get_exclusive_ratio,
)


def _find_item(stage: dict, code: str) -> dict | None:
    return next((it for it in stage.get("items") or [] if it.get("code") == code), None)


class TestExclusiveConvention:
    def test_build_module_input_produces_exclusive_pyeong(self):
        """생산처 전환: avg_area_pyeong = 전용면적/3.3058 (종전 전용/전용률/3.3058=공급)."""
        svc = FeasibilityServiceV2()
        inp = svc.build_module_input(
            dev_type="M06", site_area_sqm=1000.0, max_far_pct=200.0,
            region="서울", address="", equity_won=None, official_price_per_sqm=3_000_000,
        )
        expected_exclusive = get_avg_exclusive_area_sqm("M06") / 3.305785
        assert inp.avg_area_pyeong == pytest.approx(expected_exclusive)

    def test_revenue_roundtrip_unchanged_for_converted_producer(self):
        """라운드트립 무회귀: 전용평 생산 + revenue 공급 환산 = 종전 공급평 직곱과 동일 매출."""
        eff = get_exclusive_ratio("M06")
        exclusive_py = 84.0 / 3.305785  # 전용 84㎡
        inp = ModuleInput(
            development_type="M06", total_households=100, sale_ratio=1.0,
            avg_area_pyeong=exclusive_py, avg_sale_price_per_pyeong=15_000_000,
        )
        rev = compute_revenue(inp)
        legacy_supply_py = (84.0 / eff) / 3.305785  # 종전 생산식(공급평)
        expected = int(100 * legacy_supply_py * 15_000_000)
        assert rev["total_revenue_won"] == pytest.approx(expected, abs=2)

    def test_manual_form_revenue_corrected(self):
        """전용평 생산처(수동폼 등) 매출 과소 교정: 전용 25평 입력 → 공급(25/전용률) 기준 매출."""
        inp = ModuleInput(
            development_type="M06", total_households=10, sale_ratio=1.0,
            avg_area_pyeong=25.0, avg_sale_price_per_pyeong=10_000_000,
        )
        rev = compute_revenue(inp)
        eff = get_exclusive_ratio("M06")
        assert rev["total_revenue_won"] == pytest.approx(int(10 * (25.0 / eff) * 10_000_000), abs=2)
        # 종전(전용 직곱)이었다면 2.5억×10=25억 — 교정 후 33.3억(전용률 0.75)
        assert rev["total_revenue_won"] > int(10 * 25.0 * 10_000_000)

    def test_c01_path_a_finally_correct(self):
        """C01(전용 85㎡): 전용 84㎡(=국민주택규모 이하) → 면세 — 경로A 교정 재개 완결.

        통일 전에는 build_module_input이 공급 112㎡를 넣어 과세로 뒤집혔다(P2 리뷰 P2-2).
        """
        inp = ModuleInput(
            development_type="M06", total_land_area_sqm=2_000.0,
            official_price_per_sqm=3_000_000, total_gfa_sqm=8_000.0,
            building_type="apartment", total_households=350,
            avg_area_pyeong=84.0 / 3.305785,  # 전용 84㎡(규약)
            sido_name="서울특별시",
        )
        result = compute_taxes(inp, 50_000_000_000)
        c01 = _find_item(result["sale"], "C01")
        assert c01 is not None and c01["amount_won"] == 0

    def test_exclusive_price_basis_no_conversion(self):
        """★D1-R1(리뷰 HIGH): MOLIT 실거래 폐루프(전용단가)는 price_basis="exclusive"로
        환산 없이 전용면적 그대로 곱한다 — supply 기본으로 ÷전용률하면 매출 +33% 과대 회귀."""
        inp = ModuleInput(
            development_type="M06", total_households=100, sale_ratio=1.0,
            avg_area_pyeong=84.0 / 3.305785,  # 전용 84㎡
            avg_sale_price_per_pyeong=20_000_000,  # 원/전용평(실거래)
            price_basis="exclusive",
        )
        rev = compute_revenue(inp)
        expected = int(100 * (84.0 / 3.305785) * 20_000_000)  # 전용×전용단가(무환산)
        assert rev["total_revenue_won"] == pytest.approx(expected, abs=2)

    def test_supply_basis_default_converts(self):
        """기본(supply) 단가는 공급 환산 유지 — 지역시세·수동폼 관례."""
        inp = ModuleInput(
            development_type="M06", total_households=100, sale_ratio=1.0,
            avg_area_pyeong=84.0 / 3.305785,
            avg_sale_price_per_pyeong=15_000_000,
        )
        eff = get_exclusive_ratio("M06")
        rev = compute_revenue(inp)
        assert rev["total_revenue_won"] == pytest.approx(
            int(100 * (84.0 / 3.305785 / eff) * 15_000_000), abs=2)

    def test_c01_large_exclusive_still_taxed(self):
        """전용 99㎡(85 초과)는 정당 과세 유지 — 면세 남발 아님."""
        inp = ModuleInput(
            development_type="M06", total_land_area_sqm=2_000.0,
            official_price_per_sqm=3_000_000, total_gfa_sqm=8_000.0,
            building_type="apartment", total_households=350,
            avg_area_pyeong=99.0 / 3.305785,
            sido_name="서울특별시",
        )
        result = compute_taxes(inp, 50_000_000_000)
        c01 = _find_item(result["sale"], "C01")
        assert c01 is not None and c01["amount_won"] > 0
