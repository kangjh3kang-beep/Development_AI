"""취득단계 세금 엔진 — A01~A10 (10종).

A01: 취득세 (지목/주택수/조정지역별)
A02: 지방교육세
A03: 농어촌특별세
A04: 인지세
A05: 등록면허세
A06: 국민주택채권 매입
A07: 법무사/중개수수료
A08: 농지전용부담금
A09: 산림전용부담금(산지조성비)
A10: 개발부담금
"""

from __future__ import annotations

from typing import Any

from app.services.tax.regional_tax_data import (
    get_acquisition_tax_rates,
    FARMLAND_CONVERSION_RATE,
    FARMLAND_CONVERSION_MAX_PER_M2,
    FOREST_CONVERSION_RATES,
    DEVELOPMENT_CHARGE_RATES,
    NORMAL_LAND_RISE_RATE,
)


def calculate_a01_acquisition_tax(
    purchase_won: int,
    land_category: str = "land",
    house_count: int = 0,
    is_adjusted: bool = False,
) -> dict[str, Any]:
    """A01 취득세."""
    rates = get_acquisition_tax_rates(land_category, house_count, is_adjusted)
    amount = int(purchase_won * rates["base_rate"])
    return {
        "code": "A01", "name": "취득세",
        "base_won": purchase_won, "rate": rates["base_rate"],
        "amount_won": amount,
    }


def calculate_a02_education_tax(
    purchase_won: int,
    land_category: str = "land",
    house_count: int = 0,
    is_adjusted: bool = False,
) -> dict[str, Any]:
    """A02 지방교육세."""
    rates = get_acquisition_tax_rates(land_category, house_count, is_adjusted)
    amount = int(purchase_won * rates["education_rate"])
    return {
        "code": "A02", "name": "지방교육세",
        "base_won": purchase_won, "rate": rates["education_rate"],
        "amount_won": amount,
    }


def calculate_a03_rural_tax(
    purchase_won: int,
    land_category: str = "land",
    house_count: int = 0,
    is_adjusted: bool = False,
) -> dict[str, Any]:
    """A03 농어촌특별세."""
    rates = get_acquisition_tax_rates(land_category, house_count, is_adjusted)
    amount = int(purchase_won * rates["rural_rate"])
    return {
        "code": "A03", "name": "농어촌특별세",
        "base_won": purchase_won, "rate": rates["rural_rate"],
        "amount_won": amount,
    }


def calculate_a04_stamp_tax(purchase_won: int) -> dict[str, Any]:
    """A04 인지세 (누진세율)."""
    if purchase_won <= 100_000_000:
        amount = 0
    elif purchase_won <= 1_000_000_000:
        amount = 150_000
    elif purchase_won <= 10_000_000_000:
        amount = 350_000
    else:
        amount = 350_000  # 상한
    return {
        "code": "A04", "name": "인지세",
        "base_won": purchase_won, "rate": None,
        "amount_won": amount,
    }


def calculate_a05_registration_tax(purchase_won: int, rate: float = 0.02) -> dict[str, Any]:
    """A05 등록면허세."""
    amount = int(purchase_won * rate)
    return {
        "code": "A05", "name": "등록면허세",
        "base_won": purchase_won, "rate": rate,
        "amount_won": amount,
    }


def calculate_a06_housing_bond(purchase_won: int, rate: float = 0.05, discount: float = 0.05) -> dict[str, Any]:
    """A06 국민주택채권 매입 (매입 후 할인매각 비용)."""
    bond_amount = int(purchase_won * rate)
    cost = int(bond_amount * discount)
    return {
        "code": "A06", "name": "국민주택채권",
        "base_won": purchase_won, "rate": rate,
        "amount_won": cost,
        "detail": {"bond_amount": bond_amount, "discount_rate": discount},
    }


def calculate_a07_legal_fees(purchase_won: int, fee_rate: float = 0.003) -> dict[str, Any]:
    """A07 법무사/중개수수료."""
    amount = int(purchase_won * fee_rate)
    return {
        "code": "A07", "name": "법무사/중개수수료",
        "base_won": purchase_won, "rate": fee_rate,
        "amount_won": amount,
    }


