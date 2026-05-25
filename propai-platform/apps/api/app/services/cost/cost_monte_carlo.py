"""공사비 몬테카를로 시뮬레이션 — 삼각분포 리스크 모델.

5개 리스크 요인 (재료비/노무비/경비/설계변경/공기지연)에 대해
삼각분포 난수를 적용하여 총공사비 분포를 추정한다.
"""

from __future__ import annotations

import math
import random
from typing import Any

# 삼각분포 파라미터: (최솟값, 최빈값, 최댓값) — 비율 배수
RISK: dict[str, tuple[float, float, float]] = {
    "material": (0.90, 1.00, 1.25),   # 재료비 ±
    "labor": (0.92, 1.00, 1.20),      # 노무비 ±
    "expense": (0.95, 1.00, 1.15),    # 경비 ±
    "design_chg": (0.00, 0.05, 0.15), # 설계변경 추가 비율
    "schedule": (1.00, 1.00, 1.30),   # 공기 지연 비율
}


class CostMonteCarlo:
    """공사비 몬테카를로 시뮬레이션."""

    def __init__(
        self,
        base: dict[str, Any],
        iters: int = 10000,
        seed: int = 42,
    ):
        """
        Args:
            base: OriginCostCalculator.calculate() 결과
            iters: 시뮬레이션 반복 횟수
            seed: 난수 시드
        """
        self.base = base
        self.iters = iters
        self.seed = seed

    def run(self) -> dict[str, Any]:
        """시뮬레이션을 실행한다.

        Returns:
            P10/P50/P80/P90 백분위, 평균, 표준편차, CV, 리스크 기여도
        """
        rng = random.Random(self.seed)

        base_mat = self.base.get("direct_material_cost", 0)
        base_labor = self.base.get("total_labor_cost", 0)
        base_exp = self.base.get("direct_expense_cost", 0)
        base_total = self.base.get("total_project_cost", 0)

        if base_total == 0:
            return self._empty_result()

        results: list[float] = []
        risk_sums: dict[str, float] = {k: 0.0 for k in RISK}

        for _ in range(self.iters):
            # 삼각분포 샘플링
            factors: dict[str, float] = {}
            for key, (lo, mode, hi) in RISK.items():
                factors[key] = rng.triangular(lo, hi, mode)

            mat = base_mat * factors["material"]
            labor = base_labor * factors["labor"]
            exp = base_exp * factors["expense"]
            design_chg_cost = (mat + labor + exp) * factors["design_chg"]
            schedule_factor = factors["schedule"]

            simulated = (mat + labor + exp + design_chg_cost) * schedule_factor
            results.append(simulated)

            # 리스크 기여도 (편차 분해)
            for key in RISK:
                risk_sums[key] += abs(factors[key] - RISK[key][1])

        results.sort()

        # 통계량
        mean = sum(results) / len(results)
        variance = sum((x - mean) ** 2 for x in results) / len(results)
        std = math.sqrt(variance)
        cv = std / mean if mean > 0 else 0

        # 백분위
        def percentile(pct: float) -> float:
            idx = int(len(results) * pct / 100.0)
            idx = min(idx, len(results) - 1)
            return round(results[idx])

        p10 = percentile(10)
        p50 = percentile(50)
        p80 = percentile(80)
        p90 = percentile(90)

        # 리스크 기여도 정규화
        total_risk = sum(risk_sums.values())
        risk_contributions = {}
        if total_risk > 0:
            for key in RISK:
                risk_contributions[key] = round(risk_sums[key] / total_risk * 100, 1)

        # 수렴 검증 (CV < 5%)
        converged = cv < 0.05

        return {
            "base_total": round(base_total),
            "mean": round(mean),
            "std": round(std),
            "cv": round(cv, 4),
            "p10": p10,
            "p50": p50,
            "p80": p80,
            "p90": p90,
            "min": round(results[0]),
            "max": round(results[-1]),
            "iterations": self.iters,
            "converged": converged,
            "risk_contributions": risk_contributions,
        }

    @staticmethod
    def _empty_result() -> dict[str, Any]:
        return {
            "base_total": 0,
            "mean": 0, "std": 0, "cv": 0,
            "p10": 0, "p50": 0, "p80": 0, "p90": 0,
            "min": 0, "max": 0,
            "iterations": 0, "converged": False,
            "risk_contributions": {},
        }
