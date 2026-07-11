"""공사단계 세금 엔진 — B01~B08 (8종).

B01: 광역교통부담금
B02: 학교용지부담금
B03: 상수도 원인자부담금
B04: 하수도 원인자부담금
B05: 전기인입부담금
B06: 도시가스인입부담금
B07: 통신인입부담금
B08: 소방시설부담금
"""

from __future__ import annotations

from typing import Any

from app.services.tax.regional_tax_data import (
    SCHOOL_SITE_CHARGE_RATE,
    SCHOOL_SITE_MIN_HOUSEHOLDS,
    SEWAGE_CHARGES_WON,
    WATER_SUPPLY_CHARGES_WON,
    get_metro_transport_charge,
    get_utility_charge,
)


def calculate_b01_metro_transport(
    *,
    sido_name: str,
    sigungu_name: str = "",
    total_gfa_sqm: float = 0,
    building_type: str = "apartment",
    exclusive_area_sqm: float | None = None,
    standard_build_cost_won_per_sqm: int | None = None,
    total_households: int = 0,  # 하위호환(미사용 — 실산식은 연면적 기반)
) -> dict[str, Any]:
    """B01 광역교통시설부담금 = 표준건축비 × 부과율 × 건축연면적(대도시권광역교통관리법 §7의2).

    ★실산식(연면적 기반)으로 교체 — 이전 '만원/세대 정액표'는 법정식과 달라 날조라 폐기(무목업 수정).
    표준건축비 고시값 미설정 시 amount_won=0 + detail.confidence=unavailable(무목업·정직). 비대도시권=0.
    """
    result = get_metro_transport_charge(
        sido_name=sido_name, gfa_sqm=total_gfa_sqm, building_type=building_type,
        exclusive_area_sqm=exclusive_area_sqm,
        standard_build_cost_won_per_sqm=standard_build_cost_won_per_sqm,
    )
    amt = result.get("amount_won")
    detail = {k: v for k, v in result.items() if k != "amount_won"}
    detail["amount_computable"] = amt is not None
    return {
        "code": "B01", "name": "광역교통시설부담금",
        "base_won": int(total_gfa_sqm),
        "rate": result.get("rate"),
        "amount_won": amt if amt is not None else 0,
        "detail": detail,
    }


def calculate_b02_school_site(
    *,
    total_sale_amount_won: int,
    total_households: int,
) -> dict[str, Any]:
    """B02 학교용지부담금 (300세대 이상 의무)."""
    if total_households < SCHOOL_SITE_MIN_HOUSEHOLDS:
        return {
            "code": "B02", "name": "학교용지부담금",
            "base_won": 0, "rate": SCHOOL_SITE_CHARGE_RATE,
            "amount_won": 0,
            "detail": {"reason": f"{total_households}세대 < {SCHOOL_SITE_MIN_HOUSEHOLDS}세대 면제"},
        }
    amount = int(total_sale_amount_won * SCHOOL_SITE_CHARGE_RATE)
    return {
        "code": "B02", "name": "학교용지부담금",
        "base_won": total_sale_amount_won, "rate": SCHOOL_SITE_CHARGE_RATE,
        "amount_won": amount,
    }


def calculate_b03_water_supply(
    *,
    sido_name: str,
    sigungu_name: str,
    total_households: int,
) -> dict[str, Any]:
    """B03 상수도 원인자부담금."""
    per_hh = get_utility_charge(WATER_SUPPLY_CHARGES_WON, sido_name, sigungu_name)
    if per_hh is None:  # ★조례 미등록 — 전국 단일값 없음(수도법 §71). 지어내지 않고 정직 표기.
        return {
            "code": "B03", "name": "상수도 원인자부담금",
            "base_won": total_households, "rate": None, "amount_won": 0,
            "detail": {"confidence": "unavailable",
                       "reason": "지자체 조례 단가 미등록 — 관할 조례 확인 필요(수도법 §71·전국 단일값 없음)"},
        }
    amount = per_hh * total_households
    return {
        "code": "B03", "name": "상수도 원인자부담금",
        "base_won": total_households, "rate": per_hh,
        "amount_won": amount,
        "detail": {"per_hh_won": per_hh, "confidence": "regional"},
    }


