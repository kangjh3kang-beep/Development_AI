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

# 자재키 → 한국 EPD DB(한글명) 매핑(동적 EPD 우선 조회용)
_EPD_ALIAS = {
    "concrete_35mpa": "레미콘_35MPa", "concrete_C35": "고강도 콘크리트 (C35)",
    "concrete_C25": "일반 콘크리트 (C25)", "concrete_25mpa": "일반 콘크리트 (C25)",
    "rebar": "철근_SD400", "rebar_sd400": "철근_SD400", "steel_rebar": "철근_SD400",
    "steel_structural": "구조용강재_H형강", "insulation_eps": "EPS단열재",
    "insulation_mineral_wool": "단열재 (미네랄울)", "glass": "로이유리",
}


def _resolve_ef(material: str) -> tuple[float, str]:
    """배출계수(kgCO2e/kg)·출처 계층 조회: EPD-KR → IPCC AR6 → 기본추정."""
    from app.services.esg.epd_carbon_service import EPD_KOREA_DATABASE
    epd = EPD_KOREA_DATABASE.get(material) or EPD_KOREA_DATABASE.get(_EPD_ALIAS.get(material, ""))
    if epd and "epd_kgco2e" in epd:
        return float(epd["epd_kgco2e"]), "EPD-KR"
    key = _NAME_ALIAS.get(material, material)
    if key in IPCC_AR6_EMISSION_FACTORS:
        return IPCC_AR6_EMISSION_FACTORS[key], "IPCC-AR6"
    return 0.5, "기본추정"


class LCAService:
    """LCA 탄소 자동 계산 (ISO 14040:2006, IPCC AR6)"""

    def calculate_a1_a3(self, material_quantities) -> dict:
        """A1-A3 자재 생산 단계 GWP = sum(m_i × EF_i).

        제품수준 EPD: 입력이 리스트이고 각 항목에 epd_kgco2e(제품별 실측 EPD)가 있으면
        그 값을 우선 사용(제품 EPD > 한국 EPD-KR 평균 > IPCC AR6 > 기본).
        """
        # (자재명, 수량kg, 제품EPD|None) 정규화
        items: list[tuple[str, float, float | None]] = []
        if isinstance(material_quantities, list):
            for it in material_quantities:
                pe = it.get("epd_kgco2e")
                try:
                    pe = float(pe) if pe not in (None, "", 0) else None
                except (TypeError, ValueError):
                    pe = None
                items.append((it.get("name", ""), it.get("quantity_kg", 0) or 0, pe))
        else:
            for name, qty in material_quantities.items():
                items.append((name, qty or 0, None))

        total_gwp = 0.0
        breakdown = {}
        epd_covered = 0
        product_epd_count = 0
        for material, quantity_kg, product_epd in items:
            if product_epd is not None:
                ef, src = product_epd, "EPD-제품"
                product_epd_count += 1
                epd_covered += 1
            else:
                ef, src = _resolve_ef(material)
                if src == "EPD-KR":
                    epd_covered += 1
            gwp = quantity_kg * ef
            total_gwp += gwp
            breakdown[material] = {
                "quantity_kg": quantity_kg,
                "emission_factor_kgco2e_per_kg": ef,
                "ef_source": src,
                "gwp_kgco2e": round(gwp, 2)
            }
        total_rounded = round(total_gwp, 2)
        return {
            "phase": "A1-A3", "total_gwp_kgco2e": total_rounded,
            "total_gwp_kgco2eq": total_rounded,
            "breakdown": breakdown, "standard": "ISO 14040:2006",
            "gwp_basis": "제품 EPD > 한국 EPD-KR > IPCC AR6 폴백",
            "epd_coverage": f"{epd_covered}/{len(items)}",
            "product_epd_count": product_epd_count,
        }

    def calculate_b6_operational_energy(self, floor_area_sqm: float,
                                         energy_intensity_kwh_per_sqm: float = 120.0,
                                         grid_emission_factor: float = 0.4781,
                                         intensity_source: str = "기본추정(주거 1차에너지 120)") -> dict:
        """B6 운영 에너지 GWP (한국 전력 배출계수 0.4781).

        energy_intensity_kwh_per_sqm은 BEEC 1차에너지 원단위(kWh/㎡·yr)를 받는다.
        값이 없으면 기본 120을 쓰되 intensity_source로 출처를 명시한다.
        """
        annual_energy_kwh = floor_area_sqm * energy_intensity_kwh_per_sqm
        annual_gwp = annual_energy_kwh * grid_emission_factor
        lifecycle_gwp = annual_gwp * 50
        return {
            "phase": "B6", "annual_energy_kwh": round(annual_energy_kwh, 1),
            "annual_gwp_kgco2e": round(annual_gwp, 1),
            "lifecycle_gwp_50yr_kgco2e": round(lifecycle_gwp, 1),
            "energy_intensity_kwh_per_sqm": energy_intensity_kwh_per_sqm,
            "energy_intensity_source": intensity_source,
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

    def calculate_whole_life(self, a1a3_total: float, b6_lifecycle: float) -> dict:
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

    @staticmethod
    def _beec_intensity_for(building_type: str) -> tuple[float, str]:
        """energy_service(BEEC)의 건물유형별 표준 1차에너지 원단위(3등급 기준)를 반환.

        에너지 분석 입력이 없을 때의 명시적 기본값. 출처를 함께 표기한다.
        """
        try:
            from app.services.energy.energy_service import EnergyService
            intensity_map = EnergyService.ENERGY_INTENSITY_BY_TYPE.get(
                building_type, EnergyService.ENERGY_INTENSITY_BY_TYPE["apartment"]
            )
            intensity = float(intensity_map.get("3", intensity_map.get("1", 130)))
            return intensity, f"BEEC 3등급 표준원단위({building_type}, energy_service)"
        except Exception:
            return 120.0, "기본추정(주거 1차에너지 120)"

    def calculate_total_lca(self, material_quantities: dict[str, float],
                            floor_area_sqm: float,
                            building_type: str = "apartment",
                            energy_intensity_kwh_per_sqm: float | None = None) -> dict:
        """전생애(whole-life) LCA.

        B6 운영에너지는 energy_service(BEEC)의 1차에너지 원단위와 디커플링한다.
        energy_intensity_kwh_per_sqm이 주어지면 그 값을 B6에 반영하고, 없으면
        building_type 기준 BEEC '3등급' 표준 원단위를 출처와 함께 사용한다.
        """
        a1a3 = self.calculate_a1_a3(material_quantities)
        if energy_intensity_kwh_per_sqm is not None and energy_intensity_kwh_per_sqm > 0:
            b6 = self.calculate_b6_operational_energy(
                floor_area_sqm,
                energy_intensity_kwh_per_sqm=energy_intensity_kwh_per_sqm,
                intensity_source="입력값(BEEC 1차에너지 원단위)",
            )
        else:
            beec_intensity, beec_source = self._beec_intensity_for(building_type)
            b6 = self.calculate_b6_operational_energy(
                floor_area_sqm,
                energy_intensity_kwh_per_sqm=beec_intensity,
                intensity_source=beec_source,
            )
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
