from typing import Dict, List
import structlog

logger = structlog.get_logger()

IPCC_AR6_EMISSION_FACTORS = {
    "concrete_C25": 0.159, "concrete_C30": 0.176, "concrete_C35": 0.193,
    "steel_rebar": 1.460, "steel_structural": 1.770, "aluminum": 8.240,
    "glass": 0.850, "brick": 0.223, "insulation_eps": 3.290,
    "insulation_mineral_wool": 1.280, "wood_structure": 0.469,
    "plasterboard": 0.380, "PVC_pipe": 2.410,
}

_NAME_ALIAS = {
    "concrete_35mpa": "concrete_C35",
    "rebar_sd400": "steel_rebar",
}

class LCAService:
    """LCA 탄소 자동 계산 (ISO 14040:2006, IPCC AR6)"""

    def calculate_a1_a3(self, material_quantities) -> Dict:
        """A1-A3 자재 생산 단계 GWP = sum(m_i * EF_i)"""
        if isinstance(material_quantities, list):
            material_quantities = {
                item.get("name", ""): item.get("quantity_kg", 0)
                for item in material_quantities
            }
        total_gwp = 0.0
        breakdown = {}
        for material, quantity_kg in material_quantities.items():
            key = _NAME_ALIAS.get(material, material)
            ef = IPCC_AR6_EMISSION_FACTORS.get(key, 0.5)
            gwp = quantity_kg * ef
            total_gwp += gwp
            breakdown[material] = {
                "quantity_kg": quantity_kg,
                "emission_factor_kgco2e_per_kg": ef,
                "gwp_kgco2e": round(gwp, 2)
            }
        total_rounded = round(total_gwp, 2)
        return {
            "phase": "A1-A3", "total_gwp_kgco2e": total_rounded,
            "total_gwp_kgco2eq": total_rounded,
            "breakdown": breakdown, "standard": "ISO 14040:2006",
            "gwp_basis": "IPCC AR6 2021"
        }

    def calculate_b6_operational_energy(self, floor_area_sqm: float,
                                         energy_intensity_kwh_per_sqm: float = 120.0,
                                         grid_emission_factor: float = 0.4781) -> Dict:
        """B6 운영 에너지 GWP (한국 전력 배출계수 0.4781)"""
        annual_energy_kwh = floor_area_sqm * energy_intensity_kwh_per_sqm
        annual_gwp = annual_energy_kwh * grid_emission_factor
        lifecycle_gwp = annual_gwp * 50
        return {
            "phase": "B6", "annual_energy_kwh": round(annual_energy_kwh, 1),
            "annual_gwp_kgco2e": round(annual_gwp, 1),
            "lifecycle_gwp_50yr_kgco2e": round(lifecycle_gwp, 1),
            "grid_emission_factor_kgco2e_per_kwh": grid_emission_factor,
            "standard": "ISO 14040:2006 Phase B6"
        }

    # EN 15978 단계별 비율(A1-A3 대비) — v1 비율기반 추정(EPD 확보 시 정밀화).
    # 근거: 건축물 LCA 일반 비율(운송·시공·교체·해체). D(재활용 크레딧)는 보고만(총계 제외).
    _STAGE_RATIOS = {
        "A4": (0.04, "자재 운송"),
        "A5": (0.06, "시공(폐기물·에너지)"),
        "B1_B5": (0.12, "사용·유지·교체(50년)"),
        "C1_C4": (0.06, "해체·폐기"),
    }
    _STAGE_D_RATIO = (-0.08, "재활용·재사용 크레딧(시스템 경계 외, 총계 제외)")

    def calculate_whole_life(self, a1a3_total: float, b6_lifecycle: float) -> Dict:
        """EN 15978 전생애(whole-life) 단계 — A1-A3·B6 외 단계를 비율기반 추정."""
        stages = {}
        embodied_extra = 0.0
        for code, (ratio, label) in self._STAGE_RATIOS.items():
            gwp = round(a1a3_total * ratio, 1)
            stages[code] = {"gwp_kgco2e": gwp, "label": label, "ratio_of_a1a3": ratio}
            embodied_extra += gwp
        d_gwp = round(a1a3_total * self._STAGE_D_RATIO[0], 1)
        stages["D"] = {"gwp_kgco2e": d_gwp, "label": self._STAGE_D_RATIO[1],
                       "ratio_of_a1a3": self._STAGE_D_RATIO[0], "excluded_from_total": True}
        # 내재(embodied) = A1-A3 + A4 + A5 + B1-B5 + C1-C4 (운영 B6 제외)
        embodied_total = round(a1a3_total + embodied_extra, 1)
        whole_life_total = round(embodied_total + b6_lifecycle, 1)
        return {
            "stages": stages,
            "embodied_total_kgco2e": embodied_total,   # 내재탄소(운영 제외)
            "operational_b6_kgco2e": round(b6_lifecycle, 1),
            "whole_life_total_kgco2e": whole_life_total,
            "recycling_credit_kgco2e": d_gwp,
            "standard": "EN 15978 (A1-A3·A4·A5·B1-B5·B6·C1-C4, D 별도)",
            "basis": "A4/A5/B1-B5/C는 A1-A3 대비 비율기반 추정 — EPD 확보 시 정밀화",
        }

    def calculate_total_lca(self, material_quantities: Dict[str, float],
                            floor_area_sqm: float) -> Dict:
        a1a3 = self.calculate_a1_a3(material_quantities)
        b6 = self.calculate_b6_operational_energy(floor_area_sqm)
        whole = self.calculate_whole_life(
            a1a3["total_gwp_kgco2e"], b6["lifecycle_gwp_50yr_kgco2e"])
        total_gwp = whole["whole_life_total_kgco2e"]  # 전생애 총계로 격상
        gwp_per_sqm = total_gwp / floor_area_sqm if floor_area_sqm > 0 else 0
        embodied_per_sqm = whole["embodied_total_kgco2e"] / floor_area_sqm if floor_area_sqm > 0 else 0
        return {
            "total_gwp_kgco2e": round(total_gwp, 1),               # = 전생애(whole-life)
            "gwp_per_sqm_kgco2e": round(gwp_per_sqm, 2),
            "embodied_per_sqm_kgco2e": round(embodied_per_sqm, 2),
            "a1_a3": a1a3, "b6": b6,
            "whole_life": whole,
            "standard": "EN 15978 / ISO 14040", "ipcc_version": "AR6 2021"
        }
