"""몬테카를로 시뮬레이션 엔진 — 5변수 10K회 (수렴 σ/μ < 0.01).

numpy 벡터화 연산으로 고속 처리.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass
class MCVariable:
    """몬테카를로 확률변수."""
    name: str
    mean: float
    std: float
    distribution: str = "normal"  # normal / uniform / triangular


def run_monte_carlo(
    *,
    calculate_fn: Callable[[dict[str, float]], float],
    variables: list[MCVariable],
    n_simulations: int = 10_000,
    seed: int | None = 42,
) -> dict[str, Any]:
    """몬테카를로 시뮬레이션 실행.

    Args:
        calculate_fn: 변수 dict → NPV(원) 반환 함수
        variables: 확률변수 리스트
        n_simulations: 시뮬레이션 횟수
        seed: 랜덤 시드

    Returns:
        {'mean', 'std', 'p5', 'p50', 'p95', 'probability_positive',
         'convergence_ratio', 'histogram', 'n_simulations'}
    """
    try:
        import numpy as np

        rng = np.random.default_rng(seed)
        samples: dict[str, Any] = {}

        for var in variables:
            if var.distribution == "uniform":
                lo = var.mean - var.std * 1.732  # sqrt(3)
                hi = var.mean + var.std * 1.732
                samples[var.name] = rng.uniform(lo, hi, n_simulations)
            elif var.distribution == "triangular":
                lo = var.mean - var.std * 2
                hi = var.mean + var.std * 2
                samples[var.name] = rng.triangular(lo, var.mean, hi, n_simulations)
            else:  # normal
                samples[var.name] = rng.normal(var.mean, var.std, n_simulations)

        results = np.zeros(n_simulations)
        for i in range(n_simulations):
            var_dict = {name: float(samples[name][i]) for name in samples}
            results[i] = calculate_fn(var_dict)

        mean_val = float(np.mean(results))
        std_val = float(np.std(results))
        # convergence_ratio(σ/|μ|)는 변동계수(CV) — 결과 분포의 고유 리스크 지표 (하위호환 유지)
        convergence = abs(std_val / mean_val) if mean_val != 0 else float("inf")
        # 실제 수렴 판정은 평균의 표준오차 비율: σ/(√N·|μ|) — N이 커지면 줄어드는 값
        se_ratio = (
            std_val / (abs(mean_val) * (n_simulations ** 0.5))
            if mean_val != 0 else float("inf")
        )

        # 히스토그램 데이터 (20 빈)
        hist_counts, hist_edges = np.histogram(results, bins=20)
        histogram = [
            {"bin_start": float(hist_edges[i]), "bin_end": float(hist_edges[i + 1]),
             "count": int(hist_counts[i])}
            for i in range(len(hist_counts))
        ]

        return {
            "mean": mean_val,
            "std": std_val,
            "p5": float(np.percentile(results, 5)),
            "p50": float(np.percentile(results, 50)),
            "p95": float(np.percentile(results, 95)),
            "probability_positive": float(np.mean(results > 0)),
            "convergence_ratio": round(convergence, 6),  # CV(σ/|μ|) — 리스크 지표
            "standard_error_ratio": round(se_ratio, 8),  # σ/(√N·|μ|) — 수렴 지표
            "converged": se_ratio < 0.01,
            "histogram": histogram,
            "n_simulations": n_simulations,
        }

    except ImportError:
        # numpy 미설치 시 간이 시뮬레이션
        return _fallback_monte_carlo(calculate_fn, variables, n_simulations, seed)


def _fallback_monte_carlo(
    calculate_fn: Callable[[dict[str, float]], float],
    variables: list[MCVariable],
    n_simulations: int,
    seed: int | None,
) -> dict[str, Any]:
    """numpy 없이 간이 시뮬레이션."""
    import random
    if seed is not None:
        random.seed(seed)

    results = []
    for _ in range(min(n_simulations, 1000)):  # 폴백은 1K로 제한
        var_dict = {}
        for var in variables:
            if var.distribution == "uniform":
                lo = var.mean - var.std * 1.732  # sqrt(3)
                hi = var.mean + var.std * 1.732
                var_dict[var.name] = random.uniform(lo, hi)
            elif var.distribution == "triangular":
                lo = var.mean - var.std * 2
                hi = var.mean + var.std * 2
                var_dict[var.name] = random.triangular(lo, hi, var.mean)
            else:  # normal
                var_dict[var.name] = random.gauss(var.mean, var.std)
        results.append(calculate_fn(var_dict))

    n = len(results)
    mean_val = sum(results) / n
    variance = sum((x - mean_val) ** 2 for x in results) / n
    std_val = variance ** 0.5

    sorted_r = sorted(results)
    convergence = abs(std_val / mean_val) if mean_val != 0 else float("inf")
    se_ratio = std_val / (abs(mean_val) * (n ** 0.5)) if mean_val != 0 else float("inf")

    return {
        "mean": mean_val,
        "std": std_val,
        "p5": sorted_r[int(n * 0.05)],
        "p50": sorted_r[n // 2],
        "p95": sorted_r[int(n * 0.95)],
        "probability_positive": sum(1 for x in results if x > 0) / n,
        "convergence_ratio": round(convergence, 6),
        "standard_error_ratio": round(se_ratio, 8),
        "converged": se_ratio < 0.01,
        "histogram": [],
        "n_simulations": n,
    }
