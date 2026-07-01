"""AI 최적화 엔진 — SLSQP + Pareto + Greedy 폴백.

scipy.optimize.minimize 기반 수익률 최대화.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass
class OptimizationConstraint:
    """최적화 제약조건."""
    name: str
    min_value: float | None = None
    max_value: float | None = None


def optimize_slsqp(
    *,
    objective_fn: Callable[[dict[str, float]], float],
    variables: dict[str, tuple[float, float, float]],  # name → (initial, min, max)
    constraints: list[OptimizationConstraint] | None = None,
    maximize: bool = True,
    max_iter: int = 200,
) -> dict[str, Any]:
    """SLSQP 최적화.

    Args:
        objective_fn: 변수 dict → 목적함수 값 (최대화 시 양수가 좋음)
        variables: 변수명 → (초기값, 하한, 상한)
        maximize: True면 최대화, False면 최소화

    Returns:
        {'optimal_vars', 'optimal_value', 'iterations', 'success', 'method'}
    """
    try:
        import numpy as np
        from scipy.optimize import minimize as scipy_minimize

        var_names = list(variables.keys())
        x0 = np.array([variables[v][0] for v in var_names])
        bounds = [(variables[v][1], variables[v][2]) for v in var_names]

        sign = -1.0 if maximize else 1.0

        def _objective(x: Any) -> float:
            var_dict = {name: float(x[i]) for i, name in enumerate(var_names)}
            return sign * objective_fn(var_dict)

        result = scipy_minimize(
            _objective, x0, method="SLSQP", bounds=bounds,
            options={"maxiter": max_iter, "disp": False},
        )

        optimal_vars = {name: float(result.x[i]) for i, name in enumerate(var_names)}

        return {
            "optimal_vars": optimal_vars,
            "optimal_value": float(-sign * result.fun),
            "iterations": int(result.nit),
            "success": bool(result.success),
            "method": "SLSQP",
        }
    except ImportError:
        # scipy 미설치 시 Greedy 폴백
        return _greedy_optimize(objective_fn, variables)


def _greedy_optimize(
    objective_fn: Callable[[dict[str, float]], float],
    variables: dict[str, tuple[float, float, float]],
    steps: int = 20,
) -> dict[str, Any]:
    """Greedy 폴백 — scipy 없을 때."""
    best_vars = {v: variables[v][0] for v in variables}
    best_value = objective_fn(best_vars)

    for _ in range(steps):
        improved = False
        for var_name, (_, lo, hi) in variables.items():
            step_size = (hi - lo) / steps
            for direction in [step_size, -step_size]:
                test_vars = best_vars.copy()
                test_vars[var_name] = max(lo, min(hi, test_vars[var_name] + direction))
                test_value = objective_fn(test_vars)
                if test_value > best_value:
                    best_value = test_value
                    best_vars = test_vars
                    improved = True
        if not improved:
            break

    return {
        "optimal_vars": best_vars,
        "optimal_value": best_value,
        "iterations": steps,
        "success": True,
        "method": "Greedy",
    }


def generate_pareto_points(
    *,
    objective_fns: list[Callable[[dict[str, float]], float]],
    variables: dict[str, tuple[float, float, float]],
    n_points: int = 6,
) -> list[dict[str, Any]]:
    """Pareto 최적점 생성 (가중합 방식).

    Args:
        objective_fns: [수익률_fn, ROI_fn] 등 2개 목적함수
        n_points: 생성할 점 수

    Returns:
        [{'vars', 'values', 'weight'}, ...]
    """
    if len(objective_fns) < 2:
        return []

    points = []
    for i in range(n_points):
        w1 = i / max(n_points - 1, 1)
        w2 = 1.0 - w1

        def weighted_obj(v: dict[str, float], _w1: float = w1, _w2: float = w2) -> float:
            return _w1 * objective_fns[0](v) + _w2 * objective_fns[1](v)

        result = optimize_slsqp(
            objective_fn=weighted_obj,
            variables=variables,
            maximize=True,
        )
        points.append({
            "vars": result["optimal_vars"],
            "values": [fn(result["optimal_vars"]) for fn in objective_fns],
            "weight": [w1, w2],
            "method": result["method"],
        })

    return points
