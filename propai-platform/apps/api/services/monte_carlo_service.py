"""Monte Carlo 시뮬레이션 서비스.

numpy 기반 10,000회 확률적 시뮬레이션으로
NPV/IRR 분포, VaR, Expected Shortfall을 산출한다.

흐름:
1. 기본 파라미터(매출, 비용, 할인율, 공실률)에 정규분포 변동 적용
2. 시뮬레이션별 NPV/IRR 계산
3. 백분위수(P10/P50/P90) 및 리스크 지표 산출
4. DB 저장 후 결과 반환
"""

import asyncio
from math import isfinite
from typing import Any
from uuid import UUID

import numpy as np
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.config import get_settings
from apps.api.database.models.monte_carlo_result import MonteCarloResult

logger = structlog.get_logger(__name__)


class MonteCarloService:
    """Monte Carlo 시뮬레이션 엔진.

    10,000회 확률적 시뮬레이션을 통해 부동산 개발 사업의
    NPV/IRR 분포를 산출하고 리스크 지표를 계산한다.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.settings = get_settings()

    @staticmethod
    def _calc_irr(cashflows: list[float]) -> float:
        """이분탐색 기반 IRR 계산.

        FeasibilityService._calc_irr 로직을 인라인으로 재사용한다.
        벡터화하지 않고 루프 기반으로 계산한다.

        Args:
            cashflows: 초기 투자(-) 포함 연도별 현금흐름 리스트

        Returns:
            IRR 값 (소수)
        """
        lo, hi = -0.5, 1.0
        for _ in range(120):
            mid = (lo + hi) / 2
            npv = 0.0
            valid = True
            for index, cashflow in enumerate(cashflows):
                denominator = (1 + mid) ** index
                if denominator == 0:
                    valid = False
                    break
                npv += cashflow / denominator
            if not valid or not isfinite(npv):
                hi = mid
                continue
            if npv > 0:
                lo = mid
            else:
                hi = mid
        return round((lo + hi) / 2, 6)

    @staticmethod
    def _run_simulation(
        *,
        base_revenue: float,
        base_cost: float,
        base_rate: float,
        base_vacancy: float,
        total_investment: float,
        analysis_years: int,
        exit_value_ratio: float = 1.18,
        sigma_revenue: float = 0.12,
        sigma_cost: float = 0.08,
        sigma_rate: float = 0.015,
        sigma_vacancy: float = 0.05,
        n: int = 10_000,
        seed: int | None = None,
    ) -> list[tuple[float, float]]:
        """numpy 기반 Monte Carlo 시뮬레이션 실행.

        각 시뮬레이션마다:
        - revenue = base_revenue * (1 + N(0, sigma_revenue))
        - cost = base_cost * (1 + N(0, sigma_cost))
        - rate = base_rate + N(0, sigma_rate)
        - vacancy = base_vacancy + N(0, sigma_vacancy)
        - NPV = -investment + sum(cashflow_t / (1+rate)^t) + exit_value / (1+rate)^T
        - IRR은 이분탐색으로 계산

        Args:
            base_revenue: 기본 연간 매출 (원)
            base_cost: 기본 연간 비용 (원)
            base_rate: 기본 할인율
            base_vacancy: 기본 공실률
            total_investment: 총 투자비 (원)
            analysis_years: 분석 기간 (년)
            exit_value_ratio: 출구 가치 배율
            sigma_revenue: 매출 변동성 (표준편차)
            sigma_cost: 비용 변동성 (표준편차)
            sigma_rate: 할인율 변동성 (표준편차)
            sigma_vacancy: 공실률 변동성 (표준편차)
            n: 시뮬레이션 횟수
            seed: 난수 시드 (재현성 보장용)

        Returns:
            (npv, irr) 튜플 리스트

        Raises:
            ValueError: 투자비가 0 이하이거나 분석 기간이 0 이하인 경우
        """
        if total_investment <= 0:
            raise ValueError("총 투자비(total_investment)는 0보다 커야 합니다.")
        if analysis_years <= 0:
            raise ValueError("분석 기간(analysis_years)은 0보다 커야 합니다.")

        rng = np.random.default_rng(seed)
        results: list[tuple[float, float]] = []

        for _ in range(n):
            # 확률 변수 생성
            revenue = base_revenue * (1 + rng.normal(0, sigma_revenue))
            cost = base_cost * (1 + rng.normal(0, sigma_cost))
            rate = base_rate + rng.normal(0, sigma_rate)
            vacancy = base_vacancy + rng.normal(0, sigma_vacancy)

            # 할인율/공실률 하한 클램프
            rate = max(rate, 0.001)
            vacancy = max(0.0, min(vacancy, 1.0))

            # 순 운영 수익 (공실 반영)
            net_income = revenue * (1 - vacancy) - cost
            exit_value = total_investment * exit_value_ratio

            # NPV 계산
            npv = -total_investment
            for t in range(1, analysis_years + 1):
                npv += net_income / ((1 + rate) ** t)
            npv += exit_value / ((1 + rate) ** analysis_years)

            # IRR 계산 (이분탐색)
            cashflows = [-total_investment] + [net_income] * analysis_years
            cashflows[-1] += exit_value  # 마지막 해에 출구 가치 합산
            irr = MonteCarloService._calc_irr(cashflows)

            results.append((npv, irr))

        return results

    @staticmethod
    def _calc_percentiles(
        npv_array: np.ndarray, irr_array: np.ndarray
    ) -> dict[str, float]:
        """P10, P50, P90 백분위수를 산출한다.

        Args:
            npv_array: NPV numpy 배열
            irr_array: IRR numpy 배열

        Returns:
            p10/p50/p90 NPV 및 IRR 값 딕셔너리
        """
        return {
            "p10_npv": float(np.percentile(npv_array, 10)),
            "p50_npv": float(np.percentile(npv_array, 50)),
            "p90_npv": float(np.percentile(npv_array, 90)),
            "p10_irr": float(np.percentile(irr_array, 10)),
            "p50_irr": float(np.percentile(irr_array, 50)),
            "p90_irr": float(np.percentile(irr_array, 90)),
        }

    @staticmethod
    def _calc_var_95(npv_array: np.ndarray) -> float:
        """95% VaR(Value at Risk)를 산출한다.

        하위 5번째 백분위수의 절대값을 반환한다.
        양수 NPV 분포에서도 음수 쪽 꼬리를 포착하기 위해 절대값 사용.

        Args:
            npv_array: NPV numpy 배열

        Returns:
            VaR 절대값 (손실 기준)
        """
        percentile_5 = float(np.percentile(npv_array, 5))
        return abs(percentile_5)

    @staticmethod
    def _calc_expected_shortfall(
        npv_array: np.ndarray, confidence: float = 0.95
    ) -> float:
        """Expected Shortfall(조건부 VaR)을 산출한다.

        VaR 이하 NPV의 평균 절대값을 반환한다.

        Args:
            npv_array: NPV numpy 배열
            confidence: 신뢰수준 (기본 0.95)

        Returns:
            Expected Shortfall 절대값
        """
        alpha = 1 - confidence  # 0.05
        threshold = float(np.percentile(npv_array, alpha * 100))
        tail = npv_array[npv_array <= threshold]
        if len(tail) == 0:
            return abs(threshold)
        return abs(float(np.mean(tail)))

    async def simulate(
        self,
        project_id: UUID,
        tenant_id: UUID,
        *,
        base_revenue: float,
        base_cost: float,
        base_rate: float,
        base_vacancy: float,
        total_investment: float,
        analysis_years: int,
        exit_value_ratio: float = 1.18,
        n_simulations: int = 10_000,
        scenario_name: str = "기본 시나리오",
        seed: int | None = None,
    ) -> MonteCarloResult:
        """Monte Carlo 시뮬레이션을 실행하고 결과를 DB에 저장한다.

        asyncio.to_thread를 사용하여 CPU 집약적 시뮬레이션을
        별도 스레드에서 실행한다.

        Args:
            project_id: 프로젝트 ID
            tenant_id: 테넌트 ID
            base_revenue: 기본 연간 매출 (원)
            base_cost: 기본 연간 비용 (원)
            base_rate: 기본 할인율
            base_vacancy: 기본 공실률
            total_investment: 총 투자비 (원)
            analysis_years: 분석 기간 (년)
            exit_value_ratio: 출구 가치 배율
            n_simulations: 시뮬레이션 횟수
            scenario_name: 시나리오명
            seed: 난수 시드

        Returns:
            저장된 MonteCarloResult 모델 인스턴스
        """
        logger.info(
            "Monte Carlo 시뮬레이션 시작",
            project_id=str(project_id),
            n_simulations=n_simulations,
            scenario_name=scenario_name,
        )

        # CPU 집약적 시뮬레이션을 별도 스레드에서 실행
        raw_results = await asyncio.to_thread(
            self._run_simulation,
            base_revenue=base_revenue,
            base_cost=base_cost,
            base_rate=base_rate,
            base_vacancy=base_vacancy,
            total_investment=total_investment,
            analysis_years=analysis_years,
            exit_value_ratio=exit_value_ratio,
            n=n_simulations,
            seed=seed,
        )

        # numpy 배열 변환
        npv_array = np.array([r[0] for r in raw_results])
        irr_array = np.array([r[1] for r in raw_results])

        # 통계 산출
        percentiles = self._calc_percentiles(npv_array, irr_array)
        var_95 = self._calc_var_95(npv_array)
        es = self._calc_expected_shortfall(npv_array)
        mean_npv = float(np.mean(npv_array))
        std_npv = float(np.std(npv_array))

        # 결과 요약 JSON
        results_summary: dict[str, Any] = {
            "npv_min": float(np.min(npv_array)),
            "npv_max": float(np.max(npv_array)),
            "npv_skewness": float(
                np.mean(((npv_array - mean_npv) / std_npv) ** 3)
            ) if std_npv > 0 else 0.0,
            "irr_mean": float(np.mean(irr_array)),
            "irr_std": float(np.std(irr_array)),
            "positive_npv_ratio": float(np.sum(npv_array > 0) / len(npv_array)),
        }

        # 입력 파라미터 JSON
        input_params: dict[str, Any] = {
            "base_revenue": base_revenue,
            "base_cost": base_cost,
            "base_rate": base_rate,
            "base_vacancy": base_vacancy,
            "total_investment": total_investment,
            "analysis_years": analysis_years,
            "exit_value_ratio": exit_value_ratio,
            "n_simulations": n_simulations,
            "seed": seed,
        }

        # DB 저장
        result = MonteCarloResult(
            tenant_id=tenant_id,
            project_id=project_id,
            n_simulations=n_simulations,
            scenario_name=scenario_name,
            p10_npv=percentiles["p10_npv"],
            p50_npv=percentiles["p50_npv"],
            p90_npv=percentiles["p90_npv"],
            p10_irr=percentiles["p10_irr"],
            p50_irr=percentiles["p50_irr"],
            p90_irr=percentiles["p90_irr"],
            var_95=var_95,
            expected_shortfall=es,
            mean_npv=mean_npv,
            std_npv=std_npv,
            results_summary_json=results_summary,
            input_params_json=input_params,
        )
        self.db.add(result)
        await self.db.commit()
        await self.db.refresh(result)

        logger.info(
            "Monte Carlo 시뮬레이션 완료",
            project_id=str(project_id),
            mean_npv=mean_npv,
            var_95=var_95,
        )

        return result
