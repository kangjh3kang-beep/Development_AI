"""건물 에너지 시뮬레이션 서비스."""

from typing import Dict, List


class EnergyService:
    """건물 에너지 소비 시뮬레이션 + BEEC 등급 평가."""

    BEEC_GRADES = [
        (60, "1++"),
        (100, "1+"),
        (150, "1"),
        (200, "2"),
        (250, "3"),
        (310, "4"),
        (370, "5"),
        (440, "6"),
        (float("inf"), "7"),
    ]

    ENERGY_INTENSITY_BY_TYPE = {
        "apartment":   {"1++": 60, "1+": 90, "1": 130, "2": 170, "3": 210, "4": 260, "5": 320},
        "office":      {"1++": 100, "1+": 150, "1": 200, "2": 260, "3": 320, "4": 380, "5": 450},
        "commercial":  {"1++": 120, "1+": 170, "1": 230, "2": 300, "3": 370, "4": 440, "5": 520},
        "hospital":    {"1++": 150, "1+": 210, "1": 280, "2": 360, "3": 440, "4": 520, "5": 600},
        "school":      {"1++": 70, "1+": 100, "1": 140, "2": 180, "3": 230, "4": 280, "5": 340},
        "hotel":       {"1++": 130, "1+": 180, "1": 240, "2": 310, "3": 380, "4": 450, "5": 530},
    }

    ENERGY_BREAKDOWN_BY_TYPE = {
        "apartment":  {"heating": 0.55, "cooling": 0.10, "hot_water": 0.20, "lighting": 0.10, "equipment": 0.05},
        "office":     {"heating": 0.25, "cooling": 0.30, "hot_water": 0.05, "lighting": 0.25, "equipment": 0.15},
        "commercial": {"heating": 0.15, "cooling": 0.35, "hot_water": 0.05, "lighting": 0.30, "equipment": 0.15},
        "hospital":   {"heating": 0.20, "cooling": 0.35, "hot_water": 0.15, "lighting": 0.15, "equipment": 0.15},
        "school":     {"heating": 0.45, "cooling": 0.15, "hot_water": 0.10, "lighting": 0.20, "equipment": 0.10},
    }

    PEAK_FACTORS = {
        "apartment": 1.8, "office": 3.0, "commercial": 2.8,
        "hospital": 4.0, "school": 2.2, "hotel": 3.5,
        "default": 2.5,
    }

    def simulate_energy(self, building_data: dict, building_type: str = "apartment") -> dict:
        area = building_data.get("total_area_sqm", 5000)
        floors = building_data.get("floors", 10)
        grade = building_data.get("insulation_grade", "standard")

        # Map insulation grade to approximate BEEC grade for intensity lookup
        insulation_to_beec = {"high": "1+", "standard": "3", "low": "5"}
        beec_approx = insulation_to_beec.get(grade, "3")

        intensity_map = self.ENERGY_INTENSITY_BY_TYPE.get(
            building_type, self.ENERGY_INTENSITY_BY_TYPE["apartment"]
        )
        base_kwh = intensity_map.get(beec_approx, intensity_map.get("3", 210))

        annual = area * base_kwh
        peak_factor = self.PEAK_FACTORS.get(building_type, self.PEAK_FACTORS["default"])
        peak = annual / 8760 * peak_factor

        breakdown = self.ENERGY_BREAKDOWN_BY_TYPE.get(
            building_type, self.ENERGY_BREAKDOWN_BY_TYPE["apartment"]
        )

        return {
            "annual_energy_kwh": annual,
            "energy_per_sqm_kwh": base_kwh,
            "annual_kwh_per_sqm": base_kwh,
            "breakdown": breakdown,
            "peak_demand_kw": round(peak, 1),
            "building_type": building_type,
        }

    def calculate_beec_rating(self, primary_energy_kwh_sqm_yr: float) -> dict:
        grade = "7"
        for threshold, g in self.BEEC_GRADES:
            if primary_energy_kwh_sqm_yr < threshold:
                grade = g
                break
        return {"primary_energy": primary_energy_kwh_sqm_yr, "grade": grade}

    def calculate_peak_demand(self, annual_kwh: float, peak_factor: float = 2.5, building_type: str = "apartment") -> dict:
        if peak_factor == 2.5:
            # Use building-type specific factor if caller didn't override
            peak_factor = self.PEAK_FACTORS.get(building_type, self.PEAK_FACTORS["default"])
        avg = annual_kwh / 8760
        return {"avg_demand_kw": round(avg, 2), "peak_demand_kw": round(avg * peak_factor, 2), "peak_factor": peak_factor}

    def recommend_improvements(self, current_energy: dict, building_type: str = "apartment") -> list[dict]:
        recommendations = []
        grade = current_energy.get("beec_grade", "5")
        kwh_sqm = current_energy.get("annual_kwh_per_sqm", 300)

        if kwh_sqm > 200:
            recommendations.append({"measure": "건물 외피 단열 강화 (외단열+고성능 창호)", "saving_pct": 25, "cost_grade": "high", "priority": 1})
        if current_energy.get("breakdown", {}).get("lighting", 0) > 0.2:
            recommendations.append({"measure": "LED 조명 교체 + 조명 제어 시스템", "saving_pct": 15, "cost_grade": "low", "priority": 2})
        if current_energy.get("breakdown", {}).get("cooling", 0) > 0.25:
            recommendations.append({"measure": "고효율 공조 시스템 (VRF/지열)", "saving_pct": 20, "cost_grade": "medium", "priority": 3})
        if kwh_sqm > 150:
            recommendations.append({"measure": "태양광 패널 설치 (지붕면적 활용)", "saving_pct": 10, "cost_grade": "medium", "priority": 4})
        if building_type in ("office", "commercial"):
            recommendations.append({"measure": "BEMS(건물에너지관리시스템) 도입", "saving_pct": 12, "cost_grade": "medium", "priority": 5})

        return sorted(recommendations, key=lambda r: r["priority"])
