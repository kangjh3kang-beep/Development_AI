"""민감도 분석 엔진 — 5 시나리오 프리셋 + 토네이도 차트 데이터."""

from __future__ import annotations

from typing import Any, Callable
from dataclasses import dataclass


@dataclass
class SensitivityScenario:
    """민감도 시나리오."""
    name: str
    variable: str
    deltas_pct: list[float]  # [-20, -10, 0, 10, 20]


# 5 시나리오 프리셋
DEFAULT_SCENARIOS: list[SensitivityScenario] = [
    SensitivityScenario("분양가 변동", "sale_price", [-20, -10, 0, 10, 20]),
    SensitivityScenario("공사비 변동", "construction_cost", [-20, -10, 0, 10, 20]),
    SensitivityScenario("토지비 변동", "land_cost", [-20, -10, 0, 10, 20]),
    SensitivityScenario("금리 변동", "interest_rate", [-2, -1, 0, 1, 2]),  # pp
    SensitivityScenario("공기 변동", "project_months", [-12, -6, 0, 6, 12]),  # 월
]


def run_sensitivity_analysis(
    *,
    base_values: dict[str, float],
    calculate_fn: Callable[[dict[str, float]], dict[str, Any]],
    scenarios: list[SensitivityScenario] | None = None,
) -> dict[str, Any]:
    """민감도 분석 실행.

    Args:
        base_values: 기본값 딕셔너리
        calculate_fn: 값 dict → {'profit_rate_pct', 'npv_won', ...}
        scenarios: 시나리오 리스트 (None이면 기본 5개)

    Returns:
        {'base_result', 'scenarios': [{name, variable, results: [{delta, profit, npv}]}],
         'tornado': [{variable, low_profit, high_profit, spread}]}
    """
    if scenarios is None:
        scenarios = DEFAULT_SCENARIOS

    base_result = calculate_fn(base_values)

    scenario_results = []
    for scenario in scenarios:
        results = []
        for delta in scenario.deltas_pct:
            test_values = base_values.copy()
            current = test_values.get(scenario.variable, 0)

            if scenario.variable == "interest_rate":
                # 금리는 절대값 변동 (pp)
                test_values[scenario.variable] = current + delta / 100
            elif scenario.variable == "project_months":
                # 공기는 절대값 변동 (월)
                test_values[scenario.variable] = max(1, current + delta)
            else:
                # 비율 변동
                test_values[scenario.variable] = current * (1 + delta / 100)

            result = calculate_fn(test_values)
            results.append({
                "delta_pct": delta,
                "profit_rate_pct": result.get("profit_rate_pct", 0),
                "npv_won": result.get("npv_won", 0),
            })

        scenario_results.append({
            "name": scenario.name,
            "variable": scenario.variable,
            "results": results,
        })

    # 토네이도 차트 데이터
    tornado = []
    for sr in scenario_results:
        profits = [r["profit_rate_pct"] for r in sr["results"]]
        if profits:
            tornado.append({
                "variable": sr["variable"],
                "name": sr["name"],
                "low_profit": min(profits),
                "high_profit": max(profits),
                "spread": max(profits) - min(profits),
            })

    tornado.sort(key=lambda t: t["spread"], reverse=True)

    return {
        "base_result": base_result,
        "scenarios": scenario_results,
        "tornado": tornado,
    }
