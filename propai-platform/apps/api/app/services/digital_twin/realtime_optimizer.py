from typing import Dict
import numpy as np
import structlog

logger = structlog.get_logger()

class RealtimeOptimizer:
    """RealtimeTwinOptimizer 호환 별칭."""

    def optimize_hvac(self, current_temp: float, target_temp: float, occupancy: float = 50,
                      current_energy_kwh: float = 100.0) -> Dict:
        diff = abs(current_temp - target_temp)
        if diff > 3:
            mode = "cooling" if current_temp > target_temp else "heating"
            power_pct = min(100, int(diff * 20))
        else:
            mode = "eco"
            power_pct = max(20, int(diff * 15))
        return {
            "mode": mode, "power_pct": power_pct,
            "current_temp": current_temp, "target_temp": target_temp,
            "occupancy": occupancy,
        }


class RealtimeTwinOptimizer:
    """디지털 트윈 실시간 운영 최적화 (IFC 4.3)"""

    def optimize_hvac(self, outdoor_temp_c: float, indoor_temp_c: float,
                      occupancy_rate: float, current_energy_kwh: float) -> Dict:
        target_temp = 22.0
        occupancy_factor = max(0.3, occupancy_rate)
        baseline_energy = current_energy_kwh
        optimal_energy = baseline_energy * (1 - (1 - occupancy_factor) * 0.3)
        savings_pct = (baseline_energy - optimal_energy) / baseline_energy * 100
        return {
            "outdoor_temp_c": outdoor_temp_c, "indoor_temp_c": indoor_temp_c,
            "target_temp_c": target_temp, "occupancy_rate": occupancy_rate,
            "current_energy_kwh": round(current_energy_kwh, 2),
            "optimal_energy_kwh": round(optimal_energy, 2),
            "energy_savings_pct": round(savings_pct, 1),
            "recommendation": f"설정온도 {target_temp}C, 비재실 구역 냉난방 30% 감소",
            "ifc_standard": "IFC 4.3"
        }
