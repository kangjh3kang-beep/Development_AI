"""웹훅 발송 워커 테스트."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_dispatch_webhook_event_success(mock_db_session):
    """정상 웹훅 발송."""
    delivery1 = MagicMock(success=True)
    delivery2 = MagicMock(success=True)
    delivery3 = MagicMock(success=False)

    mock_service = AsyncMock()
    mock_service.dispatch_event = AsyncMock(return_value=[delivery1, delivery2, delivery3])

    with (
        patch("apps.api.database.session.AsyncSessionLocal", return_value=mock_db_session),
        patch("apps.api.services.webhook_service.WebhookService", return_value=mock_service),
    ):
        from apps.worker.tasks.webhook_dispatch import dispatch_webhook_event

        result = await dispatch_webhook_event(
            ctx={},
            event_type="project.created",
            payload={"project_id": "test-123"},
            tenant_id="00000000-0000-0000-0000-000000000001",
        )

    assert result["event_type"] == "project.created"
    assert result["deliveries_count"] == 3
    assert result["successful"] == 2


@pytest.mark.asyncio
async def test_dispatch_webhook_event_no_subscribers(mock_db_session):
    """구독자 없음 — 빈 배송 목록."""
    mock_service = AsyncMock()
    mock_service.dispatch_event = AsyncMock(return_value=[])

    with (
        patch("apps.api.database.session.AsyncSessionLocal", return_value=mock_db_session),
        patch("apps.api.services.webhook_service.WebhookService", return_value=mock_service),
    ):
        from apps.worker.tasks.webhook_dispatch import dispatch_webhook_event

        result = await dispatch_webhook_event(
            ctx={},
            event_type="project.deleted",
            payload={},
            tenant_id="00000000-0000-0000-0000-000000000001",
        )

    assert result["deliveries_count"] == 0
    assert result["successful"] == 0
