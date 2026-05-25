"""통합 세금 엔진 — 38종 4단계 일괄 오케스트레이션.

취득(A01~A10) + 공사(B01~B08) + 분양(C01~C08) + 양도(D01~D06) = 32종 기본
+ 조건부 6종 = 38종 완전 자동화.
"""

from __future__ import annotations

from typing import Any

from app.services.tax.acquisition_stage_engine import calculate_all_acquisition_stage
from app.services.tax.utility_stage_engine import calculate_all_utility_stage
from app.services.tax.sale_stage_engine import calculate_all_sale_stage
from app.services.tax.disposal_stage_engine import calculate_all_disposal_stage


def calculate_all_taxes(
    *,
    # 공통
    purchase_won: int = 0,
    land_category: str = "land",
    house_count: int = 0,
    is_adjusted: bool = False,
    area_sqm: float = 0,
    official_price_per_sqm: float = 0,
    forest_type: str = "semi_conservation",
    # 개발부담금
    end_land_value_won: int = 0,
    start_land_value_won: int = 0,
    development_cost_won: int = 0,
    project_years: float = 3.0,
    region_type: str = "capital_area",
    # 공사단계
    sido_name: str = "",
    sigungu_name: str = "",
    total_households: int = 0,
    total_sale_amount_won: int = 0,
    total_gfa_sqm: float = 0,
    building_type: str = "apartment",
    # 분양단계
    total_units: int = 0,
    avg_area_sqm: float = 85.0,
    # 양도단계
    gain_10k_won: float = 0,
    gain_won: int = 0,
    holding_years: int = 0,
    is_residential: bool = True,
    is_corporate: bool = False,
    excess_gain_won: int = 0,
    assessed_value_won: int = 0,
) -> dict[str, Any]:
    """38종 세금 4단계 일괄 계산.

    Returns:
        {
            'acquisition': {...},
            'construction': {...},
            'sale': {...},
            'disposal': {...},
            'grand_total_won': int,
            'total_items_count': int,
            'summary_by_stage': {...},
        }
    """
    acquisition = calculate_all_acquisition_stage(
        purchase_won=purchase_won,
        land_category=land_category,
        house_count=house_count,
        is_adjusted=is_adjusted,
        area_sqm=area_sqm,
        official_price_per_sqm=official_price_per_sqm,
        forest_type=forest_type,
        end_land_value_won=end_land_value_won,
        start_land_value_won=start_land_value_won,
        development_cost_won=development_cost_won,
        project_years=project_years,
        region_type=region_type,
    )

    construction = calculate_all_utility_stage(
        sido_name=sido_name,
        sigungu_name=sigungu_name,
        total_households=total_households,
        total_sale_amount_won=total_sale_amount_won,
        total_gfa_sqm=total_gfa_sqm,
        building_type=building_type,
    )

    sale = calculate_all_sale_stage(
        total_sale_amount_won=total_sale_amount_won,
        total_units=total_units,
        avg_area_sqm=avg_area_sqm,
        total_gfa_sqm=total_gfa_sqm,
        building_type=building_type,
    )

    disposal = calculate_all_disposal_stage(
        gain_10k_won=gain_10k_won,
        gain_won=gain_won,
        holding_years=holding_years,
        is_residential=is_residential,
        is_corporate=is_corporate,
        excess_gain_won=excess_gain_won,
        assessed_value_won=assessed_value_won,
    )

    grand_total = (
        acquisition["total_won"]
        + construction["total_won"]
        + sale["total_won"]
        + disposal["total_won"]
    )

    total_items = (
        acquisition["applicable_count"]
        + construction["applicable_count"]
        + sale["applicable_count"]
        + disposal["applicable_count"]
    )

    return {
        "acquisition": acquisition,
        "construction": construction,
        "sale": sale,
        "disposal": disposal,
        "grand_total_won": grand_total,
        "total_items_count": total_items,
        "summary_by_stage": {
            "acquisition": acquisition["total_won"],
            "construction": construction["total_won"],
            "sale": sale["total_won"],
            "disposal": disposal["total_won"],
        },
    }


def get_applicable_tax_codes(
    *,
    development_type: str,
    land_category: str = "land",
) -> list[str]:
    """개발유형+지목별 적용 가능한 세금 코드 목록.

    Returns:
        ['A01', 'A02', ...] 적용 가능 코드 리스트
    """
    # 기본 공통 코드 (항상 적용)
    base_codes = ["A01", "A02", "A03", "A04", "A05", "A06", "A07"]

    # 지목별 조건부
    if land_category == "farmland":
        base_codes.append("A08")
    elif land_category == "forest":
        base_codes.append("A09")

    # 개발부담금 (대부분 적용)
    base_codes.append("A10")

    # 공사단계 (항상)
    base_codes.extend(["B01", "B02", "B03", "B04", "B05", "B06", "B07", "B08"])

    # 분양단계
    base_codes.extend(["C01", "C02", "C03", "C04", "C05", "C06", "C07", "C08"])

    # 양도단계 (기본)
    base_codes.extend(["D01", "D03"])

    # 개발유형별 특화
    if development_type == "M02":  # 재건축
        base_codes.append("D05")  # 초과이익환수

    # 보유세
    base_codes.append("D06")

    return sorted(set(base_codes))
