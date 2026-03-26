"""CoVe O9: 에이전트 7단계 완주율 벤치마크.

기준: ≥ 95% (100회 반복)
실행: pytest tests/benchmarks/bench_agent.py -v
"""

import pytest

pytestmark = pytest.mark.benchmark

COMPLETION_THRESHOLD = 0.95
ITERATIONS = 100


class TestAgentCompletion:
    """에이전트 오케스트레이션 완주율 검증."""

    @pytest.mark.skip(reason="전체 서비스 스택 + DB 필요 — CI에서 실행")
    def test_completion_rate(self) -> None:
        """100회 실행 중 95% 이상 7단계 완주."""
        # TODO: PropAIOrchestrator.run()을 100회 실행
        # 각 실행에서 7개 AgentStepEvent(status=completed) 확인
        # 완주 횟수 / 100 >= 0.95
        pass

    @pytest.mark.skip(reason="전체 서비스 스택 + DB 필요 — CI에서 실행")
    def test_average_completion_time(self) -> None:
        """평균 완주 시간 측정 (P95 기준)."""
        pass
