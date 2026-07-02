"""MonteCarloService 단위 테스트.

시뮬레이션 결과 분포, 백분위수 순서, VaR/ES 관계,
결정론적 일치, 시드 재현성 등 핵심 로직을 검증한다.
"""

import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from apps.api.services.monte_carlo_service import MonteCarloService

# ── 공통 테스트 파라미터 ──

_BASE_PARAMS = {
    "base_revenue": 500_000_000,    # 5억 원/년
    "base_cost": 300_000_000,       # 3억 원/년
    "base_rate": 0.08,
    "base_vacancy": 0.05,
    "total_investment": 2_000_000_000,  # 20억 원
    "analysis_years": 10,
    "exit_value_ratio": 1.18,
}

_GOOD_PARAMS = {
    "base_revenue": 800_000_000,    # 8억 원/년 (좋은 사업)
    "base_cost": 200_000_000,       # 2억 원/년
    "base_rate": 0.06,
    "base_vacancy": 0.03,
    "total_investment": 2_000_000_000,
    "analysis_years": 10,
    "exit_value_ratio": 1.18,
}


class TestSimulationResults:
    """시뮬레이션 결과 기본 검증."""

    def test_시뮬레이션_결과_길이(self):
        """n=100 시뮬레이션 → 100개 결과."""
        results = MonteCarloService._run_simulation(
            **_BASE_PARAMS, n=100, seed=42
        )
        assert len(results) == 100

    def test_n_1_단일_시뮬레이션(self):
        """n=1 → 1개 결과. 결과는 (npv, irr) 튜플."""
        results = MonteCarloService._run_simulation(
            **_BASE_PARAMS, n=1, seed=42
        )
        assert len(results) == 1
        npv, irr = results[0]
        assert isinstance(npv, float)
        assert isinstance(irr, float)

    def test_대규모_시뮬레이션_10000(self):
        """n=10,000 시뮬레이션이 에러 없이 완료된다."""
        results = MonteCarloService._run_simulation(
            **_BASE_PARAMS, n=10_000, seed=42
        )
        assert len(results) == 10_000
        # NPV와 IRR 모두 유한한 값인지 확인
        for npv, irr in results:
            assert np.isfinite(npv), f"NPV가 유한하지 않음: {npv}"
            assert np.isfinite(irr), f"IRR이 유한하지 않음: {irr}"


class TestPercentiles:
    """백분위수 순서 검증."""

    def test_p10_p50_p90_순서(self):
        """P10 < P50 < P90 관계가 성립해야 한다."""
        results = MonteCarloService._run_simulation(
            **_BASE_PARAMS, n=1_000, seed=42
        )
        npv_array = np.array([r[0] for r in results])
        irr_array = np.array([r[1] for r in results])
        pct = MonteCarloService._calc_percentiles(npv_array, irr_array)
        assert pct["p10_npv"] < pct["p50_npv"] < pct["p90_npv"]

    def test_irr_p10_p50_p90_순서(self):
        """IRR도 P10 < P50 < P90 관계가 성립해야 한다."""
        results = MonteCarloService._run_simulation(
            **_BASE_PARAMS, n=1_000, seed=42
        )
        npv_array = np.array([r[0] for r in results])
        irr_array = np.array([r[1] for r in results])
        pct = MonteCarloService._calc_percentiles(npv_array, irr_array)
        assert pct["p10_irr"] < pct["p50_irr"] < pct["p90_irr"]


class TestDeterministic:
    """결정론적 시나리오 (sigma=0) 검증."""

    def test_sigma_0_결정론적_일치(self):
        """모든 sigma=0이면 모든 시뮬레이션의 NPV가 동일해야 한다."""
        results = MonteCarloService._run_simulation(
            **_BASE_PARAMS,
            sigma_revenue=0.0,
            sigma_cost=0.0,
            sigma_rate=0.0,
            sigma_vacancy=0.0,
            n=100,
            seed=42,
        )
        npvs = [r[0] for r in results]
        # 모든 NPV가 첫 번째 값과 동일
        assert all(
            abs(npv - npvs[0]) < 1e-6 for npv in npvs
        ), f"NPV 분산 발생: min={min(npvs)}, max={max(npvs)}"

    def test_p50_결정론적_npv_근사(self):
        """P50(중앙값)이 결정론적 NPV와 +/-15% 이내여야 한다."""
        # 결정론적 NPV 계산 (sigma=0)
        det_results = MonteCarloService._run_simulation(
            **_BASE_PARAMS,
            sigma_revenue=0.0,
            sigma_cost=0.0,
            sigma_rate=0.0,
            sigma_vacancy=0.0,
            n=1,
            seed=42,
        )
        det_npv = det_results[0][0]

        # 확률적 시뮬레이션
        stoch_results = MonteCarloService._run_simulation(
            **_BASE_PARAMS, n=5_000, seed=42
        )
        npv_array = np.array([r[0] for r in stoch_results])
        p50 = float(np.percentile(npv_array, 50))

        # P50이 결정론적 NPV의 +/-15% 이내
        tolerance = abs(det_npv) * 0.15
        assert abs(p50 - det_npv) <= tolerance, (
            f"P50={p50:,.0f}, det_NPV={det_npv:,.0f}, "
            f"차이={abs(p50 - det_npv):,.0f}, 허용={tolerance:,.0f}"
        )


