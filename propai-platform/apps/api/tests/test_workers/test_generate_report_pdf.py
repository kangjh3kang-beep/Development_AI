"""PDF 보고서 생성 워커 테스트."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_generate_report_pdf_success(worker_ctx):
    """정상 PDF 생성 + MinIO 업로드."""
    proj_row = MagicMock()
    proj_row.name = "테스트 프로젝트"
    proj_row.status = "planning"

    avm_row = MagicMock()
    avm_row.estimated_price = 500_000_000
    avm_row.price_per_sqm = 5_000_000
    avm_row.confidence_score = 0.92
    avm_row.comparable_count = 10
    avm_row.model_version = "v1.0"

    call_count = 0

    async def mock_execute(query, params=None):
        nonlocal call_count
        call_count += 1
        result = MagicMock()
        if call_count == 1:
            result.fetchone = MagicMock(return_value=proj_row)
        elif call_count == 2:
            result.fetchone = MagicMock(return_value=avm_row)
        else:
            result.fetchone = MagicMock(return_value=None)
        return result

    worker_ctx["db"].execute = mock_execute

    mock_minio = AsyncMock()
    mock_minio.bucket_exists = AsyncMock(return_value=True)
    mock_minio.put_object = AsyncMock()

    with (
        patch("miniopy_async.Minio", return_value=mock_minio),
        patch("reportlab.pdfbase.pdfmetrics.registerFont"),
        patch("reportlab.pdfbase.ttfonts.TTFont", side_effect=Exception("폰트 없음")),
    ):
        from apps.worker.tasks.generate_report_pdf import run_generate_report_pdf

        result = await run_generate_report_pdf(
            ctx=worker_ctx,
            project_id="00000000-0000-0000-0000-000000000003",
            tenant_id="00000000-0000-0000-0000-000000000001",
        )

    assert result["status"] == "completed"
    assert "pdf_url" in result
    mock_minio.put_object.assert_called_once()


@pytest.mark.asyncio
async def test_generate_report_pdf_empty_project(worker_ctx):
    """데이터 없는 프로젝트 — 빈 보고서 생성."""
    async def mock_execute(query, params=None):
        result = MagicMock()
        result.fetchone = MagicMock(return_value=None)
        return result

    worker_ctx["db"].execute = mock_execute

    mock_minio = AsyncMock()
    mock_minio.bucket_exists = AsyncMock(return_value=False)
    mock_minio.make_bucket = AsyncMock()
    mock_minio.put_object = AsyncMock()

    with (
        patch("miniopy_async.Minio", return_value=mock_minio),
        patch("reportlab.pdfbase.pdfmetrics.registerFont"),
        patch("reportlab.pdfbase.ttfonts.TTFont", side_effect=Exception("폰트 없음")),
    ):
        from apps.worker.tasks.generate_report_pdf import run_generate_report_pdf

        result = await run_generate_report_pdf(
            ctx=worker_ctx,
            project_id="00000000-0000-0000-0000-000000000099",
            tenant_id="00000000-0000-0000-0000-000000000001",
        )

    assert result["status"] == "completed"
    mock_minio.make_bucket.assert_called_once()
