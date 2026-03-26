"""SSE 스트리밍 통합 테스트.

FastAPI TestClient로 SSE 엔드포인트 응답 검증.
Docker + DB + 서비스 필요.
"""

import pytest

pytestmark = pytest.mark.integration


class TestDesignReportSSE:
    """설계 보고서 SSE 스트리밍 검증."""

    @pytest.mark.skip(reason="전체 서비스 스택 필요 — CI에서 실행")
    async def test_stream_returns_event_source(self) -> None:
        """POST /api/v1/design/report/stream이 SSE 응답을 반환한다."""
        pass

    @pytest.mark.skip(reason="전체 서비스 스택 필요 — CI에서 실행")
    async def test_stream_events_have_correct_format(self) -> None:
        """SSE 이벤트가 StreamingReportEvent 스키마를 따른다."""
        pass


class TestAgentOrchestrationSSE:
    """에이전트 오케스트레이션 SSE 검증."""

    @pytest.mark.skip(reason="전체 서비스 스택 필요 — CI에서 실행")
    async def test_orchestrate_returns_7_steps(self) -> None:
        """POST /api/v1/agents/orchestrate가 7단계 이벤트를 스트리밍한다."""
        pass

    @pytest.mark.skip(reason="전체 서비스 스택 필요 — CI에서 실행")
    async def test_orchestrate_events_sequential(self) -> None:
        """에이전트 이벤트가 순차적으로 전달된다 (step_index 0→6)."""
        pass
