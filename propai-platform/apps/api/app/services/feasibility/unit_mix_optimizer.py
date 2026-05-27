"""
유닛믹스 최적화 엔진.
총 연면적, 용도지역, 지역 시세를 기반으로 수익을 극대화하는 최적 평형 배분을 자동 계산.
ArkDesign AI 벤치마크 -- SLSQP 기반 최적화.
"""
import logging
from typing import Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Korean standard unit types (평형)
STANDARD_UNIT_TYPES = [
    {"code": "S39", "name": "39m2 (12평)", "area_sqm": 39, "area_pyeong": 12, "parking_per_unit": 0.5},
    {"code": "S49", "name": "49m2 (15평)", "area_sqm": 49, "area_pyeong": 15, "parking_per_unit": 0.7},
    {"code": "S59", "name": "59m2 (18평)", "area_sqm": 59, "area_pyeong": 18, "parking_per_unit": 1.0},
    {"code": "S74", "name": "74m2 (22평)", "area_sqm": 74, "area_pyeong": 22, "parking_per_unit": 1.0},
    {"code": "S84", "name": "84m2 (25평)", "area_sqm": 84, "area_pyeong": 25, "parking_per_unit": 1.0},
    {"code": "S102", "name": "102m2 (31평)", "area_sqm": 102, "area_pyeong": 31, "parking_per_unit": 1.2},
    {"code": "S135", "name": "135m2 (41평)", "area_sqm": 135, "area_pyeong": 41, "parking_per_unit": 1.5},
]

# Regional price premiums per unit type (만원/평)
DEFAULT_PRICE_BY_TYPE = {
    "S39": 2800, "S49": 3000, "S59": 3200, "S74": 3400,
    "S84": 3500, "S102": 3800, "S135": 4200,
}

# Market demand distribution (default)
DEFAULT_DEMAND_RATIO = {
    "S39": 0.05, "S49": 0.10, "S59": 0.25, "S74": 0.15,
    "S84": 0.30, "S102": 0.10, "S135": 0.05,
}


@dataclass
class UnitMixInput:
    total_gfa_sqm: float              # 총 연면적
    max_far_pct: float = 250          # 용적률 상한
    max_bcr_pct: float = 60           # 건폐율 상한
    land_area_sqm: float = 1000       # 대지면적
    max_floors: int = 25              # 최대 층수
    min_parking_ratio: float = 1.0    # 세대당 최소 주차대수
    max_parking_spaces: int = 500     # 최대 주차대수
    region: str = "서울"               # 지역 (시세 결정)
    price_by_type: Optional[dict] = None   # 평형별 분양가 (만원/평, 오버라이드)
    demand_ratio: Optional[dict] = None     # 평형별 수요 비율 (오버라이드)
    enabled_types: Optional[list] = None    # 허용 평형 (None=전체)


