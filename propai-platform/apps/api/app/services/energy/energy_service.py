"""건물 에너지 시뮬레이션 서비스."""

from typing import Dict, List


class EnergyService:
    """건물 에너지 소비 시뮬레이션 + BEEC 등급 평가."""

    BEEC_GRADES = [
        (90, "1++"), (140, "1+"), (190, "1"), (230, "2"),
        (270, "3"), (320, "4"), (380, "5"), (450, "6"), (float("inf"), "7"),
    ]

    def simulate_energy(self, building_data: Dict) -> Dict:
        area = building_data.get("total_area_sqm", 5000)
        floors = building_data.get("floors", 10)
        grade = building_data.get("insulation_grade", "standard")
        base_kwh = {"high": 80, "standard": 120, "low": 160}.get(grade, 120)
        annual = area * base_kwh
        peak = annual / 8760 * 2.5
        return {
            "annual_energy_kwh": annual,
            "energy_per_sqm_kwh": base_kwh,
            "breakdown": {"heating": 0.35, "cooling": 0.25, "lighting": 0.2, "equipment": 0.2},
            "peak_demand_kw": round(peak, 1),
        }

    def calculate_beec_rating(self, primary_energy_kwh_sqm_yr: float) -> Dict:
        grade = "7"
        for threshold, g in self.BEEC_GRADES:
            if primary_energy_kwh_sqm_yr < threshold:
                grade = g
                break
        return {"primary_energy": primary_energy_kwh_sqm_yr, "grade": grade}

    def calculate_peak_demand(self, annual_kwh: float, peak_factor: float = 2.5) -> Dict:
        avg = annual_kwh / 8760
        return {"avg_demand_kw": round(avg, 2), "peak_demand_kw": round(avg * peak_factor, 2), "peak_factor": peak_factor}

    def recommend_improvements(self, current_energy: Dict) -> List[Dict]:
        return [
            {"measure": "LED 조명 교체", "saving_pct": 15, "cost_grade": "low"},
            {"measure": "고효율 공조 시스템", "saving_pct": 25, "cost_grade": "medium"},
            {"measure": "건물 외피 단열 강화", "saving_pct": 20, "cost_grade": "high"},
        ]
