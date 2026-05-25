"""수입 산정 엔진 — 분양/임대/복합/조합원배분 수입 계산.

순수 함수형 설계: DB 의존 없음, 입력 dict → 출력 dict.
참조값: 오산 내삼미동 M04 총수입 11,812억
  - 조합원분양 5,278억, 일반분양 5,684억, 상가 750억, 부대수입 100억
"""

from __future__ import annotations

from typing import Any

# 평 → m² 변환 상수
PYEONG_TO_SQM = 3.305785


def calculate_sale_revenue(
    *,
    households: int,
    avg_area_pyeong: float,
    avg_price_per_pyeong: float,
    sale_ratio: float = 1.0,
) -> dict[str, Any]:
    """일반분양 수입 계산.

    Args:
        households: 총 세대수
        avg_area_pyeong: 평균 전용면적 (평)
        avg_price_per_pyeong: 평균 분양가 (원/평)
        sale_ratio: 분양 비율 (0~1)

    Returns:
        {'sale_households', 'total_area_pyeong', 'total_revenue_won', 'detail'}
    """
    sale_hh = int(households * sale_ratio)
    total_area = sale_hh * avg_area_pyeong
    total_revenue = int(total_area * avg_price_per_pyeong)

    return {
        "sale_households": sale_hh,
        "total_area_pyeong": round(total_area, 2),
        "total_revenue_won": total_revenue,
        "detail": {
            "avg_area_pyeong": avg_area_pyeong,
            "avg_price_per_pyeong": avg_price_per_pyeong,
        },
    }


def calculate_union_revenue(
    *,
    union_households: int,
    avg_area_pyeong: float,
    avg_allotment_price_per_pyeong: float,
) -> dict[str, Any]:
    """조합원분양 수입 계산 (M01/M02/M04 등).

    Args:
        union_households: 조합원 세대수
        avg_area_pyeong: 평균 배정면적 (평)
        avg_allotment_price_per_pyeong: 조합원 분양가 (원/평)

    Returns:
        {'union_households', 'total_area_pyeong', 'total_revenue_won'}
    """
    total_area = union_households * avg_area_pyeong
    total_revenue = int(total_area * avg_allotment_price_per_pyeong)

    return {
        "union_households": union_households,
        "total_area_pyeong": round(total_area, 2),
        "total_revenue_won": total_revenue,
    }


def calculate_rental_revenue(
    *,
    rental_units: int,
    avg_area_pyeong: float,
    avg_deposit_per_pyeong: float = 0,
    avg_monthly_rent_per_pyeong: float = 0,
    cap_rate: float = 0.05,
) -> dict[str, Any]:
    """임대수입 계산 (보증금 + 월세의 자본환원가치).

    Args:
        rental_units: 임대 세대/호수
        avg_area_pyeong: 평균 면적 (평)
        avg_deposit_per_pyeong: 보증금 (원/평)
        avg_monthly_rent_per_pyeong: 월세 (원/평)
        cap_rate: 자본환원율

    Returns:
        {'rental_units', 'total_deposit_won', 'annual_rent_won', 'capitalized_value_won'}
    """
    total_area = rental_units * avg_area_pyeong
    total_deposit = int(total_area * avg_deposit_per_pyeong)
    annual_rent = int(total_area * avg_monthly_rent_per_pyeong * 12)
    capitalized = int(annual_rent / cap_rate) if cap_rate > 0 else 0

    return {
        "rental_units": rental_units,
        "total_area_pyeong": round(total_area, 2),
        "total_deposit_won": total_deposit,
        "annual_rent_won": annual_rent,
        "capitalized_value_won": capitalized,
        "total_revenue_won": total_deposit + capitalized,
    }


def calculate_ancillary_revenue(
    *,
    commercial_area_pyeong: float = 0,
    commercial_price_per_pyeong: float = 0,
    other_income_won: int = 0,
) -> dict[str, Any]:
    """부대수입 계산 (상가분양, 기타수입).

    Returns:
        {'commercial_revenue_won', 'other_income_won', 'total_revenue_won'}
    """
    commercial = int(commercial_area_pyeong * commercial_price_per_pyeong)
    return {
        "commercial_revenue_won": commercial,
        "other_income_won": other_income_won,
        "total_revenue_won": commercial + other_income_won,
    }


def calculate_total_revenue(
    *,
    sale_revenue: dict[str, Any] | None = None,
    union_revenue: dict[str, Any] | None = None,
    rental_revenue: dict[str, Any] | None = None,
    ancillary_revenue: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """총수입 합산.

    Returns:
        {'sale', 'union', 'rental', 'ancillary', 'total_revenue_won', 'breakdown_won'}
    """
    sale_won = (sale_revenue or {}).get("total_revenue_won", 0)
    union_won = (union_revenue or {}).get("total_revenue_won", 0)
    rental_won = (rental_revenue or {}).get("total_revenue_won", 0)
    ancillary_won = (ancillary_revenue or {}).get("total_revenue_won", 0)

    total = sale_won + union_won + rental_won + ancillary_won

    return {
        "sale": sale_revenue,
        "union": union_revenue,
        "rental": rental_revenue,
        "ancillary": ancillary_revenue,
        "total_revenue_won": total,
        "breakdown_won": {
            "sale": sale_won,
            "union": union_won,
            "rental": rental_won,
            "ancillary": ancillary_won,
        },
    }