class UnitMixOptimizer:
    """수익률을 극대화하는 최적 평형 배분을 계산."""

    def optimize(self, inp: UnitMixInput) -> dict:
        prices = inp.price_by_type or DEFAULT_PRICE_BY_TYPE
        demand = inp.demand_ratio or DEFAULT_DEMAND_RATIO
        types = [
            t
            for t in STANDARD_UNIT_TYPES
            if inp.enabled_types is None or t["code"] in inp.enabled_types
        ]

        if not types:
            return {"error": "허용된 평형 타입이 없습니다.", "units": []}

        try:
            import numpy as np
            from scipy.optimize import minimize

            return self._optimize_slsqp(inp, types, prices, demand, np, minimize)
        except ImportError:
            return self._optimize_greedy(inp, types, prices, demand)

    def _optimize_slsqp(self, inp, types, prices, demand, np, minimize):
        n = len(types)
        # Decision variable: number of units per type (continuous, then rounded)
        max_units_total = int(
            inp.total_gfa_sqm / min(t["area_sqm"] for t in types)
        )

        # Objective: maximize total revenue = sum(units_i * area_pyeong_i * price_per_pyeong_i)
        def neg_revenue(x):
            return -sum(
                x[i] * types[i]["area_pyeong"] * prices.get(types[i]["code"], 3000) * 10000
                for i in range(n)
            )

        # Constraints
        constraints = [
            # Total GFA <= max
            {
                "type": "ineq",
                "fun": lambda x: inp.total_gfa_sqm
                - sum(x[i] * types[i]["area_sqm"] for i in range(n)),
            },
            # Total GFA >= 90% of max (efficiency)
            {
                "type": "ineq",
                "fun": lambda x: sum(x[i] * types[i]["area_sqm"] for i in range(n))
                - inp.total_gfa_sqm * 0.90,
            },
            # Parking constraint
            {
                "type": "ineq",
                "fun": lambda x: inp.max_parking_spaces
                - sum(x[i] * types[i]["parking_per_unit"] for i in range(n)),
            },
        ]

        # Demand ratio constraint (each type within +/-50% of demand target)
        for i in range(n):
            target = demand.get(types[i]["code"], 0.1)
            if target > 0:
                constraints.append(
                    {
                        "type": "ineq",
                        "fun": lambda x, idx=i, tgt=target: x[idx]
                        / max(sum(x), 1)
                        - tgt * 0.5,
                    }
                )

        # Bounds: 0 to max feasible units per type
        bounds = [(0, max_units_total) for _ in range(n)]

        # Initial guess: proportional to demand
        x0 = np.array(
            [demand.get(t["code"], 0.1) * max_units_total for t in types]
        )

        result = minimize(
            neg_revenue,
            x0,
            method="SLSQP",
            bounds=bounds,
            constraints=constraints,
            options={"maxiter": 500, "ftol": 1e-8},
        )

        # Round to integers
        units = [max(0, round(result.x[i])) for i in range(n)]

        return self._build_result(inp, types, units, prices, "SLSQP")

    def _optimize_greedy(self, inp, types, prices, demand):
        """scipy 미설치 시 그리디 폴백."""
        # Sort by revenue per sqm descending
        scored = [
            (t, prices.get(t["code"], 3000) * 10000 / t["area_sqm"]) for t in types
        ]
        scored.sort(key=lambda x: -x[1])

        remaining_gfa = inp.total_gfa_sqm
        units = {t["code"]: 0 for t in types}

        for t, _ in scored:
            target_ratio = demand.get(t["code"], 0.1)
            target_units = max(
                1, int(inp.total_gfa_sqm / t["area_sqm"] * target_ratio)
            )
            actual = min(target_units, int(remaining_gfa / t["area_sqm"]))
            units[t["code"]] = actual
            remaining_gfa -= actual * t["area_sqm"]

        unit_list = [units.get(t["code"], 0) for t in types]
        return self._build_result(inp, types, unit_list, prices, "Greedy")

    def _build_result(self, inp, types, units, prices, method):
        total_units = sum(units)
        total_gfa_used = sum(
            units[i] * types[i]["area_sqm"] for i in range(len(types))
        )
        total_revenue = sum(
            units[i] * types[i]["area_pyeong"] * prices.get(types[i]["code"], 3000) * 10000
            for i in range(len(types))
        )
        total_parking = sum(
            units[i] * types[i]["parking_per_unit"] for i in range(len(types))
        )

        unit_details = []
        for i, t in enumerate(types):
            if units[i] > 0:
                revenue = (
                    units[i]
                    * t["area_pyeong"]
                    * prices.get(t["code"], 3000)
                    * 10000
                )
                unit_details.append(
                    {
                        "code": t["code"],
                        "name": t["name"],
                        "area_sqm": t["area_sqm"],
                        "area_pyeong": t["area_pyeong"],
                        "count": units[i],
                        "ratio_pct": round(
                            units[i] / max(total_units, 1) * 100, 1
                        ),
                        "price_per_pyeong_10k": prices.get(t["code"], 3000),
                        "total_revenue_won": revenue,
                        "parking_required": round(units[i] * t["parking_per_unit"]),
                    }
                )

        return {
            "method": method,
            "total_units": total_units,
            "total_gfa_used_sqm": round(total_gfa_used, 1),
            "gfa_efficiency_pct": round(
                total_gfa_used / inp.total_gfa_sqm * 100, 1
            )
            if inp.total_gfa_sqm > 0
            else 0,
            "total_revenue_won": total_revenue,
            "total_revenue_100m": round(total_revenue / 100_000_000),
            "total_parking_required": round(total_parking),
            "units": unit_details,
        }
