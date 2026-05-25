"""토지비 산정 엔진 — 매입비/보상비/취득세 자동 계산.

순수 함수형 설계: DB 의존 없음.
지목별 취득세 자동 적용 (regional_tax_data 참조).
"""

from __future__ import annotations

from typing import Any

from app.services.tax.regional_tax_data import (
    get_acquisition_tax_rates,
    FARMLAND_CONVERSION_RATE,
    FARMLAND_CONVERSION_MAX_PER_M2,
    FOREST_CONVERSION_RATES,
)

PYEONG_TO_SQM = 3.305785


def calculate_land_purchase_cost(
    *,
    total_area_sqm: float,
    official_price_per_sqm: float,
    price_multiplier: float = 1.0,
) -> dict[str, Any]:
    """토지 매입비 계산.

    Args:
        total_area_sqm: 총 토지면적 (m²)
        official_price_per_sqm: 공시지가 (원/m²)
        price_multiplier: 감정가/공시지가 배율 (보통 1.0~1.3)

    Returns:
        {'total_area_sqm', 'unit_price_won', 'total_purchase_won'}
    """
    unit_price = official_price_per_sqm * price_multiplier
    total = int(total_area_sqm * unit_price)

    return {
        "total_area_sqm": round(total_area_sqm, 2),
        "unit_price_won": int(unit_price),
        "total_purchase_won": total,
    }


def calculate_acquisition_tax(
    *,
    purchase_amount_won: int,
    land_category: str = "land",
    house_count: int = 0,
    is_adjusted_area: bool = False,
) -> dict[str, Any]:
    """취득세 자동 계산 (지목/주택수/조정지역에 따라).

    Returns:
        {'rates': {...}, 'tax_amount_won', 'detail': {...}}
    """
    rates = get_acquisition_tax_rates(land_category, house_count, is_adjusted_area)
    tax_amount = int(purchase_amount_won * rates["total_rate"])

    return {
        "rates": rates,
        "base_amount_won": purchase_amount_won,
        "tax_amount_won": tax_amount,
        "detail": {
            "base_tax": int(purchase_amount_won * rates["base_rate"]),
            "surcharge_tax": int(purchase_amount_won * rates["surcharge_rate"]),
            "education_tax": int(purchase_amount_won * rates["education_rate"]),
            "rural_tax": int(purchase_amount_won * rates["rural_rate"]),
        },
    }


def calculate_farmland_conversion_fee(
    *,
    area_sqm: float,
    official_price_per_sqm: float,
) -> dict[str, Any]:
    """농지전용부담금 계산 (농지→대지 전용 시).

    Returns:
        {'area_sqm', 'fee_per_sqm', 'total_fee_won'}
    """
    fee_per_sqm = min(
        official_price_per_sqm * FARMLAND_CONVERSION_RATE,
        FARMLAND_CONVERSION_MAX_PER_M2,
    )
    total = int(area_sqm * fee_per_sqm)

    return {
        "area_sqm": round(area_sqm, 2),
        "fee_per_sqm": int(fee_per_sqm),
        "total_fee_won": total,
    }


def calculate_forest_conversion_fee(
    *,
    area_sqm: float,
    forest_type: str = "semi_conservation",
) -> dict[str, Any]:
    """산림전용부담금(산지조성비) 계산.

    Args:
        forest_type: 'conservation', 'semi_conservation', 'temporary'

    Returns:
        {'area_sqm', 'rate_per_sqm', 'total_fee_won'}
    """
    rate = FOREST_CONVERSION_RATES.get(forest_type, FOREST_CONVERSION_RATES["semi_conservation"])
    total = int(area_sqm * rate)

    return {
        "area_sqm": round(area_sqm, 2),
        "rate_per_sqm": rate,
        "total_fee_won": total,
    }


def calculate_total_land_cost(
    *,
    total_area_sqm: float,
    official_price_per_sqm: float,
    price_multiplier: float = 1.0,
    land_category: str = "land",
    house_count: int = 0,
    is_adjusted_area: bool = False,
    compensation_won: int = 0,
) -> dict[str, Any]:
    """토지비 총합 계산 (매입비 + 취득세 + 전용부담금 + 보상비).

    Returns:
        {'purchase', 'acquisition_tax', 'conversion_fee', 'compensation_won', 'total_land_cost_won'}
    """
    purchase = calculate_land_purchase_cost(
        total_area_sqm=total_area_sqm,
        official_price_per_sqm=official_price_per_sqm,
        price_multiplier=price_multiplier,
    )

    acq_tax = calculate_acquisition_tax(
        purchase_amount_won=purchase["total_purchase_won"],
        land_category=land_category,
        house_count=house_count,
        is_adjusted_area=is_adjusted_area,
    )

    # 전용부담금 (지목에 따라)
    conversion_fee: dict[str, Any] = {"total_fee_won": 0}
    if land_category == "farmland":
        conversion_fee = calculate_farmland_conversion_fee(
            area_sqm=total_area_sqm,
            official_price_per_sqm=official_price_per_sqm,
        )
    elif land_category == "forest":
        conversion_fee = calculate_forest_conversion_fee(
            area_sqm=total_area_sqm,
        )

    total = (
        purchase["total_purchase_won"]
        + acq_tax["tax_amount_won"]
        + conversion_fee["total_fee_won"]
        + compensation_won
    )

    return {
        "purchase": purchase,
        "acquisition_tax": acq_tax,
        "conversion_fee": conversion_fee,
        "compensation_won": compensation_won,
        "total_land_cost_won": total,
    }