def calculate_b04_sewage(
    *,
    sido_name: str,
    sigungu_name: str,
    total_households: int,
) -> dict[str, Any]:
    """B04 하수도 원인자부담금."""
    per_hh = get_utility_charge(SEWAGE_CHARGES_WON, sido_name, sigungu_name)
    if per_hh is None:  # ★조례 미등록 — 전국 단일값 없음(하수도법 §61). 지어내지 않고 정직 표기.
        return {
            "code": "B04", "name": "하수도 원인자부담금",
            "base_won": total_households, "rate": None, "amount_won": 0,
            "detail": {"confidence": "unavailable",
                       "reason": "지자체 조례 단가 미등록 — 관할 조례 확인 필요(하수도법 §61·오수발생량×조례단가)"},
        }
    amount = per_hh * total_households
    return {
        "code": "B04", "name": "하수도 원인자부담금",
        "base_won": total_households, "rate": per_hh,
        "amount_won": amount,
        "detail": {"per_hh_won": per_hh, "confidence": "regional"},
    }


def calculate_b05_electricity(
    *,
    total_households: int,
    per_hh_won: int = 250_000,
) -> dict[str, Any]:
    """B05 전기인입부담금."""
    amount = per_hh_won * total_households
    return {
        "code": "B05", "name": "전기인입부담금",
        "base_won": total_households, "rate": per_hh_won,
        "amount_won": amount,
    }


def calculate_b06_gas(
    *,
    total_households: int,
    per_hh_won: int = 180_000,
) -> dict[str, Any]:
    """B06 도시가스인입부담금."""
    amount = per_hh_won * total_households
    return {
        "code": "B06", "name": "도시가스인입부담금",
        "base_won": total_households, "rate": per_hh_won,
        "amount_won": amount,
    }


def calculate_b07_telecom(
    *,
    total_households: int,
    per_hh_won: int = 80_000,
) -> dict[str, Any]:
    """B07 통신인입부담금."""
    amount = per_hh_won * total_households
    return {
        "code": "B07", "name": "통신인입부담금",
        "base_won": total_households, "rate": per_hh_won,
        "amount_won": amount,
    }


def calculate_b08_fire(
    *,
    total_gfa_sqm: float,
    per_sqm_won: int = 3_500,
) -> dict[str, Any]:
    """B08 소방시설부담금."""
    amount = int(total_gfa_sqm * per_sqm_won)
    return {
        "code": "B08", "name": "소방시설부담금",
        "base_won": int(total_gfa_sqm), "rate": per_sqm_won,
        "amount_won": amount,
    }


def calculate_all_utility_stage(
    *,
    sido_name: str = "",
    sigungu_name: str = "",
    total_households: int = 0,
    total_sale_amount_won: int = 0,
    total_gfa_sqm: float = 0,
    building_type: str = "apartment",
) -> dict[str, Any]:
    """B01~B08 공사단계 전체 일괄 계산.

    Returns:
        {'items': [...], 'total_won': int, 'applicable_count': int}
    """
    items = [
        calculate_b01_metro_transport(
            sido_name=sido_name, sigungu_name=sigungu_name,
            total_gfa_sqm=total_gfa_sqm, building_type=building_type,
        ),
        calculate_b02_school_site(
            total_sale_amount_won=total_sale_amount_won,
            total_households=total_households,
        ),
        calculate_b03_water_supply(
            sido_name=sido_name, sigungu_name=sigungu_name,
            total_households=total_households,
        ),
        calculate_b04_sewage(
            sido_name=sido_name, sigungu_name=sigungu_name,
            total_households=total_households,
        ),
        calculate_b05_electricity(total_households=total_households),
        calculate_b06_gas(total_households=total_households),
        calculate_b07_telecom(total_households=total_households),
        calculate_b08_fire(total_gfa_sqm=total_gfa_sqm),
    ]

    total = sum(it["amount_won"] for it in items)
    return {
        "stage": "construction",
        "items": items,
        "total_won": total,
        "applicable_count": len(items),
    }
