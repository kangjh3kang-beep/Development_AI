"""대용량 IFC 파싱 워커 테스트."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_parse_large_ifc_success(worker_ctx):
    """정상 IFC 파싱 — 요소 추출 + DB 저장."""
    mock_http_response = MagicMock()
    mock_http_response.content = b"ISO-10303-21;HEADER;FILE_DESCRIPTION..."
    mock_http_response.raise_for_status = MagicMock()

    mock_http_client = AsyncMock()
    mock_http_client.get = AsyncMock(return_value=mock_http_response)
    mock_http_client.__aenter__ = AsyncMock(return_value=mock_http_client)
    mock_http_client.__aexit__ = AsyncMock(return_value=False)

    # ifcopenshell mock
    mock_quantity_volume = MagicMock()
    mock_quantity_volume.is_a.return_value = "IfcQuantityVolume"
    mock_quantity_volume.VolumeValue = 12.5

    mock_prop_def = MagicMock()
    mock_prop_def.Quantities = [mock_quantity_volume]

    mock_rel = MagicMock()
    mock_rel.RelatingPropertyDefinition = mock_prop_def

    mock_wall = MagicMock()
    mock_wall.IsDefinedBy = [mock_rel]

    mock_ifc = MagicMock()
    mock_ifc.by_type = MagicMock(side_effect=lambda t: [mock_wall, mock_wall] if t == "IfcWall" else [])

    mock_ifc_module = MagicMock()
    mock_ifc_module.open = MagicMock(return_value=mock_ifc)

    with (
        patch("httpx.AsyncClient", return_value=mock_http_client),
        patch.dict("sys.modules", {"ifcopenshell": mock_ifc_module}),
        patch("os.unlink"),
    ):
        from apps.worker.tasks.parse_large_ifc import run_parse_large_ifc

        result = await run_parse_large_ifc(
            ctx=worker_ctx,
            file_url="http://minio.local/bim/test.ifc",
            project_id="00000000-0000-0000-0000-000000000003",
        )

    assert result["status"] == "completed"
    assert result["element_count"] == 2
    assert len(result["element_summary"]) == 1
    assert result["element_summary"][0]["type"] == "IfcWall"
    worker_ctx["db"].commit.assert_called_once()


@pytest.mark.asyncio
async def test_parse_large_ifc_empty_file(worker_ctx):
    """빈 IFC 파일 — 요소 0개."""
    mock_http_response = MagicMock()
    mock_http_response.content = b""
    mock_http_response.raise_for_status = MagicMock()

    mock_http_client = AsyncMock()
    mock_http_client.get = AsyncMock(return_value=mock_http_response)
    mock_http_client.__aenter__ = AsyncMock(return_value=mock_http_client)
    mock_http_client.__aexit__ = AsyncMock(return_value=False)

    mock_ifc = MagicMock()
    mock_ifc.by_type = MagicMock(return_value=[])

    mock_ifc_module = MagicMock()
    mock_ifc_module.open = MagicMock(return_value=mock_ifc)

    with (
        patch("httpx.AsyncClient", return_value=mock_http_client),
        patch.dict("sys.modules", {"ifcopenshell": mock_ifc_module}),
        patch("os.unlink"),
    ):
        from apps.worker.tasks.parse_large_ifc import run_parse_large_ifc

        result = await run_parse_large_ifc(
            ctx=worker_ctx,
            file_url="http://minio.local/bim/empty.ifc",
            project_id="00000000-0000-0000-0000-000000000003",
        )

    assert result["element_count"] == 0
    assert result["element_summary"] == []
