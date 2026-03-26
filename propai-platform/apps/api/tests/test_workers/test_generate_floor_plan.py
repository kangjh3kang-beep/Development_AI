"""평면도 생성 워커 테스트."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_generate_floor_plan_success(worker_ctx):
    """정상 평면도 생성 — Replicate + MinIO."""
    mock_http_response = MagicMock()
    mock_http_response.content = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
    mock_http_response.raise_for_status = MagicMock()

    mock_http_client = AsyncMock()
    mock_http_client.get = AsyncMock(return_value=mock_http_response)
    mock_http_client.__aenter__ = AsyncMock(return_value=mock_http_client)
    mock_http_client.__aexit__ = AsyncMock(return_value=False)

    mock_minio = AsyncMock()
    mock_minio.bucket_exists = AsyncMock(return_value=True)
    mock_minio.put_object = AsyncMock()

    mock_replicate_module = MagicMock()
    mock_replicate_module.async_run = AsyncMock(
        return_value=["https://replicate.example.com/output.png"]
    )

    with (
        patch.dict("sys.modules", {"replicate": mock_replicate_module}),
        patch("httpx.AsyncClient", return_value=mock_http_client),
        patch("miniopy_async.Minio", return_value=mock_minio),
    ):
        from apps.worker.tasks.generate_floor_plan import run_generate_floor_plan

        result = await run_generate_floor_plan(
            ctx=worker_ctx,
            project_id="00000000-0000-0000-0000-000000000003",
            prompt="3LDK 아파트 평면도",
            rooms=3,
        )

    assert result["status"] == "completed"
    assert "image_url" in result
    mock_minio.put_object.assert_called_once()
    worker_ctx["db"].commit.assert_called_once()


@pytest.mark.asyncio
async def test_generate_floor_plan_empty_response(worker_ctx):
    """Replicate 빈 응답 — 실패 반환."""
    mock_replicate_module = MagicMock()
    mock_replicate_module.async_run = AsyncMock(return_value=[])

    with patch.dict("sys.modules", {"replicate": mock_replicate_module}):
        from apps.worker.tasks.generate_floor_plan import run_generate_floor_plan

        result = await run_generate_floor_plan(
            ctx=worker_ctx,
            project_id="00000000-0000-0000-0000-000000000003",
            prompt="평면도",
        )

    assert result["status"] == "failed"
    assert "error" in result