def calculate_a08_farmland_conversion(
    area_sqm: float,
    official_price_per_sqm: float,
) -> dict[str, Any]:
    """A08 농지전용부담금."""
    fee_per_sqm = min(
        official_price_per_sqm * FARMLAND_CONVERSION_RATE,
        FARMLAND_CONVERSION_MAX_PER_M2,
    )
    amount = int(area_sqm * fee_per_sqm)
    return {
        "code": "A08", "name": "농지전용부담금",
        "base_won": int(area_sqm * official_price_per_sqm),
        "rate": FARMLAND_CONVERSION_RATE,
        "amount_won": amount,
    }


def calculate_a09_forest_conversion(
    area_sqm: float,
    forest_type: str = "semi_conservation",
) -> dict[str, Any]:
    """A09 산림전용부담금(산지조성비)."""
    rate_per_sqm = FOREST_CONVERSION_RATES.get(forest_type, FOREST_CONVERSION_RATES["semi_conservation"])
    amount = int(area_sqm * rate_per_sqm)
    return {
        "code": "A09", "name": "산림전용부담금",
        "base_won": int(area_sqm * rate_per_sqm),
        "rate": rate_per_sqm,
        "amount_won": amount,
    }


def calculate_a10_development_charge(
    *,
    end_land_value_won: int,
    start_land_value_won: int,
    development_cost_won: int,
    project_years: float = 3.0,
    region_type: str = "capital_area",
) -> dict[str, Any]:
    """A10 개발부담금 — 지가상승분 기반 간이산정 (오류#4 수정).

    개발부담금 = (종료시점 지가 - 개시시점 지가 - 정상지가상승분 - 개발비용) × 부과율
    """
    normal_rise = int(start_land_value_won * NORMAL_LAND_RISE_RATE * project_years)
    taxable = max(0, end_land_value_won - start_land_value_won - normal_rise - development_cost_won)
    charge_rate = DEVELOPMENT_CHARGE_RATES.get(region_type, DEVELOPMENT_CHARGE_RATES["province"])
    amount = int(taxable * charge_rate)

    return {
        "code": "A10", "name": "개발부담금",
        "base_won": taxable,
        "rate": charge_rate,
        "amount_won": amount,
        "detail": {
            "end_value": end_land_value_won,
            "start_value": start_land_value_won,
            "normal_rise": normal_rise,
            "dev_cost": development_cost_won,
        },
    }


def calculate_all_acquisition_stage(
    *,
    purchase_won: int,
    land_category: str = "land",
    house_count: int = 0,
    is_adjusted: bool = False,
    area_sqm: float = 0,
    official_price_per_sqm: float = 0,
    forest_type: str = "semi_conservation",
    end_land_value_won: int = 0,
    start_land_value_won: int = 0,
    development_cost_won: int = 0,
    project_years: float = 3.0,
    region_type: str = "capital_area",
) -> dict[str, Any]:
    """A01~A10 취득단계 전체 일괄 계산.

    Returns:
        {'items': [...], 'total_won': int, 'applicable_count': int}
    """
    items = [
        calculate_a01_acquisition_tax(purchase_won, land_category, house_count, is_adjusted),
        calculate_a02_education_tax(purchase_won, land_category, house_count, is_adjusted),
        calculate_a03_rural_tax(purchase_won, land_category, house_count, is_adjusted),
        calculate_a04_stamp_tax(purchase_won),
        calculate_a05_registration_tax(purchase_won),
        calculate_a06_housing_bond(purchase_won),
        calculate_a07_legal_fees(purchase_won),
    ]

    # 조건부 항목
    if land_category == "farmland" and area_sqm > 0:
        items.append(calculate_a08_farmland_conversion(area_sqm, official_price_per_sqm))

    if land_category == "forest" and area_sqm > 0:
        items.append(calculate_a09_forest_conversion(area_sqm, forest_type))

    if end_land_value_won > 0:
        items.append(calculate_a10_development_charge(
            end_land_value_won=end_land_value_won,
            start_land_value_won=start_land_value_won,
            development_cost_won=development_cost_won,
            project_years=project_years,
            region_type=region_type,
        ))

    total = sum(it["amount_won"] for it in items)
    return {
        "stage": "acquisition",
        "items": items,
        "total_won": total,
        "applicable_count": len(items),
    }
