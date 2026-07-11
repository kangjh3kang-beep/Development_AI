"""분양단계 세금 엔진 — C01~C08 (8종).

C01: 부가가치세 (85m² 초과분)
C02: HUG 분양보증수수료
C03: 분양광고비 부담금
C04: 취득세 (분양자 부담, 시행사 기준)
C05: 등기비용 (분양자)
C06: 국민주택채권 (분양자)
C07: 기반시설부담금
C08: 에너지절약부담금
"""

from __future__ import annotations

from typing import Any

from app.services.tax.regional_tax_data import (
    HUG_GUARANTEE_RATES,
    VAT_EXEMPT_AREA_SQM,
    VAT_RATE,
)


def calculate_c01_vat(
    *,
    total_sale_amount_won: int,
    total_units: int,
    avg_area_sqm: float,
    exempt_area_sqm: float = VAT_EXEMPT_AREA_SQM,
) -> dict[str, Any]:
    """C01 부가가치세 (85m² 초과분에만 과세)."""
    if avg_area_sqm <= exempt_area_sqm:
        return {
            "code": "C01", "name": "부가가치세",
            "base_won": 0, "rate": VAT_RATE,
            "amount_won": 0,
            "detail": {"reason": f"평균 {avg_area_sqm}m² ≤ {exempt_area_sqm}m² 면세"},
        }

    # 초과분 비례 과세 (간이)
    taxable_ratio = (avg_area_sqm - exempt_area_sqm) / avg_area_sqm
    taxable_amount = int(total_sale_amount_won * taxable_ratio)
    amount = int(taxable_amount * VAT_RATE)

    return {
        "code": "C01", "name": "부가가치세",
        "base_won": taxable_amount, "rate": VAT_RATE,
        "amount_won": amount,
        "detail": {"taxable_ratio": round(taxable_ratio, 4)},
    }


def calculate_c02_hug_guarantee(
    *,
    total_sale_amount_won: int,
    building_type: str = "apartment",
) -> dict[str, Any]:
    """C02 HUG 분양보증수수료."""
    rate = HUG_GUARANTEE_RATES.get(building_type, HUG_GUARANTEE_RATES["apartment"])
    amount = int(total_sale_amount_won * rate)
    return {
        "code": "C02", "name": "HUG 분양보증수수료",
        "base_won": total_sale_amount_won, "rate": rate,
        "amount_won": amount,
    }


def calculate_c03_ad_charge(
    *,
    total_sale_amount_won: int,
    rate: float = 0.003,
) -> dict[str, Any]:
    """C03 분양광고비 부담금."""
    amount = int(total_sale_amount_won * rate)
    return {
        "code": "C03", "name": "분양광고비 부담금",
        "base_won": total_sale_amount_won, "rate": rate,
        "amount_won": amount,
    }


def calculate_c04_buyer_acquisition_tax(
    *,
    total_sale_amount_won: int,
    rate: float = 0.011,
) -> dict[str, Any]:
    """C04 취득세 (분양자 부담 — 시행사 대행 납부)."""
    amount = int(total_sale_amount_won * rate)
    return {
        "code": "C04", "name": "취득세(분양자)",
        "base_won": total_sale_amount_won, "rate": rate,
        "amount_won": amount,
    }


def calculate_c05_registration(
    *,
    total_sale_amount_won: int,
    rate: float = 0.002,
) -> dict[str, Any]:
    """C05 등기비용 (분양자)."""
    amount = int(total_sale_amount_won * rate)
    return {
        "code": "C05", "name": "등기비용(분양자)",
        "base_won": total_sale_amount_won, "rate": rate,
        "amount_won": amount,
    }


def calculate_c06_housing_bond_buyer(
    *,
    total_sale_amount_won: int,
    rate: float = 0.05,
    discount: float = 0.05,
) -> dict[str, Any]:
    """C06 국민주택채권 (분양자)."""
    bond = int(total_sale_amount_won * rate)
    cost = int(bond * discount)
    return {
        "code": "C06", "name": "국민주택채권(분양자)",
        "base_won": total_sale_amount_won, "rate": rate,
        "amount_won": cost,
    }


