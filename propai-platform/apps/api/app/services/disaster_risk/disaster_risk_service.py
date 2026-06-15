from typing import Dict
import structlog

logger = structlog.get_logger()

class DisasterRiskService:
    """자연재해 리스크 분석 (자연재해대책법) Risk = sum(w_i * H_i * E_i * V_i)"""

    REGIONAL_HAZARD_INDEX = {
        "서울": {"flood": 0.3, "landslide": 0.1, "earthquake": 0.2},
        "부산": {"flood": 0.4, "landslide": 0.3, "earthquake": 0.4},
        "대구": {"flood": 0.2, "landslide": 0.2, "earthquake": 0.5},
        "인천": {"flood": 0.4, "landslide": 0.1, "earthquake": 0.2},
        "광주": {"flood": 0.3, "landslide": 0.2, "earthquake": 0.3},
        "대전": {"flood": 0.3, "landslide": 0.2, "earthquake": 0.3},
        "default": {"flood": 0.3, "landslide": 0.2, "earthquake": 0.3}
    }

    def assess_disaster_risk(self, region: str, land_use: str,
                              floor_count: int, distance_to_river_m: float = 500) -> dict:
        hazard = self.REGIONAL_HAZARD_INDEX.get(region, self.REGIONAL_HAZARD_INDEX["default"])
        flood_exposure = max(0.1, 1.0 - distance_to_river_m / 1000)
        seismic_vulnerability = min(0.9, floor_count * 0.05)
        flood_risk = hazard["flood"] * flood_exposure * 0.8
        landslide_risk = hazard["landslide"] * 0.5 * 0.6
        earthquake_risk = hazard["earthquake"] * seismic_vulnerability * 0.7
        total = flood_risk * 0.4 + landslide_risk * 0.3 + earthquake_risk * 0.3
        level = "critical" if total > 0.6 else "high" if total > 0.4 else "medium" if total > 0.2 else "low"
        return {
            "region": region,
            "flood_risk_score": round(flood_risk, 3),
            "landslide_risk_score": round(landslide_risk, 3),
            "earthquake_risk_score": round(earthquake_risk, 3),
            "total_risk_score": round(total, 3), "risk_level": level,
            "evacuation_routes": ["주 출입구 대피", "비상계단 옥상 대피", "인근 고지대 대피"],
            "legal_basis": "자연재해대책법"
        }
