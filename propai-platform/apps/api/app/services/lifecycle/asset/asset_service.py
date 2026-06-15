"""자산 평가 서비스."""
from typing import Dict, List


class AssetService:
    """부동산 자산 가치 평가 (비교/수익/원가법)."""

    DEPRECIATION_RATES = {
        "apartment": 0.02, "building": 0.025, "office": 0.025, "commercial": 0.03,
        "warehouse": 0.04, "factory": 0.05,
    }

    def valuate_asset(self, asset_data: dict, method: str = "comparison") -> dict:
        methods = {
            "comparison": ("비교사례법", self._comparison_method),
            "income": ("수익환원법", self._income_method),
            "cost": ("원가법", self._cost_method),
        }
        name, fn = methods.get(method, methods["comparison"])
        value = fn(asset_data)
        return {"value": round(value), "method": method, "method_name": name}

    def _comparison_method(self, data: dict) -> float:
        comparables = data.get("comparables", [])
        if not comparables:
            return data.get("area_sqm", 0) * 3_000_000
        avg = sum(c.get("price", 0) for c in comparables) / len(comparables)
        return avg * data.get("area_sqm", 1)

    def _income_method(self, data: dict) -> float:
        noi = data.get("annual_noi", 100_000_000)
        cap_rate = data.get("cap_rate", 0.05)
        return noi / cap_rate if cap_rate > 0 else 0

    def _cost_method(self, data: dict) -> float:
        land = data.get("land_value", 500_000_000)
        construction = data.get("construction_cost", 300_000_000)
        depreciation = data.get("depreciation", 0)
        return land + construction - depreciation

    def track_depreciation(self, asset_type: str, original_cost: float, age_years: int) -> dict:
        rate = self.DEPRECIATION_RATES.get(asset_type, 0.03)
        accumulated = min(original_cost, original_cost * rate * age_years)
        return {
            "original_cost": original_cost, "depreciation_rate": rate,
            "age_years": age_years, "accumulated_depreciation": round(accumulated),
            "book_value": round(original_cost - accumulated),
        }

    def generate_valuation_report(self, valuations: list[dict]) -> dict:
        total = sum(v.get("value", 0) for v in valuations)
        return {"valuations": valuations, "count": len(valuations), "total_value": total}
