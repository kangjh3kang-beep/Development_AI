"""에이전트 오케스트레이터 재시도/타임아웃/복구 테스트 (Phase 10 강화).

_run_with_retry, save_state_to_db, load_state_from_json 테스트.
"""

import asyncio
import os
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from apps.api.agents.langgraph_orchestrator import (
    AgentState,
    LangGraphOrchestrator,
    NODE_STEPS,
)


class TestRunWithRetry:
    """_run_with_retry 메서드 테스트."""

    def _make_orchestrator(self) -> LangGraphOrchestrator:
        orch = object.__new__(LangGraphOrchestrator)
        orch.db = AsyncMock()
        orch.settings = MagicMock()
        return orch

    def _make_state(self) -> AgentState:
        return AgentState(
            project_id="test-project",
            tenant_id="test-tenant",
            results={},
            current_step=0,
            errors=[],
            should_continue=True,
        )

    @pytest.mark.asyncio
    async def test_success_on_first_try(self):
        """첫 시도에 성공."""
        orch = self._make_orchestrator()
        state = self._make_state()

        async def success_fn(s):
            s["results"]["test"] = {"status": "completed"}
            return s

        result = await orch._run_with_retry(success_fn, state, max_retries=2, timeout_sec=5)
        assert result["results"]["test"]["status"] == "completed"
        assert len(result["errors"]) == 0

    @pytest.mark.asyncio
    async def test_retry_after_failure(self):
        """실패 후 재시도 성공."""
        orch = self._make_orchestrator()
        state = self._make_state()
        call_count = 0

        async def flaky_fn(s):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise RuntimeError("일시 오류")
            s["results"]["test"] = {"status": "completed"}
            return s

        result = await orch._run_with_retry(flaky_fn, state, max_retries=2, timeout_sec=5)
        assert result["results"]["test"]["status"] == "completed"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_timeout_then_success(self):
        """타임아웃 발생 후 재시도 성공."""
        orch = self._make_orchestrator()
        state = self._make_state()
        call_count = 0

        async def slow_then_fast(s):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                await asyncio.sleep(10)  # 타임아웃 유발
            s["results"]["test"] = {"status": "completed"}
            return s

        result = await orch._run_with_retry(slow_then_fast, state, max_retries=2, timeout_sec=0.1)
        assert result["results"]["test"]["status"] == "completed"

    @pytest.mark.asyncio
    async def test_all_retries_exhausted(self):
        """모든 재시도 소진 시 에러 기록."""
        orch = self._make_orchestrator()
        state = self._make_state()

        async def always_fail(s):
            raise RuntimeError("영구 장애")

        result = await orch._run_with_retry(always_fail, state, max_retries=1, timeout_sec=5)
        assert len(result["errors"]) == 1
        assert "영구 장애" in result["errors"][0]
        assert "재시도 1회 소진" in result["errors"][0]

    @pytest.mark.asyncio
    async def test_timeout_all_exhausted(self):
        """모든 타임아웃 소진."""
        orch = self._make_orchestrator()
        state = self._make_state()

        async def always_slow(s):
            await asyncio.sleep(10)
            return s

        result = await orch._run_with_retry(always_slow, state, max_retries=0, timeout_sec=0.1)
        assert len(result["errors"]) == 1
        assert "타임아웃" in result["errors"][0]


# ── save_state_to_db 테스트 ──


class TestSaveStateToDb:
    """에이전트 상태 DB 저장 테스트."""

    @pytest.mark.asyncio
    async def test_save_state(self):
        """상태 저장 호출 시 에러 없음."""
        orch = object.__new__(LangGraphOrchestrator)
        orch.db = AsyncMock()
        orch.settings = MagicMock()

        state = AgentState(
            project_id="p1",
            tenant_id="t1",
            results={"avm": {"status": "completed"}},
            current_step=3,
            errors=[],
            should_continue=True,
        )
        # 단순히 에러 없이 실행되는지 확인
        await orch.save_state_to_db(state)


# ── load_state_from_json 테스트 ──


class TestLoadStateFromJson:
    """상태 복원 테스트."""

    def test_load_full_state(self):
        """전체 상태 복원."""
        state_json = {
            "results": {"avm": {"status": "completed"}},
            "current_step": 4,
            "errors": ["test error"],
            "should_continue": False,
        }
        state = LangGraphOrchestrator.load_state_from_json("p1", "t1", state_json)
        assert state["project_id"] == "p1"
        assert state["tenant_id"] == "t1"
        assert state["current_step"] == 4
        assert state["errors"] == ["test error"]
        assert state["should_continue"] is False

    def test_load_empty_state(self):
        """빈 JSON에서 기본값으로 복원."""
        state = LangGraphOrchestrator.load_state_from_json("p1", "t1", {})
        assert state["results"] == {}
        assert state["current_step"] == 0
        assert state["errors"] == []
        assert state["should_continue"] is True

    def test_load_partial_state(self):
        """부분 JSON 복원."""
        state_json = {"results": {"design": {"status": "completed"}}, "current_step": 2}
        state = LangGraphOrchestrator.load_state_from_json("p1", "t1", state_json)
        assert state["current_step"] == 2
        assert state["errors"] == []


# ── 폴백 파이프라인 테스트 ──


class TestFallbackPipeline:
    """폴백 모드 전체 파이프라인 테스트."""

    @pytest.mark.asyncio
    async def test_full_pipeline_execution(self):
        """전체 6단계 폴백 파이프라인 실행."""
        from uuid import uuid4

        orch = object.__new__(LangGraphOrchestrator)
        orch.db = AsyncMock()
        orch.settings = MagicMock()

        events = []
        async for event in orch.run(project_id=uuid4(), tenant_id=uuid4()):
            events.append(event)

        assert len(events) == len(NODE_STEPS)
        step_names = [e.step_name for e in events]
        assert "parcel_analysis" in step_names
        assert "report" in step_names
