"""법령 임베딩 워커 테스트."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_embed_regulations_success(worker_ctx):
    """정상 임베딩 처리 — OpenAI + Qdrant."""
    row1 = MagicMock()
    row1.id = "reg-001"
    row1.title = "건축법 제1조"
    row1.content = "건축법의 목적은..."

    row2 = MagicMock()
    row2.id = "reg-002"
    row2.title = "도시계획법 제2조"
    row2.content = "도시계획의 정의..."

    mock_result = MagicMock()
    mock_result.fetchall = MagicMock(return_value=[row1, row2])
    worker_ctx["db"].execute = AsyncMock(return_value=mock_result)

    mock_embed_item1 = MagicMock()
    mock_embed_item1.embedding = [0.1] * 1536
    mock_embed_item2 = MagicMock()
    mock_embed_item2.embedding = [0.2] * 1536

    mock_embed_response = MagicMock()
    mock_embed_response.data = [mock_embed_item1, mock_embed_item2]

    mock_openai = AsyncMock()
    mock_openai.embeddings.create = AsyncMock(return_value=mock_embed_response)

    mock_qdrant = AsyncMock()
    mock_qdrant.upsert = AsyncMock()
    mock_qdrant.close = AsyncMock()

    with (
        patch("openai.AsyncOpenAI", return_value=mock_openai),
        patch("qdrant_client.AsyncQdrantClient", return_value=mock_qdrant),
    ):
        from apps.worker.tasks.embed_regulations import run_embed_regulations

        result = await run_embed_regulations(ctx=worker_ctx, batch_size=100)

    assert result["status"] == "completed"
    assert result["processed"] == 2
    mock_qdrant.upsert.assert_called_once()
    worker_ctx["db"].commit.assert_called()


@pytest.mark.asyncio
async def test_embed_regulations_no_pending(worker_ctx):
    """미처리 법령 없음 — 즉시 완료."""
    mock_result = MagicMock()
    mock_result.fetchall = MagicMock(return_value=[])
    worker_ctx["db"].execute = AsyncMock(return_value=mock_result)

    from apps.worker.tasks.embed_regulations import run_embed_regulations

    result = await run_embed_regulations(ctx=worker_ctx)

    assert result["status"] == "completed"
    assert result["processed"] == 0
