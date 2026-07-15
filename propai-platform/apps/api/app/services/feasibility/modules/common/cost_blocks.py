"""공통 비용 블록 — 토지비/공사비/금융비/기타비 계산 위임."""

from __future__ import annotations

from typing import Any

from app.services.feasibility.construction_cost_engine import calculate_total_construction_cost
from app.services.feasibility.finance_cost_engine import calculate_total_finance_cost
from app.services.feasibility.land_cost_engine import calculate_total_land_cost
from app.services.feasibility.modules.base_module import ModuleInput
from app.services.tax.integrated_tax_engine import calculate_all_taxes


def compute_land_cost(inp: ModuleInput) -> dict[str, Any]:
    """표준 토지비 계산.

    취득세·전용부담금은 통합 세금 엔진(compute_taxes → A01~A03, A08/A09)이
    grand_total_won에 계상하므로 여기서는 제외한다 (이중계상 방지).
    """
    return calculate_total_land_cost(
        total_area_sqm=inp.total_land_area_sqm,
        official_price_per_sqm=inp.official_price_per_sqm,
        price_multiplier=inp.price_multiplier,
        land_category=inp.land_category,
        house_count=inp.house_count,
        is_adjusted_area=inp.is_adjusted_area,
        compensation_won=inp.params.get("compensation_won", 0),
        include_taxes_and_fees=False,
    )


def compute_construction_cost(inp: ModuleInput) -> dict[str, Any]:
    """표준 공사비 계산.

    공사비 정밀 분석 결과를 params.construction_cost_override_won 로 주입하면
    수지·사업성(ROI)이 그 공사비를 그대로 사용한다(3자 단일 데이터원 정합).
    """
    override = inp.params.get("construction_cost_override_won")
    if override and float(override) > 0:
        total = int(float(override))
        return {
            "direct": {"total_direct_cost_won": total},
            "indirect": {"total_indirect_cost_won": 0},
            "total_construction_cost_won": total,
            "source": "cost_analysis_override",
        }
    return calculate_total_construction_cost(
        total_gfa_sqm=inp.total_gfa_sqm,
        building_type=inp.building_type,
        unit_cost_per_sqm=inp.params.get("unit_cost_per_sqm"),
        cost_index_factor=inp.params.get("cost_index_factor", 1.0),
    )


def compute_finance_cost(inp: ModuleInput) -> dict[str, Any]:
    """표준 금융비 계산."""
    return calculate_total_finance_cost(
        bridge_amount_won=inp.bridge_amount_won,
        bridge_rate=inp.bridge_rate,
        bridge_months=inp.bridge_months,
        pf_amount_won=inp.pf_amount_won,
        pf_rate=inp.pf_rate,
        pf_months=inp.pf_months,
        midpay_amount_won=inp.midpay_amount_won,
        midpay_rate=inp.midpay_rate,
        midpay_months=inp.midpay_months,
    )


def compute_other_cost(inp: ModuleInput) -> dict[str, Any]:
    """기타경비 계산."""
    marketing = inp.params.get("marketing_cost_won", 0)
    management = inp.params.get("management_cost_won", 0)
    reserve = inp.params.get("reserve_cost_won", 0)
    return {
        "marketing_won": marketing,
        "management_won": management,
        "reserve_won": reserve,
        "total_other_cost_won": marketing + management + reserve,
    }


def _param_int(inp: ModuleInput, key: str) -> int:
    """params의 수치 입력을 int로 안전 변환(문자열 숫자 허용, 비수치·음수는 0)."""
    try:
        value = int(float(inp.params.get(key) or 0))
    except (TypeError, ValueError):
        return 0
    return max(0, value)


def compute_taxes(
    inp: ModuleInput,
    total_sale_won: int = 0,
    *,
    development_cost_won: int = 0,
) -> dict[str, Any]:
    """세금 일괄 계산.

    ★부담금 상시-0 봉합: A10 개발부담금·C07 기반시설부담금은 엔진에 구현돼 있었으나
    이 배선이 인자를 전달하지 않아 어떤 경로에서도 수지에 기여할 수 없었다(상시 0원).
    - A10: 종료시점 지가(end_land_value_won)는 감정 필요값이라 자동 추정하지 않는다(무날조)
      — params 제공 시에만 활성. 개시지가 기본값=토지 매입가(권위 출처),
      개발비용 기본값=모듈이 계산한 공사비(development_cost_won 인자).
    - C07: 기반시설부담구역 지정 여부(params.in_infra_charge_zone) 게이트를 전달.
    모든 채널의 기본값은 기존 결과와 완전 동일(미제공 시 무회귀).
    """
    purchase_won = int(inp.total_land_area_sqm * inp.official_price_per_sqm * inp.price_multiplier)
    end_land_value_won = _param_int(inp, "end_land_value_won")
    return calculate_all_taxes(
        purchase_won=purchase_won,
        land_category=inp.land_category,
        house_count=inp.house_count,
        is_adjusted=inp.is_adjusted_area,
        area_sqm=inp.total_land_area_sqm,
        official_price_per_sqm=inp.official_price_per_sqm,
        end_land_value_won=end_land_value_won,
        start_land_value_won=_param_int(inp, "start_land_value_won") or purchase_won,
        development_cost_won=_param_int(inp, "development_cost_won") or max(0, development_cost_won),
        project_years=max(0.5, (inp.project_months or 36) / 12.0),
        region_type=inp.region_type,
        sido_name=inp.sido_name,
        sigungu_name=inp.sigungu_name,
        total_households=inp.total_households,
        total_sale_amount_won=total_sale_won,
        total_gfa_sqm=inp.total_gfa_sqm,
        building_type=inp.building_type,
        total_units=inp.total_households,
        avg_area_sqm=inp.avg_area_pyeong * 3.305785 if inp.avg_area_pyeong else 85.0,
        in_infra_charge_zone=bool(inp.params.get("in_infra_charge_zone") or False),
    )