class TestRiskMetrics:
    """VaR 및 Expected Shortfall 검증."""

    def test_var_95_하위_5퍼센트(self):
        """VaR 95%가 하위 5번째 백분위수의 절대값이어야 한다."""
        results = MonteCarloService._run_simulation(
            **_BASE_PARAMS, n=1_000, seed=42
        )
        npv_array = np.array([r[0] for r in results])
        var_95 = MonteCarloService._calc_var_95(npv_array)
        p5 = float(np.percentile(npv_array, 5))
        assert var_95 == pytest.approx(abs(p5), rel=1e-6)

    def test_expected_shortfall_var_이하(self):
        """Expected Shortfall(절대값)이 VaR(절대값) 이상이어야 한다.

        ES는 VaR 이하의 평균 손실이므로, 음수 NPV 영역에서
        |ES| >= |VaR| 관계가 성립한다.
        """
        results = MonteCarloService._run_simulation(
            **_BASE_PARAMS, n=5_000, seed=42
        )
        npv_array = np.array([r[0] for r in results])
        var_95 = MonteCarloService._calc_var_95(npv_array)
        es = MonteCarloService._calc_expected_shortfall(npv_array)
        # ES(절대값) >= VaR(절대값) — 꼬리 평균이 꼬리 문턱값보다 크거나 같아야 함
        assert es >= var_95 or abs(es - var_95) < 1e-6, (
            f"ES={es:,.0f} < VaR={var_95:,.0f}"
        )


class TestStatistics:
    """통계적 특성 검증."""

    def test_평균_NPV_양수(self):
        """좋은 사업 조건에서 평균 NPV가 양수여야 한다."""
        results = MonteCarloService._run_simulation(
            **_GOOD_PARAMS, n=1_000, seed=42
        )
        npv_array = np.array([r[0] for r in results])
        mean_npv = float(np.mean(npv_array))
        assert mean_npv > 0, f"좋은 사업인데 mean NPV={mean_npv:,.0f} < 0"

    def test_표준편차_sigma_비례(self):
        """sigma가 클수록 NPV 표준편차가 커야 한다."""
        # 낮은 변동성
        results_low = MonteCarloService._run_simulation(
            **_BASE_PARAMS,
            sigma_revenue=0.05,
            sigma_cost=0.03,
            n=2_000,
            seed=42,
        )
        std_low = float(np.std([r[0] for r in results_low]))

        # 높은 변동성
        results_high = MonteCarloService._run_simulation(
            **_BASE_PARAMS,
            sigma_revenue=0.25,
            sigma_cost=0.20,
            n=2_000,
            seed=42,
        )
        std_high = float(np.std([r[0] for r in results_high]))

        assert std_high > std_low, (
            f"높은 sigma std={std_high:,.0f} <= 낮은 sigma std={std_low:,.0f}"
        )


class TestSeedReproducibility:
    """시드 재현성 검증."""

    def test_시뮬레이션_시드_재현성(self):
        """같은 seed를 사용하면 동일한 결과가 나와야 한다."""
        results_a = MonteCarloService._run_simulation(
            **_BASE_PARAMS, n=100, seed=12345
        )
        results_b = MonteCarloService._run_simulation(
            **_BASE_PARAMS, n=100, seed=12345
        )
        for (npv_a, irr_a), (npv_b, irr_b) in zip(results_a, results_b, strict=False):
            assert npv_a == pytest.approx(npv_b, rel=1e-10)
            assert irr_a == pytest.approx(irr_b, rel=1e-10)


class TestInputValidation:
    """입력값 검증."""

    def test_투자비_0_오류(self):
        """총 투자비가 0이면 ValueError가 발생해야 한다."""
        with pytest.raises(ValueError, match="총 투자비"):
            MonteCarloService._run_simulation(
                base_revenue=100_000_000,
                base_cost=50_000_000,
                base_rate=0.08,
                base_vacancy=0.05,
                total_investment=0,
                analysis_years=10,
                n=10,
                seed=42,
            )

    def test_analysis_years_0_오류(self):
        """분석 기간이 0이면 ValueError가 발생해야 한다."""
        with pytest.raises(ValueError, match="분석 기간"):
            MonteCarloService._run_simulation(
                base_revenue=100_000_000,
                base_cost=50_000_000,
                base_rate=0.08,
                base_vacancy=0.05,
                total_investment=1_000_000_000,
                analysis_years=0,
                n=10,
                seed=42,
            )

    def test_음수_base_revenue(self):
        """음수 base_revenue도 에러 없이 처리되어야 한다.

        음수 매출은 비정상이지만 시뮬레이션 자체는 실행 가능.
        결과적으로 NPV가 매우 낮게 나올 것이다.
        """
        results = MonteCarloService._run_simulation(
            base_revenue=-100_000_000,
            base_cost=50_000_000,
            base_rate=0.08,
            base_vacancy=0.05,
            total_investment=1_000_000_000,
            analysis_years=10,
            sigma_revenue=0.0,
            sigma_cost=0.0,
            sigma_rate=0.0,
            sigma_vacancy=0.0,
            n=10,
            seed=42,
        )
        assert len(results) == 10
        # 음수 매출이면 NPV가 매우 낮아야 한다
        for npv, _ in results:
            assert npv < 0, f"음수 매출인데 NPV={npv:,.0f} >= 0"


class TestCalcIRR:
    """IRR 이분탐색 계산 검증."""

    def test_기본_irr_계산(self):
        """초기투자 -100, 매년 30씩 5년 → IRR 약 15%."""
        cashflows = [-100, 30, 30, 30, 30, 30]
        irr = MonteCarloService._calc_irr(cashflows)
        assert 0.10 < irr < 0.20

    def test_즉시_회수_높은_irr(self):
        """초기투자 -100, 1년 후 200 → IRR 약 100%."""
        cashflows = [-100, 200]
        irr = MonteCarloService._calc_irr(cashflows)
        assert irr == pytest.approx(1.0, abs=0.02)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
