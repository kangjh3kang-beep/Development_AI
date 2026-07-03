"""
유닛믹스 최적화 엔진.
총 연면적, 용도지역, 지역 시세를 기반으로 수익을 극대화하는 최적 평형 배분을 자동 계산.
ArkDesign AI 벤치마크 -- SLSQP 기반 최적화.
"""
import logging
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
    price_by_type: dict | None = None   # 평형별 분양가 (만원/평, 공급면적 기준)
    demand_ratio: dict | None = None     # 평형별 수요 비율 (오버라이드)
    enabled_types: list | None = None    # 허용 평형 (None=전체)
    efficiency_ratio: float = 0.75    # 전용률 (전용면적/공급면적, 아파트 통상 0.7~0.8)


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

    def _effective_gfa(self, inp) -> float:
        """법정 용적률 상한과 입력 연면적 중 작은 값 (용적률 제약 실적용)."""
        if inp.land_area_sqm > 0 and inp.max_far_pct > 0:
            legal_max = inp.land_area_sqm * inp.max_far_pct / 100
            return min(inp.total_gfa_sqm, legal_max)
        return inp.total_gfa_sqm

    def _optimize_slsqp(self, inp, types, prices, demand, np, minimize):
        n = len(types)
        eff = max(0.5, min(inp.efficiency_ratio, 1.0))
        effective_gfa = self._effective_gfa(inp)
        # 연면적 중 전용으로 쓸 수 있는 면적 — 공용면적(복도·계단·코어) 제외
        usable_exclusive_gfa = effective_gfa * eff

        # Decision variable: number of units per type (continuous, then rounded)
        max_units_total = int(
            usable_exclusive_gfa / min(t["area_sqm"] for t in types)
        )

        # 수익 = 세대수 × 공급평수(전용평수/전용률) × 분양가(만원/평, 공급면적 기준 시세)
        def neg_revenue(x):
            return -sum(
                x[i] * (types[i]["area_pyeong"] / eff) * prices.get(types[i]["code"], 3000) * 10000
                for i in range(n)
            )

        # Constraints
        constraints = [
            # 전용면적 합 <= 사용가능 전용 연면적
            {
                "type": "ineq",
                "fun": lambda x: usable_exclusive_gfa
                - sum(x[i] * types[i]["area_sqm"] for i in range(n)),
            },
            # 전용면적 합 >= 90% (효율)
            {
                "type": "ineq",
                "fun": lambda x: sum(x[i] * types[i]["area_sqm"] for i in range(n))
                - usable_exclusive_gfa * 0.90,
            },
            # 평형별 주차 원단위 합 <= 최대 주차대수
            {
                "type": "ineq",
                "fun": lambda x: inp.max_parking_spaces
                - sum(x[i] * types[i]["parking_per_unit"] for i in range(n)),
            },
            # 법정 최소 주차(세대당 min_parking_ratio)도 최대 주차대수 내 수용 가능해야 함
            {
                "type": "ineq",
                "fun": lambda x: inp.max_parking_spaces
                - sum(x) * inp.min_parking_ratio,
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
                # 상한: 수요 대비 +50% 초과 배분 금지 (주석 "±50%"와 일치)
                constraints.append(
                    {
                        "type": "ineq",
                        "fun": lambda x, idx=i, tgt=target: tgt * 1.5
                        - x[idx] / max(sum(x), 1),
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

        # 수렴 실패 시 무의미한 해 대신 그리디 폴백 (M-1 수정)
        if not result.success:
            logger.warning(
                "SLSQP 수렴 실패 (%s) — 그리디 폴백으로 전환", result.message
            )
            return self._optimize_greedy(inp, types, prices, demand)

        # Round to integers
        units = [max(0, round(result.x[i])) for i in range(n)]

        return self._build_result(inp, types, units, prices, "SLSQP")

    def _optimize_greedy(self, inp, types, prices, demand):
        """scipy 미설치/SLSQP 수렴 실패 시 그리디 폴백."""
        eff = max(0.5, min(inp.efficiency_ratio, 1.0))
        usable_exclusive_gfa = self._effective_gfa(inp) * eff

        # Sort by revenue per (전용)sqm descending — 공급환산은 동일 비율이라 순위 불변
        scored = [
            (t, prices.get(t["code"], 3000) * 10000 / t["area_sqm"]) for t in types
        ]
        scored.sort(key=lambda x: -x[1])

        remaining_gfa = usable_exclusive_gfa
        units = {t["code"]: 0 for t in types}

        for t, _ in scored:
            target_ratio = demand.get(t["code"], 0.1)
            target_units = max(
                1, int(usable_exclusive_gfa / t["area_sqm"] * target_ratio)
            )
            actual = min(target_units, int(remaining_gfa / t["area_sqm"]))
            units[t["code"]] = actual
            remaining_gfa -= actual * t["area_sqm"]

        unit_list = [units.get(t["code"], 0) for t in types]
        return self._build_result(inp, types, unit_list, prices, "Greedy")

    def _build_result(self, inp, types, units, prices, method):
        eff = max(0.5, min(inp.efficiency_ratio, 1.0))
        usable_exclusive_gfa = self._effective_gfa(inp) * eff

        total_units = sum(units)
        total_gfa_used = sum(
            units[i] * types[i]["area_sqm"] for i in range(len(types))
        )
        # 수익은 공급평수(전용/전용률) 기준 — 시장 분양가(만원/평)는 공급면적 기준 시세
        total_revenue = sum(
            units[i] * (types[i]["area_pyeong"] / eff) * prices.get(types[i]["code"], 3000) * 10000
            for i in range(len(types))
        )
        total_parking = sum(
            units[i] * types[i]["parking_per_unit"] for i in range(len(types))
        )

        unit_details = []
        for i, t in enumerate(types):
            if units[i] > 0:
                supply_pyeong = round(t["area_pyeong"] / eff, 1)
                revenue = (
                    units[i]
                    * (t["area_pyeong"] / eff)
                    * prices.get(t["code"], 3000)
                    * 10000
                )
                unit_details.append(
                    {
                        "code": t["code"],
                        "name": t["name"],
                        "area_sqm": t["area_sqm"],
                        "area_pyeong": t["area_pyeong"],
                        "supply_area_pyeong": supply_pyeong,
                        "count": units[i],
                        "ratio_pct": round(
                            units[i] / max(total_units, 1) * 100, 1
                        ),
                        "price_per_pyeong_10k": prices.get(t["code"], 3000),
                        "total_revenue_won": int(revenue),
                        "parking_required": round(units[i] * t["parking_per_unit"]),
                    }
                )

        return {
            "method": method,
            "total_units": total_units,
            "efficiency_ratio": eff,
            "total_gfa_used_sqm": round(total_gfa_used, 1),
            "gfa_efficiency_pct": round(
                total_gfa_used / usable_exclusive_gfa * 100, 1
            )
            if usable_exclusive_gfa > 0
            else 0,
            "total_revenue_won": int(total_revenue),
            "total_revenue_100m": round(total_revenue / 100_000_000),
            "total_parking_required": round(total_parking),
            "units": unit_details,
        }
