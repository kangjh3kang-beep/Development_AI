"""세금 v2 API 라우터 — 8개 엔드포인트."""

from __future__ import annotations

from fastapi import APIRouter

from app.schemas.feasibility_v2 import TaxCalculateAllRequest, TaxResultResponse
from app.services.tax.integrated_tax_engine import calculate_all_taxes, get_applicable_tax_codes
from app.services.tax.regional_tax_data import (
    ACQUISITION_TAX_MATRIX,
    METRO_TRANSPORT_BASE,
    METRO_TRANSPORT_SIGUNGU_OVERRIDE,
    get_metro_transport_charge,
    get_acquisition_tax_rates,
)

router = APIRouter(prefix="/api/v2/tax", tags=["tax-v2"])


@router.post("/calculate-all", response_model=TaxResultResponse)
async def calculate_all(req: TaxCalculateAllRequest):
    """38종 세금 일괄 계산."""
    result = calculate_all_taxes(
        purchase_won=req.purchase_won,
        land_category=req.land_category,
        house_count=req.house_count,
        is_adjusted=req.is_adjusted,
        area_sqm=req.area_sqm,
        official_price_per_sqm=req.official_price_per_sqm,
        sido_name=req.sido_name,
        sigungu_name=req.sigungu_name,
        total_households=req.total_households,
        total_sale_amount_won=req.total_sale_amount_won,
        total_gfa_sqm=req.total_gfa_sqm,
        building_type=req.building_type,
        total_units=req.total_units,
        avg_area_sqm=req.avg_area_sqm,
    )
    return TaxResultResponse(**result)


@router.get("/applicable/{development_type}")
async def get_applicable(development_type: str, land_category: str = "land"):
    """개발유형별 적용 가능 세금 코드."""
    codes = get_applicable_tax_codes(
        development_type=development_type,
        land_category=land_category,
    )
    return {"development_type": development_type, "applicable_codes": codes, "count": len(codes)}


@router.get("/matrix")
async def get_tax_matrix():
    """취득세 매트릭스 전체."""
    matrix = []
    for key, rates in ACQUISITION_TAX_MATRIX.items():
        matrix.append({
            "land_category": key[0],
            "house_count": key[1],
            "is_adjusted": key[2],
            "base_rate": rates[0],
            "surcharge_rate": rates[1],
            "education_rate": rates[2],
            "rural_rate": rates[3],
            "total_rate": sum(rates),
        })
    return {"matrix": matrix, "count": len(matrix)}


@router.get("/regions/{sido_name}")
async def get_region_rates(sido_name: str, building_type: str = "apartment"):
    """시도별 세율 조회."""
    base = METRO_TRANSPORT_BASE.get(sido_name, {})
    overrides = {
        k: v for k, v in METRO_TRANSPORT_SIGUNGU_OVERRIDE.items()
        if k.startswith(f"{sido_name}_")
    }
    return {
        "sido_name": sido_name,
        "base_rates": base,
        "sigungu_overrides": overrides,
    }


@router.get("/rates")
async def get_rates(
    land_category: str = "land",
    house_count: int = 0,
    is_adjusted: bool = False,
):
    """취득세율 조회."""
    rates = get_acquisition_tax_rates(land_category, house_count, is_adjusted)
    return rates


@router.get("/metro-transport")
async def get_metro_transport(
    sido_name: str,
    sigungu_name: str,
    total_households: int = 1000,
    building_type: str = "apartment",
):
    """광역교통부담금 조회."""
    return get_metro_transport_charge(sido_name, sigungu_name, total_households, building_type)


@router.get("/compare")
async def compare_tax(
    land_category_a: str = "land",
    land_category_b: str = "farmland",
    purchase_won: int = 10_000_000_000,
):
    """두 지목 세금 비교."""
    rates_a = get_acquisition_tax_rates(land_category_a)
    rates_b = get_acquisition_tax_rates(land_category_b)
    return {
        "a": {"land_category": land_category_a, "rates": rates_a, "tax_won": int(purchase_won * rates_a["total_rate"])},
        "b": {"land_category": land_category_b, "rates": rates_b, "tax_won": int(purchase_won * rates_b["total_rate"])},
        "difference_won": abs(int(purchase_won * rates_a["total_rate"]) - int(purchase_won * rates_b["total_rate"])),
    }


@router.get("/development-types")
async def list_tax_by_development_types():
    """개발유형별 적용 세금 수 비교."""
    types = [f"M{i:02d}" for i in range(1, 16)]
    result = []
    for dt in types:
        codes = get_applicable_tax_codes(development_type=dt)
        result.append({"development_type": dt, "tax_count": len(codes)})
    return {"types": result}
