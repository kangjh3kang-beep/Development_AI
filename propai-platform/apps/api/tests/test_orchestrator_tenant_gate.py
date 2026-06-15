"""P1-2: 오케스트레이터 교차 테넌트 차단 게이트 단위 테스트(무DB, AsyncMock)."""
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest


def _orch_with_row(row):
    """db.execute(...).first() == row 를 반환하는 PropAIOrchestrator."""
    from apps.api.agents.propai_orchestrator import PropAIOrchestrator

    db = AsyncMock()
    res = MagicMock()
    res.first.return_value = row
    db.execute.return_value = res
    return PropAIOrchestrator(db)


async def test_verify_project_tenant_allows_owner():
    orch = _orch_with_row((1,))
    assert await orch._verify_project_tenant(uuid.uuid4(), uuid.uuid4()) is True


async def test_verify_project_tenant_blocks_cross_tenant():
    orch = _orch_with_row(None)   # 해당 테넌트 소유 행 없음
    assert await orch._verify_project_tenant(uuid.uuid4(), uuid.uuid4()) is False


async def test_run_emits_auth_error_and_stops_for_cross_tenant():
    """소유권 실패 시 run()은 첫 이벤트로 auth error를 내고 파이프라인을 돌지 않는다."""
    orch = _orch_with_row(None)
    events = [ev async for ev in orch.run(project_id=uuid.uuid4(), tenant_id=uuid.uuid4())]
    assert len(events) == 1
    assert events[0].status == "error"
    assert "권한" in (events[0].error_message or "")
