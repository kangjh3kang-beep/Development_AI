"""RE100 재생에너지 추적 서비스."""

from typing import Dict, List, Optional


class RE100Service:
    """RE100 재생에너지 100% 목표 추적."""

    def track_renewable_energy(self, total_kwh: float, renewable_kwh: float) -> Dict:
        renewable_pct = (renewable_kwh / total_kwh * 100) if total_kwh > 0 else 0
        target_pct = 100.0
        gap_kwh = max(0, total_kwh - renewable_kwh)
        return {
            "total_energy_kwh": total_kwh,
            "renewable_energy_kwh": renewable_kwh,
            "renewable_pct": round(renewable_pct, 2),
            "target_pct": target_pct,
            "gap_kwh": round(gap_kwh, 2),
        }

    def calculate_re100_progress(self, yearly_data: List[Dict]) -> Dict:
        if not yearly_data:
            return {"progress": [], "trend": "unknown", "latest_pct": 0}
        latest = yearly_data[-1].get("renewable_pct", 0)
        trend = "증가" if len(yearly_data) > 1 and yearly_data[-1].get("renewable_pct", 0) > yearly_data[0].get("renewable_pct", 0) else "안정"
        return {"progress": yearly_data, "trend": trend, "latest_pct": latest}

    def recommend_sources(self, gap_kwh: float, budget: Optional[float] = None) -> List[Dict]:
        sources = [
            {"source": "solar", "name": "태양광", "annual_cost_krw": int(gap_kwh * 80), "reliability": 0.85, "feasible": True},
            {"source": "wind", "name": "풍력", "annual_cost_krw": int(gap_kwh * 60), "reliability": 0.75, "feasible": True},
            {"source": "ppa", "name": "PPA 계약", "annual_cost_krw": int(gap_kwh * 100), "reliability": 0.95, "feasible": True},
        ]
        if budget:
            sources = [s for s in sources if s["annual_cost_krw"] <= budget]
        return sources

    def forecast_target(self, current_pct: float, annual_increase_pct: float, target_year_gap: int) -> Dict:
        projected = current_pct + annual_increase_pct * target_year_gap
        years = int((100 - current_pct) / annual_increase_pct) if annual_increase_pct > 0 else 999
        return {
            "current_pct": current_pct,
            "projected_pct": min(projected, 100),
            "years_to_target": years,
            "on_track": projected >= 100,
        }
