import structlog

logger = structlog.get_logger()

EPD_KOREA_DATABASE = {
    "보통 포틀랜드 시멘트": {"epd_kgco2e": 0.820, "unit": "kg", "category": "결합재"},
    "고강도 콘크리트 (C35)": {"epd_kgco2e": 0.193, "unit": "kg", "category": "콘크리트"},
    "일반 콘크리트 (C25)": {"epd_kgco2e": 0.159, "unit": "kg", "category": "콘크리트"},
    "레미콘_35MPa": {"epd_kgco2e": 0.193, "unit": "kg", "category": "콘크리트"},
    "철근_SD400": {"epd_kgco2e": 1.460, "unit": "kg", "category": "철강"},
    "EPS단열재": {"epd_kgco2e": 3.290, "unit": "kg", "category": "단열재"},
    "철근 (SD500)": {"epd_kgco2e": 1.460, "unit": "kg", "category": "철강"},
    "구조용강재_H형강": {"epd_kgco2e": 1.770, "unit": "kg", "category": "철강"},
    "구조용 강재 (H형강)": {"epd_kgco2e": 1.770, "unit": "kg", "category": "철강"},
    "저탄소 콘크리트 (슬래그 30%)": {"epd_kgco2e": 0.115, "unit": "kg", "category": "콘크리트"},
    "재활용 철근 (EAF)": {"epd_kgco2e": 0.580, "unit": "kg", "category": "철강"},
    "단열재 (미네랄울)": {"epd_kgco2e": 1.280, "unit": "kg", "category": "단열재"},
    "단열재 (EPS)": {"epd_kgco2e": 3.290, "unit": "kg", "category": "단열재"},
    "삼중유리": {"epd_kgco2e": 0.720, "unit": "kg", "category": "유리"},
    "로이유리": {"epd_kgco2e": 0.950, "unit": "kg", "category": "유리"},
    "CLT 구조목": {"epd_kgco2e": -0.690, "unit": "kg", "category": "목재"},
    "OSB 합판": {"epd_kgco2e": 0.450, "unit": "kg", "category": "목재"},
}

class EPDCarbonService:
    """건축자재 EPD 탄소발자국 추적 (ISO 21930:2017)"""

    def calculate_material_carbon(self, material_list: list[dict]) -> dict:
        total_carbon = 0.0
        breakdown = []
        for item in material_list:
            name = item.get("name", "")
            quantity_kg = float(item.get("quantity_kg", 0))
            epd_data = EPD_KOREA_DATABASE.get(name)
            if epd_data:
                cf = quantity_kg * epd_data["epd_kgco2e"]
                total_carbon += cf
                breakdown.append({
                    "material": name, "quantity_kg": quantity_kg,
                    "epd_kgco2e_per_kg": epd_data["epd_kgco2e"],
                    "carbon_footprint_kgco2e": round(cf, 2),
                    "category": epd_data["category"]
                })
        total_rounded = round(total_carbon, 2)
        return {
            "total_carbon_footprint_kgco2e": total_rounded,
            "total_gwp_kgco2eq": total_rounded,
            "materials_assessed": len(breakdown),
            "material_count": len(breakdown), "breakdown": breakdown,
            "standard": "ISO 21930:2017", "data_source": "EPD Korea Database"
        }

    def recommend_low_carbon_alternatives(self, material_name: str, quantity_kg: float = 1000.0) -> dict:
        current = EPD_KOREA_DATABASE.get(material_name, {})
        current_cf = quantity_kg * current.get("epd_kgco2e", 0)
        alternatives = []
        for alt_name, alt_data in EPD_KOREA_DATABASE.items():
            if alt_data["category"] == current.get("category") and alt_name != material_name:
                alt_cf = quantity_kg * alt_data["epd_kgco2e"]
                reduction_pct = ((current_cf - alt_cf) / current_cf * 100) if current_cf > 0 else 0
                if reduction_pct > 0:
                    alternatives.append({
                        "alternative_name": alt_name,
                        "gwp": alt_data["epd_kgco2e"],
                        "epd_kgco2e_per_kg": alt_data["epd_kgco2e"],
                        "alt_carbon_footprint_kgco2e": round(alt_cf, 2),
                        "carbon_reduction_pct": round(reduction_pct, 1)
                    })
        alternatives.sort(key=lambda x: x["carbon_reduction_pct"], reverse=True)
        return {
            "original_material": material_name,
            "original_carbon_kgco2e": round(current_cf, 2),
            "alternatives": alternatives[:3],
            "standard": "ISO 21930:2017"
        }
