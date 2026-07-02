"""ZEB (제로에너지빌딩) 평가 서비스."""



class ZEBService:
    """ZEB 인증 등급 평가 + 에너지 최적화."""

    GRADES = {
        1: (100, "1등급: 에너지자립률 100% 이상"),
        2: (80, "2등급: 에너지자립률 80~100%"),
        3: (60, "3등급: 에너지자립률 60~80%"),
        4: (40, "4등급: 에너지자립률 40~60%"),
        5: (20, "5등급: 에너지자립률 20~40%"),
    }

    def evaluate_zeb_grade(self, energy_data: dict) -> dict:
        primary = energy_data.get("primary_energy_kwh_sqm_yr", 0)
        renewable = energy_data.get("renewable_generation_kwh_sqm_yr", 0)
        independence = (renewable / primary * 100) if primary > 0 else 0
        grade = 5
        for g, (threshold, _) in self.GRADES.items():
            if independence >= threshold:
                grade = g
                break
        return {
            "grade": grade,
            "energy_independence_pct": round(independence, 2),
            "description": self.GRADES[grade][1],
            "certified": grade <= 5,
            "legal_basis": "녹색건축물 조성 지원법 시행령 제12조",
        }

    def calculate_primary_energy(self, building_data: dict) -> dict:
        area = building_data.get("total_area_sqm", 1000)
        kwh_per_sqm = building_data.get("energy_per_sqm_kwh", 120)
        total = area * kwh_per_sqm
        return {"total_kwh": total, "per_sqm_yr": kwh_per_sqm, "area_sqm": area}

    def optimize_envelope(self, current_data: dict) -> list[dict]:
        improvements = []
        u_wall = current_data.get("u_wall", 0.3)
        u_window = current_data.get("u_window", 1.5)
        ach = current_data.get("airtightness_ach", 3.0)
        if u_wall > 0.15:
            improvements.append({
                "item": "외벽 단열", "current_u": u_wall, "target_u": 0.15,
                "saving_pct": round((1 - 0.15 / u_wall) * 30, 1),
            })
        if u_window > 0.9:
            improvements.append({
                "item": "창호 교체", "current_u": u_window, "target_u": 0.9,
                "saving_pct": round((1 - 0.9 / u_window) * 25, 1),
            })
        if ach > 1.0:
            improvements.append({
                "item": "기밀성 강화", "current": ach, "target": 1.0,
                "saving_pct": round((1 - 1.0 / ach) * 15, 1),
            })
        return improvements

    def forecast_certification(self, current_grade: int, improvements: list[dict]) -> dict:
        total_saving = sum(i.get("saving_pct", 0) for i in improvements)
        achievable = current_grade - max(1, int(total_saving / 20))
        return {
            "current_grade": current_grade,
            "total_saving_pct": round(total_saving, 1),
            "achievable": max(1, achievable),
            "recommended_improvements": improvements,
        }
