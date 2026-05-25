import numpy as np
from typing import Dict
import structlog

logger = structlog.get_logger()

class ProcurementOptimizer:
    """자재 조달 최적화 EOQ = sqrt(2*D*S/H) + PPI 예측"""

    PPI_BASE_INDEX = {
        "시멘트": 142.3, "철근": 138.7, "레미콘": 135.2,
        "합판": 129.8, "유리": 127.5, "단열재": 133.4,
        "배관자재": 141.2, "전기자재": 136.8
    }

    def calculate_eoq(self, annual_demand: float, order_cost_krw: float,
                      holding_cost_pct: float = 0.25) -> Dict:
        holding_cost = order_cost_krw * holding_cost_pct
        eoq = np.sqrt(2 * annual_demand * order_cost_krw / holding_cost) if holding_cost > 0 else 0
        freq = annual_demand / eoq if eoq > 0 else 0
        cycle = 365 / freq if freq > 0 else 365
        return {
            "annual_demand": annual_demand, "order_cost_krw": order_cost_krw,
            "optimal_order_quantity_eoq": round(eoq, 1),
            "order_frequency_per_year": round(freq, 1),
            "order_cycle_days": round(cycle, 0),
            "formula": "EOQ = sqrt(2*D*S/H)"
        }

    def predict_optimal_order_timing(self, material_name: str, current_ppi: float,
                                      forecast_months: int = 6) -> Dict:
        base_ppi = self.PPI_BASE_INDEX.get(material_name, 130.0)
        ppi_trend = (current_ppi - base_ppi) / base_ppi
        if ppi_trend > 0.1:
            recommendation = "즉시 발주 권장 (가격 상승 추세)"
            optimal_months = 0
        elif ppi_trend < -0.05:
            recommendation = f"{forecast_months}개월 후 발주 권장"
            optimal_months = forecast_months
        else:
            recommendation = "정기 발주 유지"
            optimal_months = 3
        return {
            "material_name": material_name, "current_ppi": current_ppi,
            "base_ppi_2020": base_ppi,
            "ppi_change_pct": round(ppi_trend * 100, 1),
            "order_recommendation": recommendation,
            "data_source": "한국은행 PPI"
        }
