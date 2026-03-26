"""AVM 배치 워커 테스트."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_avm_batch_success(mock_db_session):
    """정상 배치 추정 — 전체 성공."""
    mock_valuation = MagicMock()
    mock_valuation.estimated_price = 500_000_000
    mock_valuation.confidence_score = 0.92

    mock_service = AsyncMock()
    mock_service.estimate = AsyncMock(return_value=mock_valuation)

    with (
        patch("apps.api.database.session.AsyncSessionLocal", return_value=mock_db_session),
        patch("apps.api.services.avm_service.AVMService", return_value=mock_service),
    ):
        from apps.worker.tasks.avm_batch import run_avm_batch

        result = await run_avm_batch(
            ctx={},
            tenant_id="00000000-0000-0000-0000-000000000001",
            parcel_ids=["00000000-0000-0000-0000-000000000010", "00000000-0000-0000-0000-000000000011"],
        )

    assert result["status"] == "completed"
    assert result["success"] == 2
    assert result["errors"] == 0
    assert result["total"] == 2
    assert mock_service.estimate.call_count == 2


@pytest.mark.asyncio
async def test_avm_batch_partial_failure(mock_db_session):
    """일부 필지 추정 실패 — 에러 수집."""
    mock_valuation = MagicMock()
    mock_valuation.estimated_price = 300_000_000
    mock_valuation.confidence_score = 0.85

    mock_service = AsyncMock()
    mock_service.estimate = AsyncMock(
        side_effect=[mock_valuation, Exception("필지 없음")]
    )

    with (
        patch("apps.api.database.session.AsyncSessionLocal", return_value=mock_db_session),
        patch("apps.api.services.avm_service.AVMService", return_value=mock_service),
    ):
        from apps.worker.tasks.avm_batch import run_avm_batch

        result = await run_avm_batch(
            ctx={},
            tenant_id="00000000-0000-0000-0000-000000000001",
            parcel_ids=["00000000-0000-0000-0000-000000000010", "00000000-0000-0000-0000-000000000011"],
        )

    assert result["status"] == "completed"
    assert result["success"] == 1
    assert result["errors"] == 1


@pytest.mark.asyncio
async def test_avm_batch_empty_list(mock_db_session):
    """빈 필지 목록 — 즉시 완료."""
    mock_service = AsyncMock()

    with (
        patch("apps.api.database.session.AsyncSessionLocal", return_value=mock_db_session),
        patch("apps.api.services.avm_service.AVMService", return_value=mock_service),
    ):
        from apps.worker.tasks.avm_batch import run_avm_batch

        result = await run_avm_batch(
            ctx={},
            tenant_id="00000000-0000-0000-0000-000000000001",
            parcel_ids=[],
        )

    assert result["status"] == "completed"
    assert result["total"] == 0
    assert mock_service.estimate.call_count == 0
