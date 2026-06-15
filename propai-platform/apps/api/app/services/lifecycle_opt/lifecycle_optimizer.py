import numpy as np
from typing import Dict
import structlog

logger = structlog.get_logger()

class LifecycleOptimizer:
    """생애주기 최적화 (ISO 15686-1) LCC_opt = min[sum(C_t/(1+d)^t)]"""

    COMPONENT_LIFESPAN = {
        "지붕방수": 20, "외벽도장": 10, "창호교체": 25,
        "배관설비": 30, "전기설비": 25, "냉난방설비": 15,
        "엘리베이터": 20, "주차설비": 25, "소방설비": 20, "통신설비": 15
    }

    def optimize_replacement_schedule(self, total_construction_cost_krw: float,
                                       building_lifespan_years: int = 50,
                                       discount_rate: float = 0.03) -> dict:
        schedule = {}
        total_pv = 0.0
        for component, lifespan in self.COMPONENT_LIFESPAN.items():
            cost = total_construction_cost_krw * 0.02
            years = list(range(lifespan, building_lifespan_years, lifespan))
            pv_costs = []
            for y in years:
                pv = cost / ((1 + discount_rate) ** y)
                pv_costs.append({"year": y, "pv_cost_krw": int(pv)})
                total_pv += pv
            schedule[component] = {
                "lifespan_years": lifespan, "replacement_years": years,
                "replacement_cost_krw": int(cost), "pv_replacement_costs": pv_costs
            }
        return {
            "building_lifespan_years": building_lifespan_years,
            "total_pv_replacement_krw": int(total_pv),
            "replacement_schedule": schedule, "standard": "ISO 15686-1"
        }