def calculate_c07_infrastructure_charge(
    *,
    total_gfa_sqm: float,
    in_infra_charge_zone: bool = False,
    standard_cost_per_sqm_won: int = 82_000,  # 국토부 고시 표준시설비용(2026 기준·고시 원문 재확인 권장)
    charge_rate: float = 0.20,                # 부담률 20% (국토계획법 §68 — 조례로 ±25% 가감)
) -> dict[str, Any]:
    """C07 기반시설부담금 — ★기반시설부담구역 지정 지역만 부과(국토계획법 §67~69).

    ★게이트: 부담구역으로 지정되지 않은 대다수 사업지는 미부과(0). 지정 시에만
    (표준시설비용 × 부담률) × 건축연면적으로 부과한다. 종전 구현은 게이트 없이 전 프로젝트에
    연면적 × 15,000원을 무조건 부과해, 부담구역 아닌 사업지의 총사업비를 구조적으로 과대계상했다.
    """
    if not in_infra_charge_zone:
        return {
            "code": "C07", "name": "기반시설부담금",
            "base_won": 0, "rate": 0,
            "amount_won": 0,
            "detail": {"reason": "기반시설부담구역 미지정 — 미부과 (국토계획법 §67~69)"},
        }
    per_sqm = round(standard_cost_per_sqm_won * charge_rate)  # 표준시설비용 × 부담률
    amount = int(total_gfa_sqm * per_sqm)
    return {
        "code": "C07", "name": "기반시설부담금",
        "base_won": int(total_gfa_sqm), "rate": per_sqm,
        "amount_won": amount,
        "detail": {"basis": f"표준시설비용 {standard_cost_per_sqm_won:,}원/㎡ × 부담률 {charge_rate:.0%} × 연면적"},
    }


def calculate_c08_energy_saving(
    *,
    total_gfa_sqm: float,
    per_sqm_won: int = 5_000,
) -> dict[str, Any]:
    """C08 에너지절약부담금."""
    amount = int(total_gfa_sqm * per_sqm_won)
    return {
        "code": "C08", "name": "에너지절약부담금",
        "base_won": int(total_gfa_sqm), "rate": per_sqm_won,
        "amount_won": amount,
    }


def calculate_all_sale_stage(
    *,
    total_sale_amount_won: int = 0,
    total_units: int = 0,
    avg_area_sqm: float = 85.0,
    total_gfa_sqm: float = 0,
    building_type: str = "apartment",
    in_infra_charge_zone: bool = False,
) -> dict[str, Any]:
    """C01~C08 분양단계 전체 일괄 계산.

    Returns:
        {'items': [...], 'total_won': int, 'applicable_count': int}
    """
    # 시행사 부담 항목
    developer_items = [
        calculate_c01_vat(
            total_sale_amount_won=total_sale_amount_won,
            total_units=total_units,
            avg_area_sqm=avg_area_sqm,
        ),
        calculate_c02_hug_guarantee(
            total_sale_amount_won=total_sale_amount_won,
            building_type=building_type,
        ),
        calculate_c03_ad_charge(total_sale_amount_won=total_sale_amount_won),
        calculate_c07_infrastructure_charge(
            total_gfa_sqm=total_gfa_sqm,
            in_infra_charge_zone=in_infra_charge_zone,
        ),
        calculate_c08_energy_saving(total_gfa_sqm=total_gfa_sqm),
    ]
    for it in developer_items:
        it["borne_by"] = "developer"

    # 분양자(수분양자) 부담 항목 — 참고 정보로 제공하되 시행사 사업비 총액에서 제외
    # (포함 시 분양가의 약 1.55%가 사업비로 과대계상됨 — 2026-06 리뷰 M-6)
    buyer_items = [
        calculate_c04_buyer_acquisition_tax(total_sale_amount_won=total_sale_amount_won),
        calculate_c05_registration(total_sale_amount_won=total_sale_amount_won),
        calculate_c06_housing_bond_buyer(total_sale_amount_won=total_sale_amount_won),
    ]
    for it in buyer_items:
        it["borne_by"] = "buyer"

    items = developer_items[:3] + buyer_items + developer_items[3:]  # 기존 C01~C08 순서 유지
    total = sum(it["amount_won"] for it in developer_items)
    buyer_total = sum(it["amount_won"] for it in buyer_items)
    return {
        "stage": "sale",
        "items": items,
        "total_won": total,  # 시행사 부담만 (수지분석 사업비 합산용)
        "buyer_borne_total_won": buyer_total,  # 분양자 부담 (참고)
        "applicable_count": len(items),
    }
