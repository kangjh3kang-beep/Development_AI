"""ETL 예약 태스크 테스트."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_etl_public_data_success(mock_db_session):
    """공공 데이터 수집 정상 완료."""
    mock_molit = AsyncMock()
    mock_molit.get_transactions = AsyncMock(return_value=[{"id": 1}, {"id": 2}])
    mock_molit.close = AsyncMock()

    mock_vworld = AsyncMock()
    mock_vworld.get_land_info = AsyncMock(return_value={"pnu": "1168010100"})
    mock_vworld.close = AsyncMock()

    # DB에서 PNU 목록 반환
    mock_row = MagicMock()
    mock_row.pnu = "1168010100"
    mock_result = MagicMock()
    mock_result.fetchall = MagicMock(return_value=[mock_row])
    mock_db_session.execute = AsyncMock(return_value=mock_result)

    with (
        patch("apps.api.integrations.molit_client.MolitClient", return_value=mock_molit),
        patch("apps.api.integrations.vworld_client.VWorldClient", return_value=mock_vworld),
        patch("apps.api.database.session.AsyncSessionLocal", return_value=mock_db_session),
        patch("apps.api.config.get_settings"),
    ):
        from apps.worker.tasks.etl_scheduled import run_etl_public_data

        result = await run_etl_public_data(ctx={})

    assert result["status"] == "completed"
    assert "molit_trades" in result
    assert "vworld_parcels" in result


@pytest.mark.asyncio
async def test_etl_public_data_api_failure(mock_db_session):
    """API 장애 시 graceful 실패."""
    mock_molit = AsyncMock()
    mock_molit.get_transactions = AsyncMock(side_effect=Exception("API 장애"))
    mock_molit.close = AsyncMock()

    with (
        patch("apps.api.integrations.molit_client.MolitClient", return_value=mock_molit),
        patch("apps.api.config.get_settings"),
    ):
        from apps.worker.tasks.etl_scheduled import run_etl_public_data

        result = await run_etl_public_data(ctx={})

    assert result["status"] == "completed"
    assert result["molit_trades"] == 0


@pytest.mark.asyncio
async def test_cleanup_expired(mock_db_session):
    """만료 데이터 정리."""
    mock_result = MagicMock()
    mock_result.rowcount = 5
    mock_db_session.execute = AsyncMock(return_value=mock_result)

    with patch("apps.api.database.session.AsyncSessionLocal", return_value=mock_db_session):
        from apps.worker.tasks.etl_scheduled import run_cleanup_expired

        result = await run_cleanup_expired(ctx={})

    assert result["status"] == "completed"
    assert "deleted" in result
    assert result["deleted"]["refresh_tokens"] == 5
