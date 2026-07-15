"""공통 수입 블록 — 분양/임대/조합원 수입 계산 위임.

★D1 면적 규약(2026-07-16 확정): ModuleInput.avg_area_pyeong = '전용면적 평'.
시장 시세(평당 분양가·임대료)는 공급면적 기준 관례이므로, 매출 면적은 여기서
공급평(전용 ÷ 전용률, unit_standards SSOT)으로 환산해 곱한다.
- 종전 공급평 생산처(build_module_input·precheck)는 전용평 생산으로 바뀌어
  (전용/전용률)=공급 라운드트립으로 매출 byte 무회귀.
- 전용평 생산처(프론트 수동폼 '평균 전용면적'·orchestration·baseline)는 종전
  전용×공급단가로 매출이 과소되던 결함이 함께 교정된다(의도된 정확화).
"""

from __future__ import annotations

from typing import Any

from app.services.feasibility.modules.base_module import ModuleInput
from app.services.feasibility.revenue_engine import (
    calculate_ancillary_revenue,
    calculate_rental_revenue,
    calculate_sale_revenue,
    calculate_total_revenue,
    calculate_union_revenue,
)
from app.services.feasibility.unit_standards import get_exclusive_ratio


def compute_revenue(inp: ModuleInput) -> dict[str, Any]:
    """표준 수입 계산 — 면적은 전용평 규약, 매출 곱은 공급평 환산(모듈 헤더 참조)."""
    sale = None
    union = None
    rental = None

    # ★D1-R1(단가 basis 계약): 면적과 단가의 기준을 일치시켜 곱한다.
    #   supply(기본) 단가 → 면적을 공급평(전용÷전용률)으로 환산.
    #   exclusive 단가(MOLIT 실거래 폐루프) → 전용평 그대로(환산 시 +33% 과대 회귀).
    eff_ratio = get_exclusive_ratio(inp.development_type)
    if (inp.price_basis or "supply") == "exclusive":
        revenue_area_pyeong = inp.avg_area_pyeong or 0.0
    else:
        revenue_area_pyeong = inp.avg_area_pyeong / eff_ratio if inp.avg_area_pyeong else 0.0

    sale_hh = int(inp.total_households * inp.sale_ratio)
    rental_hh = inp.total_households - sale_hh

    if sale_hh > 0:
        sale = calculate_sale_revenue(
            households=sale_hh,
            avg_area_pyeong=revenue_area_pyeong,
            avg_price_per_pyeong=inp.avg_sale_price_per_pyeong,
        )

    # 조합원 분양 (params에서) — union_avg_area_pyeong 도 전용평 규약(동일 환산).
    union_hh = inp.params.get("union_households", 0)
    if union_hh > 0:
        union_area = inp.params.get("union_avg_area_pyeong")
        union_supply = (
            (float(union_area) if (inp.price_basis or "supply") == "exclusive" else float(union_area) / eff_ratio)
            if union_area
            else revenue_area_pyeong
        )
        union = calculate_union_revenue(
            union_households=union_hh,
            avg_area_pyeong=union_supply,
            avg_allotment_price_per_pyeong=inp.params.get("union_price_per_pyeong", inp.avg_sale_price_per_pyeong),
        )

    if rental_hh > 0 and inp.sale_ratio < 1.0:
        rental = calculate_rental_revenue(
            rental_units=rental_hh,
            avg_area_pyeong=revenue_area_pyeong,  # 임대 단가도 동일 price_basis 계약
            avg_deposit_per_pyeong=inp.params.get("avg_deposit_per_pyeong", 0),
            avg_monthly_rent_per_pyeong=inp.params.get("avg_monthly_rent_per_pyeong", 0),
        )

    ancillary = calculate_ancillary_revenue(
        commercial_area_pyeong=inp.params.get("commercial_area_pyeong", 0),
        commercial_price_per_pyeong=inp.params.get("commercial_price_per_pyeong", 0),
        other_income_won=inp.params.get("other_income_won", 0),
    )

    return calculate_total_revenue(
        sale_revenue=sale,
        union_revenue=union,
        rental_revenue=rental,
        ancillary_revenue=ancillary,
    )
