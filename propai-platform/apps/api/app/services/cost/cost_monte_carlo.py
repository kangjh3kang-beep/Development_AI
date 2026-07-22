"""공사비 몬테카를로 시뮬레이션 — 삼각분포 리스크 모델.

5개 리스크 요인 (재료비/노무비/경비/설계변경/공기지연)에 대해
삼각분포 난수를 적용하여 총공사비 분포를 추정한다.

W3-3(P9) MC 상관 1차: 기본은 5개 요인 전부 **독립표본**(기존 동작, 무회귀)이다.
opt-in 으로 재료비/노무비/경비(공종 간, 예: 자재비 동반 상승) 3개 요인 사이에
상관계수를 지정하면, Gaussian copula(표준정규 상관 → Cholesky 분해 → 각 변수의
삼각분포 역함수)로 상관된 표본을 만든다. 각 변수의 한계분포(marginal)는 여전히
RISK 테이블의 삼각분포 그대로다 — 상관은 변수 "사이의 동시성"만 바꾼다.
상관행렬이 양정치(positive definite)가 아니면 ValueError로 즉시 거부한다
(근거 없는 상관값 기본 주입 금지 — correlation 미전달 시 항상 독립·회귀 0).
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

# 상관 도입 대상(공종 간 상관 — 자재비 동반 상승 등 실무적으로 의미 있는 3축).
# design_chg/schedule 은 성격이 달라(설계변경 발생여부·공정 지연) 1차 범위에서 제외한다.
_CORR_KEYS: tuple[str, ...] = ("material", "labor", "expense")


def _triangular_ppf(u: float, lo: float, mode: float, hi: float) -> float:
    """삼각분포(lo, mode, hi)의 역누적분포함수(분위수함수). u∈[0,1]."""
    if hi <= lo:  # 퇴화분포 가드(hi==lo) — 상수 반환
        return lo
    fc = (mode - lo) / (hi - lo)
    if u < fc:
        return lo + math.sqrt(max(0.0, u * (hi - lo) * (mode - lo)))
    return hi - math.sqrt(max(0.0, (1.0 - u) * (hi - lo) * (hi - mode)))


def _std_normal_cdf(z: float) -> float:
    """표준정규 누적분포함수 Φ(z) — math.erf 기반(외부 의존 없음)."""
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def _build_cholesky(correlation: dict[str, dict[str, float]]) -> list[list[float]]:
    """상관계수 dict(_CORR_KEYS 대상) → Cholesky 하삼각행렬 L(양정치 검증 포함).

    correlation: {"material": {"labor": 0.3, "expense": 0.2}, ...}(대칭 자동 보완,
    누락 쌍은 상관 0). 대각은 항상 1(자기상관). 범위 밖 값·양정치 실패는 ValueError.
    """
    n = len(_CORR_KEYS)
    m = [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]
    for i, ki in enumerate(_CORR_KEYS):
        for j, kj in enumerate(_CORR_KEYS):
            if i == j:
                continue
            v = None
            if ki in correlation and kj in correlation[ki]:
                v = correlation[ki][kj]
            elif kj in correlation and ki in correlation[kj]:
                v = correlation[kj][ki]
            if v is None:
                continue
            if not (-1.0 <= v <= 1.0):
                raise ValueError(f"상관계수는 -1~1 범위여야 합니다: {ki}-{kj}={v}")
            m[i][j] = v

    unknown = set(correlation) - set(_CORR_KEYS)
    if unknown:
        raise ValueError(
            f"상관 대상 키가 아닙니다({sorted(unknown)}) — 허용: {list(_CORR_KEYS)}"
        )

    L = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1):
            s = sum(L[i][k] * L[j][k] for k in range(j))
            if i == j:
                val = m[i][i] - s
                if val < 1e-12:
                    raise ValueError(
                        "상관행렬이 양정치(positive definite)가 아닙니다 — Cholesky 분해 실패"
                    )
                L[i][j] = math.sqrt(val)
            else:
                L[i][j] = (m[i][j] - s) / L[j][j]
    return L


class CostMonteCarlo:
    """공사비 몬테카를로 시뮬레이션."""

    def __init__(
        self,
        base: dict[str, Any],
        iters: int = 10000,
        seed: int = 42,
        correlation: dict[str, dict[str, float]] | None = None,
    ):
        """
        Args:
            base: OriginCostCalculator.calculate() 결과
            iters: 시뮬레이션 반복 횟수
            seed: 난수 시드
            correlation: opt-in 공종간 상관계수(material/labor/expense 3축, 예:
                {"material": {"labor": 0.3}}) — 기본 None=완전 독립(기존 동작, 무회귀).
                양정치 아닌 행렬·허용 밖 키는 __init__ 시점에 ValueError.
        """
        self.base = base
        self.iters = iters
        self.seed = seed
        self.correlation = correlation
        self._chol: list[list[float]] | None = (
            _build_cholesky(correlation) if correlation else None
        )

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
            # 삼각분포 샘플링 — correlation 미지정(기본) 시 기존 독립표본 경로 그대로(회귀 0).
            if self._chol is None:
                factors: dict[str, float] = {}
                for key, (lo, mode, hi) in RISK.items():
                    factors[key] = rng.triangular(lo, hi, mode)
            else:
                factors = self._sample_correlated(rng)

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
            # W3-3(P9) MC 상관 1차 — additive(기존 키 무변경). correlation 미지정 시
            # applied=False(완전 독립, 이전과 100% 동일 산출 — 회귀 0).
            "correlation_applied": self._chol is not None,
            "correlation": self.correlation,
        }

    def _sample_correlated(self, rng: random.Random) -> dict[str, float]:
        """공종간 상관(1차: material/labor/expense) 적용 삼각분포 표본.

        Gaussian copula: 표준정규 3변량을 Cholesky(L)로 상관시킨 뒤 Φ(정규CDF)로
        [0,1] 분위수로 변환, 각 변수의 삼각분포 역함수(_triangular_ppf)에 대입한다.
        각 변수의 한계분포는 여전히 RISK 테이블의 삼각분포와 동일(상관만 추가).
        design_chg/schedule 은 이번 1차 범위 밖이라 기존과 동일하게 독립 표본이다.
        호출부(run())가 self._chol is not None 일 때만 이 메서드를 호출한다.
        """
        chol = self._chol or []
        z = [rng.gauss(0.0, 1.0) for _ in _CORR_KEYS]
        corr_z = [sum(chol[i][j] * z[j] for j in range(i + 1)) for i in range(len(_CORR_KEYS))]
        factors: dict[str, float] = {}
        for idx, key in enumerate(_CORR_KEYS):
            u = _std_normal_cdf(corr_z[idx])
            lo, mode, hi = RISK[key]
            factors[key] = _triangular_ppf(u, lo, mode, hi)
        for key in RISK:
            if key in _CORR_KEYS:
                continue
            lo, mode, hi = RISK[key]
            factors[key] = rng.triangular(lo, hi, mode)
        return factors

    @staticmethod
    def _empty_result() -> dict[str, Any]:
        return {
            "base_total": 0,
            "mean": 0, "std": 0, "cv": 0,
            "p10": 0, "p50": 0, "p80": 0, "p90": 0,
            "min": 0, "max": 0,
            "iterations": 0, "converged": False,
            "risk_contributions": {},
            "correlation_applied": False,
            "correlation": None,
        }
